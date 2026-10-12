# Configuration

FORGEX features layered configuration (highest wins):
CLI args → environment → project `.forgex/config.toml` → global `~/.forgex/config.toml` → schema defaults.

Secrets are NEVER saved in configuration files. Only the name of the environment variable (e.g. `api_key_env = "FORGEX_GROQ_API_KEY"`) is stored. Real secrets live in the environment or `~/.forgex/.env` (permissions `0600`).

## Sections

### `[workflow]`
- `max_iterations = 5`: Maximum repair loops before stopping.

### `[permissions]`
- `mode = "ask"`: Policy mode (`"auto"`, `"ask"`, or `"safe"`).

### `[terminal]`
- `allowed = []`: Allowlist of commands (if non-empty, only these may run).
- `denied = []`: Additional denied commands.
- `timeout_seconds = 120`: Default timeout for command execution.
- `max_output_bytes = 1000000`: Output size cap before truncation.

### `[sandbox]`
- `enabled = false`: Whether to run commands in Docker containers.
- `network = false`: Whether sandboxed containers have network access.
- `image = "python:3.12-slim"`: Docker image to execute in.
- `cpu_limit = "2.0"`: CPU limit.
- `memory_limit = "1g"`: Memory limit.
- `read_only = true`: Read-only container rootfs with tmpfs `/tmp`.

### `[models]`
Configure model bindings per agent role:
```toml
[models.architect]
provider = "groq"
model = "llama-3.3-70b-versatile"

[models.builder]
provider = "groq"
model = "llama-3.3-70b-versatile"

[models.expert_coder]
provider = "groq"
model = "llama-3.3-70b-versatile"

[models.supervisor]
provider = "groq"
model = "llama-3.3-70b-versatile"
```

### `[fallback]`
- `enabled = true`: Whether to attempt fallback providers if primary fails.
- `providers = ["openai_compatible"]`: Ordered fallback providers.

### `[ensemble]`
- `enabled = false`: Multi-model ensemble review.
- `reviewers = 2`: Number of parallel reviewer models.
