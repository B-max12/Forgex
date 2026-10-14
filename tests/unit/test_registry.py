from forgex.models.capabilities import ModelCapabilities
from forgex.models.registry import ModelRegistry


def test_known_model_capabilities():
    caps = ModelRegistry().lookup("llama-3.3-70b-versatile")
    assert caps.known and caps.context_window == 131072 and caps.supports_tools


def test_unknown_model_gets_conservative_defaults():
    caps = ModelRegistry().lookup("mystery-model")
    assert not caps.known and not caps.supports_tools and not caps.supports_json
    assert caps.context_window is None and not caps.supports_streaming


def test_user_override_is_authoritative():
    reg = ModelRegistry({"my-model": ModelCapabilities(
        model="my-model", context_window=8192, supports_tools=True)})
    caps = reg.lookup("my-model")
    assert caps.known and caps.context_window == 8192 and caps.supports_tools


def test_catalog_lists_known_models():
    assert any(c.model == "llama-3.3-70b-versatile" for c in ModelRegistry().catalog())


def test_provider_prefix_lookup():
    reg = ModelRegistry()
    caps = reg.lookup("openrouter:meta-llama/llama-3.3-70b-instruct")
    assert caps.known and caps.supports_json

