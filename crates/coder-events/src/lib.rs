use coder_core::RunId;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use time::OffsetDateTime;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EventRef {
    pub label: String,
    pub uri: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CoderEvent {
    pub event_id: String,
    pub run_id: RunId,
    pub sequence: u64,
    #[serde(with = "time::serde::rfc3339")]
    pub timestamp: OffsetDateTime,
    pub kind: String,
    #[serde(default)]
    pub payload: Value,
    #[serde(default)]
    pub refs: Vec<EventRef>,
}

impl CoderEvent {
    pub fn new(run_id: RunId, sequence: u64, kind: impl Into<String>, payload: Value) -> Self {
        Self {
            event_id: format!("evt_{}", uuid::Uuid::new_v4()),
            run_id,
            sequence,
            timestamp: OffsetDateTime::now_utc(),
            kind: kind.into(),
            payload,
            refs: Vec::new(),
        }
    }

    pub fn with_ref(mut self, label: impl Into<String>, uri: impl Into<String>) -> Self {
        self.refs.push(EventRef {
            label: label.into(),
            uri: uri.into(),
        });
        self
    }

    pub fn to_jsonl(&self) -> Result<String, serde_json::Error> {
        serde_json::to_string(self).map(|line| format!("{line}\n"))
    }

    pub fn from_jsonl_line(line: &str) -> Result<Self, serde_json::Error> {
        serde_json::from_str(line)
    }
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;

    #[test]
    fn event_roundtrips_as_jsonl() {
        let run_id = RunId::from_string("run_1");
        let event = CoderEvent::new(run_id, 1, "run.started", json!({"workflow_id": "wf"}));

        let line = event.to_jsonl().unwrap();
        let decoded = CoderEvent::from_jsonl_line(line.trim()).unwrap();

        assert_eq!(decoded.sequence, 1);
        assert_eq!(decoded.kind, "run.started");
        assert_eq!(decoded.payload["workflow_id"], "wf");
    }
}
