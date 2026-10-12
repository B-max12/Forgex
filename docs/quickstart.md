# FORGEX Quickstart Guide

Plan. Build. Refine. Verify.

FORGEX is an interactive, multi-agent AI software engineering runtime for your terminal.

---

## 1. Quick Installation (Zero-Activation)

Like other modern developer CLIs, you don't need to manage or activate virtual environments:

### Option A: One-Line Automated Installer (Recommended)
```bash
curl -sSL https://raw.githubusercontent.com/forgex-dev/forgex/main/install.sh | bash
```
*(Or if you cloned this repository locally, just run `./install.sh`)*

### Option B: Using `pipx` or `uv tool`
```bash
pipx install forgex
# or
uv tool install forgex
```

Both options install FORGEX into an isolated background runtime and link the `forgex` binary directly to your PATH. Once installed, **just type `forgex` anywhere**!

---

## 2. First-Run Setup

Run `forgex` in your terminal to start the interactive session:

```bash
forgex
```

On first launch, FORGEX detects that no global configuration exists and guides you through the setup wizard:
- **Terms & Security**: Understand execution boundaries, permission modes, and local workspace safety.
- **Provider Setup**: Choose Groq, OpenAI-compatible, Local (Ollama/vLLM), or Custom.
- **API Key & Health Check**: Enter your key; FORGEX performs a live connectivity test.
- **Model Assignment**: Assign models for Architect, Builder, Expert Coder, and Supervisor.
- **Sandbox & Permissions**: Configure Docker sandbox and approval mode (`ask`, `auto`, or `safe`).

You can also re-run the setup wizard anytime:
```bash
forgex config setup
```

---

## 3. Interactive REPL Mode

When you run `forgex`, you enter the persistent REPL:

```text
███████╗ ██████╗ ██████╗  ██████╗ ███████╗██╗  ██╗
██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝╚██╗██╔╝
█████╗  ██║   ██║██████╔╝██║  ███╗█████╗   ╚███╔╝ 
██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝   ██╔██╗ 
██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗██╔╝ ██╗
╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝
Persistent Adaptive Multi-Model Software Engineering CLI
Plan. Build. Refine. Verify. (v0.1.0)

forgex [my-project] ❯
```

### In-REPL Features
- **Prompt Coloring**: Dynamically indicates your active project and readiness.
- **Auto-completion**: Tab-completion for all subcommands and slash-commands.
- **Directory Navigation**: Use `cd <path>` to switch directories and auto-attach to projects without leaving the shell.
- **Interrupt Safety**: `Ctrl+C` cancels active jobs without exiting the shell. `Ctrl+D` exits cleanly.

---

## 4. Natural Language Commands

In the REPL, you can issue commands in plain English:

- `build me a REST API for managing books with FastAPI and SQLite`
  - Routes automatically to: `plan "a REST API for managing books..."` → `build`
- `fix the failing tests`
  - Runs deterministic verification + supervisor audit + targeted repair loop.
- `review recent changes`
  - Runs Expert Coder review on uncommitted diffs.
- `show status`
  - Displays project state, task completion, git dirty status, and token costs.

---

## 5. Direct CLI Workflow

You can also use FORGEX in one-shot scripts or CI/CD pipelines:

```bash
# 1. Initialize project
forgex init

# 2. Plan a feature
forgex plan "Add JWT authentication endpoints and tests"

# 3. Build & self-heal
forgex build

# 4. Deterministic verification
forgex verify

# 5. Check Git checkpoints and diff
forgex diff
forgex checkpoint "Auth feature complete"
```
