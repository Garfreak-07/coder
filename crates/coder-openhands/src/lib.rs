use serde::{Deserialize, Serialize};
use thiserror::Error;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OpenHandsServerConfig {
    pub server_url: String,
    pub session_api_key_env: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OpenHandsHealth {
    pub server_url: String,
    pub available: bool,
    pub detail: String,
}

pub struct OpenHandsClient {
    config: OpenHandsServerConfig,
    client: reqwest::Client,
}

impl OpenHandsClient {
    pub fn new(config: OpenHandsServerConfig) -> Self {
        Self {
            config,
            client: reqwest::Client::new(),
        }
    }

    pub async fn health(&self) -> Result<OpenHandsHealth, OpenHandsError> {
        let url = format!("{}/health", self.config.server_url.trim_end_matches('/'));
        let response = self.client.get(url).send().await?;
        let status = response.status();
        Ok(OpenHandsHealth {
            server_url: self.config.server_url.clone(),
            available: status.is_success(),
            detail: format!("HTTP {status}"),
        })
    }
}

#[derive(Debug, Error)]
pub enum OpenHandsError {
    #[error("OpenHands server request failed: {0}")]
    Request(#[from] reqwest::Error),
}
