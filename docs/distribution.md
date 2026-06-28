# Distribution Baseline

The Rust-first Coder track now has a testable release and installer baseline.
Publishing to npm, Homebrew, or signed artifact channels still requires external
credentials and release-time checksums.

## CLI Surface

The Rust binary is `coder-rust`. The baseline command surface includes:

- `coder-rust doctor`
- `coder-rust config validate`
- `coder-rust workflow validate`
- `coder-rust workflow preview`
- `coder-rust workflow run`
- `coder-rust runs list`
- `coder-rust runs show`
- `coder-rust server`
- `coder-rust openhands doctor`
- `coder-rust tools ...`

The command surface is covered by Rust CLI tests so these entrypoints do not
disappear accidentally.

## Release Workflow

`.github/workflows/release.yml` runs on tags matching `v*` and can also be
started manually. It builds release archives for:

- Windows x86_64: `coder-rust-x86_64-pc-windows-msvc.zip`
- macOS Apple Silicon: `coder-rust-aarch64-apple-darwin.tar.gz`
- macOS Intel: `coder-rust-x86_64-apple-darwin.tar.gz`
- Linux x86_64 GNU: `coder-rust-x86_64-unknown-linux-gnu.tar.gz`

Each archive contains:

- `coder-rust` binary, or `coder-rust.exe` on Windows
- `README.md`
- `LICENSE`
- `examples/coder.yaml`

Tagged runs upload archives to the GitHub Release with the repository
`GITHUB_TOKEN`. No npm token, Homebrew tap token, or live LLM credential is
required.

## Install Scripts

PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1 -DryRun
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1 -Version latest
```

POSIX shell:

```bash
bash ./scripts/install.sh --dry-run
bash ./scripts/install.sh --version latest
```

Both scripts detect OS/architecture, construct the expected GitHub release
asset URL, and in non-dry-run mode download, extract, verify the binary exists,
install into a user-local bin directory, and print `coder-rust doctor` as the
next step.

## Package Sources

`packaging/npm` contains a thin npm `bin` wrapper. It checks for a vendored
binary or `coder-rust` on `PATH`; it does not silently download code during
install.

`packaging/homebrew/coder-rust.rb` is a Homebrew formula template. Replace the
placeholder SHA256 values after a release before publishing it to a tap.

## CI Coverage

The CI workflow includes an `installer-dry-run` job:

```text
pwsh ./scripts/install.ps1 -DryRun
bash ./scripts/install.sh --dry-run
node packaging/npm/bin/coder-rust.js --dry-run
```

These checks prove the installer scripts and wrapper are syntactically runnable
without touching the network or installing files.

## Future Enhancements

Non-blocking follow-ups:

- publish npm package
- publish Homebrew tap
- add signed Windows/macOS artifacts
- add checksum verification to installer scripts
- attach SBOM/provenance metadata to releases
