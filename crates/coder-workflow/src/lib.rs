use coder_config::{validate_project_config, ProjectConfig, WorkflowSpec};
use coder_core::{FinalReport, RunId, RunRequest, RunState, RunStatus, WorkflowId};
use coder_events::CoderEvent;
use coder_store::{RunStore, StoreError};
use serde_json::json;
use thiserror::Error;

pub struct MockWorkflowRunner<'a> {
    config: &'a ProjectConfig,
    store: RunStore,
}

impl<'a> MockWorkflowRunner<'a> {
    pub fn new(config: &'a ProjectConfig, store: RunStore) -> Self {
        Self { config, store }
    }

    pub fn run(&self, workflow_id: &str, task: &str) -> Result<MockRunOutput, WorkflowError> {
        let validation = validate_project_config(self.config);
        if !validation.is_pass() {
            return Err(WorkflowError::InvalidConfig(validation.status));
        }
        let workflow = self
            .config
            .workflows
            .get(workflow_id)
            .ok_or_else(|| WorkflowError::WorkflowNotFound(workflow_id.to_owned()))?;

        let run_id = RunId::new();
        let request = RunRequest {
            repo_root: ".".to_owned(),
            task: task.to_owned(),
            workflow_id: WorkflowId::new(workflow_id),
        };
        let mut state = RunState::new(run_id.clone(), request.workflow_id.clone());
        state.status = RunStatus::Running;
        self.store.write_metadata(&state)?;

        let mut sequence = 1;
        self.emit(
            &run_id,
            sequence,
            "run.started",
            json!({"workflow_id": workflow_id, "task": task}),
        )?;
        sequence += 1;

        for node in &workflow.nodes {
            self.emit(
                &run_id,
                sequence,
                "node.started",
                json!({
                    "node_id": node.id,
                    "agent": node.agent,
                    "harness": node.harness
                }),
            )?;
            sequence += 1;
            self.emit(
                &run_id,
                sequence,
                "node.completed",
                json!({
                    "node_id": node.id,
                    "status": "completed",
                    "mock": true
                }),
            )?;
            sequence += 1;
        }

        let report = report_for_mock_run(workflow_id, workflow, task);
        let report_ref = self.store.write_report(&run_id, &report)?;
        self.emit(
            &run_id,
            sequence,
            "report.created",
            json!({"report_ref": report_ref}),
        )?;
        sequence += 1;
        self.emit(
            &run_id,
            sequence,
            "run.completed",
            json!({"status": "completed", "report_ref": report_ref}),
        )?;

        state.status = RunStatus::Completed;
        state.updated_at = time::OffsetDateTime::now_utc();
        self.store.write_metadata(&state)?;

        Ok(MockRunOutput {
            run_id,
            report,
            report_ref,
        })
    }

    fn emit(
        &self,
        run_id: &RunId,
        sequence: u64,
        kind: &str,
        payload: serde_json::Value,
    ) -> Result<(), WorkflowError> {
        let event = CoderEvent::new(run_id.clone(), sequence, kind, payload);
        self.store.append_event(run_id, &event)?;
        Ok(())
    }
}

#[derive(Debug)]
pub struct MockRunOutput {
    pub run_id: RunId,
    pub report: FinalReport,
    pub report_ref: String,
}

#[derive(Debug, Error)]
pub enum WorkflowError {
    #[error("invalid configuration: {0}")]
    InvalidConfig(String),
    #[error("workflow not found: {0}")]
    WorkflowNotFound(String),
    #[error("store error: {0}")]
    Store(#[from] StoreError),
}

fn report_for_mock_run(workflow_id: &str, workflow: &WorkflowSpec, task: &str) -> FinalReport {
    FinalReport::completed(format!(
        "Mock workflow '{workflow_id}' accepted task '{task}' and visited {} node(s).",
        workflow.nodes.len()
    ))
}

#[cfg(test)]
mod tests {
    use std::fs;

    use coder_config::ProjectConfig;

    use super::*;

    #[test]
    fn mock_runner_writes_jsonl_events_and_report() {
        let config: ProjectConfig =
            serde_yaml::from_str(include_str!("../../../examples/coder.yaml")).unwrap();
        let root = std::env::temp_dir().join(format!(
            "coder-workflow-{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let store = RunStore::new(&root);
        let runner = MockWorkflowRunner::new(&config, store.clone());

        let output = runner.run("planner-led", "summarize the repo").unwrap();
        let events = store.read_events(&output.run_id).unwrap();

        assert_eq!(events.first().unwrap().kind, "run.started");
        assert_eq!(events.last().unwrap().kind, "run.completed");
        assert!(output.report_ref.contains("final-report.json"));
        let _ = fs::remove_dir_all(root);
    }
}
