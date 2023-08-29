# redesc
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
