use crate::docker::compose::DockerCompose;
use crate::docker::health::HealthChecker;
use crate::error::{Result, ZecDevError};
use colored::*;
use indicatif::{ProgressBar, ProgressStyle};
use reqwest::Client;
use serde_json::json;
use std::process::Command;
use std::fs;
use tokio::time::{sleep, Duration};

const MAX_WAIT_SECONDS: u64 = 2000;

pub async fn execute(backend: String, fresh: bool) -> Result<()> {
    println!("{}", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━".cyan());
    println!("{}", "  ZecKit - Starting Devnet".cyan().bold());
    println!("{}", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━".cyan());
    println!();
    
    let compose = DockerCompose::new()?;
    
    if fresh {
        println!("{}", "🧹 Cleaning up old data...".yellow());
        compose.down(true)?;
    }
    
    let services = match backend.as_str() {
        "lwd" => vec!["zebra", "faucet"],
        "zaino" => vec!["zebra", "faucet"],
        "none" => vec!["zebra", "faucet"],
        _ => {
            return Err(ZecDevError::Config(format!(
                "Invalid backend: {}. Use 'lwd', 'zaino', or 'none'", 
                backend
            )));
        }
    };
    
    println!("{} Starting services: {}", "🚀".green(), services.join(", "));
    
    if backend == "lwd" {
        compose.up_with_profile("lwd")?;
    } else if backend == "zaino" {
        compose.up_with_profile("zaino")?;
    } else {
        compose.up(&services)?;
    }
    
    let pb = ProgressBar::new_spinner();
    pb.set_style(
        ProgressStyle::default_spinner()
            .template("{spinner:.green} {msg}")
            .unwrap()
    );
    
    pb.set_message("⏳ Waiting for Zebra...");
    let checker = HealthChecker::new();
    checker.wait_for_zebra(&pb).await?;
    
    pb.set_message("⏳ Waiting for Faucet...");
    checker.wait_for_faucet(&pb).await?;
    
    if backend == "lwd" || backend == "zaino" {
        let backend_name = if backend == "lwd" { "Lightwalletd" } else { "Zaino" };
        pb.set_message(format!("⏳ Waiting for {}...", backend_name));
        checker.wait_for_backend(&backend, &pb).await?;
    }
    
    pb.finish_with_message("✓ Services starting...".green().to_string());
    
    let backend_uri = if backend == "lwd" {
        "http://lightwalletd:9067"
    } else if backend == "zaino" {
        "http://zaino:9067"
    } else {
        "http://lightwalletd:9067"
    };
    
    // WAIT FOR WALLET FIRST (before mining!)
    println!();
    println!("{} Waiting for wallet to initialize...", "⏳".cyan());
    pb.set_message("⏳ Wallet starting...");
    wait_for_wallet_ready(&pb, backend_uri).await?;
    pb.finish_with_message("✓ Wallet ready".green().to_string());
    
    // GET WALLET ADDRESS AND UPDATE ZEBRA CONFIG
    println!();
    println!("{} Configuring Zebra to mine to wallet...", "⚙️".cyan());
    
    match get_wallet_transparent_address(backend_uri).await {
        Ok(t_address) => {
            println!("{} Wallet transparent address: {}", "✓".green(), t_address);
            
            if let Err(e) = update_zebra_miner_address(&t_address) {
                println!("{} Warning: Could not update zebra.toml: {}", "⚠️".yellow(), e);
            } else {
                println!("{} Updated zebra.toml miner_address", "✓".green());
                
                println!("{} Restarting Zebra with new miner address...", "🔄".yellow());
                if let Err(e) = restart_zebra().await {
                    println!("{} Warning: Zebra restart had issues: {}", "⚠️".yellow(), e);
                }
            }
        }
        Err(e) => {
            println!("{} Warning: Could not get wallet address: {}", "⚠️".yellow(), e);
            println!("   {} Mining will use default address in zebra.toml", "→".yellow());
        }
    }
    
    // NOW WAIT FOR BLOCKS (mining to correct address)
    wait_for_mined_blocks(&pb, 101).await?;
    
    // Wait extra time for coinbase maturity
    println!();
    println!("{} Waiting for coinbase maturity (100 confirmations)...", "⏳".yellow());
    sleep(Duration::from_secs(120)).await;
    
    // Generate UA fixtures
    println!();
    println!("{} Generating ZIP-316 Unified Address fixtures...", "📋".cyan());
    
    match generate_ua_fixtures(backend_uri).await {
        Ok(address) => {
            println!("{} Generated UA: {}...", "✓".green(), &address[..20]);
        }
        Err(e) => {
            println!("{} Warning: Could not generate UA fixture ({})", "⚠️".yellow(), e);
            println!("   {} You can manually update fixtures/unified-addresses.json", "→".yellow());
        }
    }
    
    // Sync wallet
    println!();
    println!("{} Syncing wallet with blockchain...", "🔄".cyan());
    if let Err(e) = sync_wallet(backend_uri).await {
        println!("{} Wallet sync warning: {}", "⚠️".yellow(), e);
    } else {
        println!("{} Wallet synced with blockchain", "✓".green());
    }
    
    // Check balance
    println!();
    println!("{} Checking wallet balance...", "💰".cyan());
    match check_wallet_balance().await {
        Ok(balance) if balance > 0.0 => {
            println!("{} Wallet has {} ZEC available", "✓".green(), balance);
        }
        Ok(_) => {
            println!("{} Wallet synced but balance not yet available", "⚠️".yellow());
            println!("   {} Blocks still maturing, wait a few more minutes", "→".yellow());
        }
        Err(e) => {
            println!("{} Could not check balance: {}", "⚠️".yellow(), e);
        }
    }
    
    print_connection_info(&backend);
    print_mining_info().await?;
    
    Ok(())
}

async fn wait_for_wallet_ready(pb: &ProgressBar, backend_uri: &str) -> Result<()> {
    let start = std::time::Instant::now();
    
    loop {
        pb.tick();
        
        let cmd_str = format!(
            "bash -c \"echo -e 't_addresses\\nquit' | zingo-cli --data-dir /var/zingo --server {} --chain regtest --nosync 2>&1\"",
            backend_uri
        );
        
        let output = Command::new("docker")
            .args(&["exec", "zeckit-zingo-wallet", "bash", "-c", &cmd_str])
            .output();
        
        if let Ok(out) = output {
            let output_str = String::from_utf8_lossy(&out.stdout);
            if output_str.contains("tm") && output_str.contains("encoded_address") {
                return Ok(());
            }
        }
        
        if start.elapsed().as_secs() > 60 {
            return Err(ZecDevError::ServiceNotReady("Wallet not ready after 60s".into()));
        }
        
        sleep(Duration::from_secs(2)).await;
    }
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
            Err(_) => {}
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

async fn get_wallet_transparent_address(backend_uri: &str) -> Result<String> {
    let cmd_str = format!(
        "bash -c \"echo -e 't_addresses\\nquit' | zingo-cli --data-dir /var/zingo --server {} --chain regtest --nosync 2>&1\"",
        backend_uri
    );
    
    let output = Command::new("docker")
        .args(&["exec", "zeckit-zingo-wallet", "bash", "-c", &cmd_str])
        .output()
        .map_err(|e| ZecDevError::HealthCheck(format!("Docker exec failed: {}", e)))?;
    
    let output_str = String::from_utf8_lossy(&output.stdout);
    
    for line in output_str.lines() {
        if line.contains("\"encoded_address\"") && line.contains("tm") {
            if let Some(start) = line.find("tm") {
                let addr_part = &line[start..];
                let end = addr_part.find(|c: char| c == '"' || c == '\n' || c == ' ')
                    .unwrap_or(addr_part.len());
                let address = &addr_part[..end];
                
                if address.starts_with("tm") && address.len() > 30 {
                    return Ok(address.to_string());
                }
            }
        }
    }
    
    Err(ZecDevError::HealthCheck("Could not find transparent address in wallet output".into()))
}

fn update_zebra_miner_address(address: &str) -> Result<()> {
    let zebra_config_path = "docker/configs/zebra.toml";
    
    let config = fs::read_to_string(zebra_config_path)
        .map_err(|e| ZecDevError::Config(format!("Could not read zebra.toml: {}", e)))?;
    
    let new_config = if config.contains("miner_address") {
        use regex::Regex;
        let re = Regex::new(r#"miner_address = "tm[a-zA-Z0-9]+""#).unwrap();
        re.replace(&config, format!("miner_address = \"{}\"", address)).to_string()
    } else {
        config.replace(
            "[mining]",
            &format!("[mining]\nminer_address = \"{}\"", address)
        )
    };
    
    fs::write(zebra_config_path, new_config)
        .map_err(|e| ZecDevError::Config(format!("Could not write zebra.toml: {}", e)))?;
    
    Ok(())
}

async fn restart_zebra() -> Result<()> {
    let output = Command::new("docker")
        .args(&["restart", "zeckit-zebra"])
        .output()
        .map_err(|e| ZecDevError::Docker(format!("Failed to restart Zebra: {}", e)))?;
    
    if !output.status.success() {
        return Err(ZecDevError::Docker("Zebra restart failed".into()));
    }
    
    sleep(Duration::from_secs(15)).await;
    
    Ok(())
}

async fn generate_ua_fixtures(backend_uri: &str) -> Result<String> {
    let cmd_str = format!(
        "bash -c \"echo -e 'addresses\\nquit' | zingo-cli --data-dir /var/zingo --server {} --chain regtest --nosync 2>&1\"",
        backend_uri
    );
    
    let output = Command::new("docker")
        .args(&["exec", "zeckit-zingo-wallet", "bash", "-c", &cmd_str])
        .output()
        .map_err(|e| ZecDevError::HealthCheck(format!("Docker exec failed: {}", e)))?;
    
    let output_str = String::from_utf8_lossy(&output.stdout);
    
    for line in output_str.lines() {
        if line.contains("uregtest") {
            if let Some(start) = line.find("uregtest") {
                let addr_part = &line[start..];
                let end = addr_part.find(|c: char| c == '"' || c == '\n' || c == ' ')
                    .unwrap_or(addr_part.len());
                let address = &addr_part[..end];
                
                let fixture = json!({
                    "faucet_address": address,
                    "type": "unified",
                    "receivers": ["orchard"]
                });
                
                fs::create_dir_all("fixtures")?;
                fs::write(
                    "fixtures/unified-addresses.json",
                    serde_json::to_string_pretty(&fixture)?
                )?;
                
                return Ok(address.to_string());
            }
        }
    }
    
    Err(ZecDevError::HealthCheck("Could not find wallet address in output".into()))
}

async fn sync_wallet(backend_uri: &str) -> Result<()> {
    let cmd_str = format!(
        "echo 'sync run\nquit' | zingo-cli --data-dir /var/zingo --server {} --chain regtest 2>&1",
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

async fn check_wallet_balance() -> Result<f64> {
    let client = Client::new();
    let resp = client
        .get("http://127.0.0.1:8080/stats")
        .timeout(Duration::from_secs(5))
        .send()
        .await?;
    
    let json: serde_json::Value = resp.json().await?;
    Ok(json["current_balance"].as_f64().unwrap_or(0.0))
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