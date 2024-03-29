from __future__ import annotations

import logging
from typing import Any, cast

import googleapiclient.discovery
import googleapiclient.errors

from redesc.common import youtube_oauth2

_LOGGER = logging.getLogger("redesc.api")
DEFAULT_LIMIT: int = 1000000


def fix_tags(tags: list[str]) -> list[str]:
    total = 0
    all_tags = []
    for tag in tags:
        total += len(tag) + (2 * (" " in tag))
        if total >= 350:
            break
        total += 1
        all_tags.append(tag)
    return all_tags


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
        item_map = {}
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
                    msg = f"Playlist {playlist_id=} not found"
                    raise LookupError(msg) from exc
                raise
            page_items = resp.get("items", [])
            if page_idx == pages_to_fetch:
                page_items = page_items[:last_page_limit]
            items.extend(page_items)
            for item in items:
                item["id"] = item["snippet"]["resourceId"]["videoId"]
                item_map[item["id"]] = item
            item_ids = ",".join(item["id"] for item in page_items)
            items_with_tags = (
                self.client.videos()
                .list(
                    part="snippet",
                    id=item_ids,
                )
                .execute()
            )
            for item_with_tags in items_with_tags["items"]:
                item_snippet = item_with_tags["snippet"]
                item_map[item_with_tags["id"]]["snippet"][
                    "tags"
                ] = item_snippet.setdefault("tags", [])

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
        tags: list[str],
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
            data = (
                self.client.videos()
                .list(
                    part="snippet",
                    id=video_id,
                )
                .execute()
            )
            item = data["items"][0]
            if video_title is None:
                video_title = item["snippet"]["title"]
            if video_category_id is None:
                video_category_id = item["snippet"]["categoryId"]

        tags[:] = fix_tags(tags)
        request = self.client.videos().update(
            part="snippet",
            body={
                "id": video_id,
                "snippet": {
                    "title": video_title,
                    "categoryId": video_category_id,
                    "description": description,
                    "tags": fix_tags(tags),
                },
            },
        )
        return cast(dict[str, Any], request.execute())
