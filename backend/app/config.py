from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Repo-root .env when running from backend/ locally; real env vars win in Docker.
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    secret_key: str = "dev-insecure-secret"
    cf_api_key: str = ""
    mc_root: Path = Path("/srv/mcpanel")
    data_dir: Path = Path("data")
    # Built React app; served by FastAPI when present (production image).
    frontend_dist: Path = Path("frontend/dist")
    session_days: int = 7
    max_upload_mb: int = 2048
    # Plain http is expected (localhost / SSH tunnel); set true behind HTTPS.
    cookie_secure: bool = False

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'mcpanel.db'}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
