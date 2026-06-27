use std::path::PathBuf;

use clap::{Parser, Subcommand};
use coder_config::{load_project_config, validate_project_config};
use coder_openhands::{OpenHandsClient, OpenHandsServerConfig};
use coder_store::RunStore;
use coder_workflow::MockWorkflowRunner;

#[derive(Debug, Parser)]
#[command(name = "coder-rust")]
#[command(about = "Rust-first Coder control-plane skeleton")]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    Doctor,
    Config {
        #[command(subcommand)]
        command: ConfigCommand,
    },
    Workflow {
        #[command(subcommand)]
        command: WorkflowCommand,
    },
    Openhands {
        #[command(subcommand)]
        command: OpenHandsCommand,
    },
}

#[derive(Debug, Subcommand)]
enum ConfigCommand {
    Validate {
        #[arg(long, default_value = "examples/coder.yaml")]
        path: PathBuf,
    },
}

#[derive(Debug, Subcommand)]
enum WorkflowCommand {
    Validate {
        #[arg(long, default_value = "examples/coder.yaml")]
        config: PathBuf,
    },
    Run {
        #[arg(long)]
        mock: bool,
        #[arg(long, default_value = "examples/coder.yaml")]
        config: PathBuf,
        #[arg(long, default_value = ".coder-rust")]
        store: PathBuf,
        workflow_id: String,
        task: String,
    },
}

#[derive(Debug, Subcommand)]
enum OpenHandsCommand {
    Doctor {
        #[arg(long)]
        server: String,
        #[arg(long)]
        session_api_key_env: Option<String>,
    },
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();
    match cli.command {
        Command::Doctor => {
            println!("coder-rust: ok");
            println!("control_plane: rust skeleton");
        }
        Command::Config {
            command: ConfigCommand::Validate { path },
        } => {
            let config = load_project_config(&path)?;
            let report = validate_project_config(&config);
            println!("{}", serde_json::to_string_pretty(&report)?);
            if !report.is_pass() {
                std::process::exit(1);
            }
        }
        Command::Workflow {
            command: WorkflowCommand::Validate { config },
        } => {
            let config = load_project_config(&config)?;
            let report = validate_project_config(&config);
            println!("{}", serde_json::to_string_pretty(&report)?);
            if !report.is_pass() {
                std::process::exit(1);
            }
        }
        Command::Workflow {
            command:
                WorkflowCommand::Run {
                    mock,
                    config,
                    store,
                    workflow_id,
                    task,
                },
        } => {
            if !mock {
                anyhow::bail!("only --mock workflow runs are implemented in this skeleton");
            }
            let config = load_project_config(&config)?;
            let runner = MockWorkflowRunner::new(&config, RunStore::new(store));
            let output = runner.run(&workflow_id, &task)?;
            println!("run_id={}", output.run_id);
            println!("report_ref={}", output.report_ref);
            println!("summary={}", output.report.summary);
        }
        Command::Openhands {
            command:
                OpenHandsCommand::Doctor {
                    server,
                    session_api_key_env,
                },
        } => {
            let client = OpenHandsClient::new(OpenHandsServerConfig {
                server_url: server,
                session_api_key_env,
            });
            let health = client.health().await?;
            println!("{}", serde_json::to_string_pretty(&health)?);
            if !health.available {
                std::process::exit(1);
            }
        }
    }
    Ok(())
}
