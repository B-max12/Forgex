# Providers

FORGEX is provider-independent (spec section 2.2). Agents talk to the `ModelRouter`; the router resolves your configuration into provider adapters. No agent code contains provider-specific logic.

## Built-in Adapters

| Type | Target | Notes |
|---|---|---|
| `groq` | Groq API | OpenAI-compatible; default `base_url` + `FORGEX_GROQ_API_KEY` |
| `openai_compatible` | OpenAI & any compatible endpoint | requires `base_url` |
| `local` | Ollama, llama.cpp, vLLM, LM Studio | requires `base_url`; no auth by default |

## Configuration Example

```toml
[providers.groq]
type = "groq"
default_model = "llama-3.3-70b-versatile"
api_key_env = "FORGEX_GROQ_API_KEY"

[providers.ollama]
type = "local"
base_url = "http://localhost:11434/v1"
default_model = "llama3.1:8b"

[models.architect]
provider = "groq"
model = "llama-3.3-70b-versatile"
```

Resolution per agent: `models.<agent>.model` → provider's `default_model` → configuration error. Nothing is guessed.

## Secrets

- Config files store only the name of the environment variable.
- Keys are read from the environment or `~/.forgex/.env`.
- `forgex config setup` writes keys to `~/.forgex/.env` (`chmod 0600`).
- Provider error text is scrubbed through a redactor before surfacing.

## Fallback

```toml
[fallback]
enabled = true
providers = ["openai_compatible"]
```
After a provider exhausts retries (rate limits, 5xx, timeouts), the router tries the next fallback provider using its `default_model`.
