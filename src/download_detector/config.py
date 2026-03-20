from pathlib import Path
from typing import Any
import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class ProviderConfig(BaseModel):
    enabled: bool = True
    service_filter: list[str] = []


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DD_", env_nested_delimiter="__")

    polling_interval_seconds: int = 60
    ui: str = "web"  # "web" or "terminal"
    web_port: int = 5000
    azure: ProviderConfig = ProviderConfig()
    gcp: ProviderConfig = ProviderConfig()
    oci: ProviderConfig = ProviderConfig()
    cloudflare: ProviderConfig = ProviderConfig()

    @classmethod
    def from_yaml(cls, path: Path | None = None) -> "AppConfig":
        if path is None:
            # Look for config relative to project root
            candidates = [
                Path("config/services.yaml"),
                Path(__file__).parent.parent.parent / "config" / "services.yaml",
            ]
            path = next((p for p in candidates if p.exists()), None)

        data: dict[str, Any] = {}
        if path and path.exists():
            with open(path) as f:
                data = yaml.safe_load(f) or {}

        # Normalize provider sections
        for provider in ("azure", "gcp", "oci", "cloudflare"):
            if provider in data and isinstance(data[provider], dict):
                pass  # pydantic handles nested model parsing

        return cls(**data)
