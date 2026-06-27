use serde::{Deserialize, Serialize};
use serde_json::Value;
use thiserror::Error;

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ExtensionType {
    #[default]
    Plugin,
    HarnessRuntime,
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ExtensionRiskLevel {
    #[default]
    Low,
    Medium,
    High,
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ExtensionTrustLevel {
    Official,
    Verified,
    Community,
    #[default]
    Local,
    Untrusted,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PluginManifest {
    pub id: String,
    pub name: String,
    #[serde(default = "default_version")]
    pub version: String,
    #[serde(default)]
    pub description: String,
    #[serde(default)]
    pub extension_type: ExtensionType,
    #[serde(default = "default_true")]
    pub installed: bool,
    #[serde(default = "default_true")]
    pub enabled: bool,
    #[serde(default)]
    pub risk_level: ExtensionRiskLevel,
    #[serde(default)]
    pub trust_level: ExtensionTrustLevel,
    #[serde(default)]
    pub tags: Vec<String>,
    #[serde(default)]
    pub operations: Vec<String>,
    #[serde(default)]
    pub external_effect: bool,
    #[serde(default)]
    pub requires_preview: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PluginManifestValidation {
    pub ok: bool,
    #[serde(default)]
    pub errors: Vec<String>,
    #[serde(default)]
    pub warnings: Vec<String>,
    pub manifest: Option<PluginManifest>,
}

#[derive(Debug, Error)]
pub enum ExtensionError {
    #[error("plugin manifest must be a JSON object")]
    NotObject,
    #[error("unsupported extension_type '{0}'")]
    UnsupportedExtensionType(String),
    #[error("unsupported risk_level '{0}'")]
    UnsupportedRiskLevel(String),
    #[error("unsupported trust_level '{0}'")]
    UnsupportedTrustLevel(String),
}

pub fn validate_plugin_manifest(raw: &Value) -> PluginManifestValidation {
    let mut errors = Vec::new();
    let mut warnings = Vec::new();
    let manifest = match parse_plugin_manifest(raw) {
        Ok(manifest) => manifest,
        Err(error) => {
            return PluginManifestValidation {
                ok: false,
                errors: vec![error.to_string()],
                warnings,
                manifest: None,
            };
        }
    };

    if manifest.id.is_empty() {
        errors.push("id is required".to_owned());
    }
    if manifest.name.is_empty() {
        errors.push("name is required".to_owned());
    }
    if manifest.operations.is_empty() {
        errors.push("at least one operation is required".to_owned());
    }
    if manifest.external_effect && !manifest.requires_preview {
        errors.push("external_effect plugins must require preview".to_owned());
    }
    if manifest.external_effect && manifest.risk_level == ExtensionRiskLevel::Low {
        warnings.push("external_effect plugin is declared low risk".to_owned());
    }

    PluginManifestValidation {
        ok: errors.is_empty(),
        errors,
        warnings,
        manifest: Some(manifest),
    }
}

pub fn parse_plugin_manifest(raw: &Value) -> Result<PluginManifest, ExtensionError> {
    let object = raw.as_object().ok_or(ExtensionError::NotObject)?;
    let id = string_field(object.get("id"));
    let name = string_field(object.get("name"));
    Ok(PluginManifest {
        id,
        name,
        version: string_field(object.get("version")).or_else(default_version),
        description: string_field(object.get("description")),
        extension_type: parse_extension_type(object.get("extension_type"))?,
        installed: bool_field(object.get("installed"), true),
        enabled: bool_field(object.get("enabled"), true),
        risk_level: parse_risk_level(object.get("risk_level"))?,
        trust_level: parse_trust_level(object.get("trust_level"))?,
        tags: string_list_field(object.get("tags")),
        operations: string_list_field(object.get("operations")),
        external_effect: bool_field(object.get("external_effect"), false),
        requires_preview: bool_field(object.get("requires_preview"), false),
    })
}

pub fn builtin_plugin_manifests() -> Vec<PluginManifest> {
    vec![
        PluginManifest {
            id: "command-runner".to_owned(),
            name: "Command Runner".to_owned(),
            description: "Runs approved local commands through CommandService.".to_owned(),
            operations: vec!["run_check".to_owned(), "sandbox_check".to_owned()],
            external_effect: true,
            requires_preview: true,
            tags: vec!["coding".to_owned(), "checks".to_owned()],
            ..PluginManifest::builtin_default()
        },
        PluginManifest {
            id: "filesystem-patch".to_owned(),
            name: "File Patch Service".to_owned(),
            description:
                "Creates patch previews, applies authorized patches, and rolls back snapshots."
                    .to_owned(),
            operations: vec![
                "patch_preview".to_owned(),
                "apply_patch".to_owned(),
                "rollback_patch".to_owned(),
            ],
            external_effect: true,
            requires_preview: true,
            tags: vec!["coding".to_owned(), "files".to_owned()],
            ..PluginManifest::builtin_default()
        },
        PluginManifest {
            id: "openhands-task-executor-runtime".to_owned(),
            name: "OpenHands Task Executor Runtime".to_owned(),
            description: "Harness runtime provider for coding work items.".to_owned(),
            extension_type: ExtensionType::HarnessRuntime,
            operations: vec!["harness_runtime.run_task_execution".to_owned()],
            tags: vec![
                "harness_runtime".to_owned(),
                "executor".to_owned(),
                "coding".to_owned(),
            ],
            ..PluginManifest::builtin_default()
        },
    ]
}

impl PluginManifest {
    fn builtin_default() -> Self {
        Self {
            id: String::new(),
            name: String::new(),
            version: default_version(),
            description: String::new(),
            extension_type: ExtensionType::Plugin,
            installed: true,
            enabled: true,
            risk_level: ExtensionRiskLevel::Low,
            trust_level: ExtensionTrustLevel::Local,
            tags: Vec::new(),
            operations: Vec::new(),
            external_effect: false,
            requires_preview: false,
        }
    }
}

fn parse_extension_type(value: Option<&Value>) -> Result<ExtensionType, ExtensionError> {
    match string_field(value).as_str() {
        "" | "plugin" => Ok(ExtensionType::Plugin),
        "harness_runtime" => Ok(ExtensionType::HarnessRuntime),
        other => Err(ExtensionError::UnsupportedExtensionType(other.to_owned())),
    }
}

fn parse_risk_level(value: Option<&Value>) -> Result<ExtensionRiskLevel, ExtensionError> {
    match string_field(value).as_str() {
        "" | "low" => Ok(ExtensionRiskLevel::Low),
        "medium" => Ok(ExtensionRiskLevel::Medium),
        "high" => Ok(ExtensionRiskLevel::High),
        other => Err(ExtensionError::UnsupportedRiskLevel(other.to_owned())),
    }
}

fn parse_trust_level(value: Option<&Value>) -> Result<ExtensionTrustLevel, ExtensionError> {
    match string_field(value).as_str() {
        "" | "local" => Ok(ExtensionTrustLevel::Local),
        "official" => Ok(ExtensionTrustLevel::Official),
        "verified" => Ok(ExtensionTrustLevel::Verified),
        "community" => Ok(ExtensionTrustLevel::Community),
        "untrusted" => Ok(ExtensionTrustLevel::Untrusted),
        other => Err(ExtensionError::UnsupportedTrustLevel(other.to_owned())),
    }
}

fn string_field(value: Option<&Value>) -> String {
    value
        .and_then(Value::as_str)
        .map(str::trim)
        .unwrap_or_default()
        .to_owned()
}

fn string_list_field(value: Option<&Value>) -> Vec<String> {
    value
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(Value::as_str)
                .map(str::trim)
                .filter(|item| !item.is_empty())
                .map(str::to_owned)
                .collect()
        })
        .unwrap_or_default()
}

fn bool_field(value: Option<&Value>, default: bool) -> bool {
    value.and_then(Value::as_bool).unwrap_or(default)
}

fn default_version() -> String {
    "builtin".to_owned()
}

trait StringExt {
    fn or_else(self, fallback: impl FnOnce() -> String) -> String;
}

impl StringExt for String {
    fn or_else(self, fallback: impl FnOnce() -> String) -> String {
        if self.is_empty() {
            fallback()
        } else {
            self
        }
    }
}

fn default_true() -> bool {
    true
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;

    #[test]
    fn valid_plugin_manifest_accepts_builtin_shape() {
        let validation = validate_plugin_manifest(&json!({
            "id": "filesystem-patch",
            "name": "File Patch Service",
            "operations": ["patch_preview", "apply_patch"],
            "external_effect": true,
            "requires_preview": true,
            "tags": ["coding", "files"]
        }));

        assert!(validation.ok);
        let manifest = validation.manifest.unwrap();
        assert_eq!(manifest.extension_type, ExtensionType::Plugin);
        assert_eq!(manifest.version, "builtin");
        assert!(manifest.installed);
        assert!(manifest.enabled);
    }

    #[test]
    fn external_effect_plugin_requires_preview() {
        let validation = validate_plugin_manifest(&json!({
            "id": "unsafe",
            "name": "Unsafe",
            "operations": ["publish"],
            "external_effect": true,
            "requires_preview": false
        }));

        assert!(!validation.ok);
        assert!(validation
            .errors
            .iter()
            .any(|error| error == "external_effect plugins must require preview"));
    }

    #[test]
    fn invalid_manifest_rejects_unknown_extension_type() {
        let validation = validate_plugin_manifest(&json!({
            "id": "x",
            "name": "x",
            "extension_type": "skill",
            "operations": ["op"]
        }));

        assert!(!validation.ok);
        assert!(validation.errors[0].contains("unsupported extension_type"));
    }

    #[test]
    fn builtin_plugins_match_python_registry_contract() {
        let plugins = builtin_plugin_manifests();
        let ids = plugins
            .iter()
            .map(|plugin| plugin.id.as_str())
            .collect::<std::collections::BTreeSet<_>>();
        let command_runner = plugins
            .iter()
            .find(|plugin| plugin.id == "command-runner")
            .unwrap();
        let openhands_runtime = plugins
            .iter()
            .find(|plugin| plugin.id == "openhands-task-executor-runtime")
            .unwrap();

        assert!(ids.contains("command-runner"));
        assert!(ids.contains("filesystem-patch"));
        assert!(command_runner.external_effect);
        assert!(command_runner.requires_preview);
        assert_eq!(
            openhands_runtime.extension_type,
            ExtensionType::HarnessRuntime
        );
    }
}
