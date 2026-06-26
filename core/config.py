"""Configuración central de Hermes Agent.

Carga variables desde config/.env usando pydantic-settings.
Singleton pattern via get_settings().
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings cargadas desde .env."""

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent.parent / "config" / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # === Identidad ===
    project_name: str = "HermesAgent"
    environment: str = "production"
    log_level: str = "INFO"
    tz: str = "America/Caracas"

    # === OpenRouter ===
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_default_model: str = "z-ai/glm-4.5"
    openrouter_fusion_models: str = (
        "z-ai/glm-4.5,"
        "anthropic/claude-sonnet-4.5,"
        "deepseek/deepseek-chat-v3.2,"
        "google/gemini-2.5-flash"
    )
    openrouter_judge_model: str = "z-ai/glm-4.5"
    openrouter_site_url: str = "https://github.com/elpelon27/EstacionH2OIA"
    openrouter_app_name: str = "HermesAgent"
    openrouter_daily_alert_usd: float = 5.0
    openrouter_daily_block_usd: float = 15.0

    # === Ollama ===
    ollama_host: str = "http://localhost:11434"
    ollama_default_model: str = "qwen2.5:7b"
    ollama_timeout: int = 30

    # === Telegram ===
    telegram_bot_token_h2o: str = ""
    telegram_bot_token_hermes: str = ""
    telegram_chat_id_lider: int = 0

    # === WAHA ===
    waha_base_url: str = "http://localhost:3000"
    waha_api_key: str = "PENDIENTE"
    waha_webhook_secret: str = "PENDIENTE"
    waha_session_id: str = "estacionh2o_main"
    whatsapp_phone: str = "584122560721"

    # === Qdrant ===
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = "PENDIENTE"
    qdrant_collection: str = "hermes_memory"

    # === Database ===
    database_url: str = "sqlite+aiosqlite:////mnt/ssd_trabajo/sqlite/hermes.db"
    database_backup_path: str = "/mnt/ssd_trabajo/backups/daily"

    # === Umbrales ===
    suspicious_payment_threshold_usd: float = 100.0
    rate_limit_client_per_min: int = 30
    rate_limit_client_per_day: int = 100
    rate_limit_ip_per_min: int = 100
    rate_limit_llm_per_agent_per_min: int = 60

    # === Operación ===
    operation_center_lat: float = 10.6447
    operation_center_lon: float = -71.6101
    operation_radius_km: int = 10
    working_hours_start: str = "08:30"
    working_hours_end: str = "17:00"

    # === Fusion ===
    fusion_min_score: float = 7.0
    fusion_timeout_sec: int = 30
    fusion_parallel: bool = True

    @property
    def fusion_models_list(self) -> list[str]:
        """Lista de modelos para Fusion Tournament."""
        return [m.strip() for m in self.openrouter_fusion_models.split(",") if m.strip()]


@lru_cache
def get_settings() -> Settings:
    """Singleton settings. Carga una sola vez."""
    return Settings()
