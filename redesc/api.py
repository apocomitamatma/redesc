from __future__ import annotations
import logging

from typing import Any, cast

import googleapiclient.discovery
import googleapiclient.errors

from redesc.common import youtube_oauth2

_LOGGER = logging.getLogger("redesc.api")
DEFAULT_LIMIT: int = 1000000


class YouTubeAPI:
    def __init__(
        self,
        *,
        api_key: str,
    ) -> None:
        self.api_key = api_key

    @property
    def client(self) -> googleapiclient.discovery.Resource:
        return googleapiclient.discovery.build(
            "youtube",
            "v3",
            developerKey=self.api_key,
            credentials=youtube_oauth2.get_credentials(),
        )

    def get_playlist_items(
        self,
        playlist_id: str,
        *,
        limit: int = 10,
        empty_on_404: bool = True,
    ) -> list[dict[str, Any]]:
        current_page = None
        items = []
        pages_to_fetch, last_page_limit = divmod(limit, 50)
        for page_idx in range(pages_to_fetch + 1):
            request = self.client.playlistItems().list(
                part="snippet",
                maxResults=limit,
                playlistId=playlist_id,
                pageToken=current_page,
            )
            try:
                resp = request.execute()
            except googleapiclient.errors.HttpError as exc:
                if exc.resp.status == 404:
                    if empty_on_404:
                        break
                    raise LookupError(
                        f"Playlist {playlist_id=} not found"
                    ) from exc
                raise
            page_items = resp.get("items", [])
            if page_idx == pages_to_fetch:
                page_items = page_items[:last_page_limit]
            items.extend(page_items)
            if len(items) >= limit:
                break
            current_page = resp.get("nextPageToken")
            if not current_page:
                break
        return items

    def update_video_description(
        self,
        video_id: str,
        description: str,
        video_title: str | None = None,
        video_category_id: str | None = None,
    ) -> dict[str, Any]:
        _LOGGER.info(
            "Updating video %s title to %r and description to %r...",
            video_id,
            video_title,
            description,
        )
        if video_title is None or video_category_id is None:
            data = self.client.videos().list(
                part="snippet",
                id=video_id,
            ).execute()
            item = data["items"][0]
            if video_title is None:
                video_title = item["snippet"]["title"]
            if video_category_id is None:
                video_category_id = item["snippet"]["categoryId"]

        request = self.client.videos().update(
            part="snippet",
            body={
                "id": video_id,
                "snippet": {
                    "title": video_title,
                    "categoryId": video_category_id,
                    "description": description,
                },
            },
        )
        return cast(dict[str, Any], request.execute())
