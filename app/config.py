from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # GitHub App
    github_app_id: str = Field(default="", description="Numeric ID of the GitHub App.")
    github_app_webhook_secret: str = Field(
        default="",
        description="Webhook secret used to verify incoming GitHub webhook signatures.",
    )
    github_app_private_key_path: Path = Field(
        default=Path("./private-key.pem"),
        description="Path to the GitHub App's PEM private key.",
    )
    github_app_private_key_pem: str = Field(
        default="",
        description=(
            "Optional inline PEM contents. If set, the contents are written to "
            "github_app_private_key_path on startup. Useful for hosts where "
            "shipping a file is awkward (Railway, Fly, etc.)."
        ),
    )

    # LLM provider
    groq_api_key: str = Field(default="", description="Groq API key for LLM calls.")
    groq_model: str = Field(
        default="llama-3.3-70b-versatile",
        description="Default Groq model ID.",
    )

    # Review behavior
    review_style_notes: str = Field(
        default="",
        description=(
            "Extra instructions appended to the reviewer system prompt. "
            "Use this to nudge tone (e.g. 'be especially blunt about security') "
            "or to focus reviews on specific concerns."
        ),
    )

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"

    # Database
    database_url: str = "sqlite+aiosqlite:///./prsage.db"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached singleton accessor. Re-import to pick up changes during tests."""
    return Settings()
