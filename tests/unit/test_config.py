"""Tests para core/config.py."""

from core.config import get_settings


def test_settings_loads_env():
    """Settings debe cargar desde config/.env."""
    settings = get_settings()
    assert settings.project_name == "HermesAgent"
    assert settings.environment in ("production", "staging", "development")
    assert settings.tz == "America/Caracas"


def test_openrouter_config():
    """OpenRouter debe tener API key y modelos configurados."""
    import pytest
    settings = get_settings()
    if not settings.openrouter_api_key or settings.openrouter_api_key == "test-key-dummy":
        pytest.skip("OPENROUTER_API_KEY no configurado en .env (dummy)")
    assert settings.openrouter_api_key.startswith("sk-or-v1-")
    assert "z-ai/glm-4.5" in settings.fusion_models_list
    assert len(settings.fusion_models_list) == 4


def test_ollama_config():
    """Ollama debe estar configurado para local."""
    settings = get_settings()
    assert settings.ollama_host == "http://localhost:11434"
    assert settings.ollama_default_model == "qwen2.5:7b"


def test_telegram_config():
    """Telegram debe tener tokens y chat_id."""
    import pytest
    settings = get_settings()
    if not settings.telegram_bot_token_h2o or settings.telegram_bot_token_h2o == "test-token":
        pytest.skip("TELEGRAM_BOT_TOKEN_H2O no configurado en .env (dummy)")
    assert settings.telegram_bot_token_hermes != ""
    assert settings.telegram_chat_id_lider > 0


def test_fusion_models_list():
    """fusion_models_list debe retornar 4 modelos."""
    settings = get_settings()
    models = settings.fusion_models_list
    assert isinstance(models, list)
    assert len(models) == 4
    assert "z-ai/glm-4.5" in models
    assert "anthropic/claude-sonnet-4.5" in models


def test_rate_limits():
    """Rate limits deben tener valores razonables."""
    settings = get_settings()
    assert 0 < settings.rate_limit_client_per_min <= 100
    assert 0 < settings.rate_limit_client_per_day <= 1000


def test_cost_thresholds():
    """Umbrales de costo deben ser coherentes."""
    settings = get_settings()
    assert 0 < settings.openrouter_daily_alert_usd < settings.openrouter_daily_block_usd


def test_get_settings_singleton():
    """get_settings debe retornar la misma instancia (lru_cache)."""
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
