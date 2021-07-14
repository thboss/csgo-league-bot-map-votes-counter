# commands.py

from discord.ext import commands
from discord.utils import get
from datetime import datetime, timezone
from steam.steamid import SteamID, from_url
from dotenv import load_dotenv
import re
import asyncio
import os

from .message import MapPoolMessage
from .utils.utils import (translate, timedelta_str, unbantime, check_setup,
                          check_pug, get_guild_config, get_user_data, get_match_data, align_text)

load_dotenv()


class CommandsCog(commands.Cog):
    """"""

    def __init__(self, bot):
        self.bot = bot
        self.lobby_cog = bot.get_cog('LobbyCog')

    @commands.command(brief=translate('command-setup-brief', 'http://g5.thboss.xyz:3301'),
                      usage='setup <api_user_id> <api_user_key>')
    @commands.has_permissions(kick_members=True)
    async def setup(self, ctx, api_user_id=None, api_user_key=None):
        """"""
        if not api_user_id or not api_user_key:
            msg = translate('invalid-usage', self.bot.command_prefix[0], ctx.command.usage)
            raise commands.UserInputError(message=msg)

        is_user = await self.bot.api.is_user(int(api_user_id))
        if not is_user:
            msg = translate('command-setup-key-invalid')
            raise commands.UserInputError(message=msg)

        auth = {'user_id': int(api_user_id), 'api_key': api_user_key}

        is_valid = await self.bot.api.check_auth(auth)
        if not is_valid:
            msg = translate('command-setup-key-invalid')
            raise commands.UserInputError(message=msg)

        guild_config = await get_guild_config(self.bot, ctx.guild.id)
        linked_role = guild_config.linked_role
        prematch_channel = guild_config.prematch_channel

        if not linked_role:
            linked_role = await ctx.guild.create_role(name='Linked')

        if not prematch_channel:
            prematch_channel = await ctx.guild.create_voice_channel(name='Pre-Match')

        guild_data = {
            'linked_role': linked_role.id,
            'prematch_channel': prematch_channel.id,
            'user_id': int(api_user_id),
            'api_key': api_user_key
        }

        await self.bot.db.update_guild(ctx.guild.id, **guild_data)

        msg = translate('command-setup-success')
        embed = self.bot.embed_template(description=msg, color=self.bot.colors['green'])
        embed.set_footer(text=translate('command-setup-footer'))
        await ctx.send(embed=embed)

    @commands.command(usage='create_server <ip:port> <rcon_password> <server_name|optional> <server_gotv|optional>',
                      brief=translate('command-create_server-brief'))
    @commands.has_permissions(administrator=True)
    async def create_server(self, ctx, *args):
        """"""
        guild_config = await check_setup(self.bot, ctx)

        try:
            ip = args[0].split(':')[0]
            port = int(args[0].split(':')[1])
            rcon_pass = args[1]
            if len(args) > 3:
                gotv = int(args[3])
        except (IndexError, TypeError):
            msg = translate('invalid-usage', self.bot.command_prefix[0], ctx.command.usage)
            raise commands.UserInputError(message=msg)
        
        if len(args) == 2:
            result = await self.bot.api.create_server(guild_config.auth, ip, port, rcon_pass)
        elif len(args) == 3:
            result = await self.bot.api.create_server(guild_config.auth, ip, port, rcon_pass, args[2])
        else:
            result = await self.bot.api.create_server(guild_config.auth, ip, port, rcon_pass, args[2], gotv)
        
        if not result:
            msg = translate('command-create_server-failed')
            raise commands.UserInputError(message=msg)

        msg = translate('command-create_server-success', ip, port)
        embed = self.bot.embed_template(title=msg, color=self.bot.colors['green'])
        await ctx.send(embed=embed)

    @commands.command(usage='lobby <name>',
                      brief=translate('command-lobby-brief'))
    @commands.has_permissions(kick_members=True)
    async def lobby(self, ctx, *args):
        """"""
        guild_config = await check_setup(self.bot, ctx)
        args = ' '.join(arg for arg in args)

        if not len(args):
            msg = translate('invalid-usage', self.bot.command_prefix[0], ctx.command.usage)
            raise commands.UserInputError(message=msg)
        
        linked_role = guild_config.linked_role

        category = await ctx.guild.create_category_channel(args)
        awaitables = [
            ctx.guild.create_text_channel(name=f'{args}-queue', category=category),
            ctx.guild.create_voice_channel(name=f'{args} Lobby', category=category, user_limit=10),
            self.bot.db.insert_pugs(),
        ]
        results = await asyncio.gather(*awaitables, loop=self.bot.loop)

        queue_channel = results[0]
        lobby_channel = results[1]

        await queue_channel.set_permissions(ctx.guild.self_role, send_messages=True)
        await lobby_channel.set_permissions(ctx.guild.self_role, connect=True)

        awaitables = [
            self.bot.db.update_pug(results[2][0], guild=ctx.guild.id,
                                                  queue_channel=queue_channel.id,
                                                  lobby_channel=lobby_channel.id),
            queue_channel.set_permissions(ctx.guild.default_role, send_messages=False),
            lobby_channel.set_permissions(ctx.guild.default_role, connect=False),
            lobby_channel.set_permissions(linked_role, connect=True)
        ]
        await asyncio.gather(*awaitables, loop=self.bot.loop)

        msg = translate('command-lobby-success', args)
        embed = self.bot.embed_template(title=msg, color=self.bot.colors['green'])
        await ctx.send(embed=embed)

    @commands.command(usage='link <Steam ID/Profile>',
                      brief=translate('command-link-brief'))
    async def link(self, ctx, *args):
        """"""
        guild_config = await check_setup(self.bot, ctx)
        user_data = await get_user_data(self.bot, ctx.guild, ctx.author.id)
        banned_users = await self.bot.db.get_banned_users(ctx.guild.id)

        if ctx.author.id in banned_users:
            msg = translate('command-link-user-is-banned')
            unban_time = banned_users[ctx.author.id]
            if unban_time:
                msg += f' for {timedelta_str(unban_time - datetime.now(timezone.utc))}'
            raise commands.UserInputError(message=msg)

        if user_data is not None:
            msg = translate('command-link-already-linked', user_data.steam)
            await ctx.author.add_roles(guild_config.linked_role)
            raise commands.UserInputError(message=msg)

        try:
            steam_id = SteamID(args[0])
        except (IndexError, KeyError):
            msg = translate('invalid-usage', self.bot.command_prefix[0], ctx.command.usage)
            raise commands.UserInputError(message=msg)

        if not steam_id.is_valid():
            steam_id = from_url(args[0], http_timeout=15)
            if steam_id is None:
                steam_id = from_url(f'https://steamcommunity.com/id/{args[0]}/', http_timeout=15)
                if steam_id is None:
                    msg = translate('command-link-steam-invalid')
                    raise commands.UserInputError(message=msg)

        user_data = await get_user_data(self.bot, ctx.guild, str(steam_id), 'steam_id')
        if user_data is not None:
            msg = translate('command-link-steam-used')
            raise commands.UserInputError(message=msg)

        await self.bot.db.insert_users(ctx.author.id, str(steam_id), os.environ['GET5_CAPTAIN_FLAG'])
        await ctx.author.add_roles(guild_config.linked_role)

        title = translate('command-link-success', steam_id)
        embed = self.bot.embed_template(description=title, color=self.bot.colors['green'])
        embed.set_footer(text=translate('command-link-footer'))
        await ctx.send(embed=embed)

    @commands.command(brief=translate('command-unlink-brief'))
    async def unlink(self, ctx):
        """"""
        guild_config = await check_setup(self.bot, ctx)

        awaitables = []
        for pug_id in await self.bot.db.get_guild_pugs(ctx.guild.id):
            awaitables.append(self.bot.db.get_queued_users(pug_id))
        queued_ids = await asyncio.gather(*awaitables, loop=self.bot.loop)
        queued_ids = sum(queued_ids, [])

        awaitables = [
            get_user_data(self.bot, ctx.guild, ctx.author.id),
            self.bot.db.get_all_matches_users(),
            self.bot.db.get_banned_users(ctx.guild.id)
        ]
        results = await asyncio.gather(*awaitables, loop=self.bot.loop)
        is_linked = results[0]
        matches_users = results[1]
        banned_users = results[2]

        if ctx.author.id in banned_users:
            msg = translate('command-link-user-is-banned')
            unban_time = banned_users[ctx.author.id]
            if unban_time:
                msg += f' for {timedelta_str(unban_time - datetime.now(timezone.utc))}'
            raise commands.UserInputError(message=msg)

        if not is_linked:
            msg = translate('command-unlink-not-linked')
            raise commands.UserInputError(message=msg)

        if ctx.author.id in queued_ids:
            msg = translate('command-unlink-in-lobby')
            raise commands.UserInputError(message=msg)

        if ctx.author.id in matches_users:
            msg = translate('command-unlink-in-match')
            raise commands.UserInputError(message=msg)

        await self.bot.db.delete_users([ctx.author.id])
        await ctx.author.remove_roles(guild_config.linked_role)

        title = translate('command-unlink-success', ctx.author)
        embed = self.bot.embed_template(title=title, color=self.bot.colors['green'])
        embed.set_footer(text=translate('command-unlink-footer'))
        await ctx.send(embed=embed)

    @commands.command(usage='empty <mention_queue_channel>',
                      brief=translate('command-empty-brief'))
    @commands.has_permissions(kick_members=True)
    async def empty(self, ctx):
        """"""
        try:
            args = ctx.message.content.split()[1:]
            queue_id = int(re.search('<#(.+?)>', args[0]).group(1))
        except:
            msg = translate('invalid-usage', self.bot.command_prefix[0], ctx.command.usage)
            raise commands.UserInputError(message=msg)

        pug_config = await check_pug(self.bot, ctx, queue_id)
        lobby_channel = pug_config.lobby_channel

        if self.lobby_cog.locked_lobby[pug_config.id]:
            msg = translate('command-empty-locked')
            raise commands.UserInputError(message=msg)

        self.lobby_cog.locked_lobby[pug_config.id] = True
        await self.bot.db.clear_queued_users(pug_config.id)
        msg = translate('command-empty-success')
        embed = await self.lobby_cog.queue_embed(pug_config, msg)
        await self.lobby_cog.update_last_msg(pug_config, embed)
        guild_config = await get_guild_config(self.bot, ctx.guild.id)

        for member in lobby_channel.members:
            await member.move_to(guild_config.prematch_channel)

        self.lobby_cog.locked_lobby[pug_config.id] = False
        _embed = self.bot.embed_template(title=msg, color=self.bot.colors['green'])
        await ctx.send(embed=_embed)

    @commands.command(usage='cap <mention_queue_channel> <new_capacity>',
                      brief=translate('command-cap-brief'),
                      aliases=['capacity'])
    @commands.has_permissions(kick_members=True)
    async def cap(self, ctx):
        """"""
        try:
            args = ctx.message.content.split()[1:]
            queue_id = int(re.search('<#(.+?)>', args[0]).group(1))
            new_cap = int(args[1])
        except:
            msg = translate('invalid-usage', self.bot.command_prefix[0], ctx.command.usage)
            raise commands.UserInputError(message=msg)

        pug_config = await check_pug(self.bot, ctx, queue_id)
        curr_cap = pug_config.capacity

        if new_cap == curr_cap:
            msg = translate('command-cap-already', curr_cap)
            raise commands.UserInputError(message=msg)

        if new_cap < 2 or new_cap > 100 or new_cap %2 == 1:
            msg = translate('command-cap-out-range')
            raise commands.UserInputError(message=msg)

        if self.lobby_cog.locked_lobby[pug_config.id]:
            msg = translate('command-cap-locked')
            raise commands.UserInputError(message=msg)

        self.lobby_cog.locked_lobby[pug_config.id] = True
        await self.bot.db.clear_queued_users(pug_config.id)
        await self.bot.db.update_pug(pug_config.id, capacity=new_cap)
        embed = await self.lobby_cog.queue_embed(pug_config, translate('command-empty-success'))
        embed.set_footer(text=translate('command-cap-footer'))
        await self.lobby_cog.update_last_msg(pug_config, embed)
        msg = translate('command-cap-success', new_cap)
        lobby_channel = pug_config.lobby_channel
        guild_config = await get_guild_config(self.bot, ctx.guild.id)

        awaitables = []
        for player in lobby_channel.members:
            awaitables.append(player.move_to(guild_config.prematch_channel))
        awaitables.append(lobby_channel.edit(user_limit=new_cap))
        await asyncio.gather(*awaitables, loop=self.bot.loop, return_exceptions=True)

        self.lobby_cog.locked_lobby[pug_config.id] = False

        embed = self.bot.embed_template(title=msg)
        await ctx.send(embed=embed)

    @commands.command(usage='teams <mention_queue_channel> <captains|autobalance|random>',
                      brief=translate('command-teams-brief'),
                      aliases=['team'])
    @commands.has_permissions(kick_members=True)
    async def teams(self, ctx):
        """"""
        try:
            args = ctx.message.content.split()[1:]
            queue_id = int(re.search('<#(.+?)>', args[0]).group(1))
            method = args[1].lower() if len(args) > 1 else None
        except:
            msg = translate('invalid-usage', self.bot.command_prefix[0], ctx.command.usage)
            raise commands.UserInputError(message=msg)

        pug_config = await check_pug(self.bot, ctx, queue_id)
        curr_method = pug_config.team_method
        valid_methods = ['autobalance', 'captains', 'random']

        if method is None:
            title = translate('command-teams-method', curr_method)
        else:
            if method == curr_method:
                msg = translate('command-teams-already', curr_method)
                raise commands.UserInputError(message=msg)

            if method not in valid_methods:
                msg = translate('command-teams-invalid', valid_methods[0], valid_methods[1])
                raise commands.UserInputError(message=msg)

            title = translate('command-teams-changed', method)
            await self.bot.db.update_pug(pug_config.id, team_method=method)

        embed = self.bot.embed_template(title=title)
        await ctx.send(embed=embed)

    @commands.command(usage='captains <mention_queue_channel> <volunteer|rank|random>',
                      brief=translate('command-captains-brief'),
                      aliases=['captain', 'picker', 'pickers'])
    @commands.has_permissions(kick_members=True)
    async def captains(self, ctx):
        """"""
        try:
            args = ctx.message.content.split()[1:]
            queue_id = int(re.search('<#(.+?)>', args[0]).group(1))
            new_method = args[1].lower() if len(args) > 1 else None
        except:
            msg = translate('invalid-usage', self.bot.command_prefix[0], ctx.command.usage)
            raise commands.UserInputError(message=msg)

        pug_config = await check_pug(self.bot, ctx, queue_id)
        curr_method = pug_config.captain_method
        valid_methods = ['volunteer', 'rank', 'random']

        if new_method is None:
            title = translate('command-captains-method', curr_method)
        else:
            if new_method == curr_method:
                msg = translate('command-captains-already', curr_method)
                raise commands.UserInputError(message=msg)

            if new_method not in valid_methods:
                msg = translate('command-captains-invalid', valid_methods[0], valid_methods[1])
                raise commands.UserInputError(message=msg)

            title = translate('command-captains-changed', new_method)
            await self.bot.db.update_pug(pug_config.id, captain_method=new_method)

        embed = self.bot.embed_template(title=title)
        await ctx.send(embed=embed)

    @commands.command(usage='maps <mention_queue_channel> <ban|vote|random>',
                      brief=translate('command-maps-brief'),
                      aliases=['map'])
    @commands.has_permissions(kick_members=True)
    async def maps(self, ctx):
        """"""
        try:
            args = ctx.message.content.split()[1:]
            queue_id = int(re.search('<#(.+?)>', args[0]).group(1))
            new_method = args[1].lower() if len(args) > 1 else None
        except:
            msg = translate('invalid-usage', self.bot.command_prefix[0], ctx.command.usage)
            raise commands.UserInputError(message=msg)

        pug_config = await check_pug(self.bot, ctx, queue_id)
        curr_method = pug_config.map_method
        valid_methods = ['ban', 'vote', 'random']

        if new_method is None:
            title = translate('command-maps-method', curr_method)
        else:
            if new_method == curr_method:
                msg = translate('command-maps-already', curr_method)
                raise commands.UserInputError(message=msg)

            if new_method not in valid_methods:
                msg = translate('command-maps-invalid', valid_methods[0], valid_methods[1], valid_methods[2])
                raise commands.UserInputError(message=msg)

            title = translate('command-maps-changed', new_method)
            await self.bot.db.update_pug(pug_config.id, map_method=new_method)

        embed = self.bot.embed_template(title=title)
        await ctx.send(embed=embed)

    @commands.command(usage='mpool <mention_queue_channel>',
                      brief=translate('command-mpool-brief'),
                      aliases=['mappool', 'pool'])
    @commands.has_permissions(kick_members=True)
    async def mpool(self, ctx):
        """"""
        try:
            args = ctx.message.content.split()[1:]
            queue_id = int(re.search('<#(.+?)>', args[0]).group(1))
        except:
            msg = translate('invalid-usage', self.bot.command_prefix[0], ctx.command.usage)
            raise commands.UserInputError(message=msg)

        pug_config = await check_pug(self.bot, ctx, queue_id)
        message = await ctx.send('Map Pool')
        menu = MapPoolMessage(message, self.bot, ctx.author, pug_config)
        await menu.pick()

    @commands.command(usage='spectators <mention_queue_channel> {+|-} <mention> <mention> ...',
                      brief=translate('command-spectators-brief'),
                      aliases=['spec', 'spectator'])
    async def spectators(self, ctx):
        """"""
        try:
            args = ctx.message.content.split()[1:]
            queue_id = int(re.search('<#(.+?)>', args[0]).group(1))
            prefix = args[1] if len(args) > 1 else None
        except:
            msg = translate('invalid-usage', self.bot.command_prefix[0], ctx.command.usage)
            raise commands.UserInputError(message=msg)

        pug_config = await check_pug(self.bot, ctx, queue_id)
        curr_spectator_ids = await self.bot.db.get_spect_users(pug_config.id)
        curr_spectators = [ctx.guild.get_member(spectator_id) for spectator_id in curr_spectator_ids]
        spectators = ctx.message.mentions

        if prefix is None:
            if not curr_spectators:
                spect_value = 'No spectators'
            else:
                spect_value = ''.join(f'{num}. {user.mention}\n' for num, user in enumerate(curr_spectators, start=1))

            embed = self.bot.embed_template()
            embed.add_field(name='__Spectators__', value=spect_value)
            await ctx.send(embed=embed)
            return

        author_perms = ctx.author.guild_permissions
        if not author_perms.administrator:
            raise commands.MissingPermissions(missing_perms=['kick_members'])

        title = ''

        if prefix not in ['+', '-']:
            msg = translate('invalid-usage', self.bot.command_prefix[0], ctx.command.usage)
            raise commands.UserInputError(message=msg)

        await self.bot.db.delete_queued_users(pug_config.id, [spectator.id for spectator in spectators])
        for spectator in spectators:
            if prefix == '+':
                if spectator.id in curr_spectator_ids:
                    msg = f'{translate("command-spectators-already", spectator.display_name)}'
                    raise commands.UserInputError(message=msg)

                await self.bot.db.insert_spect_users(pug_config.id, spectator.id)
                title += f'{translate("command-spectators-added", spectator.display_name)}\n'

            elif prefix == '-':
                if spectator.id not in curr_spectator_ids:
                    msg = f'{translate("command-spectators-not", spectator.display_name)}'
                    raise commands.UserInputError(message=msg)

                await self.bot.db.delete_spect_users(pug_config.id, spectator.id)
                title += f'{translate("ommand-spectators-removed", spectator.display_name)}\n'

        embed = self.bot.embed_template(title=title)
        await ctx.send(embed=embed)

    @commands.command(usage='end <match_id>',
                      brief=translate('command-end-brief'),
                      aliases=['cancel', 'stop'])
    @commands.has_permissions(kick_members=True)
    async def end(self, ctx, match_id=None):
        """"""
        guild_config = await check_setup(self.bot, ctx)
        if match_id is None:
            msg = translate('invalid-usage', self.bot.command_prefix[0], ctx.command.usage)
            raise commands.UserInputError(message=msg)

        status_code = await self.bot.api.cancel_match(match_id, guild_config.auth)
        if status_code != 200:
            if status_code == 404:
                msg = translate('command-end-not-found', match_id)
            elif status_code == 403:
                msg = translate('command-end-no-permission')
            elif status_code == 401:
                msg = translate('command-end-already-finished', match_id)
            else:
                msg = translate('command-end-unknown-error')
            raise commands.UserInputError(message=msg)

        title = translate('command-end-success', match_id)
        embed = self.bot.embed_template(title=title)
        await ctx.send(embed=embed)

    @commands.command(brief=translate('command-stats-brief'),
                      aliases=['rank'])
    async def stats(self, ctx):
        """"""
        user_data = await get_user_data(self.bot, ctx.guild, ctx.author.id)
        if not user_data:
            msg = f'Unable to get {ctx.author.display_name}\'s stats: Account not linked'
            raise commands.UserInputError(message=msg)

        stats = await self.bot.api.player_stats(user_data)
        description = '```ml\n' \
                     f' {translate("command-stats-kills")}:             {stats.kills} \n' \
                     f' {translate("command-stats-deaths")}:            {stats.deaths} \n' \
                     f' {translate("command-stats-assists")}:           {stats.assists} \n' \
                     f' {translate("command-stats-kdr")}:         {stats.kdr} \n' \
                     f' {translate("command-stats-hs")}:         {stats.hsk} \n' \
                     f' {translate("command-stats-hsp")}:  {stats.hsp} \n' \
                     f' {translate("command-stats-played")}:    {stats.total_maps} \n' \
                     f' {translate("command-stats-wins")}:        {stats.wins} \n' \
                     f' {translate("command-stats-win-rate")}:       {stats.win_percent} \n' \
                     f' ------------------------- \n' \
                     f' {translate("command-stats-rating")}:    {stats.average_rating} \n' \
                      '```'
        embed = self.bot.embed_template(description=description)
        embed.set_author(name=ctx.author.display_name, url=stats.profile,
                            icon_url=ctx.author.avatar_url_as(size=128))
        await ctx.send(embed=embed)

    @commands.command(brief=translate('command-leaders-brief'),
                      aliases=['top', 'ranks'])
    async def leaders(self, ctx):
        """"""
        num = 10
        guild_players = await self.bot.api.leaderboard(ctx.guild.members)
        guild_players.sort(key=lambda u: (u.average_rating), reverse=True)
        guild_players = guild_players[:num]

        # Generate leaderboard text
        data = [['Player'] + [ctx.guild.get_member(player.discord).display_name for player in guild_players],
                ['Rating'] + [str(player.average_rating) for player in guild_players],
                ['Winrate'] + [player.win_percent for player in guild_players],
                ['Played'] + [str(player.total_maps) for player in guild_players]]
        data[0] = [name if len(name) < 12 else name[:9] + '...' for name in data[0]]  # Shorten long names
        widths = list(map(lambda x: len(max(x, key=len)), data))
        aligns = ['left', 'right', 'right', 'right']
        z = zip(data, widths, aligns)
        formatted_data = [list(map(lambda x: align_text(x, width, align), col)) for col, width, align in z]
        formatted_data = list(map(list, zip(*formatted_data)))  # Transpose list for .format() string

        description = '```ml\n    {}  {}  {}  {} \n'.format(*formatted_data[0])

        for rank, player_row in enumerate(formatted_data[1:], start=1):
            description += ' {}. {}  {}  {}  {} \n'.format(rank, *player_row)

        description += '```'

        # Send leaderboard
        title = f'__{translate("command-leaders-leaderboard")}__'
        embed = self.bot.embed_template(title=title, description=description)
        await ctx.send(embed=embed)

    @commands.command(usage='ban <user mention> ... [<days>d] [<hours>h] [<minutes>m]',
                      brief=translate('command-ban-brief'),
                      aliases=['banned'])
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, *args):
        """"""
        guild_config = await check_setup(self.bot, ctx)
        if len(ctx.message.mentions) == 0:
            msg = translate('command-ban-mention-to-ban')
            raise commands.UserInputError(message=msg)

        time_delta, unban_time = unbantime(ctx.message.content)

        user_ids = [user.id for user in ctx.message.mentions]
        await self.bot.db.insert_banned_users(ctx.guild.id, *user_ids, unban_time=unban_time)

        for user in ctx.message.mentions:
            await user.remove_roles(guild_config.linked_role)

        banned_users_str = ', '.join(f'**{user.display_name}**' for user in ctx.message.mentions)
        ban_time_str = '' if unban_time is None else f' for {timedelta_str(time_delta)}'
        embed = self.bot.embed_template(title=f'Banned {banned_users_str}{ban_time_str}')
        embed.set_footer(text=translate('command-ban-footer'))
        await ctx.send(embed=embed)

        if not self.lobby_cog.check_unbans.is_running():
            self.lobby_cog.check_unbans.start()

    @commands.command(usage='unban <user mention> ...',
                      brief=translate('command-unban-brief'),
                      aliases=['unbanned'])
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx):
        """"""
        guild_config = await check_setup(self.bot, ctx)
        if len(ctx.message.mentions) == 0:
            msg = translate('command-unban-mention-to-unban')
            raise commands.UserInputError(message=msg)

        user_ids = [user.id for user in ctx.message.mentions]
        unbanned_ids = await self.bot.db.delete_banned_users(ctx.guild.id, *user_ids)

        unbanned_users = [user for user in ctx.message.mentions if user.id in unbanned_ids]
        never_banned_users = [user for user in ctx.message.mentions if user.id not in unbanned_ids]
        unbanned_users_str = ', '.join(f'**{user.display_name}**' for user in unbanned_users)
        never_banned_users_str = ', '.join(f'**{user.display_name}**' for user in never_banned_users)
        title_1 = 'nobody' if unbanned_users_str == '' else unbanned_users_str
        were_or_was = 'were' if len(never_banned_users) > 1 else 'was'
        title_2 = '' if never_banned_users_str == '' else f' ({never_banned_users_str} {were_or_was} never banned)'
        embed = self.bot.embed_template(title=f'Unbanned {title_1}{title_2}')
        embed.set_footer(text=translate('command-unban-footer'))
        await ctx.send(embed=embed)

        for user in ctx.message.mentions:
            await user.add_roles(guild_config.linked_role)

    @commands.command(usage='add <match_id> <team1|team2|spec> <mention>',
                      brief=translate('command-add-brief'))
    @commands.has_permissions(kick_members=True)
    async def add(self, ctx, match_id=None, team=None):
        """"""
        guild_config = await check_setup(self.bot, ctx)

        try:
            user = ctx.message.mentions[0]
        except IndexError:
            msg = translate('invalid-usage', self.bot.command_prefix[0], ctx.command.usage)
            raise commands.UserInputError(message=msg)

        if not match_id or team not in ['team1', 'team2', 'spec']:
            msg = translate('invalid-usage', self.bot.command_prefix[0], ctx.command.usage)
            raise commands.UserInputError(message=msg)

        user_data = await get_user_data(self.bot, ctx.guild, user.id)
        if not user_data:
            msg = translate('command-add-not-linked', user.mention)
            raise commands.UserInputError(message=msg)

        match_id = int(match_id)
        status_code = await self.bot.api.add_match_player(user_data, match_id, team, guild_config.auth)
        
        if status_code != 200:
            if status_code == 404:
                msg = translate('command-add-match-not-exist', match_id)
            elif status_code == 403:
                msg = translate('command-add-no-permission')
            elif status_code == 401:
                msg = translate('command-add-already-finished', match_id)
            elif status_code == 500:
                msg = translate('command-add-game-server-error')
            else:
                msg = translate('command-add-unknown-error')
            raise commands.UserInputError(message=msg)

        await self.bot.db.insert_match_users(match_id, [user.id])
        match = await get_match_data(self.bot, match_id)
        await user.remove_roles(guild_config.linked_role)

        if team == 'team1':
            await match.team1_channel.set_permissions(user, connect=True)
            try:
                await user.move_to(match.team1_channel)
            except:
                pass
        elif team == 'team2':
            await match.team2_channel.set_permissions(user, connect=True)
            try:
                await user.move_to(match.team2_channel)
            except:
                pass

        msg = translate('command-add-success', user.mention, match_id)
        embed = self.bot.embed_template(description=msg)
        await ctx.send(embed=embed)

    @commands.command(usage='remove <match_id> <mention>',
                      brief=translate('command-remove-brief'))
    @commands.has_permissions(kick_members=True)
    async def remove(self, ctx, match_id=None):
        """"""
        guild_config = await check_setup(self.bot, ctx)

        try:
            user = ctx.message.mentions[0]
        except IndexError:
            msg = translate('invalid-usage', self.bot.command_prefix[0], ctx.command.usage)
            raise commands.UserInputError(message=msg)

        if not match_id:
            msg = translate('invalid-usage', self.bot.command_prefix[0], ctx.command.usage)
            raise commands.UserInputError(message=msg)

        user_data = await get_user_data(self.bot, ctx.guild, user.id)
        if not user_data:
            msg = translate('command-add-not-linked', user.mention)
            raise commands.UserInputError(message=msg)

        match_id = int(match_id)
        status_code = await self.bot.api.remove_match_player(user_data, match_id, guild_config.auth)
        
        if status_code != 200:
            if status_code == 404:
                msg = translate('command-remove-match-not-exist', match_id)
            elif status_code == 403:
                msg = translate('command-remove-no-permission')
            elif status_code == 401:
                msg = translate('command-remove-already-finished', match_id)
            elif status_code == 500:
                msg = translate('command-remove-game-server-error')
            else:
                msg = translate('command-remove-unknown-error')
            raise commands.UserInputError(message=msg)

        await self.bot.db.delete_match_users(match_id, user.id)
        match = await get_match_data(self.bot, match_id)
        await user.add_roles(guild_config.linked_role)
        await match.team1_channel.set_permissions(user, connect=False)
        await match.team2_channel.set_permissions(user, connect=False)
        try:
            await user.move_to(guild_config.prematch_channel)
        except:
            pass

        msg = translate('command-remove-success', user.mention, match_id)
        embed = self.bot.embed_template(description=msg)
        await ctx.send(embed=embed)

    @commands.command(usage='pause <match_id>',
                      brief=translate('command-pause-brief'))
    @commands.has_permissions(kick_members=True)
    async def pause(self, ctx, match_id=None):
        """"""
        guild_config = await check_setup(self.bot, ctx)

        if not match_id:
            msg = translate('invalid-usage', self.bot.command_prefix[0], ctx.command.usage)
            raise commands.UserInputError(message=msg)

        status_code = await self.bot.api.pause_match(match_id, guild_config.auth)
        
        if status_code != 200:
            if status_code == 404:
                msg = translate('command-pause-not-found', match_id)
            elif status_code == 403:
                msg = translate('command-pause-no-permission')
            elif status_code == 401:
                msg = translate('command-pause-already-finished', match_id)
            else:
                msg = translate('command-pause-unknown-error')
            raise commands.UserInputError(message=msg)

        msg = translate('command-pause-success', match_id)
        embed = self.bot.embed_template(description=msg)
        await ctx.send(embed=embed)

    @commands.command(usage='unpause <match_id>',
                      brief=translate('command-unpause-brief'))
    @commands.has_permissions(kick_members=True)
    async def unpause(self, ctx, match_id=None):
        """"""
        guild_config = await check_setup(self.bot, ctx)

        if not match_id:
            msg = translate('invalid-usage', self.bot.command_prefix[0], ctx.command.usage)
            raise commands.UserInputError(message=msg)

        status_code = await self.bot.api.unpause_match(match_id, guild_config.auth)
        
        if status_code != 200:
            if status_code == 404:
                msg = translate('command-unpause-not-found', match_id)
            elif status_code == 403:
                msg = translate('command-unpause-no-permission')
            elif status_code == 401:
                msg = translate('command-unpause-already-finished', match_id)
            else:
                msg = translate('command-unpause-unknown-error')
            raise commands.UserInputError(message=msg)

        msg = translate('command-unpause-success', match_id)
        embed = self.bot.embed_template(description=msg)
        await ctx.send(embed=embed)

    @setup.error
    @lobby.error
    @link.error
    @unlink.error
    @cap.error
    @empty.error
    @teams.error
    @captains.error
    @maps.error
    @mpool.error
    @spectators.error
    @end.error
    @stats.error
    @ban.error
    @unban.error
    @add.error
    @remove.error
    @pause.error
    @unpause.error
    async def config_error(self, ctx, error):
        """"""
        if isinstance(error, commands.MissingPermissions):
            await ctx.trigger_typing()
            missing_perm = error.missing_perms[0].replace('_', ' ')
            embed = self.bot.embed_template(title=translate('command-required-perm', missing_perm),
                                            color=self.bot.colors['red'])
            await ctx.send(embed=embed)

        if isinstance(error, commands.UserInputError):
            await ctx.trigger_typing()
            embed = self.bot.embed_template(description='**' + str(error) + '**', color=self.bot.colors['red'])
            await ctx.send(embed=embed)
