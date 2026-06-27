use coder_core::RunId;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use time::OffsetDateTime;

pub const DEFAULT_LARGE_PAYLOAD_PREVIEW_LIMIT: usize = 4096;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EventRef {
    pub label: String,
    pub uri: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LargePayloadRef {
    pub preview: String,
    pub truncated: bool,
    pub blob_ref: String,
}

impl LargePayloadRef {
    pub fn from_text(text: &str, blob_ref: impl Into<String>, preview_limit: usize) -> Self {
        let mut chars = text.chars();
        let preview: String = chars.by_ref().take(preview_limit).collect();
        let truncated = chars.next().is_some();
        Self {
            preview,
            truncated,
            blob_ref: blob_ref.into(),
        }
    }
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
            payload: redact_payload(payload),
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

pub fn redact_payload(value: Value) -> Value {
    match value {
        Value::Object(object) => {
            let redacted = object
                .into_iter()
                .map(|(key, value)| {
                    let value = if is_secret_key(&key) {
                        Value::String("[REDACTED]".to_owned())
                    } else {
                        redact_payload(value)
                    };
                    (key, value)
                })
                .collect::<Map<String, Value>>();
            Value::Object(redacted)
        }
        Value::Array(items) => Value::Array(items.into_iter().map(redact_payload).collect()),
        other => other,
    }
}

fn is_secret_key(key: &str) -> bool {
    let normalized = key.to_ascii_lowercase();
    normalized.contains("api_key")
        || normalized.contains("apikey")
        || normalized.contains("token")
        || normalized.contains("secret")
        || normalized.contains("password")
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

    #[test]
    fn secret_like_payload_keys_are_redacted() {
        let event = CoderEvent::new(
            RunId::from_string("run_1"),
            1,
            "backend.connected",
            json!({
                "api_key": "sk-live",
                "nested": {
                    "session_token": "token-value",
                    "safe": "visible"
                }
            }),
        );

        assert_eq!(event.payload["api_key"], "[REDACTED]");
        assert_eq!(event.payload["nested"]["session_token"], "[REDACTED]");
        assert_eq!(event.payload["nested"]["safe"], "visible");
    }

    #[test]
    fn large_payload_ref_keeps_preview_and_blob_reference() {
        let payload = LargePayloadRef::from_text("abcdef", "blob://sha256/test", 3);

        assert_eq!(payload.preview, "abc");
        assert!(payload.truncated);
        assert_eq!(payload.blob_ref, "blob://sha256/test");
    }
}
