import logging

import crescent
import hikari
import miru

from redesc.common import app, app_config, app_var, client, client_var, running_app_var


_LOGGER = logging.getLogger(__name__)

running_app_var.set(True)
__import__("redesc.setup")

app_var.set(hikari.GatewayBot(token=app_config.token))
miru.install(app)

client_var.set(crescent.Client(app))
client.plugins.load("redesc.main")


async def interaction_made(event: hikari.InteractionCreateEvent) -> None:
    interaction = event.interaction
    if isinstance(interaction, hikari.CommandInteraction):
        _LOGGER.info(
            "Interaction from %s (%s): /%s %s",
            interaction.user,
            interaction.user.id,
            interaction.command_name,
            " ".join(
                (
                    f"{option.name}:{option.value}"
                    for option in (interaction.options or [])
                )
            ),
        )
    elif isinstance(interaction, hikari.ComponentInteraction):
        _LOGGER.info(
            "Interaction from %s (%s): %s %s",
            interaction.user,
            interaction.user.id,
            interaction.custom_id,
            " ".join(map(str, interaction.values)),
        )


if __name__ == "__main__":
    activity = hikari.Activity(
        name="opisy do podmiany",
        type=hikari.ActivityType.WATCHING,
    )
    app.event_manager.subscribe(hikari.InteractionCreateEvent, interaction_made)
    app.run(activity=activity)
