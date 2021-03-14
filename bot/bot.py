# bot.py

import discord
from discord.ext import commands

from . import cogs
from .cogs import utils
from .cogs.utils.utils import create_emojis

import json
import sys
import os
import logging


_CWD = os.path.dirname(os.path.abspath(__file__))
INTENTS_JSON = os.path.join(_CWD, 'intents.json')


class PUGsBot(commands.AutoShardedBot):
    """ Sub-classed AutoShardedBot modified to fit the needs of the application. """

    def __init__(self, discord_token, web_url, db_connect_url):
        """ Set attributes and configure bot. """
        # Call parent init
        with open(INTENTS_JSON) as f:
            intents_attrs = json.load(f)

        intents = discord.Intents(**intents_attrs)
        super().__init__(command_prefix=('g!', 'G!'), case_insensitive=True, intents=intents)

        # Set argument attributes
        self.discord_token = discord_token
        self.web_url = web_url
        self.db_connect_url = db_connect_url
        self.all_maps = {}

        # Set constants
        self.colors = {
            'red': 0xFF0000,
            'green': 0x00FF00,
            'blue': 0x0086FF,
            'orange': 0xFF9933
        }

        self.activity = discord.Activity(type=discord.ActivityType.watching, name="noobs use g!help")
        self.logger = logging.getLogger('PUGs.bot')

        # Create DB helper to use connection pool
        self.db = utils.DBHelper(self.db_connect_url)

        # Create session for API
        self.api = utils.ApiHelper(self, self.loop, self.web_url)

        # Initialize set of errors to ignore
        self.ignore_error_types = set()

        # Add check to not respond to DM'd commands
        self.add_check(lambda ctx: ctx.guild is not None)
        self.ignore_error_types.add(commands.errors.CheckFailure)
        self.ignore_error_types.add(commands.errors.MissingPermissions)
        self.ignore_error_types.add(commands.errors.UserInputError)

        # Trigger typing before every command
        self.before_invoke(commands.Context.trigger_typing)

        # Add cogs
        for cog in cogs.__all__:
            self.add_cog(cog(self))

        self.block_on_channel_delete = False

    async def on_error(self, event_method, *args, **kwargs):
        """"""
        try:
            logging_cog = self.get_cog('LoggingCog')

            if logging_cog is None:
                super().on_error(event_method, *args, **kwargs)
            else:
                exc_type, exc_value, traceback = sys.exc_info()
                logging_cog.log_exception(f'Uncaught exception when handling "{event_method}" event:', exc_value)
        except Exception as e:
            print(e)

    def embed_template(self, **kwargs):
        """ Implement the bot's default-style embed. """
        try:
            kwargs['color']
        except KeyError:
            kwargs['color'] = self.colors['blue']
        return discord.Embed(**kwargs)

    @commands.Cog.listener()
    async def on_ready(self):
        """ Synchronize the guilds the bot is in with the guilds table. """
        if self.guilds:
            print('Synchronize guilds...')
            await self.db.sync_guilds(*(guild.id for guild in self.guilds))
            print('Creating emojis...')
            await create_emojis(self, self.guilds[0])
            print('Bot is ready now!')

        lobby_cog = self.get_cog('LobbyCog')
        match_cog = self.get_cog('MatchCog')
        if not match_cog.check_matches.is_running():
            self.get_cog('MatchCog').check_matches.start()
        if not lobby_cog.check_unbans.is_running():
            self.get_cog('LobbyCog').check_unbans.start()

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        """ Insert the newly added guild to the guilds table. """
        await self.db.insert_guilds(guild.id)
        await create_emojis(self, self.guilds[0])

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        """ Delete the recently removed guild from the guilds table. """
        await self.db.delete_guilds(guild.id)

    async def on_guild_channel_delete(self, channel):
        """"""
        if self.block_on_channel_delete:
            return

        pug_data = None

        if isinstance(channel, discord.VoiceChannel):
            try:
                pug_data = await self.db.get_pug(channel.id, column='lobby_channel')
            except AttributeError:
                pass
        elif isinstance(channel, discord.TextChannel):
            try:
                pug_data = await self.db.get_pug(channel.id, column='queue_channel')
            except AttributeError:
                pass

        if pug_data is not None and channel.id in pug_data.values():
            self.block_on_channel_delete = True
            try:
                await channel.guild.get_channel(pug_data['queue_channel']).delete()
            except (AttributeError, discord.errors.NotFound):
                pass
            try:
                await channel.guild.get_channel(pug_data['lobby_channel']).delete()
            except (AttributeError, discord.errors.NotFound):
                pass
            try:
                await self.db.delete_pugs(pug_data['id'])
                print(f"Removed PUG ID #{pug_data['id']} from Discord ({channel.guild.name})")
            except AttributeError:
                pass

        self.block_on_channel_delete = False

    def run(self):
        """ Override parent run to automatically include Discord token. """
        super().run(self.discord_token)

    async def close(self):
        """ Override parent close to close the API session also. """
        await super().close()
        await self.api.close()
        await self.db.close()
