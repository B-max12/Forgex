# FORGEX Quickstart Guide

Plan. Build. Refine. Verify.

FORGEX is an interactive, multi-agent AI software engineering runtime for your terminal.

---

## 1. Quick Installation (Zero-Activation)

Like other modern developer CLIs, you don't need to manage or activate virtual environments:

### Option A: One-Line Automated Installer (Recommended)
```bash
curl -sSL https://raw.githubusercontent.com/B-max12/Forgex/main/install.sh | bash
```
*(Or if you cloned this repository locally, just run `./install.sh`)*

### Option B: Using `pipx` or `uv tool`
```bash
pipx install "git+https://github.com/B-max12/Forgex.git"
# or
uv tool install "git+https://github.com/B-max12/Forgex.git"
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

## 4. Universal Autonomous Pipeline (Zero Learning Curve)

You don't need to know separate commands. Just describe your goal, and FORGEX executes the complete software engineering pipeline:

```text
forgex ❯ Build a REST API for managing books with FastAPI and SQLite
```

Behind the scenes, FORGEX automatically executes:
1. **Auto-Initialize**: Sets up `.forgex/` workspace and git tracking if needed
2. **Architect Planning**: Researches dependencies and breaks request into ordered tasks
3. **Builder & Expert Coder Loop**: Implements files and reviews each task
4. **Deterministic Verification**: Executes tests, linter, and build checks
5. **Supervisor Quality Gates**: Audits full codebase against criteria
6. **Self-Healing Auto-Repair**: Fixes test failures automatically (up to max iterations)
7. **Git Checkpoint**: Creates a reversible commit snapshot on success!

Follow up naturally using conversational context:
```text
forgex ❯ now add rate limiting to those endpoints
forgex ❯ fix the failing tests in users.py
```

---

## 5. One-Shot CLI / CI/CD Execution

You can run any autonomous task directly from bash or CI/CD without entering the interactive REPL:

```bash
# Direct autonomous run (auto-init → plan → build → verify → checkpoint)
forgex "Add JWT authentication endpoints and tests"

# Or explicitly:
forgex do "Add JWT authentication endpoints and tests"
```

---

## 6. Granular Power User Commands (Optional)

If you ever want granular control over individual stages, all specialized commands remain available:

```bash
# 1. Plan a feature only (Architect)
forgex plan "Add caching layer"

# 2. Execute existing plan tasks (Builder)
forgex build

# 3. Deterministic verification only (Tests/Lint)
forgex verify

# 4. Auto-repair without replanning
forgex fix

# 5. Inspect checkpoints and rollback
forgex status
forgex diff
forgex checkpoint "Stable release"
forgex rollback
```
