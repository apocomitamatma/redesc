from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING

from proxyvars import lookup_proxy

if TYPE_CHECKING:
    import hikari
    from crescent import Client

    from redesc.api import YouTubeAPI
    from redesc.setup import AppConfig, YouTubeOAuth2

app_config_var: ContextVar[AppConfig] = ContextVar("app_config_var")
app_var: ContextVar[hikari.GatewayBot] = ContextVar("app_var")
client_var: ContextVar[Client] = ContextVar("client_var")
youtube_oauth2_var: ContextVar[YouTubeOAuth2] = ContextVar("youtube_oauth2_var")
youtube_api_var: ContextVar[YouTubeAPI] = ContextVar("youtube_api_var")
running_app_var: ContextVar[bool] = ContextVar("running_app_var", default=False)

running_app: bool = lookup_proxy(running_app_var, bool)
app_config: AppConfig = lookup_proxy(app_config_var)
app: hikari.GatewayBot = lookup_proxy(app_var)
client: Client = lookup_proxy(client_var)
youtube_oauth2: YouTubeOAuth2 = lookup_proxy(youtube_oauth2_var)
youtube_api: YouTubeAPI = lookup_proxy(youtube_api_var)
