# lobby.py

from discord.ext import commands, tasks
from discord.errors import NotFound
from discord.utils import get
from collections import defaultdict
from datetime import datetime, timezone
import asyncio

from .message import ReadyMessage
from .utils.utils import *


class LobbyCog(commands.Cog):
    """"""
    def __init__(self, bot):
        """"""
        self.bot = bot
        self.locked_lobby = {}
        self.locked_lobby = defaultdict(lambda: False, self.locked_lobby)

    async def queue_embed(self, pug_data, title=None, queued_ids=None):
        """"""
        if queued_ids is None:
            queued_ids = await self.bot.db.get_queued_users(pug_data.id)

        if title:
            title += f' ({len(queued_ids)}/{pug_data.capacity})'

        if len(queued_ids) == 0:
            queue_str = translate('lobby-is-empty')
        else:
            queued_users = [pug_data.guild.get_member(user_id) for user_id in queued_ids]
            queue_str = ''.join(
                f'{num}. {user.mention}\n' for num, user in enumerate(queued_users, start=1))

        embed = self.bot.embed_template(title=title, description=queue_str)
        embed.set_footer(text=translate('lobby-footer'))
        return embed

    async def update_last_msg(self, pug_data, embed):
        """"""
        msg = pug_data.last_message

        try:
            await msg.edit(embed=embed)
        except (AttributeError, NotFound):
            msg = await pug_data.queue_channel.send(embed=embed)
            await self.bot.db.update_pug(pug_data.id, last_message=msg.id)

    async def check_ready(self, message, users, guild_data):
        """"""
        menu = ReadyMessage(message, self.bot, users, guild_data)
        ready_users = await menu.ready_up()
        return ready_users

    @commands.Cog.listener()
    async def on_voice_state_update(self, user, before, after):
        """"""
        if before.channel == after.channel:
            return

        if before.channel is not None:
            before_pug_data = await get_pug_data(self.bot, before.channel.id, 'lobby_channel')
            if before_pug_data is not None and before.channel == before_pug_data.lobby_channel:
                if not self.locked_lobby[before_pug_data.id]:
                    removed = await self.bot.db.delete_queued_users(before_pug_data.id, user.id)

                    if user.id in removed:
                        title = translate('lobby-user-removed', user.display_name)
                    else:
                        title = translate('lobby-user-not-in-lobby', user.display_name)

                    embed = await self.queue_embed(before_pug_data, title)
                    await self.update_last_msg(before_pug_data, embed)

        if after.channel is not None:
            after_pug_data = await get_pug_data(self.bot, after.channel.id, 'lobby_channel')
            if after_pug_data is not None and after.channel == after_pug_data.lobby_channel:
                if not self.locked_lobby[after_pug_data.id]:
                    awaitables = []
                    for pug_id in await self.bot.db.get_guild_pugs(after.channel.guild.id):
                        if pug_id != after_pug_data.id:
                            awaitables.append(self.bot.db.get_queued_users(pug_id))
                    others_queued_ids = await asyncio.gather(*awaitables, loop=self.bot.loop)
                    others_queued_ids = sum(others_queued_ids, [])

                    awaitables = [
                        get_user_data(self.bot, user.guild, user.id),
                        self.bot.db.get_queued_users(after_pug_data.id),
                        self.bot.db.get_spect_users(after_pug_data.id),
                        self.bot.db.get_banned_users(after.channel.guild.id),
                        self.bot.db.get_all_matches_users()
                    ]
                    results = await asyncio.gather(*awaitables, loop=self.bot.loop)
                    is_linked = results[0]
                    queued_ids = results[1]
                    spect_ids = results[2]
                    banned_users = results[3]
                    matches_users = results[4]

                    if not is_linked:
                        title = translate('lobby-user-not-linked', user.display_name)
                    elif user.id in banned_users:
                        title = translate('lobby-user-is-banned', user.display_name)
                        unban_time = banned_users[user.id]
                        if unban_time is not None:
                            title += f' for {timedelta_str(unban_time - datetime.now(timezone.utc))}'
                    elif user.id in queued_ids:
                        title = translate('lobby-user-in-lobby', user.display_name)
                    elif user.id in matches_users:
                        title = translate('lobby-user-in-match', user.display_name)
                    elif user.id in others_queued_ids:
                        title = translate('lobby-user-in-another-lobby', user.display_name)
                    elif user.id in spect_ids:
                        title = translate('lobby-user-in-spectators', user.display_name)
                    elif len(queued_ids) >= after_pug_data.capacity:
                        title = translate('lobby-is-full', user.display_name)
                    else:
                        await self.bot.db.insert_queued_users(after_pug_data.id, user.id)
                        queued_ids += [user.id]
                        title = translate('lobby-user-added', user.display_name)

                        if len(queued_ids) == after_pug_data.capacity:
                            self.locked_lobby[after_pug_data.id] = True

                            match_cog = self.bot.get_cog('MatchCog')
                            guild_data = await get_guild_data(self.bot, after.channel.guild.id)
                            linked_role = guild_data.linked_role
                            prematch_channel = guild_data.prematch_channel
                            queue_channel = after_pug_data.queue_channel
                            queued_users = [user.guild.get_member(user_id) for user_id in queued_ids]

                            await after.channel.set_permissions(linked_role, connect=False)

                            queue_msg = after_pug_data.last_message
                            if queue_msg is not None:
                                try:
                                    await queue_msg.delete()
                                except (NotFound, AttributeError):
                                    pass

                            ready_msg = await queue_channel.send(''.join([user.mention for user in queued_users]))
                            ready_users = await self.check_ready(ready_msg, queued_users, guild_data)
                            await asyncio.sleep(1)
                            unreadied = set(queued_users) - ready_users

                            if unreadied:
                                description = ''.join(f':x: {user.mention}\n' for user in unreadied)
                                title = translate('lobby-not-all-ready')
                                burst_embed = self.bot.embed_template(title=title, description=description,
                                                                      color=self.bot.colors['red'])
                                burst_embed.set_footer(text=translate('lobby-unready-footer'))

                                awaitables = [
                                    ready_msg.clear_reactions(),
                                    ready_msg.edit(content='', embed=burst_embed),
                                    self.bot.db.delete_queued_users(after_pug_data.id,
                                                                    *(user.id for user in unreadied))
                                ]

                                for user in queued_users:
                                    awaitables.append(user.add_roles(linked_role))
                                for user in unreadied:
                                    awaitables.append(user.move_to(prematch_channel))
                                await asyncio.gather(*awaitables, loop=self.bot.loop, return_exceptions=True)
                            else:
                                await ready_msg.clear_reactions()
                                new_match = await match_cog.start_match(queued_users, ready_msg, after_pug_data,
                                                                        guild_data)
                                if new_match:
                                    await self.bot.db.clear_queued_users(after_pug_data.id)
                                else:
                                    awaitables = [self.bot.db.clear_queued_users(after_pug_data.id)]
                                    for user in queued_users:
                                        awaitables.append(user.add_roles(linked_role))
                                    for user in queued_users:
                                        awaitables.append(user.move_to(prematch_channel))
                                    await asyncio.gather(*awaitables, loop=self.bot.loop, return_exceptions=True)

                            title = translate('lobby-players-in-lobby')
                            embed = await self.queue_embed(after_pug_data, title)
                            await self.update_last_msg(after_pug_data, embed)

                            self.locked_lobby[after_pug_data.id] = False
                            await after_pug_data.lobby_channel.set_permissions(linked_role, connect=True)
                            return

                    embed = await self.queue_embed(after_pug_data, title)
                    await self.update_last_msg(after_pug_data, embed)

    @tasks.loop(seconds=30.0)
    async def check_unbans(self):
        there_banned_users = False
        unbanned_users = {}
        for guild in self.bot.guilds:
            guild_data = await get_guild_data(self.bot, guild.id)
            guild_bans = await self.bot.db.get_banned_users(guild.id)

            if guild_bans:
                there_banned_users = True
                guild_unbanned_users = await self.bot.db.get_unbanned_users(guild.id)
                unbanned_users[guild] = guild_unbanned_users

                for user_ids in unbanned_users[guild]:
                    users = [get(guild.members, id=user_id) for user_id in user_ids]
                    for user in users:
                        await user.add_roles(guild_data.linked_role)

        if not there_banned_users:
            self.check_unbans.cancel()
