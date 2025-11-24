use crate::docker::compose::DockerCompose;
use crate::docker::health::HealthChecker;
use crate::error::{Result, ZecDevError};
use colored::*;
use indicatif::{ProgressBar, ProgressStyle};
use reqwest::Client;
use serde_json::json;
use tokio::time::{sleep, Duration};

pub async fn execute(backend: String, fresh: bool) -> Result<()> {
    println!("{}", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━".cyan());
    println!("{}", "  ZecKit - Starting Devnet".cyan().bold());
    println!("{}", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━".cyan());
    println!();
    
    let compose = DockerCompose::new()?;
    
    // Fresh start if requested
    if fresh {
        println!("{}", "🧹 Cleaning up old data...".yellow());
        compose.down(true)?;
    }
    
    // Determine services to start
    let services = match backend.as_str() {
        "lwd" => vec!["zebra", "faucet", "lightwalletd", "zingo-wallet"],
        "zaino" => {
            println!("{}", "⚠️  Zaino backend is experimental".yellow());
            vec!["zebra", "faucet", "zaino"]
        },
        "none" => vec!["zebra", "faucet"],
        _ => {
            return Err(ZecDevError::Config(format!(
                "Invalid backend: {}. Use 'lwd', 'zaino', or 'none'", 
                backend
            )));
        }
    };
    
    println!("{} Starting services: {}", "🚀".green(), services.join(", "));
    
    // Start with appropriate profiles
    if backend == "lwd" {
        compose.up_with_profile("lwd")?;
    } else {
        compose.up(&services)?;
    }
    
    // Health checks with progress
    let pb = ProgressBar::new_spinner();
    pb.set_style(
        ProgressStyle::default_spinner()
            .template("{spinner:.green} {msg}")
            .unwrap()
    );
    
    pb.set_message("Waiting for Zebra...");
    let checker = HealthChecker::new();
    checker.wait_for_zebra(&pb).await?;
    
    // Wait for internal miner to produce blocks (M2 requirement: pre-mined funds)
    pb.set_message("⛏️  Waiting for internal miner to generate blocks...");
    wait_for_mined_blocks(&pb, 101).await?;
    
    pb.set_message("Waiting for Faucet...");
    checker.wait_for_faucet(&pb).await?;
    
    if backend == "lwd" || backend == "zaino" {
        pb.set_message(format!("Waiting for {}...", backend));
        checker.wait_for_backend(&backend, &pb).await?;
    }
    
    pb.finish_with_message("✓ All services ready!".green().to_string());
    
    // Generate UA fixtures (M2 requirement: ZIP-316 fixtures)
    println!();
    println!("{} Generating ZIP-316 Unified Address fixtures...", "📋".cyan());
    generate_ua_fixtures(&compose).await?;
    
    // Sync wallet with mined blocks
    if backend == "lwd" {
        println!("{} Syncing wallet with blockchain...", "🔄".cyan());
        sync_wallet().await?;
    }
    
    // Display connection info
    print_connection_info(&backend);
    print_mining_info().await?;
    
    Ok(())
}

async fn wait_for_mined_blocks(pb: &ProgressBar, min_blocks: u64) -> Result<()> {
    let client = Client::new();
    let max_wait = 1500; // 3 minutes max
    
    for i in 0..max_wait {
        pb.tick();
        
        match get_block_count(&client).await {
            Ok(height) if height >= min_blocks => {
                println!();
                println!("{} Mined {} blocks (coinbase maturity reached)", "✓".green(), height);
                return Ok(());
            }
            Ok(height) => {
                pb.set_message(format!(
                    "⛏️  Internal miner generating blocks... ({}/{})", 
                    height, min_blocks
                ));
            }
            Err(_) if i < max_wait - 1 => {
                // Keep waiting
            }
            Err(e) => return Err(e),
        }
        
        sleep(Duration::from_secs(1)).await;
    }
    
    Err(ZecDevError::ServiceNotReady(
        "Internal miner did not generate enough blocks".into()
    ))
}

async fn get_block_count(client: &Client) -> Result<u64> {
    let resp = client
        .post("http://127.0.0.1:8232")
        .json(&json!({
            "jsonrpc": "2.0",
            "id": "blockcount",
            "method": "getblockcount",
            "params": []
        }))
        .timeout(Duration::from_secs(5))
        .send()
        .await?;
    
    let json: serde_json::Value = resp.json().await?;
    
    json.get("result")
        .and_then(|v| v.as_u64())
        .ok_or_else(|| ZecDevError::HealthCheck("Invalid block count response".into()))
}

async fn generate_ua_fixtures(compose: &DockerCompose) -> Result<()> {
    // Generate unified address from zingo wallet
    let output = compose.exec("zingo-wallet", &[
        "zingo-cli",
        "--data-dir", "/var/zingo",
        "--server", "http://lightwalletd:9067",
        "--nosync"
    ])?;
    
    // Parse address from output
    if output.contains("u1") {
        println!("{} Generated unified address (ZIP-316 compliant)", "✓".green());
        
        // Save to fixtures file
        let addresses_output = compose.exec("zingo-wallet", &[
            "sh", "-c",
            "zingo-cli --data-dir /var/zingo --server http://lightwalletd:9067 --nosync << 'EOF'\naddresses\nquit\nEOF\n"
        ])?;
        
        // Extract and save unified address
        if let Some(ua) = extract_ua_from_output(&addresses_output) {
            std::fs::write(
                "fixtures/unified-addresses.json",
                serde_json::to_string_pretty(&json!({
                    "faucet_address": ua,
                    "type": "unified",
                    "receivers": ["orchard"]
                }))?
            )?;
            
            println!("{} UA fixtures saved to fixtures/unified-addresses.json", "✓".green());
        }
    } else {
        println!("{} Warning: Could not generate UA fixture", "⚠️".yellow());
    }
    
    Ok(())
}

fn extract_ua_from_output(output: &str) -> Option<String> {
    // Look for unified address (starts with u1)
    output.lines()
        .find(|line| line.contains("u1"))
        .and_then(|line| {
            line.split_whitespace()
                .find(|word| word.starts_with("u1"))
                .map(|s| s.to_string())
        })
}

async fn sync_wallet() -> Result<()> {
    let client = Client::new();
    
    let resp = client
        .post("http://127.0.0.1:8080/sync")
        .timeout(Duration::from_secs(30))
        .send()
        .await?;
    
    if resp.status().is_success() {
        println!("{} Wallet synced with blockchain", "✓".green());
    } else {
        println!("{} Warning: Wallet sync may have failed", "⚠️".yellow());
    }
    
    Ok(())
}

async fn print_mining_info() -> Result<()> {
    let client = Client::new();
    
    if let Ok(height) = get_block_count(&client).await {
        println!();
        println!("{}", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━".cyan());
        println!("{}", "  Blockchain Status".green().bold());
        println!("{}", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━".cyan());
        println!();
        println!("  {} {}", "Block Height:".bold(), height);
        println!("  {} {}", "Network:".bold(), "Regtest");
        println!("  {} {}", "Mining:".bold(), "Active (internal miner)");
        println!("  {} {}", "Pre-mined Funds:".bold(), "Available ✓");
    }
    
    Ok(())
}

fn print_connection_info(backend: &str) {
    println!();
    println!("{}", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━".cyan());
    println!("{}", "  Services Ready".green().bold());
    println!("{}", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━".cyan());
    println!();
    println!("  {} {}", "Zebra RPC:".bold(), "http://127.0.0.1:8232");
    println!("  {} {}", "Faucet API:".bold(), "http://127.0.0.1:8080");
    
    if backend == "lwd" {
        println!("  {} {}", "LightwalletD:".bold(), "http://127.0.0.1:9067");
    } else if backend == "zaino" {
        println!("  {} {}", "Zaino:".bold(), "http://127.0.0.1:9067 (experimental)");
    }
    
    println!();
    println!("{}", "Next steps:".bold());
    println!("  • Check status: zecdev status");
    println!("  • Run tests: zecdev test");
    println!("  • View fixtures: cat fixtures/unified-addresses.json");
    println!();
}