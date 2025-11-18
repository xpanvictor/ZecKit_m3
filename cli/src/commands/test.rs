use crate::error::Result;
use colored::*;
use reqwest::Client;
use serde_json::Value;

pub async fn execute() -> Result<()> {
    println!("{}", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━".cyan());
    println!("{}", "  ZecKit - Running Smoke Tests".cyan().bold());
    println!("{}", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━".cyan());
    println!();

    let client = Client::new();
    let mut passed = 0;
    let mut failed = 0;

    // Test 1: Zebra RPC
    print!("  [1/5] Zebra RPC connectivity... ");
    match test_zebra_rpc(&client).await {
        Ok(_) => {
            println!("{}", "✓ PASS".green());
            passed += 1;
        }
        Err(e) => {
            println!("{} {}", "✗ FAIL".red(), e);
            failed += 1;
        }
    }

    // Test 2: Faucet Health
    print!("  [2/5] Faucet health check... ");
    match test_faucet_health(&client).await {
        Ok(_) => {
            println!("{}", "✓ PASS".green());
            passed += 1;
        }
        Err(e) => {
            println!("{} {}", "✗ FAIL".red(), e);
            failed += 1;
        }
    }

    // Test 3: Faucet Stats
    print!("  [3/5] Faucet stats endpoint... ");
    match test_faucet_stats(&client).await {
        Ok(_) => {
            println!("{}", "✓ PASS".green());
            passed += 1;
        }
        Err(e) => {
            println!("{} {}", "✗ FAIL".red(), e);
            failed += 1;
        }
    }

    // Test 4: Faucet Address
    print!("  [4/5] Faucet address retrieval... ");
    match test_faucet_address(&client).await {
        Ok(_) => {
            println!("{}", "✓ PASS".green());
            passed += 1;
        }
        Err(e) => {
            println!("{} {}", "✗ FAIL".red(), e);
            failed += 1;
        }
    }

    // Test 5: Faucet Request (mock transaction)
    print!("  [5/5] Faucet funding request... ");
    match test_faucet_request(&client).await {
        Ok(_) => {
            println!("{}", "✓ PASS".green());
            passed += 1;
        }
        Err(e) => {
            println!("{} {}", "✗ FAIL".red(), e);
            failed += 1;
        }
    }

    println!();
    println!("{}", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━".cyan());
    println!("  {} Tests passed: {}", "✓".green(), passed.to_string().green());
    println!("  {} Tests failed: {}", "✗".red(), failed.to_string().red());
    println!("{}", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━".cyan());
    println!();

    if failed > 0 {
        return Err(crate::error::ZecDevError::HealthCheck(
            format!("{} test(s) failed", failed)
        ));
    }

    Ok(())
}

async fn test_zebra_rpc(client: &Client) -> Result<()> {
    let resp = client
        .post("http://127.0.0.1:8232")
        .json(&serde_json::json!({
            "jsonrpc": "2.0",
            "id": "test",
            "method": "getblockcount",
            "params": []
        }))
        .send()
        .await?;

    if !resp.status().is_success() {
        return Err(crate::error::ZecDevError::HealthCheck(
            "Zebra RPC not responding".into()
        ));
    }

    Ok(())
}

async fn test_faucet_health(client: &Client) -> Result<()> {
    let resp = client
        .get("http://127.0.0.1:8080/health")
        .send()
        .await?;

    if !resp.status().is_success() {
        return Err(crate::error::ZecDevError::HealthCheck(
            "Faucet health check failed".into()
        ));
    }

    Ok(())
}

async fn test_faucet_stats(client: &Client) -> Result<()> {
    let resp = client
        .get("http://127.0.0.1:8080/stats")
        .send()
        .await?;

    if !resp.status().is_success() {
        return Err(crate::error::ZecDevError::HealthCheck(
            "Faucet stats not available".into()
        ));
    }

    let json: Value = resp.json().await?;
    
    // More lenient checks - just verify key fields exist
    if json.get("faucet_address").is_none() {
        return Err(crate::error::ZecDevError::HealthCheck(
            "Stats missing faucet_address".into()
        ));
    }
    
    // Check that current_balance exists (can be any number including 0)
    if json.get("current_balance").is_none() {
        return Err(crate::error::ZecDevError::HealthCheck(
            "Stats missing current_balance".into()
        ));
    }

    Ok(())
}

async fn test_faucet_address(client: &Client) -> Result<()> {
    let resp = client
        .get("http://127.0.0.1:8080/address")
        .send()
        .await?;

    if !resp.status().is_success() {
        return Err(crate::error::ZecDevError::HealthCheck(
            "Could not get faucet address".into()
        ));
    }

    let json: Value = resp.json().await?;
    if json.get("address").is_none() {
        return Err(crate::error::ZecDevError::HealthCheck(
            "Invalid address response".into()
        ));
    }

    Ok(())
}

async fn test_faucet_request(client: &Client) -> Result<()> {
    // First ensure faucet has funds
    let _ = client
        .post("http://127.0.0.1:8080/admin/add-funds")
        .json(&serde_json::json!({
            "amount": 100.0,
            "secret": "dev-secret-change-in-production"
        }))
        .send()
        .await;

    // Test funding request
    let resp = client
        .post("http://127.0.0.1:8080/request")
        .json(&serde_json::json!({
            "address": "tmBsTi2xWTjUdEXnuTceL7fecEQKeWu4u6d",
            "amount": 1.0
        }))
        .send()
        .await?;

    if !resp.status().is_success() {
        return Err(crate::error::ZecDevError::HealthCheck(
            "Faucet request failed".into()
        ));
    }

    let json: Value = resp.json().await?;
    if json.get("txid").is_none() {
        return Err(crate::error::ZecDevError::HealthCheck(
            "No TXID returned".into()
        ));
    }

    Ok(())
}