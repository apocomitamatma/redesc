from __future__ import annotations

import datetime
from typing import Any, Optional

from configzen import ConfigField, ConfigMeta, ConfigModel, field_validator
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials

from redesc.api import YouTubeAPI
from redesc.common import (
    app_config,
    app_config_var,
    running_app,
    youtube_api_var,
    youtube_oauth2_var,
)

load_dotenv()


class AppConfig(ConfigModel):
    """App config model."""

    default_playlist_id: str
    youtube_api_key: str
    permitted_discord_channel_id: int
    token: str = ConfigField(exclude=True)

    class Config(ConfigMeta):
        """Config meta."""

        env_prefix = "REDESC_"
        resource = "config.yml"


class YouTubeOAuth2(ConfigModel):
    flow: dict[str, Any]
    expiry: Optional[datetime.datetime] = None  # noqa: UP007
    client_id: Optional[str] = None  # noqa: UP007
    client_secret: Optional[str] = None  # noqa: UP007
    token_uri: Optional[str] = None  # noqa: UP007
    token: Optional[str] = None  # noqa: UP007
    refresh_token: Optional[str] = None  # noqa: UP007
    scopes: list[str] = ["https://www.googleapis.com/auth/youtube.force-ssl"]  # noqa: RUF012

    def get_credentials(self) -> Credentials:
        return Credentials(
            token=self.token,
            refresh_token=self.refresh_token,
            token_uri=self.token_uri,
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=self.scopes,
        )

    @property
    def valid(self) -> bool:
        if self.expiry is None:
            return False
        return self.expiry > datetime.datetime.utcnow() and self.get_credentials().valid

    @field_validator("expiry")
    def _normalize_expiry_datetime(
        cls,  # noqa: N805
        expiry: datetime.datetime | None,
    ) -> datetime.datetime:
        if expiry is None:
            return datetime.datetime.utcnow()
        return expiry.replace(tzinfo=None)

    class Config(ConfigMeta):
        env_prefix = "GOOGLE_AUTH_"
        resource = "oauth2.json"
        extra = "allow"  # type: ignore[assignment]


if running_app:
    app_config_var.set(AppConfig.load())
    youtube_api_var.set(YouTubeAPI(api_key=app_config.youtube_api_key))

youtube_oauth2_var.set(YouTubeOAuth2.load())
