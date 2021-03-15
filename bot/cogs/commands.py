# commands.py

from discord.ext import commands
from discord.utils import get
from steam.steamid import SteamID, from_url
from iso3166 import countries
import re
import asyncio

from .message import MapPoolMessage
from .utils.utils import (translate, timedelta_str, unbantime, check_channel,
                          check_pug, get_guild_config, get_user_config, align_text)


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
            ctx.guild.create_text_channel(name=f'{args}-queue', category=g5_category),
            ctx.guild.create_voice_channel(name=f'{args} Lobby', category=g5_category, user_limit=10),
            self.bot.db.insert_pugs(),
        ]
        results = await asyncio.gather(*awaitables, loop=self.bot.loop)

        queue_channel = results[0]
        lobby_channel = results[1]

        awaitables = [
            self.bot.db.update_pug(results[2][0], guild=ctx.guild.id,
                                                    queue_channel=queue_channel.id,
                                                    lobby_channel=lobby_channel.id),
            queue_channel.set_permissions(everyone_role, send_messages=False),
            lobby_channel.set_permissions(everyone_role, connect=False),
            lobby_channel.set_permissions(linked_role, connect=True)
        ]
        await asyncio.gather(*awaitables, loop=self.bot.loop)

        msg = translate('command-lobby-success', args)

        embed = self.bot.embed_template(title=msg, color=self.bot.colors['green'])
        await ctx.send(embed=embed)

    @commands.command(usage='link <Steam ID/Profile> <country_flag_code>',
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
        embed = self.bot.embed_template(description=title, color=self.bot.colors['green'])
        await ctx.send(embed=embed)

    @commands.command(brief=translate('command-unlink-brief'))
    async def unlink(self, ctx):
        """"""
        guild_config = await check_channel(self.bot, ctx)

        await self.bot.db.delete_users([ctx.author.id])
        await ctx.author.remove_roles(guild_config.linked_role)

        title = translate('command-unlink-success', ctx.author)
        embed = self.bot.embed_template(title=title, color=self.bot.colors['green'])
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

        await check_channel(self.bot, ctx)
        pug_config = await check_pug(self.bot, ctx, queue_id)
        guild_config = await get_guild_config(self.bot, ctx.guild.id)
        lobby_channel = pug_config.lobby_channel

        if self.lobby_cog.locked_lobby[pug_config.id]:
            msg = translate('command-empty-locked')
            raise commands.UserInputError(message=msg)

        self.lobby_cog.locked_lobby[pug_config.id] = True
        await self.bot.db.clear_queued_users(pug_config.id)
        msg = translate('command-empty-success')
        embed = await self.lobby_cog.queue_embed(pug_config, msg)
        await self.lobby_cog.update_last_msg(pug_config, embed)

        for member in lobby_channel.members:
            await member.move_to(guild_config.afk_channel)

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

        await check_channel(self.bot, ctx)
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

        guild_config = await get_guild_config(self.bot, ctx.guild.id)
        lobby_channel = pug_config.lobby_channel

        awaitables = []
        for player in lobby_channel.members:
            awaitables.append(player.move_to(guild_config.afk_channel))
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

        await check_channel(self.bot, ctx)
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

        await check_channel(self.bot, ctx)
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

        await check_channel(self.bot, ctx)
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

        await check_channel(self.bot, ctx)
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

        await check_channel(self.bot, ctx)
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
        guild_config = await check_channel(self.bot, ctx)
        if match_id is None:
            msg = translate('invalid-usage', self.bot.command_prefix[0], ctx.command.usage)
            raise commands.UserInputError(message=msg)

        try:
            await self.bot.api.cancel_match(match_id, guild_config.auth)
        except:
            msg = translate('command-end-invalid-id', match_id)
            raise commands.UserInputError(message=msg)

        title = translate('command-end-canceled', match_id)

        embed = self.bot.embed_template(title=title)
        await ctx.send(embed=embed)

    @commands.command(brief=translate('command-stats-brief'),
                      aliases=['rank'])
    async def stats(self, ctx):
        """"""
        guild_config = await check_channel(self.bot, ctx)
        user = ctx.author
        player = await self.bot.api.players_stats([user])
        player_stats = dict(player[0].__dict__)
        player_stats.pop('steam')
        player_stats.pop('discord')
        embed = self.bot.embed_template()

        for attr in list(player_stats):
            state = attr.capitalize().replace('_', ' ')
            if len(state) < 4:
                state = state.upper()
            player_stats[state] = player_stats.pop(attr)
            embed.add_field(name=state, value=player_stats[state])

        embed.set_author(name=user.display_name, url=player[0].profile, icon_url=user.avatar_url_as(size=128))
        await ctx.send(embed=embed)

    @commands.command(brief=translate('command-leaders-brief'),
                      aliases=['top', 'ranks'])
    async def leaders(self, ctx):
        """"""
        await check_channel(self.bot, ctx)

        num = 10
        guild_players = await self.bot.api.players_stats(ctx.guild.members)
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
