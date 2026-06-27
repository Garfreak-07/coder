use std::{
    fs::{self, OpenOptions},
    io::{BufRead, BufReader, Write},
    path::{Path, PathBuf},
};

use coder_core::{FinalReport, RunId, RunState};
use coder_events::CoderEvent;
use serde::Serialize;
use sha2::{Digest, Sha256};
use thiserror::Error;

#[derive(Debug, Clone)]
pub struct RunStore {
    root: PathBuf,
}

impl RunStore {
    pub fn new(root: impl Into<PathBuf>) -> Self {
        Self { root: root.into() }
    }

    pub fn write_metadata(&self, state: &RunState) -> Result<(), StoreError> {
        write_json(self.run_dir(&state.run_id).join("metadata.json"), state)
    }

    pub fn append_event(&self, run_id: &RunId, event: &CoderEvent) -> Result<(), StoreError> {
        let path = self.run_dir(run_id).join("events.jsonl");
        ensure_parent(&path)?;
        let mut file = OpenOptions::new().create(true).append(true).open(path)?;
        file.write_all(event.to_jsonl()?.as_bytes())?;
        Ok(())
    }

    pub fn read_events(&self, run_id: &RunId) -> Result<Vec<CoderEvent>, StoreError> {
        let path = self.run_dir(run_id).join("events.jsonl");
        if !path.exists() {
            return Ok(Vec::new());
        }
        let file = fs::File::open(path)?;
        let reader = BufReader::new(file);
        let mut events = Vec::new();
        for line in reader.lines() {
            let line = line?;
            if !line.trim().is_empty() {
                events.push(CoderEvent::from_jsonl_line(&line)?);
            }
        }
        Ok(events)
    }

    pub fn write_report(&self, run_id: &RunId, report: &FinalReport) -> Result<String, StoreError> {
        self.write_artifact(run_id, "final-report.json", report)
    }

    pub fn write_artifact<T: Serialize>(
        &self,
        run_id: &RunId,
        name: &str,
        value: &T,
    ) -> Result<String, StoreError> {
        let safe_name = safe_file_name(name)?;
        let path = self.run_dir(run_id).join("artifacts").join(&safe_name);
        write_json(&path, value)?;
        Ok(format!(
            "artifact://runs/{}/artifacts/{safe_name}",
            run_id.as_str()
        ))
    }

    pub fn write_blob(&self, content: &[u8]) -> Result<String, StoreError> {
        let digest = Sha256::digest(content);
        let hex = format!("{digest:x}");
        let path = self.root.join("blobs").join(&hex[..2]).join(&hex);
        ensure_parent(&path)?;
        if !path.exists() {
            fs::write(path, content)?;
        }
        Ok(format!("blob://sha256/{hex}"))
    }

    pub fn run_dir(&self, run_id: &RunId) -> PathBuf {
        self.root.join("runs").join(run_id.as_str())
    }
}

#[derive(Debug, Error)]
pub enum StoreError {
    #[error("io error: {0}")]
    Io(#[from] std::io::Error),
    #[error("json error: {0}")]
    Json(#[from] serde_json::Error),
    #[error("invalid file name: {0}")]
    InvalidFileName(String),
}

fn write_json(path: impl AsRef<Path>, value: &impl Serialize) -> Result<(), StoreError> {
    let path = path.as_ref();
    ensure_parent(path)?;
    fs::write(path, serde_json::to_string_pretty(value)?)?;
    Ok(())
}

fn ensure_parent(path: &Path) -> Result<(), StoreError> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    Ok(())
}

fn safe_file_name(value: &str) -> Result<String, StoreError> {
    if value.is_empty()
        || value.contains('/')
        || value.contains('\\')
        || value == "."
        || value == ".."
    {
        return Err(StoreError::InvalidFileName(value.to_owned()));
    }
    Ok(value.to_owned())
}

#[cfg(test)]
mod tests {
    use coder_events::CoderEvent;
    use serde_json::json;

    use super::*;

    #[test]
    fn event_log_roundtrips() {
        let root = temp_root();
        let store = RunStore::new(&root);
        let run_id = RunId::from_string("run_test");
        let event = CoderEvent::new(
            run_id.clone(),
            1,
            "run.started",
            json!({"workflow_id": "wf"}),
        );

        store.append_event(&run_id, &event).unwrap();
        let events = store.read_events(&run_id).unwrap();

        assert_eq!(events.len(), 1);
        assert_eq!(events[0].kind, "run.started");
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn blob_refs_are_content_addressed() {
        let root = temp_root();
        let store = RunStore::new(&root);

        let first = store.write_blob(b"same content").unwrap();
        let second = store.write_blob(b"same content").unwrap();

        assert_eq!(first, second);
        assert!(first.starts_with("blob://sha256/"));
        let _ = fs::remove_dir_all(root);
    }

    fn temp_root() -> PathBuf {
        std::env::temp_dir().join(format!(
            "coder-store-{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ))
    }
}
