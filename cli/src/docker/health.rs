use crate::error::{Result, ZecDevError};
use reqwest::Client;
use indicatif::ProgressBar;
use tokio::time::{sleep, Duration};
use serde_json::Value;

pub struct HealthChecker {
    client: Client,
    max_retries: u32,
    retry_delay: Duration,
    backend_max_retries: u32, // Longer timeout for backends
}

impl HealthChecker {
    pub fn new() -> Self {
        Self {
            client: Client::new(),
            max_retries: 60, // 60 retries * 2s = 2 minutes max
            retry_delay: Duration::from_secs(2),
            backend_max_retries: 90, // 90 retries * 2s = 3 minutes for backends
        }
    }

    pub async fn wait_for_zebra(&self, pb: &ProgressBar) -> Result<()> {
        for i in 0..self.max_retries {
            pb.tick();
            
            match self.check_zebra().await {
                Ok(_) => return Ok(()),
                Err(_) if i < self.max_retries - 1 => {
                    sleep(self.retry_delay).await;
                }
                Err(e) => return Err(e),
            }
        }

        Err(ZecDevError::ServiceNotReady("Zebra".into()))
    }

    pub async fn wait_for_faucet(&self, pb: &ProgressBar) -> Result<()> {
        for i in 0..self.max_retries {
            pb.tick();
            
            match self.check_faucet().await {
                Ok(_) => return Ok(()),
                Err(_) if i < self.max_retries - 1 => {
                    sleep(self.retry_delay).await;
                }
                Err(e) => return Err(e),
            }
        }

        Err(ZecDevError::ServiceNotReady("Faucet".into()))
    }

    pub async fn wait_for_backend(&self, backend: &str, pb: &ProgressBar) -> Result<()> {
        // Use longer timeout for backends since they need to sync with Zebra
        for i in 0..self.backend_max_retries {
            pb.tick();
            
            match self.check_backend(backend).await {
                Ok(_) => return Ok(()),
                Err(_) if i < self.backend_max_retries - 1 => {
                    sleep(self.retry_delay).await;
                }
                Err(e) => return Err(e),
            }
        }

        Err(ZecDevError::ServiceNotReady(format!("{} (may need more sync time)", backend)))
    }

    async fn check_zebra(&self) -> Result<()> {
        let resp = self
            .client
            .post("http://127.0.0.1:8232")
            .json(&serde_json::json!({
                "jsonrpc": "2.0",
                "id": "health",
                "method": "getblockcount",
                "params": []
            }))
            .timeout(Duration::from_secs(5))
            .send()
            .await?;

        if resp.status().is_success() {
            Ok(())
        } else {
            Err(ZecDevError::HealthCheck("Zebra not ready".into()))
        }
    }

    async fn check_faucet(&self) -> Result<()> {
        let resp = self
            .client
            .get("http://127.0.0.1:8080/health")
            .timeout(Duration::from_secs(5))
            .send()
            .await?;

        if !resp.status().is_success() {
            return Err(ZecDevError::HealthCheck("Faucet not ready".into()));
        }

        let json: Value = resp.json().await?;
        
        // Check if faucet is actually healthy
        if json.get("status").and_then(|s| s.as_str()) == Some("unhealthy") {
            return Err(ZecDevError::HealthCheck("Faucet unhealthy".into()));
        }

        Ok(())
    }

    async fn check_backend(&self, backend: &str) -> Result<()> {
        // For lightwalletd, check gRPC port
        // For zaino, check its port
        let port = match backend {
            "lwd" => 9067,
            "zaino" => 9067,
            _ => return Err(ZecDevError::HealthCheck("Unknown backend".into())),
        };
        
        let url = format!("http://127.0.0.1:{}", port);
        
        // Simple TCP check - just see if port responds
        // Note: gRPC won't return valid HTTP, but connection is what matters
        let resp = self
            .client
            .get(&url)
            .timeout(Duration::from_secs(5))
            .send()
            .await;

        // For gRPC services, any response (even errors) means it's listening
        match resp {
            Ok(_) => Ok(()),
            Err(e) => {
                // Check if it's a connection error or just HTTP error
                if e.is_connect() || e.is_timeout() {
                    Err(ZecDevError::HealthCheck(format!("{} not ready", backend)))
                } else {
                    // Got a response (even if HTTP error), means service is up
                    Ok(())
                }
            }
        }
    }
}