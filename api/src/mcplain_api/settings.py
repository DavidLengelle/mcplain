"""Settings of the API and of the dispatcher, read from environment variables"""

from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DISPATCHER_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$"
DAILY_FUSE_SHARE_OF_BUDGET = 20
MAX_PROXY_HOPS = 5
DEFAULT_ALTCHA_COST = 2000
MAX_ALTCHA_COST = 1_000_000


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
    dispatcher_id: str = Field(default="main", pattern=DISPATCHER_ID_PATTERN, validation_alias="MCPLAIN_DISPATCHER_ID")
    anthropic_api_key: SecretStr | None = Field(default=None, validation_alias="MCPLAIN_ANTHROPIC_API_KEY")
    ai_model: str = Field(default="claude-sonnet-5-5", validation_alias="MCPLAIN_AI_MODEL")
    ai_effort: str = Field(default="low", validation_alias="MCPLAIN_AI_EFFORT")
    # between_tools only exists on Claude Sonnet 5.5: change this value if you change the model.
    ai_thinking: str = Field(default="between_tools", validation_alias="MCPLAIN_AI_THINKING")
    ai_max_tokens: int = Field(default=3500, gt=0, validation_alias="MCPLAIN_AI_MAX_TOKENS")
    ai_translation_max_tokens: int = Field(default=6000, gt=0, validation_alias="MCPLAIN_AI_TRANSLATION_MAX_TOKENS")
    ai_api_version: str = Field(default="2026-10-21", validation_alias="MCPLAIN_AI_API_VERSION")
    ai_timeout_s: float = Field(default=60, gt=0, validation_alias="MCPLAIN_AI_TIMEOUT_S")
    ai_price_input_per_mtok: float = Field(default=2, ge=0, validation_alias="MCPLAIN_AI_PRICE_INPUT_PER_MTOK")
    ai_price_output_per_mtok: float = Field(default=10, ge=0, validation_alias="MCPLAIN_AI_PRICE_OUTPUT_PER_MTOK")
    ai_monthly_budget_usd: float = Field(default=10, ge=0, validation_alias="MCPLAIN_AI_MONTHLY_BUDGET_USD")
    ai_daily_fuse_usd: float | None = Field(default=None, ge=0, validation_alias="MCPLAIN_AI_DAILY_FUSE_USD")
    trusted_proxy_hops: int = Field(default=1, ge=0, le=MAX_PROXY_HOPS, validation_alias="MCPLAIN_TRUSTED_PROXY_HOPS")
    altcha_hmac_key: SecretStr | None = Field(default=None, validation_alias="MCPLAIN_ALTCHA_HMAC_KEY")
    altcha_cost: int = Field(default=DEFAULT_ALTCHA_COST, ge=1, le=MAX_ALTCHA_COST, validation_alias="MCPLAIN_ALTCHA_COST")
    altcha_lifetime_s: int = Field(default=300, ge=10, le=3600, validation_alias="MCPLAIN_ALTCHA_LIFETIME_S")
    signups_per_ip_per_day: int = Field(default=30, ge=1, validation_alias="MCPLAIN_SIGNUPS_PER_IP_PER_DAY")
    guichet_url: str = Field(default="http://guichet:3100", validation_alias="MCPLAIN_GUICHET_URL")
    auth_guard_peers: str = Field(default="guichet", validation_alias="MCPLAIN_AUTH_GUARD_PEERS")

    @field_validator("github_token", "anthropic_api_key", "ai_daily_fuse_usd", "altcha_hmac_key", mode="before")
    @classmethod
    def empty_value_is_none(cls, value: object) -> object:
        """Treat an empty variable, as compose passes it when unset, as no value"""

        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("jobs_dir")
    @classmethod
    def jobs_dir_is_absolute(cls, value: Path) -> Path:
        """Refuse a relative jobs folder: the same absolute path must exist on the host and in the dispatcher"""

        if not value.is_absolute():
            raise ValueError("MCPLAIN_JOBS_DIR must be an absolute path")
        return value

    def daily_fuse(self) -> float:
        """Return the daily AI budget: its own setting, or a twentieth of the monthly budget"""

        if self.ai_daily_fuse_usd is not None:
            return self.ai_daily_fuse_usd
        return self.ai_monthly_budget_usd / DAILY_FUSE_SHARE_OF_BUDGET

    def auth_guard_peer_list(self) -> list[str]:
        """Return the host names allowed to call the internal auth guard, given as a comma separated list"""

        return [name.strip() for name in self.auth_guard_peers.split(",") if name.strip()]

    def cors_origin_list(self) -> list[str]:
        """Return the allowed CORS origins, given as a comma separated list"""

        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
