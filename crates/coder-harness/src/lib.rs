use async_trait::async_trait;
use coder_core::{FinalReport, RunId};
use serde::{Deserialize, Serialize};
use serde_json::Value;
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

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RiskLevel {
    Low,
    #[default]
    Medium,
    High,
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SideEffectLevel {
    None,
    Read,
    Write,
    #[default]
    External,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct McpManifestOperation {
    pub name: String,
    #[serde(default)]
    pub description: String,
    #[serde(default)]
    pub risk: RiskLevel,
    #[serde(default)]
    pub side_effect: SideEffectLevel,
    #[serde(default)]
    pub enabled_by_default: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct McpServerManifest {
    pub server_id: String,
    pub name: String,
    #[serde(default)]
    pub operations: Vec<McpManifestOperation>,
    #[serde(default)]
    pub enabled_by_default: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct McpManifestValidation {
    pub ok: bool,
    #[serde(default)]
    pub errors: Vec<String>,
    #[serde(default)]
    pub warnings: Vec<String>,
    pub manifest: Option<McpServerManifest>,
}

impl McpManifestOperation {
    pub fn requires_approval(&self) -> bool {
        true
    }
}

pub fn validate_mcp_manifest(raw: &Value) -> McpManifestValidation {
    let mut errors = Vec::new();
    let mut warnings = Vec::new();
    let mut manifest = match parse_mcp_manifest(raw) {
        Ok(manifest) => manifest,
        Err(error) => {
            return McpManifestValidation {
                ok: false,
                errors: vec![error],
                warnings,
                manifest: None,
            };
        }
    };

    if manifest.server_id.is_empty() {
        errors.push("server_id is required".to_owned());
    }
    if manifest.operations.is_empty() {
        errors.push("at least one operation is required".to_owned());
    }
    if manifest.enabled_by_default {
        warnings.push(
            "MCP servers are not enabled by default; explicit user approval is required".to_owned(),
        );
        manifest.enabled_by_default = false;
    }
    for operation in &mut manifest.operations {
        if operation.enabled_by_default {
            warnings.push(format!(
                "operation {} default enablement was disabled",
                operation.name
            ));
            operation.enabled_by_default = false;
        }
    }

    McpManifestValidation {
        ok: errors.is_empty(),
        errors,
        warnings,
        manifest: Some(manifest),
    }
}

pub fn parse_mcp_manifest(raw: &Value) -> Result<McpServerManifest, String> {
    let object = raw
        .as_object()
        .ok_or_else(|| "MCP manifest must be a JSON object".to_owned())?;
    let server_id = string_field(object.get("server_id").or_else(|| object.get("id")));
    let mut name = string_field(object.get("name"));
    if name.is_empty() {
        name = server_id.clone();
    }
    let raw_operations = object
        .get("operations")
        .or_else(|| object.get("tools"))
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let mut operations = Vec::new();
    for item in raw_operations {
        let Some(operation) = parse_mcp_operation(&item)? else {
            continue;
        };
        operations.push(operation);
    }
    Ok(McpServerManifest {
        server_id,
        name,
        operations,
        enabled_by_default: bool_field(object.get("enabled_by_default")),
    })
}

fn parse_mcp_operation(raw: &Value) -> Result<Option<McpManifestOperation>, String> {
    let Some(object) = raw.as_object() else {
        return Ok(None);
    };
    let name = string_field(
        object
            .get("name")
            .or_else(|| object.get("operation"))
            .or_else(|| object.get("id")),
    );
    if name.is_empty() {
        return Ok(None);
    }
    Ok(Some(McpManifestOperation {
        name,
        description: string_field(object.get("description")),
        risk: parse_risk_level(object.get("risk").or_else(|| object.get("risk_level")))?,
        side_effect: parse_side_effect_level(object.get("side_effect"))?,
        enabled_by_default: bool_field(object.get("enabled_by_default")),
    }))
}

fn parse_risk_level(value: Option<&Value>) -> Result<RiskLevel, String> {
    match string_field(value).as_str() {
        "" | "medium" => Ok(RiskLevel::Medium),
        "low" => Ok(RiskLevel::Low),
        "high" => Ok(RiskLevel::High),
        other => Err(format!("unsupported MCP risk level '{other}'")),
    }
}

fn parse_side_effect_level(value: Option<&Value>) -> Result<SideEffectLevel, String> {
    match string_field(value).as_str() {
        "" | "external" => Ok(SideEffectLevel::External),
        "none" => Ok(SideEffectLevel::None),
        "read" => Ok(SideEffectLevel::Read),
        "write" => Ok(SideEffectLevel::Write),
        other => Err(format!("unsupported MCP side effect '{other}'")),
    }
}

fn string_field(value: Option<&Value>) -> String {
    value
        .and_then(Value::as_str)
        .map(str::trim)
        .unwrap_or_default()
        .to_owned()
}

fn bool_field(value: Option<&Value>) -> bool {
    value.and_then(Value::as_bool).unwrap_or(false)
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;

    #[test]
    fn mcp_manifest_validation_never_enables_by_default() {
        let validation = validate_mcp_manifest(&json!({
            "server_id": "github",
            "name": "GitHub",
            "enabled_by_default": true,
            "operations": [
                {
                    "name": "search_issues",
                    "risk": "low",
                    "side_effect": "read",
                    "enabled_by_default": true
                }
            ]
        }));

        assert!(validation.ok);
        let manifest = validation.manifest.unwrap();
        assert!(!manifest.enabled_by_default);
        assert!(!manifest.operations[0].enabled_by_default);
        assert!(manifest.operations[0].requires_approval());
        assert!(validation.warnings.len() >= 2);
    }

    #[test]
    fn mcp_manifest_supports_tool_aliases_and_defaults() {
        let manifest = parse_mcp_manifest(&json!({
            "id": "fs",
            "tools": [
                {"id": "read_file"}
            ]
        }))
        .unwrap();

        assert_eq!(manifest.server_id, "fs");
        assert_eq!(manifest.name, "fs");
        assert_eq!(manifest.operations[0].name, "read_file");
        assert_eq!(manifest.operations[0].risk, RiskLevel::Medium);
        assert_eq!(
            manifest.operations[0].side_effect,
            SideEffectLevel::External
        );
    }

    #[test]
    fn mcp_manifest_reports_missing_required_fields() {
        let validation = validate_mcp_manifest(&json!({"name": "Empty"}));

        assert!(!validation.ok);
        assert!(validation
            .errors
            .iter()
            .any(|error| error == "server_id is required"));
        assert!(validation
            .errors
            .iter()
            .any(|error| error == "at least one operation is required"));
    }

    #[test]
    fn mcp_manifest_rejects_unknown_risk_and_side_effect() {
        let risk = validate_mcp_manifest(&json!({
            "server_id": "x",
            "operations": [{"name": "op", "risk": "critical"}]
        }));
        let side_effect = validate_mcp_manifest(&json!({
            "server_id": "x",
            "operations": [{"name": "op", "side_effect": "network"}]
        }));

        assert!(!risk.ok);
        assert!(risk.errors[0].contains("unsupported MCP risk level"));
        assert!(!side_effect.ok);
        assert!(side_effect.errors[0].contains("unsupported MCP side effect"));
    }
}
