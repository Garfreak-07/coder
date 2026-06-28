#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const args = process.argv.slice(2);
const exe = process.platform === "win32" ? "coder-rust.exe" : "coder-rust";
const packageRoot = path.resolve(__dirname, "..");
const localBinary = path.join(packageRoot, "vendor", exe);

if (args.includes("--dry-run")) {
  console.log(`coder-rust npm wrapper`);
  console.log(`Local binary: ${localBinary}`);
  console.log(`PATH fallback: ${exe}`);
  process.exit(0);
}

function commandExists(command) {
  const checker = process.platform === "win32" ? "where.exe" : "command";
  const checkerArgs = process.platform === "win32" ? [command] : ["-v", command];
  return spawnSync(checker, checkerArgs, { stdio: "ignore", shell: process.platform !== "win32" }).status === 0;
}

const binary = fs.existsSync(localBinary) ? localBinary : commandExists(exe) ? exe : null;

if (!binary) {
  console.error("coder-rust binary was not found.");
  console.error("Install it from a GitHub release with scripts/install.sh or scripts/install.ps1,");
  console.error("or place the binary at packaging/npm/vendor/" + exe + ".");
  process.exit(1);
}

const result = spawnSync(binary, args, { stdio: "inherit" });
if (result.error) {
  console.error(result.error.message);
  process.exit(1);
}
process.exit(result.status === null ? 1 : result.status);
