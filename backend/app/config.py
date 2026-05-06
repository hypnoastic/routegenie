import json
from functools import lru_cache
from typing import Literal

from google.oauth2 import service_account
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Route Genie API"
    environment: Literal["development", "test", "production"] = "development"
    frontend_origin: str = "http://localhost:5173"
    cors_origins: str | None = None

    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    session_secret: str = Field(default="development-session-secret", alias="SESSION_SECRET")
    session_cookie_name: str = "route_genie_session"
    session_ttl_days: int = 30

    google_cloud_project: str | None = Field(default=None, alias="GOOGLE_CLOUD_PROJECT")
    google_cloud_location: str = Field(default="us-central1", alias="GOOGLE_CLOUD_LOCATION")
    google_cloud_text_location: str | None = Field(default=None, alias="GOOGLE_CLOUD_TEXT_LOCATION")
    google_cloud_live_location: str | None = Field(default=None, alias="GOOGLE_CLOUD_LIVE_LOCATION")
    google_service_account_json: str | None = Field(default=None, alias="GOOGLE_SERVICE_ACCOUNT_JSON")
    use_vertex_ai: bool = Field(default=False, alias="USE_VERTEX_AI")

    google_maps_server_api_key: str | None = Field(default=None, alias="GOOGLE_MAPS_SERVER_API_KEY")
    google_oauth_client_id: str | None = Field(default=None, alias="GOOGLE_OAUTH_CLIENT_ID")

    gemini_text_model: str = Field(default="gemini-3-flash-preview", alias="GEMINI_TEXT_MODEL")
    gemini_live_model_primary: str = Field(
        default="gemini-3.1-flash-live-preview",
        alias="GEMINI_LIVE_MODEL_PRIMARY",
    )
    gemini_live_model_fallback: str = Field(
        default="gemini-live-2.5-flash-native-audio",
        alias="GEMINI_LIVE_MODEL_FALLBACK",
    )

    port: int = Field(default=8000, alias="PORT")

    @property
    def allowed_origins(self) -> list[str]:
        raw = self.cors_origins or self.frontend_origin
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    @property
    def vertex_text_location(self) -> str:
        return self.google_cloud_text_location or "global"

    @property
    def vertex_live_location(self) -> str:
        return self.google_cloud_live_location or self.google_cloud_location or "us-central1"

    def vertex_credentials(self):
        if not self.google_service_account_json:
            return None
        info = json.loads(self.google_service_account_json)
        return service_account.Credentials.from_service_account_info(
            info,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )

    def runtime_validation_errors(self) -> list[str]:
        errors: list[str] = []
        if not self.database_url:
            errors.append("DATABASE_URL is missing")
        if self.use_vertex_ai and not self.google_cloud_project:
            errors.append("GOOGLE_CLOUD_PROJECT is missing while USE_VERTEX_AI=true")
        if self.use_vertex_ai and not self.vertex_live_location:
            errors.append("GOOGLE_CLOUD_LIVE_LOCATION is missing while USE_VERTEX_AI=true")
        if self.use_vertex_ai and not self.vertex_text_location:
            errors.append("GOOGLE_CLOUD_TEXT_LOCATION is missing while USE_VERTEX_AI=true")
        if not self.google_maps_server_api_key:
            errors.append("GOOGLE_MAPS_SERVER_API_KEY is missing")
        return errors


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
