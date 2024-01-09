## Redbot imports ##

from AAA3A_utils import Cog, CogsUtils, Menu  # isort:skip

from redbot.core import commands, Config  # isort:skip
from redbot.core.bot import Red
from redbot.core.i18n import Translator, cog_i18n  # isort:skip
import discord  # isort:skip
import typing  # isort:skip

import aiohttp
import asyncio
from functools import partial

from redbot.core.utils.chat_formatting import inline, pagify

from .converters import StringToEmbed, ListStringToEmbed, PastebinConverter, PastebinListConverter, MyMessageConverter, MessageableOrMessageConverter, StrConverter, Emoji

_ = Translator("secretBeds", __file__)

YAML_CONVERTER = StringToEmbed(conversion_type="yaml", content=False)
YAML_CONTENT_CONVERTER = StringToEmbed(conversion_type="yaml")
YAML_LIST_CONVERTER = ListStringToEmbed(conversion_type="yaml")
JSON_CONVERTER = StringToEmbed(content=False)
JSON_CONTENT_CONVERTER = StringToEmbed()
JSON_LIST_CONVERTER = ListStringToEmbed()
PASTEBIN_CONVERTER = PastebinConverter(conversion_type="json", content=False)
PASTEBIN_CONTENT_CONVERTER = PastebinConverter(conversion_type="json")
PASTEBIN_LIST_CONVERTER = PastebinListConverter(conversion_type="json")

class MyMessageConverter(commands.MessageConverter):
    async def convert(self, ctx: commands.Context, argument: str) -> discord.Message:
        message = await super().convert(ctx, argument=argument)
        if message.author != ctx.me:
            raise commands.UserFeedbackCheckFailure(
                _("I have to be the author of the message. You can use EmbedUtils by AAA3A to send one.")
            )
        return message

            ##### --- Bot Setup --- #####

@cog_i18n(_)
class secretBeds(Cog):
    def __init__(self, bot: Red) -> None:
        super().__init__(bot=bot)

        self.config: Config = Config.get_conf(
            self,
            identifier=205192943327321000143939875896557571750,  # 370638632963
            force_registration=True,
        )

        self.secret_embeds_global: typing.Dict[str, typing.Dict[str, typing.Any]] = {
            "stored_embeds": {}
        }
        self.secret_embeds_guild: typing.Dict[str, typing.Dict[str, typing.Any]] = {
            "stored_embeds": {}
        }

        self.CONFIG_SCHEMA = 2
        self.secret_buttons_global: typing.Dict[str, typing.Optional[int]] = {
            "CONFIG_SCHEMA": None,
        }
        self.secret_buttons_guild: typing.Dict[
            str, typing.Dict[str, typing.Dict[str, typing.Dict[str, str]]]
        ] = {
            "secret_buttons": {},
        }

        self.config.register_global(**self.secret_buttons_global)
        self.config.register_guild(**self.secret_buttons_guild)
        self.config.register_global(**self.secret_embeds_global)
        self.config.register_guild(**self.secret_embeds_guild)
        self.cache: typing.List[embedSet.Context] = []

        self._session: aiohttp.ClientSession = None

    async def cog_load(self) -> None:
        await super().cog_load()
        await self.edit_config_schema()
        self._session: aiohttp.ClientSession = aiohttp.ClientSession()
        asyncio.create_task(self.load_buttons())

    async def cog_unload(self) -> None:
        if self._session is not None:
            await self._session.close()
        await super().cog_unload()

            ##### --- Config Setup/Editing --- #####

    async def edit_config_schema(self) -> None:
        CONFIG_SCHEMA = await self.config.CONFIG_SCHEMA()
        if CONFIG_SCHEMA is None:
            CONFIG_SCHEMA = 1
            await self.config.CONFIG_SCHEMA(CONFIG_SCHEMA)
        if CONFIG_SCHEMA == self.CONFIG_SCHEMA:
            return
        if CONFIG_SCHEMA == 1:
            for guild_id in await self.config.all_guilds():
                secret_buttons = await self.config.guild_from_id(guild_id).secret_buttons()
                for message in secret_buttons:
                    message_data = secret_buttons[message].copy()
                    for emoji in message_data:
                        data = secret_buttons[message].pop(emoji)
                        data["emoji"] = emoji
                        config_identifier = CogsUtils.generate_key(
                            length=5, existing_keys=secret_buttons[message]
                        )
                        secret_buttons[message][config_identifier] = data
                await self.config.guild_from_id(guild_id).secret_buttons.set(secret_buttons)
            CONFIG_SCHEMA = 2
            await self.config.CONFIG_SCHEMA.set(CONFIG_SCHEMA)
        if CONFIG_SCHEMA < self.CONFIG_SCHEMA:
            CONFIG_SCHEMA = self.CONFIG_SCHEMA
            await self.config.CONFIG_SCHEMA.set(CONFIG_SCHEMA)

            ##### --- Button handling --- #####

    async def load_buttons(self) -> None:
        await self.bot.wait_until_red_ready()
        all_guilds = await self.config.all_guilds()
        for guild in all_guilds:
            config = all_guilds[guild]["secret_buttons"]
            for message in config:
                channel = self.bot.get_channel(int((str(message).split("-"))[0]))
                if channel is None:
                    continue
                message_id = int((str(message).split("-"))[1])
                try:
                    view = self.get_buttons(config=config, message=message)
                    self.bot.add_view(view, message_id=message_id)
                    self.views[discord.PartialMessage(channel=channel, id=message_id)] = view
                except Exception as e:
                    self.log.error(
                        f"The Button View could not be added correctly for the `{guild}-{message}` message.",
                        exc_info=e,
                    )

    def get_buttons(
        self, config: typing.Dict[str, dict], message: typing.Union[discord.Message, str]
    ) -> discord.ui.View:
        message = (
            f"{message.channel.id}-{message.id}"
            if isinstance(message, discord.Message)
            else message
        )
        view = discord.ui.View(timeout=None)
        for config_identifier in config[message]:
            if config[message][config_identifier]["emoji"] is not None:
                try:
                    int(config[message][config_identifier]["emoji"])
                except ValueError:
                    b = config[message][config_identifier]["emoji"]
                else:
                    b = str(self.bot.get_emoji(int(config[message][config_identifier]["emoji"])))
            else:
                b = None
            button = discord.ui.Button(
                label=config[message][config_identifier]["text_button"],
                emoji=b,
                style=discord.ButtonStyle(
                    config[message][config_identifier].get("style_button", 2)
                ),
                custom_id=f"secret_buttons {config_identifier}",
                disabled=False,
            )
            button.callback = partial(
                self.on_button_interaction, config_identifier=config_identifier
            )
            view.add_item(button)
        return view

    async def on_button_interaction(self, interaction: discord.Interaction, config_identifier: str) -> None:
        if await self.bot.cog_disabled_in_guild(self, interaction.guild):
            return
       
        if not interaction.data["custom_id"].startswith("secret_buttons"):
            return

        config = await self.config.guild(interaction.guild).secret_buttons.all()
        
        if(
            f"{interaction.channel.id}-{interaction.message.id}" not in config
            or config[f"{interaction.channel.id}-{interaction.message.id}"].get(config_identifier) is None
        ):
            await interaction.response.send_message(
                "Stored embeds not found. Please report this to an admin.",
                ephemeral=True
            )
        else:
            embedData = config[f"{interaction.channel.id}-{interaction.message.id}"][config_identifier]["embedSet"]
            stored_embeds = await self.config.guild(interaction.guild).stored_embeds()
        
            try:
                embedStore: discord.Embed = discord.Embed.from_dict(stored_embeds[embedData]["embed"])
                await interaction.response.send_message(embed=embedStore, ephemeral=True)
            except KeyError:
                await interaction.response.send_message(
                    f"Error 404: {embedData} not found within stored_embeds.\nPlease report this to an admin. {KeyError}",
                    ephemeral=True
                )
                self.log.error(
                    f"The button with identifier {config_identifier} is setup incorrectly of broken\n {embedData} was not found within the stored embeds.\nRun [p]secretbeds embedlist and ensure the button value is set accordingly",
                    exc_info=KeyError,
                )
            finally:
                if not interaction.response.is_done():
                    await interaction.response.defer(ephemeral=True)

            ##### --- Error handling --- #####

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context) -> None:
        if ctx in self.cache:
            self.cache.remove(ctx)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if message.guild is None:
            return
        config = await self.config.guild(message.guild).secret_buttons.all()
        if f"{message.channel.id}-{message.id}" not in config:
            return
        del config[f"{message.channel.id}-{message.id}"]
        await self.config.guild(message.guild).secret_buttons.set(config)

            ##### --- Hybrid group definition --- #####

    @commands.guild_only()
    @commands.is_owner()
    @commands.bot_has_permissions(embed_links=True)
    @commands.hybrid_group()
    async def secretbeds(self, ctx: commands.Context) -> None:
        """Group of commands to use SecretBeds."""
        pass

            ##### --- Button functions --- #####

    @commands.bot_has_permissions(embed_links=True)
    @secretbeds.command(name="embedbutton", aliases=["addbuttonembed"], usage="[messageID] [storedEmbedID] [Emoji] [buttonType] [buttonText]")
    async def secret_embed_button(
        self,
        ctx: commands.Context,
        message: MyMessageConverter,
        embedSet: str,
        emoji: typing.Optional[Emoji],
        style_button: typing.Optional[typing.Literal["1", "2", "3", "4"]] = "2",
        *,
        text_button: typing.Optional[commands.Range[str, 1, 100]] = None,
    ) -> None:
        """Add a secret-embed-button to a message.

        (Use the number for the color.)
        • `primary`: 1
        • `secondary`: 2
        • `success`: 3
        • `danger`: 4
        # Aliases
        • `blurple`: 1
        • `grey`: 2
        • `gray`: 2
        • `green`: 3
        • `red`: 4
        """
        channel_permissions = message.channel.permissions_for(ctx.me)
        if (
            not channel_permissions.view_channel
            or not channel_permissions.read_messages
            or not channel_permissions.read_message_history
        ):
            raise commands.UserFeedbackCheckFailure(
                _(
                    "I don't have sufficient permissions on the channel where the message you specified is located.\nI need the permissions to see the messages in that channel."
                )
            )
        if emoji is None and text_button is None:
            raise commands.UserFeedbackCheckFailure(
                _("You have to specify at least an emoji or a label.")
            )
        if emoji is not None and ctx.interaction is None and ctx.bot_permissions.add_reactions:
            try:
                await ctx.message.add_reaction(emoji)
            except discord.HTTPException:
                raise commands.UserFeedbackCheckFailure(
                    _(
                        "The emoji you selected seems invalid. Check that it is an emoji. If you have Nitro, you may have used a custom emoji from another server."
                    )
                )
        config = await self.config.guild(ctx.guild).secret_buttons.all()
        if f"{message.channel.id}-{message.id}" not in config:
            if message.components:
                raise commands.UserFeedbackCheckFailure(_("This message already has components."))
            config[f"{message.channel.id}-{message.id}"] = {}
        if len(config[f"{message.channel.id}-{message.id}"]) > 25:
            raise commands.UserFeedbackCheckFailure(
                _("I can't do more than 25 commands-buttons for one message.")
            )
        config_identifier = CogsUtils.generate_key(
            length=5, existing_keys=config[f"{message.channel.id}-{message.id}"]
        )
        config[f"{message.channel.id}-{message.id}"][config_identifier] = {
            "embedSet": embedSet,
            "emoji": f"{getattr(emoji, 'id', emoji)}" if emoji is not None else None,
            "style_button": int(style_button),
            "text_button": text_button,
        }
        view = self.get_buttons(config, message)
        message = await message.edit(view=view)
        self.views[message] = view
        await self.config.guild(ctx.guild).secret_buttons.set(config)
        await self.list.callback(self, ctx, message=message)

    @commands.bot_has_permissions(embed_links=True)
    @secretbeds.command()
    async def list(self, ctx: commands.Context, message: MyMessageConverter = None) -> None:
        """List all embed-buttons of this server or display the settings for a specific one."""
        secret_buttons = await self.config.guild(ctx.guild).secret_buttons()
        for secret_button in secret_buttons:
            secret_buttons[secret_button]["message"] = secret_button
        if message is None:
            _secret_buttons = list(secret_buttons.values()).copy()
        elif f"{message.channel.id}-{message.id}" not in secret_buttons:
            raise commands.UserFeedbackCheckFailure(
                _("No embed-buttons are configured for this message.")
            )
        else:
            _secret_buttons = secret_buttons.copy()
            _secret_buttons = [secret_buttons[f"{message.channel.id}-{message.id}"]]
        if not _secret_buttons:
            raise commands.UserFeedbackCheckFailure(_("No embed-buttons are in this server."))
        embed: discord.Embed = discord.Embed(
            title=_("Embed Buttons"),
            description=_(
                "There is {len_secret_buttons} embed buttons in this server."
            ).format(len_secret_buttons=len(secret_buttons)),
            color=await ctx.embed_color(),
        )
        embed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon)
        embeds = []
        for li in discord.utils.as_chunks(_secret_buttons, max_size=5):
            e = embed.copy()
            for secret_button in li:
                value = _("Message Jump Link: {message_jump_link}\n").format(
                    message_jump_link=f"https://discord.com/channels/{ctx.guild.id}/{secret_button['message'].replace('-', '/')}"
                )
                value += "\n".join(
                    [
                        f"`{config_identifier}` - Emoji {(ctx.bot.get_emoji(int(data['emoji'])) if data['emoji'].isdigit() else data['emoji']) if data['emoji'] is not None else '`None`'} - Label `{data['text_button']}` - Command `{data['embedSet']}`"
                        for config_identifier, data in secret_button.items()
                        if config_identifier != "message"
                    ]
                )
                for page in pagify(value, page_length=1024):
                    e.add_field(
                        name="\u200B",
                        value=page,
                        inline=False,
                    )
            embeds.append(e)
        await Menu(pages=embeds).start(ctx)

    @secretbeds.command()
    async def clear(self, ctx: commands.Context, message: MyMessageConverter) -> None:
        """Clear all commands-buttons for a message."""
        config = await self.config.guild(ctx.guild).secret_buttons.all()
        if f"{message.channel.id}-{message.id}" not in config:
            raise commands.UserFeedbackCheckFailure(
                _("No command-button is configured for this message.")
            )
        try:
            await message.edit(view=None)
        except discord.HTTPException:
            pass
        del config[f"{message.channel.id}-{message.id}"]
        await self.config.guild(ctx.guild).secret_buttons.set(config)
        await ctx.send(_("Commands-buttons cleared for this message."))

            ##### --- TODO: PURGE NEEDS TO GRAB MESSAGE ID AND EDIT WITH A VIEW OF NONE OR DELETE THE MESSAGE! --- #####

    @secretbeds.command(hidden=True)
    async def purge(self, ctx: commands.Context) -> None:
        """Clear all commands-buttons for a guild."""
        await self.config.guild(ctx.guild).secret_buttons.clear()
        await ctx.send(_("All embed-buttons purged."))


            ##### --- Embed functions --- #####

    @commands.mod_or_permissions(manage_guild=True)
    @secretbeds.command(name="store", aliases=["storeembed"], usage="[global_level=False] [locked=False] <name> <json|yaml|jsonfile|yamlfile|pastebin|message> [data]")
    async def embed_store(
        self,
        ctx: commands.Context,
        global_level: typing.Optional[bool],
        locked: typing.Optional[bool],
        name: str,
        conversion_type: typing.Literal["json", "fromjson", "fromdata", "yaml", "fromyaml", "fromfile", "jsonfile", "fromjsonfile", "fromdatafile", "yamlfile", "fromyamlfile", "gist", "pastebin", "hastebin", "message", "frommessage", "frommsg"],
        *,
        data: str = None,
    ):
        """Store an embed.

        Put the name in quotes if it is multiple words.
        The `locked` argument specifies whether the embed should be locked to mod and superior only (guild level) or bot owners only (global level).
        """
        if global_level is None:
            global_level = False
        elif global_level and ctx.author.id not in ctx.bot.owner_ids:
            raise commands.UserFeedbackCheckFailure(_("You can't manage global stored embeds."))
        if locked is None:
            locked = False

        if conversion_type in ("json", "fromjson", "fromdata"):
            if data is None:
                raise commands.UserInputError()
            data = await JSON_CONVERTER.convert(ctx, argument=data)
        elif conversion_type in ("yaml", "fromyaml"):
            if data is None:
                raise commands.UserInputError()
            data = await YAML_CONVERTER.convert(ctx, argument=data)
        elif conversion_type in ("fromfile", "jsonfile", "fromjsonfile", "fromdatafile"):
            if not ctx.message.attachments or ctx.message.attachments[
                0
            ].filename.split(".")[-1] not in ("json", "txt"):
                raise commands.UserInputError()
            try:
                argument = (await ctx.message.attachments[0].read()).decode(encoding="utf-8")
            except UnicodeDecodeError:
                raise commands.UserFeedbackCheckFailure(_("Unreadable attachment with `utf-8`."))
            data = await JSON_CONVERTER.convert(ctx, argument=argument)
        elif conversion_type in ("yamlfile", "fromyamlfile"):
            if not ctx.message.attachments or ctx.message.attachments[
                0
            ].filename.split(".")[-1] not in ("yaml", "txt"):
                raise commands.UserInputError()
            try:
                argument = (await ctx.message.attachments[0].read()).decode(encoding="utf-8")
            except UnicodeDecodeError:
                raise commands.UserFeedbackCheckFailure(_("Unreadable attachment with `utf-8`."))
            data = await YAML_CONVERTER.convert(ctx, argument=argument)
        elif conversion_type in ("gist", "pastebin", "hastebin"):
            if data is None:
                raise commands.UserInputError()
            data = await PASTEBIN_CONVERTER.convert(ctx, argument=data)
        elif conversion_type in ("message", "frommessage", "frommsg"):
            if data is None:
                raise commands.UserInputError()
            message = await commands.MessageConverter().convert(ctx, argument=data)
            if not message.embeds:
                raise commands.UserInputError()
            data = {"embed": message.embeds[0].to_dict()}
        embed = data["embed"]
        try:
            await ctx.channel.send(embed=embed)
        except discord.HTTPException as error:
            return await StringToEmbed.embed_convert_error(ctx, _("Embed Send Error"), error)

        async with (self.config if global_level else self.config.guild(ctx.guild)).stored_embeds() as stored_embeds:
            total_embeds = set(stored_embeds)
            total_embeds.add(name)
            # If the user provides a name that's already used as an embed, it won't increment the embed count, which is why total embeds is converted to a set to calculate length to prevent duplicate names.
            embed_limit = 100
            if not global_level and len(total_embeds) > embed_limit:
                raise commands.UserFeedbackCheckFailure(
                    _(
                        "This server has reached the embed limit of {embed_limit}. You must remove an embed with `{ctx.clean_prefix}embed unstore` before you can add a new one."
                    ).format(embed_limit=embed_limit, ctx=ctx)
                )
            stored_embeds[name] = {"author": ctx.author.id, "embed": embed.to_dict(), "locked": locked, "uses": 0}

    @commands.mod_or_permissions(manage_guild=True)
    @secretbeds.command(name="unstore", aliases=["unstoreembed"], usage="[global_level=False] <name>")
    async def embed_unstore(
        self,
        ctx: commands.Context,
        global_level: typing.Optional[bool],
        name: str,
    ):
        """Remove a stored embed."""
        if global_level is None:
            global_level = False
        elif global_level and ctx.author.id not in ctx.bot.owner_ids:
            raise commands.UserFeedbackCheckFailure(_("You can't manage global stored embeds."))
        async with (self.config if global_level else self.config.guild(ctx.guild)).stored_embeds() as stored_embeds:
            if name not in stored_embeds:
                raise commands.UserFeedbackCheckFailure(_("This is not a stored embed at this level."))
            del stored_embeds[name]

    @secretbeds.command(name="poststored", aliases=["poststoredembed", "post"], usage="[channel_or_message=<CurrentChannel>] [global_level=False] <names>")
    async def embed_post_stored(
        self,
        ctx: commands.Context,
        channel_or_message: typing.Optional[MessageableOrMessageConverter],
        global_level: typing.Optional[bool],
        names: commands.Greedy[StrConverter]
    ):
        """Post stored embeds."""
        if global_level is None:
            global_level = False
        elif global_level and ctx.author.id not in ctx.bot.owner_ids:
            raise commands.UserFeedbackCheckFailure(_("You can't manage global stored embeds."))
        async with (self.config if global_level else self.config.guild(ctx.guild)).stored_embeds() as stored_embeds:
            embeds = []
            for name in names:
                if (
                    name not in stored_embeds
                    or (global_level and stored_embeds[name]["locked"] and ctx.author.id not in ctx.bot.owner_ids)
                    or (not global_level and stored_embeds[name]["locked"] and await ctx.bot.is_mod(ctx.author))
                ):
                    raise commands.UserFeedbackCheckFailure(_("`{name}` is not a stored embed at this level.").format(name=name))
                embeds.append(discord.Embed.from_dict(stored_embeds[name]["embed"]))
                stored_embeds[name]["uses"] += 1
        try:
            if not isinstance(channel_or_message, discord.Message):
                channel = channel_or_message or ctx.channel
                await channel.send(embeds=embeds)
            else:
                await channel_or_message.edit(embeds=embeds)
        except discord.HTTPException as error:
            return await StringToEmbed.embed_convert_error(ctx, _("Embed Send Error"), error)

    @commands.mod_or_permissions(manage_guild=True)
    @secretbeds.command(name="embedlist", aliases=["liststored", "liststoredembeds"], usage="[global_level=False]")
    async def embed_list(self, ctx: commands.Context, global_level: typing.Optional[bool]):
        """Get info about a stored embed."""
        if global_level is None:
            global_level = False
        elif global_level and ctx.author.id not in ctx.bot.owner_ids:
            raise commands.UserFeedbackCheckFailure(_("You can't manage global stored embeds."))
        stored_embeds = await (self.config if global_level else self.config.guild(ctx.guild)).stored_embeds()
        if not stored_embeds:
            raise commands.UserFeedbackCheckFailure(
                _("No stored embeds is configured at this level.")
            )
        description = "\n".join(f"- `{name}`" for name in stored_embeds)
        embed: discord.Embed = discord.Embed(
            title=(_("Global ") if global_level else "") + _("Stored Embeds"),
            color=await ctx.embed_color()
        )
        embed.set_author(name=ctx.me.display_name, icon_url=ctx.me.display_avatar)
        embeds = []
        for page in pagify(description):
            e = embed.copy()
            e.description = page
            embeds.append(e)
        await Menu(pages=embeds).start(ctx)

    @commands.mod_or_permissions(manage_guild=True)
    @secretbeds.command(name="info", aliases=["infostored", "infostoredembed"], usage="[global_level=False] <name>")
    async def embed_info(self, ctx: commands.Context, global_level: typing.Optional[bool], name: str):
        """Get info about a stored embed."""
        if global_level is None:
            global_level = False
        elif global_level and ctx.author.id not in ctx.bot.owner_ids:
            raise commands.UserFeedbackCheckFailure(_("You can't manage global stored embeds."))
        stored_embeds = await (self.config if global_level else self.config.guild(ctx.guild)).stored_embeds()
        if name not in stored_embeds:
            raise commands.UserFeedbackCheckFailure(_("This is not a stored embed at this level."))
        stored_embed = stored_embeds[name]
        description = [
            f" **Author:** <@{stored_embed['author']}> ({stored_embed['author']})",
            f" **Uses:** {stored_embed['uses']}",
            f" **Length:** {len(stored_embed['embed'])}",
            f" **Locked:** {stored_embed['locked']}",
        ]
        embed: discord.Embed = discord.Embed(
            title=f"Info about `{name}`",
            description="\n".join(description),
            color=await ctx.embed_color()
        )
        embed.set_author(name=ctx.me.display_name, icon_url=ctx.me.display_avatar)
        await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions(users=False))