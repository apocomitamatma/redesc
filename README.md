
# redesc [![skeleton](https://img.shields.io/badge/61eeffb-skeleton?label=%F0%9F%92%80%20bswck/skeleton&labelColor=black&color=grey&link=https%3A//github.com/bswck/skeleton)](https://github.com/bswck/skeleton/tree/61eeffb)
[![Package version](https://img.shields.io/pypi/v/redesc?label=PyPI)](https://pypi.org/project/redesc/)
[![Supported Python versions](https://img.shields.io/pypi/pyversions/redesc.svg?logo=python&label=Python)](https://pypi.org/project/redesc/)

[![Coverage](https://coverage-badge.samuelcolvin.workers.dev/apocomitamatma/redesc.svg)](https://coverage-badge.samuelcolvin.workers.dev/redirect/apocomitamatma/redesc)
[![Poetry](https://img.shields.io/endpoint?url=https://python-poetry.org/badge/v0.json)](https://python-poetry.org/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License](https://img.shields.io/github/license/apocomitamatma/redesc.svg?label=License)](https://github.com/apocomitamatma/redesc/blob/HEAD/LICENSE)
[![Pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)

A tool for substituting YouTube video descriptions with regex.

Modify your YouTube video descriptions with regex, en masse (pretty much only 100 videos at once, though).

(Instructions below may be unprecise, maybe some update soon.)

# Set up
Copy your OAuth2 credentials from the Google Cloud Console.
Paste them into `oauth2.json` file in the root directory of this repository.

Create `config.yml` file there with the following structure:
```yaml
youtube_api_key: your_youtube_api_key
default_playlist_id: UU_YourYoutubeChannelID
permitted_discord_channel_id: exclusive_discord_channel_id
```
and configure it to your liking.

Finally, create `.env` file where the bot token will be stored:
```
REDESC_TOKEN=your_discord_bot_token
```

Everything manual is set up now.

## Run
1. Clone this repository and `cd` to it.
2. `./run`

## Use
On Discord, navigate to the channel of the same ID as in the `config.yml` file.
Use the bot commands there.


# Legal info
© Copyright by Bartosz Sławecki ([@bswck](https://github.com/bswck)).
<br />This software is licensed under the terms of [MIT License](https://github.com/apocomitamatma/redesc/blob/HEAD/LICENSE).

