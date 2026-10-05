"""Settings of the API and of the dispatcher, read from environment variables"""

from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Class that holds every setting of the API and of the dispatcher"""

    model_config = SettingsConfigDict(populate_by_name=True, extra="ignore")

    database_url: str = Field(validation_alias="DATABASE_URL")
    github_token: SecretStr | None = Field(default=None, validation_alias="GITHUB_TOKEN")
    jobs_dir: Path = Field(default=Path("/var/lib/mcplain/jobs"), validation_alias="MCPLAIN_JOBS_DIR")
    atelier_image: str = Field(default="mcplain-atelier:dev", validation_alias="MCPLAIN_ATELIER_IMAGE")
    atelier_timeout: int = Field(default=120, gt=0, validation_alias="MCPLAIN_ATELIER_TIMEOUT")
    max_parallel: int = Field(default=2, ge=1, validation_alias="MCPLAIN_MAX_PARALLEL")
    max_queued: int = Field(default=100, ge=1, validation_alias="MCPLAIN_MAX_QUEUED")
    cors_origins: str = Field(default="http://localhost:3000", validation_alias="MCPLAIN_CORS_ORIGINS")

    @field_validator("jobs_dir")
    @classmethod
    def jobs_dir_is_absolute(cls, value: Path) -> Path:
        """Refuse a relative jobs folder: the same absolute path must exist on the host and in the dispatcher"""

        if not value.is_absolute():
            raise ValueError("MCPLAIN_JOBS_DIR must be an absolute path")
        return value

    def cors_origin_list(self) -> list[str]:
        """Return the allowed CORS origins, given as a comma separated list"""

        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
