"""Global pytest configuration for Hermes Agent tests."""

import os

# Set dummy API keys before any module imports that need them
os.environ.setdefault("OPENROUTER_API_KEY", "test-key-dummy")
os.environ.setdefault("OPENAI_API_KEY", "test-key-dummy")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-dummy")
os.environ.setdefault("META_ACCESS_TOKEN", "test-token")
os.environ.setdefault("META_PHONE_NUMBER_ID", "123456789")
os.environ.setdefault("META_APP_SECRET", "test-secret")
os.environ.setdefault("META_VERIFY_TOKEN", "test-verify")
os.environ.setdefault("TELEGRAM_BOT_TOKEN_HERMES", "test-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN_H2O", "test-token")
os.environ.setdefault("TELEGRAM_CHAT_ID_HERMES", "1663148211")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:////tmp/test.db")

# Ensure config directory exists for settings loading (solo en servidor local, no en CI)
if not os.environ.get("CI") and not os.environ.get("GITHUB_ACTIONS"):
    os.makedirs("/mnt/ssd_trabajo/hermes-agent/config", exist_ok=True)

    # Create minimal .env if not exists
    env_path = "/mnt/ssd_trabajo/hermes-agent/config/.env"
    if not os.path.exists(env_path):
        with open(env_path, "w") as f:
            f.write("""OPENROUTER_API_KEY=test-key-dummy
OPENAI_API_KEY=test-key-dummy
META_ACCESS_TOKEN=test-token
META_PHONE_NUMBER_ID=123456789
META_APP_SECRET=test-secret
META_VERIFY_TOKEN=test-verify
TELEGRAM_BOT_TOKEN_HERMES=test-token
TELEGRAM_BOT_TOKEN_H2O=test-token
TELEGRAM_CHAT_ID_HERMES=1663148211
DATABASE_URL=sqlite+aiosqlite:////tmp/test.db
OLLAMA_HOST=http://localhost:11434
OLLAMA_DEFAULT_MODEL=qwen2.5:7b
LOG_LEVEL=DEBUG
""")
