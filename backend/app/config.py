"""Configuración leída del archivo .env (nunca se escriben claves en el código)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://contabilidad:cambiar@localhost:5433/contabilidad"
    secret_key: str = "cambiar-esta-clave"
    token_horas: int = 8
    cors_origenes: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def origenes(self) -> list[str]:
        return [o.strip() for o in self.cors_origenes.split(",") if o.strip()]


settings = Settings()
