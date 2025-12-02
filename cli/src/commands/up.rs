use crate::docker::compose::DockerCompose;
use crate::docker::health::HealthChecker;
use crate::error::{Result, ZecDevError};
use colored::*;
use indicatif::{ProgressBar, ProgressStyle};
use reqwest::Client;
use serde_json::json;
use std::process::Command;
use tokio::time::{sleep, Duration};

const MAX_WAIT_SECONDS: u64 = 1500; // 25 minutes for mining

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
        "lwd" => vec!["zebra", "faucet"],
        "zaino" => vec!["zebra", "faucet"], // ✅ ZAINO NOW SUPPORTED!
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
    } else if backend == "zaino" {
        compose.up_with_profile("zaino")?; // ✅ START ZAINO PROFILE!
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
    
    pb.set_message("⏳ Waiting for Zebra...");
    let checker = HealthChecker::new();
    checker.wait_for_zebra(&pb).await?;
    
    // Wait for internal miner to produce blocks (M2 requirement: pre-mined funds)
    wait_for_mined_blocks(&pb, 101).await?;
    
    pb.set_message("⏳ Waiting for Faucet...");
    checker.wait_for_faucet(&pb).await?;
    
    // Wait for backend (lightwalletd or zaino)
    if backend == "lwd" || backend == "zaino" {
        let backend_name = if backend == "lwd" { "Lightwalletd" } else { "Zaino" };
        pb.set_message(format!("⏳ Waiting for {}...", backend_name));
        checker.wait_for_backend(&backend, &pb).await?;
    }
    
    pb.finish_with_message("✓ All services ready!".green().to_string());
    
    // Generate UA fixtures (M2 requirement: ZIP-316 fixtures)
    println!();
    println!("{} Generating ZIP-316 Unified Address fixtures...", "📋".cyan());
    
    if backend == "lwd" || backend == "zaino" {
        // Wait a bit for wallet to initialize
        sleep(Duration::from_secs(5)).await;
        
        // Determine backend URI for wallet commands
        let backend_uri = if backend == "lwd" {
            "http://lightwalletd:9067"
        } else {
            "http://zaino:9067"
        };
        
        match generate_ua_fixtures(backend_uri).await {
            Ok(address) => {
                println!("{} Generated UA: {}...", "✓".green(), &address[..20]);
            }
            Err(e) => {
                println!("{} Warning: Could not generate UA fixture ({})", "⚠️".yellow(), e);
                println!("   {} You can manually update fixtures/unified-addresses.json", "→".yellow());
            }
        }
        
        // Sync wallet with blockchain
        println!();
        println!("{} Syncing wallet with blockchain...", "🔄".cyan());
        if let Err(e) = sync_wallet(backend_uri).await {
            println!("{} Wallet sync warning: {}", "⚠️".yellow(), e);
        } else {
            println!("{} Wallet synced with blockchain", "✓".green());
        }
    }
    
    // Display connection info
    print_connection_info(&backend);
    print_mining_info().await?;
    
    Ok(())
}

async fn wait_for_mined_blocks(pb: &ProgressBar, min_blocks: u64) -> Result<()> {
    let client = Client::new();
    let start = std::time::Instant::now();
    
    loop {
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
            Err(_) => {
                // Keep waiting during startup
            }
        }
        
        if start.elapsed().as_secs() > MAX_WAIT_SECONDS {
            return Err(ZecDevError::ServiceNotReady(
                "Internal miner timeout - blocks not reaching maturity".into()
            ));
        }
        
        sleep(Duration::from_secs(2)).await;
    }
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

async fn generate_ua_fixtures(backend_uri: &str) -> Result<String> {
    // Get address from zingo wallet
    let cmd_str = format!(
        "echo 'addresses\nquit' | zingo-cli --data-dir /var/zingo --server {} --nosync 2>/dev/null",
        backend_uri
    );
    
    let output = Command::new("docker")
        .args(&[
            "exec", "-i", "zeckit-zingo-wallet",
            "sh", "-c",
            &cmd_str
        ])
        .output()
        .map_err(|e| ZecDevError::HealthCheck(format!("Docker exec failed: {}", e)))?;
    
    let output_str = String::from_utf8_lossy(&output.stdout);
    
    // Parse JSON array from output
    for line in output_str.lines() {
        let trimmed = line.trim();
        if trimmed.starts_with('[') {
            // Try to parse as JSON array
            if let Ok(addresses) = serde_json::from_str::<Vec<serde_json::Value>>(trimmed) {
                if let Some(addr_obj) = addresses.first() {
                    if let Some(address) = addr_obj.get("encoded_address").and_then(|v| v.as_str()) {
                        // Save fixture to file
                        let fixture = json!({
                            "faucet_address": address,
                            "type": "unified",
                            "receivers": ["orchard"]
                        });
                        
                        std::fs::create_dir_all("fixtures")?;
                        std::fs::write(
                            "fixtures/unified-addresses.json",
                            serde_json::to_string_pretty(&fixture)?
                        )?;
                        
                        return Ok(address.to_string());
                    }
                }
            }
        }
    }
    
    Err(ZecDevError::HealthCheck("Could not parse wallet address".into()))
}

async fn sync_wallet(backend_uri: &str) -> Result<()> {
    let cmd_str = format!(
        "echo 'sync run\nquit' | zingo-cli --data-dir /var/zingo --server {} 2>&1",
        backend_uri
    );
    
    let output = Command::new("docker")
        .args(&[
            "exec", "-i", "zeckit-zingo-wallet",
            "sh", "-c",
            &cmd_str
        ])
        .output()
        .map_err(|e| ZecDevError::HealthCheck(format!("Sync command failed: {}", e)))?;
    
    let output_str = String::from_utf8_lossy(&output.stdout);
    
    if output_str.contains("Sync error") {
        Err(ZecDevError::HealthCheck("Wallet sync error detected".into()))
    } else {
        Ok(())
    }
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
        println!("  {} {}", "Zaino:".bold(), "http://127.0.0.1:9067");
    }
    
    println!();
    println!("{}", "Next steps:".bold());
    println!("  • Run tests: zecdev test");
    println!("  • View fixtures: cat fixtures/unified-addresses.json");
    println!();
}