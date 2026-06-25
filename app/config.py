"""Central settings, loaded from environment / .env.

Nothing here is a secret; secrets are read from the environment at runtime and
NEVER logged. `redact()` is provided for any place that might print a token.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root = two levels up from this file (app/config.py -> repo/).
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SOT_DIR = DATA / "sot"
SAMPLE_DIR = DATA / "sample_strings"
CACHE_DIR = DATA / "cache"
CONFIG_DIR = ROOT / "config"
DB_PATH = DATA / "loc_sentinel.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Anthropic ---
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-8"

    # --- Crowdin ---
    crowdin_api_token: str = ""
    crowdin_project_id: str = ""
    crowdin_base_url: str = ""  # blank => crowdin.com; set for Enterprise
    crowdin_webhook_secret: str = ""

    # --- Slack ---
    slack_bot_token: str = ""
    slack_app_token: str = ""
    slack_signing_secret: str = ""
    slack_loc_channel_id: str = ""          # the SUMMARY / digest channel (#localization)
    # Per-language review channels (review cards route here by target language).
    slack_channel_de: str = ""
    slack_channel_pt_br: str = ""
    slack_channel_es: str = ""
    # Platform/product label for the digest (a real org has App, Web, iOS, ...).
    platform_label: str = "App"

    # --- Webhook receiver ---
    public_base_url: str = ""
    webhook_port: int = 8000

    # --- Languages ---
    target_langs: str = "de,pt-BR,es"

    # --- Demo / playground ---
    demo_mode: bool = True
    demo_rate_limit_per_min: int = 20

    @property
    def langs(self) -> list[str]:
        return [s.strip() for s in self.target_langs.split(",") if s.strip()]

    @property
    def crowdin_api_base(self) -> str:
        base = self.crowdin_base_url.strip().rstrip("/")
        if not base:
            return "https://api.crowdin.com/api/v2"
        # Enterprise base like https://acme.api.crowdin.com -> append /api/v2
        return f"{base}/api/v2"

    def has_anthropic(self) -> bool:
        return bool(self.anthropic_api_key)

    def has_crowdin(self) -> bool:
        return bool(self.crowdin_api_token and self.crowdin_project_id)

    def has_slack(self) -> bool:
        return bool(self.slack_bot_token and self.slack_app_token)

    @property
    def summary_channel(self) -> str:
        """The digest channel (#localization) — platform-level 'what happened'."""
        return self.slack_loc_channel_id

    def channel_for(self, lang: str) -> str:
        """Review channel for a target language; falls back to the summary channel."""
        mapping = {
            "de": self.slack_channel_de,
            "pt-BR": self.slack_channel_pt_br,
            "es": self.slack_channel_es,
        }
        return mapping.get(lang) or self.slack_loc_channel_id


@lru_cache
def get_settings() -> Settings:
    return Settings()


def redact(token: str | None) -> str:
    """Safe-for-logs representation of a secret."""
    if not token:
        return "<empty>"
    if len(token) <= 8:
        return "****"
    return f"{token[:4]}…{token[-4:]}"
