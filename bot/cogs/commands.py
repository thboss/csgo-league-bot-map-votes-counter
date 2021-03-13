# commands.py

from discord.ext import commands
from discord.utils import get
from steam.steamid import SteamID, from_url
from iso3166 import countries
import asyncio

from .message import MapPoolMessage
from .utils.utils import (translate, timedelta_str, unbantime, check_channel,
                          check_pug, get_guild_config, get_user_config)


class CommandsCog(commands.Cog):
    """"""

    def __init__(self, bot):
        self.bot = bot
        self.lobby_cog = self.bot.get_cog('LobbyCog')

    @commands.command(brief=translate('command-setup-brief'))
    @commands.has_permissions(kick_members=True)
    async def setup(self, ctx):
        """"""
        def check(msg):
            return msg.author.id == ctx.author.id

        msg = translate('command-setup-enter-userid', self.bot.web_url)
        embed = self.bot.embed_template(description=msg)
        footer = translate('command-setup-footer')
        embed.set_footer(text=footer)
        await ctx.send(embed=embed)

        try:
            msg = await self.bot.wait_for('message', check=check, timeout=60.0)
        except asyncio.TimeoutError:
            msg = translate('command-setup-no-answer')
            raise commands.UserInputError(message=msg)

        user_id = int(msg.content)

        is_user = await self.bot.api.is_user(user_id)
        if not is_user:
            msg = translate('command-setup-user-invalid')
            raise commands.UserInputError(message=msg)

        msg = translate('command-setup-user-valid')
        embed = self.bot.embed_template(description=msg)
        await ctx.send(embed=embed)

        msg = translate('command-setup-enter-key', self.bot.web_url)
        embed = self.bot.embed_template(description=msg)
        embed.set_footer(text=footer)
        await ctx.send(embed=embed)

        try:
            msg = await self.bot.wait_for('message', check=check, timeout=60.0)
        except asyncio.TimeoutError:
            msg = translate('command-setup-no-answer')
            raise commands.UserInputError(message=msg)

        api_key = msg.content
        auth = {'user_id': user_id, 'api_key': api_key}

        is_valid = await self.bot.api.check_auth(auth)
        if not is_valid:
            msg = translate('command-setup-key-invalid')
            raise commands.UserInputError(message=msg)

        msg = translate('command-setup-key-valid')
        embed = self.bot.embed_template(description=msg)
        await ctx.send(embed=embed)

        guild_config = await get_guild_config(self.bot, ctx.guild.id)
        linked_role = guild_config.linked_role
        afk_channel = guild_config.afk_channel
        commands_channel = guild_config.commands_channel
        g5_category = guild_config.g5_category

        if not g5_category:
            g5_category = await ctx.guild.create_category_channel(name='G5')
        if not linked_role:
            linked_role = await ctx.guild.create_role(name='Linked')
        if not afk_channel:
            afk_channel = await ctx.guild.create_voice_channel(name='G5 AFK', category=g5_category)
        if not commands_channel:
            commands_channel = await ctx.guild.create_text_channel(name='g5-commands', category=g5_category)

        guild_data = {
            'linked_role': linked_role.id,
            'afk_channel': afk_channel.id,
            'commands_channel': commands_channel.id,
            'g5_category': g5_category.id,
            'user_id': user_id,
            'api_key': api_key
        }

        await self.bot.db.update_guild(ctx.guild.id, **guild_data)

        msg = translate('command-setup-completed')
        embed = self.bot.embed_template(description=msg)
        await ctx.send(embed=embed)

    @commands.command(usage='lobby <name>',
                      brief=translate('command-lobby-brief'))
    @commands.has_permissions(kick_members=True)
    async def lobby(self, ctx, *args):
        """"""
        guild_config = await check_channel(self.bot, ctx)

        args = ' '.join(arg for arg in args)

        if not len(args):
            msg = translate('invalid-usage', self.bot.command_prefix[0], ctx.command.usage)
            raise commands.UserInputError(message=msg)

        g5_category = guild_config.g5_category
        linked_role = guild_config.linked_role
        everyone_role = get(ctx.guild.roles, name='@everyone')

        awaitables = [
            ctx.guild.create_text_channel(name=f'{args}-setup', category=g5_category),
            ctx.guild.create_voice_channel(name=f'{args} Lobby', category=g5_category, user_limit=10),
            self.bot.db.insert_pugs(),
        ]
        results = await asyncio.gather(*awaitables, loop=self.bot.loop)

        setup_channel = results[0]
        lobby_channel = results[1]

        awaitables = [
            self.bot.db.update_pug(results[2][0], guild=ctx.guild.id,
                setup_channel=setup_channel.id,
                lobby_channel=lobby_channel.id),
            setup_channel.set_permissions(everyone_role, send_messages=False),
            lobby_channel.set_permissions(everyone_role, connect=False),
            lobby_channel.set_permissions(linked_role, connect=True)
        ]
        await asyncio.gather(*awaitables, loop=self.bot.loop)

        msg = translate('command-lobby-success', args)

        embed = self.bot.embed_template(title=msg, color=self.bot.colors['green'])
        await ctx.send(embed=embed)

    @commands.command(usage='link <Steam ID/Profile> <flag>',
                      brief=translate('command-link-brief'))
    async def link(self, ctx, *args):
        """"""
        guild_config = await check_channel(self.bot, ctx)
        user_config = await get_user_config(self.bot, ctx.author.id)
        if user_config is not None:
            msg = translate('command-link-already-linked', user_config.steam)
            raise commands.UserInputError(message=msg)

        try:
            steam_id = SteamID(args[0])
            flag = countries.get(args[1]).alpha2
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

        user_config = await get_user_config(self.bot, str(steam_id), 'steam_id')
        if user_config is not None:
            msg = translate('command-link-steam-used')
            raise commands.UserInputError(message=msg)

        await self.bot.db.insert_users(ctx.author.id, str(steam_id), flag)
        await ctx.author.add_roles(guild_config.linked_role)

        title = translate('command-link-success', ctx.author.display_name, steam_id)
        embed = self.bot.embed_template(description=title)
        await ctx.send(embed=embed)

    @commands.command(brief=translate('command-unlink-brief'))
    async def unlink(self, ctx):
        """"""
        guild_config = await check_channel(self.bot, ctx)

        await self.bot.db.delete_users([ctx.author.id])
        await ctx.author.remove_roles(guild_config.linked_role)

        title = translate('command-unlink-success', ctx.author)
        embed = self.bot.embed_template(title=title)
        await ctx.send(embed=embed)

    @commands.command(usage='empty <voice lobby id>',
                      brief=translate('command-empty-brief'))
    @commands.has_permissions(kick_members=True)
    async def empty(self, ctx, lobby_id=None):
        """"""
        await check_channel(self.bot, ctx)
        pug_config = await check_pug(self.bot, ctx, lobby_id)

        guild_config = await get_guild_config(self.bot, ctx.guild.id)
        self.lobby_cog.block_lobby[pug_config.id] = True
        await self.bot.db.clear_queued_users(pug_config.id)
        msg = translate('command-empty-success')
        embed = await self.lobby_cog.queue_embed(pug_config, msg)
        await self.lobby_cog.update_last_msg(pug_config, embed)

        lobby_channel = pug_config.lobby_channel

        for member in lobby_channel.members:
            await member.move_to(guild_config.afk_channel)

        self.lobby_cog.block_lobby[pug_config.id] = False
        _embed = self.bot.embed_template(title=msg)
        await ctx.send(embed=_embed)

    @commands.command(usage='cap <voice lobby id> <new capacity>',
                      brief=translate('command-cap-brief'),
                      aliases=['capacity'])
    @commands.has_permissions(kick_members=True)
    async def cap(self, ctx, lobby_id=None, cap=None):
        """"""
        await check_channel(self.bot, ctx)
        pug_config = await check_pug(self.bot, ctx, lobby_id)

        capacity = pug_config.capacity

        try:
            new_cap = int(cap)
        except (ValueError, TypeError):
            msg = translate('invalid-usage', self.bot.command_prefix[0], ctx.command.usage)
            raise commands.UserInputError(message=msg)

        if new_cap == capacity:
            msg = translate('command-cap-already', capacity)
            raise commands.UserInputError(message=msg)

        if new_cap < 2 or new_cap > 100:
            msg = translate('command-cap-out-range')
            raise commands.UserInputError(message=msg)

        self.lobby_cog.block_lobby[pug_config.id] = True
        await self.bot.db.clear_queued_users(pug_config.id)
        await self.bot.db.update_pug(pug_config.id, capacity=new_cap)
        embed = await self.lobby_cog.queue_embed(pug_config, translate('command-empty-success'))
        embed.set_footer(text=translate('command-cap-footer'))
        await self.lobby_cog.update_last_msg(pug_config, embed)
        msg = translate('command-cap-success', new_cap)

        guild_config = await get_guild_config(self.bot, ctx.guild.id)
        lobby_channel = pug_config.lobby_channel

        awaitables = []
        for player in lobby_channel.members:
            awaitables.append(player.move_to(guild_config.afk_channel))
        awaitables.append(lobby_channel.edit(user_limit=new_cap))
        await asyncio.gather(*awaitables, loop=self.bot.loop, return_exceptions=True)

        self.lobby_cog.block_lobby[pug_config.id] = False

        embed = self.bot.embed_template(title=msg)
        await ctx.send(embed=embed)

    @commands.command(usage='teams <voice lobby id> <captains|random>',
                      brief=translate('command-teams-brief'),
                      aliases=['team'])
    @commands.has_permissions(kick_members=True)
    async def teams(self, ctx, lobby_id=None, method=None):
        """"""
        await check_channel(self.bot, ctx)
        pug_config = await check_pug(self.bot, ctx, lobby_id)

        team_method = pug_config.team_method
        valid_methods = ['autobalance', 'captains', 'random']

        if method is None:
            title = translate('command-teams-method', team_method)
        else:
            method = method.lower()

            if method == team_method:
                msg = translate('command-teams-already', team_method)
                raise commands.UserInputError(message=msg)

            if method not in valid_methods:
                msg = translate('command-teams-invalid', valid_methods[0], valid_methods[1])
                raise commands.UserInputError(message=msg)

            title = translate('command-teams-changed', method)
            await self.bot.db.update_pug(pug_config.id, team_method=method)

        embed = self.bot.embed_template(title=title)
        await ctx.send(embed=embed)

    @commands.command(usage='captains <voice lobby id> <volunteer|random>',
                      brief=translate('command-captains-brief'),
                      aliases=['captain', 'picker', 'pickers'])
    @commands.has_permissions(kick_members=True)
    async def captains(self, ctx, lobby_id=None, method=None):
        """"""
        await check_channel(self.bot, ctx)
        pug_config = await check_pug(self.bot, ctx, lobby_id)

        captain_method = pug_config.captain_method
        valid_methods = ['volunteer', 'rank', 'random']

        if method is None:
            title = translate('command-captains-method', captain_method)
        else:
            method = method.lower()

            if method == captain_method:
                msg = translate('command-captains-already', captain_method)
                raise commands.UserInputError(message=msg)

            if method not in valid_methods:
                msg = translate('command-captains-invalid', valid_methods[0], valid_methods[1])
                raise commands.UserInputError(message=msg)

            title = translate('command-captains-changed', method)
            await self.bot.db.update_pug(pug_config.id, captain_method=method)

        embed = self.bot.embed_template(title=title)
        await ctx.send(embed=embed)

    @commands.command(usage='maps <voice lobby id> <ban|vote|random>',
                      brief=translate('command-maps-brief'),
                      aliases=['map'])
    @commands.has_permissions(kick_members=True)
    async def maps(self, ctx, lobby_id=None, method=None):
        """"""
        await check_channel(self.bot, ctx)
        pug_config = await check_pug(self.bot, ctx, lobby_id)

        map_method = pug_config.map_method
        valid_methods = ['ban', 'vote', 'random']

        if method is None:
            title = translate('command-maps-method', map_method)
        else:
            method = method.lower()

            if method == map_method:
                msg = translate('command-maps-already', map_method)
                raise commands.UserInputError(message=msg)

            if method not in valid_methods:
                msg = translate('command-maps-invalid', valid_methods[0], valid_methods[1], valid_methods[2])
                raise commands.UserInputError(message=msg)

            title = translate('command-maps-changed', method)
            await self.bot.db.update_pug(pug_config.id, map_method=method)

        embed = self.bot.embed_template(title=title)
        await ctx.send(embed=embed)

    @commands.command(usage='mpool <voice lobby id>',
                      brief=translate('command-mpool-brief'),
                      aliases=['mappool', 'pool'])
    @commands.has_permissions(kick_members=True)
    async def mpool(self, ctx, lobby_id=None):
        """"""
        await check_channel(self.bot, ctx)
        pug_config = await check_pug(self.bot, ctx, lobby_id)
        message = await ctx.send('Map Pool')
        menu = MapPoolMessage(message, self.bot, ctx.author, pug_config)
        await menu.pick()

    @commands.command(usage='spectators <voice lobby id> {+|-} <mention> <mention> ...',
                      brief=translate('command-spectators-brief'),
                      aliases=['spec', 'spectator'])
    async def spectators(self, ctx, lobby_id=None, prefix=None):
        """"""
        await check_channel(self.bot, ctx)
        pug_config = await check_pug(self.bot, ctx, lobby_id)

        curr_spectator_ids = await self.bot.db.get_spect_users(pug_config.id)
        curr_spectators = [ctx.guild.get_member(spectator_id) for spectator_id in curr_spectator_ids]
        spectators = ctx.message.mentions

        if prefix is None:
            embed = self.bot.embed_template()
            embed.add_field(name='__Spectators__',
                            value='No spectators' if not curr_spectators else ''.join(f'{num}. {user.mention}\n'
                                for num, user in enumerate(curr_spectators, start=1)))
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

    @commands.command(usage='end <voice lobby id> <match id>',
                      brief=translate('command-end-brief'),
                      aliases=['cancel', 'stop'])
    @commands.has_permissions(kick_members=True)
    async def end(self, ctx, match_id=None):
        """"""
        guild_config = await check_channel(self.bot, ctx)
        if match_id is None:
            msg = translate('invalid-usage', self.bot.command_prefix[0], ctx.command.usage)
            raise commands.UserInputError(message=msg)

        try:
            await self.bot.api.cancel_match(match_id, guild_config.auth)
        except Exception as e:
            print(e)
            msg = translate('command-end-invalid-id', match_id)
            raise commands.UserInputError(message=msg)

        title = translate('command-end-canceled', match_id)

        embed = self.bot.embed_template(title=title)
        await ctx.send(embed=embed)

    @commands.command(usage='ban <user mention> ... [<days>d] [<hours>h] [<minutes>m]',
                      brief=translate('command-ban-brief'),
                      aliases=['banned'])
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, *args):
        """"""
        guild_config = await check_channel(self.bot, ctx)

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
        guild_config = await check_channel(self.bot, ctx)

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
            if await self.bot.api.is_linked(user.id):
                await user.add_roles(guild_config.linked_role)

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
    @ban.error
    @unban.error
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
