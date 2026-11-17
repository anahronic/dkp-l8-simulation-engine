"""HTTP and worker adapters, deliberately outside the hashed lab package."""

from dataclasses import dataclass, fields


@dataclass(frozen=True)
class Settings:
    MAX_BODY_BYTES: int = 262144
    MAX_VARIANTS: int = 8
    MAX_QUEUED: int = 50
    MAX_ATTEMPTS: int = 3
    RATE_PER_MINUTE: float = 10
    RATE_BURST: int = 5
    JOB_TIMEOUT: float = 120
    LEASE_SECONDS: float = 30
    POLL_SECONDS: float = 0.1
    RETENTION_SECONDS: float = 7 * 86400
    PURGE_EVERY: int = 100
    CORS_ORIGINS: tuple = ("https://dikenocracy.com", "https://www.dikenocracy.com")


def settings_from(value=None) -> Settings:
    if value is None:
        return Settings()
    if isinstance(value, Settings):
        return value
    names = {f.name for f in fields(Settings)}
    return Settings(**({k: v for k, v in value.items() if k in names} if isinstance(value, dict)
                       else {k: getattr(value, k) for k in names if hasattr(value, k)}))
