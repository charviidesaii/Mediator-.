import os
from typing import List, Literal, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration and environment settings."""

    # Project metadata
    project_name: str = "AI Team Alignment Platform"
    version: str = "0.2.0"
    api_prefix: str = "/api"
    app_env: str = Field(default="development", alias="APP_ENV")
    debug: bool = Field(default=True, alias="DEBUG")

    # Google Gemini & Google ADK Settings
    gemini_api_key: Optional[str] = Field(default=None, alias="GEMINI_API_KEY")
    google_api_key: Optional[str] = Field(default=None, alias="GOOGLE_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")
    agent_temperature: float = Field(default=0.2, alias="AGENT_TEMPERATURE")
    max_retries: int = Field(default=3, alias="MAX_RETRIES")

    # Execution Mode: Auto (Gemini if key exists, else mock), Live, or Mock
    mock_llm: bool = Field(default=False, alias="MOCK_LLM")
    use_adk_runner: bool = Field(default=True, alias="USE_ADK_RUNNER")

    # Storage Backend Configuration: "sqlite" (default persistent), "supabase", or "memory"
    storage_backend: Literal["sqlite", "supabase", "memory"] = Field(
        default="sqlite", alias="STORAGE_BACKEND"
    )
    sqlite_db_path: str = Field(default="data/mediator.db", alias="SQLITE_DB_PATH")

    # Supabase Settings (for remote Supabase PostgreSQL integration)
    supabase_url: Optional[str] = Field(default=None, alias="SUPABASE_URL")
    supabase_key: Optional[str] = Field(default=None, alias="SUPABASE_KEY")
    supabase_service_role_key: Optional[str] = Field(default=None, alias="SUPABASE_SERVICE_ROLE_KEY")

    # Authentication & Security
    auth_enabled: bool = Field(default=False, alias="AUTH_ENABLED")
    api_secret_key: str = Field(default="dev-mediator-key-123", alias="API_SECRET_KEY")

    # CORS Settings (configured for external Figma Make wireframe / frontend)
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173", "http://localhost:8000", "*"],
        alias="CORS_ORIGINS",
    )

    # Slack Bot Configuration (Socket Mode & Bot Token)
    slack_bot_token: Optional[str] = Field(default=None, alias="SLACK_BOT_TOKEN")
    slack_app_token: Optional[str] = Field(default=None, alias="SLACK_APP_TOKEN")
    slack_signing_secret: Optional[str] = Field(default=None, alias="SLACK_SIGNING_SECRET")
    slack_default_channel: str = Field(default="#general", alias="SLACK_DEFAULT_CHANNEL")
    dashboard_base_url: str = Field(default="http://localhost:8000", alias="DASHBOARD_BASE_URL")

    # n8n Automation Webhook Configuration (Triggered on human-approved commitments)
    n8n_webhook_url: Optional[str] = Field(
        default="https://dtakang.app.n8n.cloud/webhook/mediator-decision",
        alias="N8N_WEBHOOK_URL",
    )
    n8n_webhook_secret: Optional[str] = Field(default=None, alias="N8N_WEBHOOK_SECRET")

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def resolved_sqlite_db_path(self) -> str:
        """Returns absolute path to the SQLite database file, anchored to project repository root."""
        if os.path.isabs(self.sqlite_db_path):
            return self.sqlite_db_path
        # Anchor relative to repository root (parent of backend)
        app_dir = os.path.dirname(os.path.abspath(__file__))
        backend_dir = os.path.dirname(app_dir)
        repo_root = os.path.dirname(backend_dir)
        return os.path.abspath(os.path.join(repo_root, self.sqlite_db_path))

    @property
    def effective_webhook_secret(self) -> str:
        """Shared secret token for authenticating n8n webhook dispatches."""
        return self.n8n_webhook_secret or self.api_secret_key

    @property
    def active_api_key(self) -> Optional[str]:
        """Returns the active Gemini / Google API key if configured."""
        return self.gemini_api_key or self.google_api_key

    @property
    def is_live_gemini_available(self) -> bool:
        """Indicates whether real Gemini execution is available."""
        return bool(self.active_api_key) and not self.mock_llm

    @property
    def is_slack_configured(self) -> bool:
        """Indicates whether Slack Socket Mode credentials are configured."""
        return bool(self.slack_bot_token and self.slack_app_token)


settings = Settings()

# Sync active Gemini API key to os.environ for Google ADK Runner internal clients
if settings.active_api_key and not os.environ.get("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = settings.active_api_key

