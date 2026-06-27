use async_trait::async_trait;
use coder_core::{FinalReport, RunId};
use serde::{Deserialize, Serialize};
use thiserror::Error;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HarnessRunRequest {
    pub run_id: RunId,
    pub workflow_id: String,
    pub node_id: String,
    pub agent_id: String,
    pub harness_id: String,
    pub task: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HarnessRunResult {
    pub status: String,
    pub report: Option<FinalReport>,
}

#[async_trait]
pub trait HarnessBackend: Send + Sync {
    async fn run(&self, request: HarnessRunRequest) -> Result<HarnessRunResult, HarnessError>;
}

#[derive(Debug, Error)]
pub enum HarnessError {
    #[error("backend unavailable: {0}")]
    Unavailable(String),
    #[error("backend rejected request: {0}")]
    Rejected(String),
    #[error("backend failed: {0}")]
    Failed(String),
}
