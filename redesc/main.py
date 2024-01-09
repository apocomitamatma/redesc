from __future__ import annotations

import asyncio
import dataclasses
import datetime
import functools
import itertools
import json
import logging
import operator
import pathlib
import re
from typing import TYPE_CHECKING, Any

import crescent
import googleapiclient.errors  # type: ignore[import-untyped]
import hikari
import miru
from google.auth.exceptions import RefreshError  # type: ignore[import-untyped]
from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore[import-untyped]
from oauthlib.oauth2.rfc6749.errors import (
    AccessDeniedError,  # type: ignore[import-untyped]
)

from redesc.api import DEFAULT_LIMIT
from redesc.common import app_config, youtube_api, youtube_oauth2

if TYPE_CHECKING:
    from collections.abc import Callable

_LOGGER = logging.getLogger(__name__)

OLD_MARKER = "-"
NEW_MARKER = "+"
SKIP_MARKER_RE = r"_?\((\d+) lini[aei] bez zmian\)_?"
DIFF_SCOPES = ("tytuł", "opis")
PLAYLIST_PATTERN: str = (
    r"(https?://)?(www\.)?((youtube\.com|youtu\.be)/(playlist|watch\?v=[^&]+))"
    r"&list=(?P<playlist_id>[^&]+)"
)

plugin: crescent.Plugin[hikari.GatewayBot, None] = crescent.Plugin()
running_oauth2_server = False


class AuthURLCapturer(str):
    __slots__ = ("callback",)

    def __init__(self, callback: Callable[[str], None]) -> None:
        self.callback = callback

    def format(self, *, url: str) -> str:  # type: ignore[override]
        if callable(self.callback):
            self.callback(url)
        return ""


async def ensure_proper_channel(ctx: crescent.Context) -> bool:
    expected_channel_id = app_config.permitted_discord_channel_id
    if ctx.channel_id != expected_channel_id:
        await ctx.respond(
            f"Ta komenda może być używana tylko na kanale <#{expected_channel_id}>.",
            ephemeral=True,
        )
        return False
    return True


@plugin.include
@crescent.command(
    name="uwierzytelnij",
    description="Uwierzytelnij konto Google do użycia YouTube API.",
    default_member_permissions=hikari.Permissions.ADMINISTRATOR,
)
async def authorize(ctx: crescent.Context) -> None:
    """Authorize the bot to use YouTube API."""
    await _authorize_impl(ctx)


@plugin.include
@crescent.catch_command(RefreshError)
async def _authorize_on_error(_: RefreshError, ctx: crescent.Context) -> None:
    _LOGGER.exception("Failed to refresh OAuth2 token")
    await ctx.respond("Wystąpił błąd. Uwierzytelnij konto i spróbuj ponownie.")
    await _authorize_impl(ctx)


async def _authorize_impl(ctx: crescent.Context) -> None:
    if not await ensure_proper_channel(ctx):
        _LOGGER.error(
            "Someone tried to run /%s on %s channel",
            ctx.command,
            ctx.channel,
        )
        return

    await ctx.defer(ephemeral=True)
    future: asyncio.Future[str] = asyncio.Future()
    tasks = set()

    def callback(url: str) -> None:
        future.set_result(url)

    @future.add_done_callback
    def url_captured(_: object) -> None:
        url = future.result()
        tasks.add(
            asyncio.create_task(
                ctx.respond(
                    "Hej Artur! Uwierzytelnij mnie proszę "
                    f"za pomocą tego linku:\n{url}",
                    ephemeral=True,
                ),
            ),
        )

    global running_oauth2_server
    if running_oauth2_server:
        return
    running_oauth2_server = True
    app_flow = InstalledAppFlow.from_client_config(
        youtube_oauth2.flow,
        scopes=youtube_oauth2.scopes,
    )
    capturer = AuthURLCapturer(callback)
    loop = asyncio.get_running_loop()
    try:
        credentials = await loop.run_in_executor(
            None,
            functools.partial(
                app_flow.run_local_server,
                authorization_prompt_message=capturer,
                open_browser=False,
                port=0,
            ),
        )
    except AccessDeniedError:
        await ctx.respond("Anulowano.")
        return
    finally:
        running_oauth2_server = False
    youtube_oauth2.update(dict(json.loads(credentials.to_json())))
    await youtube_oauth2.save_async()
    message = await ctx.respond("Uwierzytelniono!", ensure_message=True, ephemeral=True)
    await asyncio.sleep(3.5)
    await message.delete()


@dataclasses.dataclass
class VideoDiff:
    video_id: str
    old_title: str
    new_title: str
    old_description: str
    new_description: str
    tags: list[str]
    video_category_id: str | None = None


def _pronounce_lines(count: int) -> str:
    if count == 1:
        return "linia"
    mod_100 = count % 100
    if (mod_100 < 10 or mod_100 > 20) and count % 10 in (2, 3, 4):
        return "linie"
    return "linii"


def highlight_diffs(
    old_text: str,
    new_text: str,
    sep: str = "\n\n",
    old_marker: str = OLD_MARKER,
    new_marker: str = NEW_MARKER,
) -> str:
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    diff: list[str] = []
    for old_line, new_line in zip(old_lines, new_lines):
        skip = None
        if diff:
            skip = re.match(SKIP_MARKER_RE, diff[-1])
        if old_line != new_line:
            log = f"{old_marker} {old_line}\n{new_marker} {new_line}"
            diff.append(log)
        elif skip:
            skipped = int(skip.group(1)) + 1
            diff[-1] = f"({skipped} {_pronounce_lines(skipped)} bez zmian)"
        else:
            log = f"({1} linia bez zmian)"
            diff.append(log)
    return sep.join(diff)


def argument_unescape(argument: str) -> str:
    if argument.startswith('"') and argument.endswith('"'):
        return argument[1:-1]
    if argument.startswith('\\"') and argument.endswith('\\"'):
        return argument[2:-2].join('""')
    return argument


DIFFIZE_ABORT = "⚠️"


def diffize(string: str, abort_if: str = DIFFIZE_ABORT) -> str:
    if string.startswith(abort_if):
        return string
    return escape(string, "`").join(("```diff\n", "\n```"))


def escape(string: str, substring: str, *, use: str = "\\") -> str:
    return string.replace(substring, "".join(map(use.__add__, substring)))


def prepend_new_title(old_title: str, new_title: str, initial_description: str) -> str:
    if old_title == new_title:
        return initial_description
    diff = f"\n- {old_title}\n+ {new_title}"
    return f"Zmieniono tytuł: {diffize(diff)}\n{initial_description}"


@plugin.include
@crescent.command(
    name="podmien",
    description="Podmień opisu filmów na kanale YouTube.",
    default_member_permissions=hikari.Permissions.ADMINISTRATOR,
)
class SubstituteCommand:
    expression: crescent.ClassCommandOption[str] = crescent.option(
        str,
        name="wyrazenie",
        description="Wyrażenie regularne do wyszukania w opisach filmów.",
    )
    replacement: crescent.ClassCommandOption[str] = crescent.option(
        str,
        name="zamiana",
        description="Tekst, który ma zastąpić wyrażenie regularne.",
        min_length=0,
    )
    limit: crescent.ClassCommandOption[int] = crescent.option(
        int,
        name="limit",
        description=(
            "Limit filmów do podmiany. Duże limity lub częste podmiany mogą spowodować "
            "tymczasową blokadę API."
        ),
        default=100,
        min_value=10,
    )
    playlist_id: crescent.ClassCommandOption[str | None] = crescent.option(
        str,
        name="playlista",
        default=None,
        description="ID playlisty, z której mają być modfikowane filmy.",
    )
    include_titles: crescent.ClassCommandOption[bool] = crescent.option(
        bool,
        name="tytuly",
        description="Podmień tytuły filmów.",
        default=True,
    )
    include_descriptions: crescent.ClassCommandOption[bool] = crescent.option(
        bool,
        name="opisy",
        description="Podmień opisy filmów.",
        default=True,
    )

    async def callback(  # noqa: C901
        self,
        command_context: crescent.Context,
    ) -> None:
        """Show videos on the YouTube channel."""
        if not await ensure_proper_channel(command_context):
            return
        if not youtube_oauth2.valid:
            await _authorize_impl(command_context)
        else:
            await command_context.defer()

        if not (self.include_titles or self.include_descriptions):
            await command_context.respond(
                "Nie wybrano żadnych elementów do podmiany.",
                ephemeral=True,
            )
            return

        replacement = argument_unescape(self.replacement)
        expression = argument_unescape(self.expression)

        playlist_id = self.playlist_id

        if playlist_id is None:
            playlist_id = app_config.default_playlist_id
        elif match := re.match(PLAYLIST_PATTERN, playlist_id):
            playlist_id = match.group("playlist_id")
            if not playlist_id:
                await command_context.respond(
                    "Niepoprawny identyfikator playlisty.",
                    ephemeral=True,
                )
                return

        _LOGGER.info("Using playlist ID: %s", playlist_id)

        log_ts = datetime.datetime.now(tz=datetime.timezone.utc).timestamp()
        log_filename = f"log-{log_ts}.txt"
        log = pathlib.Path(log_filename)

        try:
            regex = re.compile(expression)
        except re.error as e:
            await command_context.respond(
                f"Niepoprawne wyrażenie regularne: {e}",
                ephemeral=True,
            )
            return

        diffs: list[VideoDiff] = []

        for item in youtube_api.get_playlist_items(playlist_id, limit=DEFAULT_LIMIT):
            snippet = item["snippet"]
            old_title = snippet["title"]
            old_description = snippet["description"]

            if self.include_titles:
                try:
                    new_title = regex.sub(replacement, old_title)
                except re.error as e:
                    await command_context.respond(
                        f"Niepoprawne wyrażenie zastępujące: {e}",
                        ephemeral=True,
                    )
                    return
            else:
                new_title = old_title

            if self.include_descriptions:
                try:
                    new_description = regex.sub(replacement, old_description)
                except re.error as e:
                    await command_context.respond(
                        f"Niepoprawne wyrażenie zastępujące: {e}",
                        ephemeral=True,
                    )
                    return
            else:
                new_description = old_description

            if (old_title, old_description) != (new_title, new_description):
                diffs.append(
                    VideoDiff(
                        video_id=snippet["resourceId"]["videoId"],
                        old_title=old_title,
                        new_title=new_title,
                        old_description=old_description,
                        new_description=new_description,
                        tags=snippet["tags"],
                    ),
                )

        def create_embeds() -> list[hikari.Embed]:
            diff = diffs[current_page]
            highlighted = highlight_diffs(diff.old_description, diff.new_description)
            tails = [highlighted]
            url = f"https://www.youtube.com/watch?v={diff.video_id}"

            while len(tails[-1]) > 2000:
                msg = tails[-1]
                if "\n\n" not in msg[:2000]:
                    break
                diff_break = msg[:2000].rindex("\n\n")
                tails[-1] = msg[:diff_break]
                tails.append(msg[diff_break:])
            times_repeated = 0

            while len(url) + len(diff.new_title) + sum(map(len, tails)) >= 4500:
                _LOGGER.warning("Embed too long, truncating")
                if times_repeated > 0:
                    tails.pop(-1)
                tails[-1] = (
                    f"{DIFFIZE_ABORT} "
                    "**Nie udało się wyświetlić całego opisu, ponieważ przekroczył "
                    "on limit długości.**"
                )
                times_repeated += 1

            return [
                hikari.Embed(
                    title=diff.old_title,
                    description=prepend_new_title(
                        old_title=diff.old_title,
                        new_title=diff.new_title,
                        initial_description=diffize(tails.pop(0)),
                    ),
                    color=0x0000FF,
                    url=url,
                ),
                *(
                    hikari.Embed(description=tail, color=0x0000FF)
                    for tail in map(diffize, tails)
                ),
            ]

        current_page = 0
        n_diffs = len(diffs)
        max_page = n_diffs - 1
        left_over = 0
        current_limit = min((self.limit, n_diffs))

        async def on_end(context: miru.ViewContext) -> None:
            await context.defer()
            if not diffs:
                return
            nonlocal n_diffs
            diffs.clear()
            n_diffs = 0
            await make_message()

        async def on_next_page(context: miru.ViewContext) -> None:
            await context.defer()
            if not diffs:
                return
            nonlocal current_page
            current_page += current_page + 1 <= max_page
            message = context.message
            await make_message(message=message)

        async def on_previous_page(context: miru.ViewContext) -> None:
            await context.defer()
            if not diffs:
                return
            nonlocal current_page
            current_page -= current_page - 1 >= 0
            message = context.message
            await make_message(message=message)

        async def on_submit(
            context: miru.ViewContext,
            *,
            with_title: bool = self.include_titles,
            with_description: bool = self.include_descriptions,
            reuse: bool = False,
        ) -> bool:
            if not reuse:
                await context.defer()
            nonlocal current_page, max_page, current_limit
            if not diffs:
                if reuse:
                    await context.defer()
                return True
            diff = diffs[current_page]
            try:
                youtube_api.update_video_description(
                    video_id=diff.video_id,
                    video_title=diff.new_title if with_title else diff.old_title,
                    video_category_id=diff.video_category_id,
                    description=(
                        diff.new_description
                        if with_description
                        else diff.old_description
                    ),
                    tags=diff.tags,
                )
            except googleapiclient.errors.HttpError as e:
                await command_context.respond(
                    f"Nie udało się podmienić opisu filmu: `{e}`",
                )
                return False
            diffs.pop(current_page)
            done_diffs.append(diff)
            max_page -= 1
            current_limit -= 1
            if current_page == max_page and max_page != 0:
                current_page -= 1
            if not reuse:
                message = context.message
                await make_message(message=message)
            return True

        async def on_finalize(context: miru.ViewContext) -> None:
            nonlocal left_over, n_diffs
            await context.defer()
            await context.message.delete()
            message = await command_context.respond(
                f"Podmieniam automatycznie, zostało: {current_limit}",
                ensure_message=True,
            )
            while current_limit > 0:
                await message.edit(
                    f"Podmieniam automatycznie, zostało: {current_limit}",
                )
                ok = await on_submit(context, reuse=True)
                if not ok:
                    await message.edit(
                        "Wystąpił błąd, którego szczegóły są podane powyżej.\n"
                        "Zakończono podmianę automatyczną. Spróbuj ponownie później.",
                    )
                    break
            await message.delete()
            left_over = len(diffs)
            diffs.clear()
            n_diffs = 0
            await make_message()

        async def make_message(**kwargs: Any) -> None:
            message = kwargs.pop("message", None)
            if message is not None:
                await message.delete()

            if not diffs:
                await command_context.respond(
                    "Seria podmian zakończona."
                    + (
                        f"\nLiczba filmów do podmiany następnego dnia: **{left_over}**."
                        if left_over > 0
                        else ""
                    ),
                )

                if done_diffs:
                    log.write_text(
                        "\n\n".join(
                            (
                                title := (
                                    f"{diff.old_title} -> {diff.new_title}"
                                    if diff.old_title != diff.new_title
                                    else diff.old_title
                                )
                            )
                            + "\n"
                            + f"https://www.youtube.com/watch?v={diff.video_id}"
                            + "\n"
                            + "-" * len(title)
                            + "\n"
                            + highlight_diffs(
                                new_text=diff.new_description,
                                old_text=diff.old_description,
                                sep="\n",
                            )
                            for diff in done_diffs
                        ),
                        encoding="utf-8",
                    )
                    await command_context.respond("Załączam raport:", attachment=log)
                else:
                    await command_context.respond(
                        "Nie dokonano żadnej podmiany, dlatego nie ma raportu.",
                    )
                return

            view = miru.View(timeout=None)

            previous_button = miru.Button(
                emoji="⬅️",
                custom_id="previous",
                disabled=current_page == 0,
            )
            previous_button.callback = on_previous_page
            view.add_item(previous_button)

            next_button = miru.Button(
                emoji="➡️",
                custom_id="next",
                disabled=current_page == max_page,
            )
            next_button.callback = on_next_page
            view.add_item(next_button)

            diff = diffs[current_page]

            for _, scope_selectors in filter(
                operator.itemgetter(0),
                (
                    (
                        diff.old_title != diff.new_title
                        and diff.old_description != diff.new_description,
                        (True, True),
                    ),
                    (diff.old_title != diff.new_title, (True, False)),
                    (diff.old_description != diff.new_description, (False, True)),
                ),
            ):
                scope_description = " i ".join(
                    itertools.compress(DIFF_SCOPES, scope_selectors),
                )
                with_title, with_description = scope_selectors
                submit_button = miru.Button(
                    emoji="✍️",
                    custom_id=f"submit_{with_title:d}_{with_description:d}",
                    label=f"Podmień {scope_description}",
                )
                submit_button.callback = functools.partial(  # type: ignore[assignment]
                    on_submit,
                    with_title=with_title,
                    with_description=with_description,
                )
                view.add_item(submit_button)

            end_button = miru.Button(
                emoji="⏹️",
                label="Zakończ" if done_diffs else "Anuluj",
                custom_id="end",
            )
            end_button.callback = on_end  # type: ignore[method-assign]
            view.add_item(end_button)

            if current_limit > 1:
                finalize_button = miru.Button(
                    emoji="⚙️",
                    custom_id="finalize",
                    label=f"Podmień wszystkie ({current_limit})",
                )
                finalize_button.callback = on_finalize  # type: ignore[method-assign]
                view.add_item(finalize_button)

            embeds = create_embeds()
            done = 0
            invoked_by = (
                (member := command_context.member)
                and member.mention
                or "(brak informacji)"
            )
            content = f"_Komenda wywołana przez {invoked_by}._\n"
            if done > 0:
                content += f"Podmieniono opis w {done} filmach.\n"
            if current_page > current_limit:
                content = (
                    "⚠️ _Uwaga. W tym filmie%s nie będzie podmieniany opis. "
                    "Możesz zrobić to w następnym wywołaniu komendy._\n"
                ) % (" i kolejnych" if current_page < max_page else "")
            content += (
                f"Zamiana napisów opisanych wyrażeniem `{escape(expression, '`')}` "
                f"na `{escape(replacement, '`')}`.\n"
                f"Strona `{current_page + 1}` z `{max_page + 1}`.\n"
                f"Zmiany zostaną wykonane nie dalej niż dla **{current_limit}** "
                "filmów spośród podanych.\n"
            )
            left_after = max_page + 1 - current_limit
            if left_after > 0:
                content += (
                    f"Potem zostanie {left_after} filmów do podmiany "
                    "w późniejszym terminie.\n"
                )
            response = await command_context.respond(
                content,
                embeds=embeds,
                components=view,
                **kwargs,
            )
            await view.start(response)

        done_diffs: list[VideoDiff] = []
        if diffs:
            await make_message(ensure_message=True)
        else:
            await command_context.respond("Żadne filmy nie podlegają takiej podmianie.")


@plugin.include
@crescent.command(
    name="dodajtagi",
    description="Dodaj tagi do filmów na kanale YouTube.",
    default_member_permissions=hikari.Permissions.ADMINISTRATOR,
)
class AddTags:
    playlist_id: crescent.ClassCommandOption[str | None] = crescent.option(
        str,
        name="playlista",
        default=None,
        description="ID playlisty, z której mają być modfikowane filmy.",
    )

    async def callback(  # noqa: C901
        self,
        command_context: crescent.Context,
    ) -> None:
        """
        Use the tags.json file with video IDs and tags to traverse videos
        with the provided video IDs and add tags to them. The tags are added
        via the YouTube API and they reuse data from the API that initially
        collected information about the videos from tags.json
        """
        if not await ensure_proper_channel(command_context):
            return
        if not youtube_oauth2.valid:
            await _authorize_impl(command_context)
        else:
            await command_context.defer()

        tags_file = pathlib.Path("tags.json")

        try:
            tags = json.loads(tags_file.read_text())
        except json.JSONDecodeError as e:
            await command_context.respond(
                f"Niepoprawny format pliku tags.json: {e}",
                ephemeral=True,
            )
            return

        playlist_id = self.playlist_id

        if playlist_id is None:
            playlist_id = app_config.default_playlist_id
        _LOGGER.info("Using playlist ID: %s", playlist_id)

        diffs: list[VideoDiff] = []

        for item in youtube_api.get_playlist_items(playlist_id, limit=DEFAULT_LIMIT):
            snippet = item["snippet"]
            video_id = snippet["resourceId"]["videoId"]
            if video_id in tags:
                diff = VideoDiff(
                    video_id=video_id,
                    old_title=snippet["title"],
                    new_title=snippet["title"],
                    old_description=snippet["description"],
                    new_description=snippet["description"],
                    tags=snippet["tags"],
                )
                if not diff.tags:
                    diff.tags = tags.get(video_id, {"tags": []})["tags"]
                    diffs.append(diff)

        def make_msg() -> str:
            return f"Liczba filmów bez tagów do uzupełnienia: **{len(diffs)}**\n"

        message = await command_context.respond(
            make_msg(),
            ensure_message=True,
        )
        channel: hikari.GuildTextChannel = await message.fetch_channel()  # type: ignore[assignment]

        for diff in diffs[:]:
            try:
                youtube_api.update_video_description(
                    video_id=diff.video_id,
                    video_title=diff.new_title,
                    video_category_id=diff.video_category_id,
                    description=diff.new_description,
                    tags=diff.tags,
                )
            except googleapiclient.errors.HttpError as e:  # noqa: PERF203
                await command_context.respond(
                    f"Nie udało się podmienić opisu filmu: `{e}`",
                )
                return
            else:
                url = f"https://www.youtube.com/watch?v={diff.video_id}"
                diffs.remove(diff)
                await message.edit(make_msg())
                await channel.send(
                    f"Uzupełniono tagi w filmie [`{diff.new_title}`]({url}).",
                    reply=message,
                )
