use std::fmt::{Display, Formatter};

use serde::{Deserialize, Serialize};
use thiserror::Error;
use time::OffsetDateTime;

#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(transparent)]
pub struct RunId(String);

impl RunId {
    pub fn new() -> Self {
        Self(uuid::Uuid::new_v4().to_string())
    }

    pub fn from_string(value: impl Into<String>) -> Self {
        Self(value.into())
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

impl Default for RunId {
    fn default() -> Self {
        Self::new()
    }
}

impl Display for RunId {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        self.0.fmt(formatter)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(transparent)]
pub struct WorkflowId(String);

impl WorkflowId {
    pub fn new(value: impl Into<String>) -> Self {
        Self(value.into())
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

impl Display for WorkflowId {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        self.0.fmt(formatter)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RunStatus {
    Queued,
    Running,
    Completed,
    Blocked,
    Failed,
    Cancelled,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RunRequest {
    pub repo_root: String,
    pub task: String,
    pub workflow_id: WorkflowId,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RunState {
    pub run_id: RunId,
    pub workflow_id: WorkflowId,
    pub status: RunStatus,
    pub created_at: OffsetDateTime,
    pub updated_at: OffsetDateTime,
}

impl RunState {
    pub fn new(run_id: RunId, workflow_id: WorkflowId) -> Self {
        let now = OffsetDateTime::now_utc();
        Self {
            run_id,
            workflow_id,
            status: RunStatus::Queued,
            created_at: now,
            updated_at: now,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ReportStatus {
    Completed,
    Blocked,
    Failed,
    Cancelled,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EvidenceRef {
    pub kind: String,
    pub reference: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FinalReport {
    pub status: ReportStatus,
    pub summary: String,
    #[serde(default)]
    pub changed_files: Vec<String>,
    #[serde(default)]
    pub checks: Vec<String>,
    #[serde(default)]
    pub patch_refs: Vec<String>,
    #[serde(default)]
    pub artifact_refs: Vec<String>,
    #[serde(default)]
    pub evidence_refs: Vec<EvidenceRef>,
    #[serde(default)]
    pub blockers: Vec<String>,
    #[serde(default)]
    pub next_steps: Vec<String>,
}

impl FinalReport {
    pub fn with_status(status: ReportStatus, summary: impl Into<String>) -> Self {
        Self {
            status,
            summary: summary.into(),
            changed_files: Vec::new(),
            checks: Vec::new(),
            patch_refs: Vec::new(),
            artifact_refs: Vec::new(),
            evidence_refs: Vec::new(),
            blockers: Vec::new(),
            next_steps: Vec::new(),
        }
    }

    pub fn completed(summary: impl Into<String>) -> Self {
        Self::with_status(ReportStatus::Completed, summary)
    }

    pub fn blocked(summary: impl Into<String>, blocker: impl Into<String>) -> Self {
        let mut report = Self::with_status(ReportStatus::Blocked, summary);
        report.blockers.push(blocker.into());
        report
    }

    pub fn failed(summary: impl Into<String>, blocker: impl Into<String>) -> Self {
        let mut report = Self::with_status(ReportStatus::Failed, summary);
        report.blockers.push(blocker.into());
        report
    }

    pub fn with_check(mut self, check: impl Into<String>) -> Self {
        self.checks.push(check.into());
        self
    }

    pub fn with_evidence(mut self, kind: impl Into<String>, reference: impl Into<String>) -> Self {
        self.evidence_refs.push(EvidenceRef {
            kind: kind.into(),
            reference: reference.into(),
        });
        self
    }
}

#[derive(Debug, Error)]
pub enum CoderError {
    #[error("invalid configuration: {0}")]
    InvalidConfig(String),
    #[error("workflow not found: {0}")]
    WorkflowNotFound(String),
    #[error("runtime error: {0}")]
    Runtime(String),
}
