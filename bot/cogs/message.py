# message.py

import asyncio
import discord
from random import shuffle, choice

from . import utils


EMOJI_NUMBERS = [u'\u0030\u20E3',
                 u'\u0031\u20E3',
                 u'\u0032\u20E3',
                 u'\u0033\u20E3',
                 u'\u0034\u20E3',
                 u'\u0035\u20E3',
                 u'\u0036\u20E3',
                 u'\u0037\u20E3',
                 u'\u0038\u20E3',
                 u'\u0039\u20E3',
                 u'\U0001F51F']


class ReadyMessage(discord.Message):
    def __init__(self, message, bot, users, guild_data):
        """"""
        for attr_name in message.__slots__:
            try:
                attr_val = getattr(message, attr_name)
            except AttributeError:
                continue

            setattr(self, attr_name, attr_val)

        self.bot = bot
        self.users = users
        self.guild_data = guild_data
        self.reactors = None
        self.future = None

    def _ready_embed(self):
        """"""
        str_value = ''
        description = utils.translate('message-react-ready', '✅')
        embed = self.bot.embed_template(title=utils.translate('message-lobby-filled-up'), description=description)

        for num, user in enumerate(self.users, start=1):
            if user not in self.reactors:
                str_value += f':heavy_multiplication_x:  {num}. {user.mention}\n '
            else:
                str_value += f'✅  {num}. {user.mention}\n '

        embed.add_field(name=f":hourglass: __{utils.translate('message-player')}__",
                        value='-------------------\n' + str_value)
        return embed

    async def _process_ready(self, reaction, user):
        """"""
        if reaction.message.id != self.id or user == self.author:
            return

        if user not in self.users or reaction.emoji != '✅':
            await self.remove_reaction(reaction, user)
            return

        self.reactors.add(user)
        await self.edit(embed=self._ready_embed())

        if self.reactors.issuperset(self.users):
            if self.future is not None:
                try:
                    self.future.set_result(None)
                except asyncio.InvalidStateError:
                    pass

    async def ready_up(self):
        """"""
        self.reactors = set()
        self.future = self.bot.loop.create_future()
        await self.edit(embed=self._ready_embed())
        await self.add_reaction('✅')

        self.bot.add_listener(self._process_ready, name='on_reaction_add')

        awaitables = []
        for user in self.users:
            awaitables.append(user.remove_roles(self.guild_data.linked_role))
        await asyncio.gather(*awaitables, loop=self.bot.loop, return_exceptions=True)

        try:
            await asyncio.wait_for(self.future, 60)
        except asyncio.TimeoutError:
            pass

        self.bot.remove_listener(self._process_ready, name='on_reaction_add')

        return self.reactors


class TeamDraftMessage(discord.Message):
    """"""
    def __init__(self, message, bot, users, pug_data):
        """"""
        for attr_name in message.__slots__:
            try:
                attr_val = getattr(message, attr_name)
            except AttributeError:
                continue

            setattr(self, attr_name, attr_val)

        self.bot = bot
        self.users = users
        self.pug_data = pug_data
        self.pick_emojis = dict(zip(EMOJI_NUMBERS[1:], users))
        self.pick_order = '1' + '2211'*20
        self.pick_number = None
        self.users_left = None
        self.teams = None
        self.captains_emojis = None
        self.future = None
        self.title = None

    @property
    def _active_picker(self):
        """"""
        if self.pick_number is None:
            return None

        picking_team_number = int(self.pick_order[self.pick_number])
        picking_team = self.teams[picking_team_number - 1]

        if len(picking_team) == 0:
            return None

        return picking_team[0]

    def _picker_embed(self, title):
        """"""
        embed = self.bot.embed_template(title=title)
        embed.set_footer(text=utils.translate('message-team-pick-footer'))

        for team in self.teams:
            team_name = f'__{utils.translate("match-team")}__' if len(
                team) == 0 else f'__{utils.translate("match-team", team[0].display_name)}__'

            if len(team) == 0:
                team_players = utils.translate("message-team-empty")
            else:
                team_players = '\n'.join(p.display_name for p in team)

            embed.add_field(name=team_name, value=team_players)

        users_left_str = ''

        for index, (emoji, user) in enumerate(self.pick_emojis.items()):
            if not any(user in team for team in self.teams):
                users_left_str += f'{emoji}  {user.mention}\n'
            else:
                users_left_str += f':heavy_multiplication_x:  ~~{user.mention}~~\n'

        embed.insert_field_at(1, name=utils.translate("message-players-left"), value=users_left_str)

        status_str = ''

        status_str += f'{utils.translate("message-capt1", self.teams[0][0].mention)}\n' if len(
            self.teams[0]) else f'{utils.translate("message-capt1")}\n '

        status_str += f'{utils.translate("message-capt2", self.teams[1][0].mention)}\n\n' if len(
            self.teams[1]) else f'{utils.translate("message-capt2")}\n\n '

        status_str += utils.translate("message-current-capt", self._active_picker.mention) \
            if self._active_picker is not None else utils.translate("message-current-capt")

        embed.add_field(name=utils.translate("message-info"), value=status_str)
        return embed

    def _pick_player(self, picker, pickee):
        """"""
        if picker == pickee:
            return False
        elif not self.teams[0]:
            picking_team = self.teams[0]
            self.captains_emojis.append(list(self.pick_emojis.keys())[list(self.pick_emojis.values()).index(picker)])
            self.users_left.remove(picker)
            picking_team.append(picker)
        elif self.teams[1] == [] and picker == self.teams[0][0]:
            return False
        elif self.teams[1] == [] and picker in self.teams[0]:
            return False
        elif not self.teams[1]:
            picking_team = self.teams[1]
            self.captains_emojis.append(list(self.pick_emojis.keys())[list(self.pick_emojis.values()).index(picker)])
            self.users_left.remove(picker)
            picking_team.append(picker)
        elif picker == self.teams[0][0]:
            picking_team = self.teams[0]
        elif picker == self.teams[1][0]:
            picking_team = self.teams[1]
        else:
            return False

        if picker != self._active_picker:
            return False

        if len(picking_team) > len(self.users) // 2:
            return False

        self.users_left.remove(pickee)
        picking_team.append(pickee)
        self.pick_number += 1
        return True

    async def _process_pick(self, reaction, user):
        """"""
        if reaction.message.id != self.id or user == self.author:
            return

        pick = self.pick_emojis.get(str(reaction.emoji), None)

        if pick is None or pick not in self.users_left or user not in self.users:
            await self.remove_reaction(reaction, user)
            return

        if not self._pick_player(user, pick):
            await self.remove_reaction(reaction, user)
            return

        await self.clear_reaction(reaction.emoji)
        title = utils.translate('message-team-picked', user.display_name, pick.display_name)

        if len(self.users) - len(self.users_left) == 2:
            await self.clear_reaction(self.captains_emojis[0])
        elif len(self.users) - len(self.users_left) == 4:
            await self.clear_reaction(self.captains_emojis[1])

        if len(self.users_left) == 1:
            fat_kid_team = self.teams[0] if len(self.teams[0]) <= len(self.teams[1]) else self.teams[1]
            fat_kid_team.append(self.users_left.pop(0))
            await self.edit(embed=self._picker_embed(title))
            if self.future is not None:
                try:
                    self.future.set_result(None)
                except asyncio.InvalidStateError:
                    pass
            return

        if len(self.users_left) == 0:
            await self.edit(embed=self._picker_embed(title))
            if self.future is not None:
                try:
                    self.future.set_result(None)
                except asyncio.InvalidStateError:
                    pass
            return

        await self.edit(embed=self._picker_embed(title))

    async def draft(self):
        """"""
        self.users_left = self.users.copy()
        self.teams = [[], []]
        self.pick_number = 0
        self.captains_emojis = []
        captain_method = self.pug_data.captain_method

        if captain_method == 'rank':
            users_dict = dict(zip(await self.bot.api.leaderboard(self.users_left), self.users_left))
            players = list(users_dict.keys())
            players.sort(key=lambda x: x.average_rating)

            for team in self.teams:
                player = [players.pop()]
                captain = list(map(users_dict.get, player))
                self.users_left.remove(captain[0])
                team.append(captain[0])
                captain_emoji_index = list(self.pick_emojis.values()).index(captain[0])
                self.captains_emojis.append(list(self.pick_emojis.keys())[captain_emoji_index])
        elif captain_method == 'random':
            temp_users = self.users_left.copy()
            shuffle(temp_users)

            for team in self.teams:
                captain = temp_users.pop()
                self.users_left.remove(captain)
                team.append(captain)
                captain_emoji_index = list(self.pick_emojis.values()).index(captain)
                self.captains_emojis.append(list(self.pick_emojis.keys())[captain_emoji_index])
        else:  # captain_method is volunteer
            pass

        await self.edit(embed=self._picker_embed(utils.translate('message-team-draft-begun')))

        if self.users_left:
            for emoji, user in self.pick_emojis.items():
                if user in self.users_left:
                    await self.add_reaction(emoji)

            self.future = self.bot.loop.create_future()
            self.bot.add_listener(self._process_pick, name='on_reaction_add')
            try:
                await asyncio.wait_for(self.future, 180)
            except asyncio.TimeoutError:
                self.bot.remove_listener(self._process_pick, name='on_reaction_add')
                await self.clear_reactions()
                raise

        await self.clear_reactions()
        return self.teams


class MapVetoMessage(discord.Message):
    """"""
    def __init__(self, message, bot):
        """"""
        for attr_name in message.__slots__:
            try:
                attr_val = getattr(message, attr_name)
            except AttributeError:
                continue

            setattr(self, attr_name, attr_val)

        self.bot = bot
        self.ban_order = '12' * 20
        self.captains = None
        self.map_pool = None
        self.maps_left = None
        self.ban_number = None
        self.future = None

    @property
    def _active_picker(self):
        """"""
        if self.ban_number is None or self.captains is None:
            return None

        picking_player_number = int(self.ban_order[self.ban_number])
        return self.captains[picking_player_number - 1]

    def _veto_embed(self, title):
        """"""
        embed = self.bot.embed_template(title=title)
        embed.set_footer(text=utils.translate('message-map-veto-footer'))
        maps_str = ''

        if self.map_pool is not None and self.maps_left is not None:
            for m in self.map_pool:
                maps_str += f'{m.emoji}  {m.name}\n' if m.emoji in self.maps_left else f':heavy_multiplication_x:  ' \
                            f'~~{m.name}~~\n '

        status_str = ''

        if self.captains is not None and self._active_picker is not None:
            status_str += utils.translate("message-capt1", self.captains[0].mention) + '\n'
            status_str += utils.translate("message-capt2", self.captains[1].mention) + '\n\n'
            status_str += utils.translate("message-current-capt", self._active_picker.mention)

        embed.add_field(name=utils.translate("message-maps-left"), value=maps_str)
        embed.add_field(name=utils.translate("message-info"), value=status_str)
        return embed

    async def _process_ban(self, reaction, user):
        """"""
        if reaction.message.id != self.id or user == self.author:
            return

        if user not in self.captains or str(reaction) not in [m for m in self.maps_left] or user != self._active_picker:
            await self.remove_reaction(reaction, user)
            return

        try:
            map_ban = self.maps_left.pop(str(reaction))
        except KeyError:
            return

        self.ban_number += 1
        await self.clear_reaction(map_ban.emoji)
        embed = self._veto_embed(utils.translate('message-user-banned-map', user.display_name, map_ban.name))
        await self.edit(embed=embed)

        if len(self.maps_left) == 1:
            if self.future is not None:
                try:
                    self.future.set_result(None)
                except asyncio.InvalidStateError:
                    pass

    async def veto(self, pool, captain_1, captain_2):
        """"""
        self.captains = [captain_1, captain_2]
        self.map_pool = pool
        self.maps_left = {m.emoji: m for m in self.map_pool}
        self.ban_number = 0

        if len(self.map_pool) % 2 == 0:
            self.captains.reverse()

        await self.edit(embed=self._veto_embed(utils.translate('message-map-bans-begun')))

        for m in self.map_pool:
            await self.add_reaction(m.emoji)

        self.future = self.bot.loop.create_future()
        self.bot.add_listener(self._process_ban, name='on_reaction_add')
        try:
            await asyncio.wait_for(self.future, 180)
        except asyncio.TimeoutError:
            self.bot.remove_listener(self._process_ban, name='on_reaction_add')
            await self.clear_reactions()
            raise

        await self.clear_reactions()
        return list(self.maps_left.values())


class MapVoteMessage(discord.Message):
    """"""
    def __init__(self, message, bot, users):
        """"""
        for attr_name in message.__slots__:
            try:
                attr_val = getattr(message, attr_name)
            except AttributeError:
                continue

            setattr(self, attr_name, attr_val)

        self.bot = bot
        self.users = users
        self.voted_users = None
        self.map_pool = None
        self.map_votes = None
        self.future = None
        self.tie_count = 0

    def _vote_embed(self):
        embed = self.bot.embed_template(title=utils.translate('message-vote-map-started'))
        str_value = '--------------------\n'
        max_map = max(self.map_votes.values())
        str_value += '\n'.join(
            f'{EMOJI_NUMBERS[self.map_votes[m.emoji]]} {m.emoji} {m.name} '
            f'{"🔸" if self.map_votes[m.emoji] == max_map and self.map_votes[m.emoji] != 0 else ""} '
            for m in self.map_pool)
        embed.add_field(name=f':repeat_one: :map: {utils.translate("message-maps")}', value=str_value)
        embed.set_footer(text=utils.translate('message-vote-map-footer'))
        return embed

    async def _process_vote(self, reaction, user):
        """"""
        if reaction.message.id != self.id or user == self.author:
            return

        if user not in self.users or user in self.voted_users or str(reaction) not in [m.emoji for m in self.map_pool]:
            await self.remove_reaction(reaction, user)
            return

        self.map_votes[str(reaction)] += 1
        self.voted_users[user] = str(reaction)
        await self.edit(embed=self._vote_embed())

        if len(self.voted_users) == len(self.users):
            if self.future is not None:
                try:
                    self.future.set_result(None)
                except asyncio.InvalidStateError:
                    pass

    async def vote(self, mpool):
        """"""
        self.voted_users = {}
        self.map_pool = mpool
        self.map_votes = {m.emoji: 0 for m in self.map_pool}
        await self.edit(embed=self._vote_embed())

        for m in self.map_pool:
            await self.add_reaction(m.emoji)

        self.future = self.bot.loop.create_future()
        self.bot.add_listener(self._process_vote, name='on_reaction_add')

        try:
            await asyncio.wait_for(self.future, 60)
        except asyncio.TimeoutError:
            pass

        self.bot.remove_listener(self._process_vote, name='on_reaction_add')
        try:
            await self.clear_reactions()
        except discord.errors.NotFound:
            pass

        winners_emoji = []
        winners_votes = 0

        for emoji, votes in self.map_votes.items():
            if votes > winners_votes:
                winners_emoji.clear()
                winners_emoji.append(emoji)
                winners_votes = votes
            elif votes == winners_votes:
                winners_emoji.append(emoji)

        self.map_pool = [m for m in mpool if m.emoji in winners_emoji]
        self.voted_users = None
        self.map_votes = None
        self.future = None

        if len(winners_emoji) == 1:
            return self.map_pool
        elif len(winners_emoji) == 2 and self.tie_count == 1:
            return [choice(self.map_pool)]
        else:
            if len(winners_emoji) == 2:
                self.tie_count += 1
            return await self.vote(self.map_pool)


class MapPoolMessage(discord.Message):
    """"""

    def __init__(self, message, bot, user, pug_data):
        """"""
        for attr_name in message.__slots__:
            try:
                attr_val = getattr(message, attr_name)
            except AttributeError:
                continue

            setattr(self, attr_name, attr_val)

        self.bot = bot
        self.user = user
        self.pug_data = pug_data
        self.map_pool = None
        self.active_maps = None
        self.inactive_maps = None
        self.future = None

    def _pick_embed(self, footer=None):
        embed = self.bot.embed_template(title=utils.translate('message-map-pool'))

        active_maps = ''.join(f'{emoji}  `{m.name}`\n' for emoji, m in self.active_maps.items())
        inactive_maps = ''.join(f'{emoji}  `{m.name}`\n' for emoji, m in self.inactive_maps.items())

        if not inactive_maps:
            inactive_maps = utils.translate("message-none")

        if not active_maps:
            active_maps = utils.translate("message-none")

        embed.add_field(name=utils.translate("message-active-maps"), value=active_maps)
        embed.add_field(name=utils.translate("message-inactive-maps"), value=inactive_maps)
        if not footer:
            footer = utils.translate('message-map-pool-footer')
        embed.set_footer(text=footer)
        return embed

    async def _process_pick(self, reaction, user):
        """"""
        if reaction.message.id != self.id or user == self.author:
            return

        emoji = str(reaction.emoji)

        if emoji == '✅':
            if len(self.active_maps) < 3:
                pass
            else:
                footer = 'Changes have been saved'
                await self.edit(embed=self._pick_embed(footer))
                if self.future is not None:
                    try:
                        self.future.set_result(None)
                    except asyncio.InvalidStateError:
                        pass
                return

        if emoji not in [m.emoji for m in self.bot.all_maps.values()] or user != self.user:
            await self.remove_reaction(reaction, user)
            return

        if emoji in self.inactive_maps:
            self.active_maps[emoji] = self.inactive_maps[emoji]
            self.inactive_maps.pop(emoji)
            self.map_pool.append(self.active_maps[emoji].dev_name)
        elif emoji in self.active_maps:
            self.inactive_maps[emoji] = self.active_maps[emoji]
            self.active_maps.pop(emoji)
            self.map_pool.remove(self.inactive_maps[emoji].dev_name)

        await self.remove_reaction(reaction, user)
        await self.edit(embed=self._pick_embed())

    async def pick(self):
        """"""
        self.map_pool = [m.dev_name for m in self.pug_data.mpool]
        self.active_maps = {m.emoji: m for m in self.bot.all_maps.values() if m.dev_name in self.map_pool}
        self.inactive_maps = {m.emoji: m for m in self.bot.all_maps.values() if m.dev_name not in self.map_pool}

        await self.edit(embed=self._pick_embed())

        awaitables = [self.add_reaction(m.emoji) for m in self.bot.all_maps.values()]
        await asyncio.gather(*awaitables, loop=self.bot.loop)
        await self.add_reaction('✅')

        self.future = self.bot.loop.create_future()
        self.bot.add_listener(self._process_pick, name='on_reaction_add')

        try:
            await asyncio.wait_for(self.future, 300)
        except asyncio.TimeoutError:
            self.bot.remove_listener(self._process_pick, name='on_reaction_add')
            return
        self.bot.remove_listener(self._process_pick, name='on_reaction_add')

        map_pool_data = {m.dev_name: m.dev_name in self.map_pool for m in self.bot.all_maps.values()}
        await self.bot.db.update_pug(self.pug_data.id, **map_pool_data)
        try:
            await self.clear_reactions()
        except discord.errors.NotFound:
            pass
