from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration and environment settings."""

    # Project metadata
    project_name: str = "AI Team Alignment Platform"
    version: str = "0.1.0"
    api_prefix: str = "/api"
    app_env: str = Field(default="development", alias="APP_ENV")
    debug: bool = Field(default=True, alias="DEBUG")

    # Google Gemini & Google ADK Settings
    gemini_api_key: Optional[str] = Field(default=None, alias="GEMINI_API_KEY")
    google_api_key: Optional[str] = Field(default=None, alias="GOOGLE_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")
    agent_temperature: float = Field(default=0.2, alias="AGENT_TEMPERATURE")
    max_retries: int = Field(default=3, alias="MAX_RETRIES")

    # Supabase Settings (for persistent database storage in Phase 3)
    supabase_url: Optional[str] = Field(default=None, alias="SUPABASE_URL")
    supabase_key: Optional[str] = Field(default=None, alias="SUPABASE_KEY")
    supabase_service_role_key: Optional[str] = Field(default=None, alias="SUPABASE_SERVICE_ROLE_KEY")

    # CORS Settings (configured for eventual frontend integration)
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173", "*"],
        alias="CORS_ORIGINS",
    )

    # Security & Project Authorization
    api_secret_key: str = Field(default="dev-insecure-secret-key-change-in-prod", alias="API_SECRET_KEY")

    # Mock mode option for deterministic testing / offline development
    mock_llm: bool = Field(default=False, alias="MOCK_LLM")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def active_api_key(self) -> Optional[str]:
        """Returns the active Gemini / Google API key if configured."""
        return self.gemini_api_key or self.google_api_key


settings = Settings()
