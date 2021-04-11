# match.py

import asyncio
from discord.ext import commands, tasks
from discord.utils import get
from discord.errors import NotFound

from .message import TeamDraftMessage, MapVetoMessage, MapVoteMessage
from .utils.utils import translate, get_match_config, align_text

from random import shuffle, choice
from traceback import print_exception
from datetime import datetime
import time
import sys


class MatchCog(commands.Cog):
    """"""
    def __init__(self, bot):
        """"""
        self.bot = bot

    async def autobalance_teams(self, users):
        """ Balance teams based on players' avarage raitng. """
        # Get players and sort by average rating
        users_dict = dict(zip(await self.bot.api.players_stats(users), users))
        players = list(users_dict.keys())
        players.sort(key=lambda x: x.average_rating)

        # Balance teams
        team_size = len(players) // 2
        team_one = [players.pop()]
        team_two = [players.pop()]

        while players:
            if len(team_one) >= team_size:
                team_two.append(players.pop())
            elif len(team_two) >= team_size:
                team_one.append(players.pop())
            elif sum(p.average_rating for p in team_one) < sum(p.average_rating for p in team_two):
                team_one.append(players.pop())
            else:
                team_two.append(players.pop())

        return list(map(users_dict.get, team_one)), list(map(users_dict.get, team_two))

    async def draft_teams(self, message, users, pug_config):
        """"""
        menu = TeamDraftMessage(message, self.bot, users, pug_config)
        teams = await menu.draft()
        return teams[0], teams[1]

    @staticmethod
    async def randomize_teams(users):
        """"""
        temp_users = users.copy()
        shuffle(temp_users)
        team_size = len(temp_users) // 2
        return temp_users[:team_size], temp_users[team_size:]

    async def ban_maps(self, message, mpool, captain_1, captain_2):
        """"""
        menu = MapVetoMessage(message, self.bot)
        return await menu.veto(mpool, captain_1, captain_2)

    async def vote_maps(self, message, mpool, users):
        """"""
        menu = MapVoteMessage(message, self.bot, users)
        return await menu.vote(mpool)

    @staticmethod
    async def random_map(mpool):
        """"""
        return [choice(mpool)]

    async def _embed_server(self, match, team_one, team_two, spectators, map_pick):
        """"""
        description = f'{translate("match-server-info", match.connect_url, match.connect_command)}\n'
        embed = self.bot.embed_template(title=translate('match-server-ready'), description=description)

        embed.set_author(name=translate("match-id", match.id), url=match.match_page)
        embed.set_thumbnail(url=map_pick[0].image_url)

        for team in [team_one, team_two]:
            team_name = f'__Team {team[0].display_name}__'
            team_players = '\n'.join(f'{num}. {user.mention}' for num, user in enumerate(team, start=1))
            embed.add_field(name=team_name, value=team_players)

        embed.add_field(name=translate('match-spectators'),
                        value=translate('match-no-spectators') if not spectators
                        else ''.join(f'{num}. {user.mention}\n' for num, user in enumerate(spectators, start=1)))
        embed.set_footer(text=translate('match-server-message-footer'))
        return embed

    async def start_match(self, users, message, pug_config, guild_config):
        """"""
        try:
            if pug_config.team_method == 'captains':
                team_one, team_two = await self.draft_teams(message, users, pug_config)
            elif pug_config.team_method == 'autobalance':
                team_one, team_two = await self.autobalance_teams(users)
            else:  # team_method is random
                team_one, team_two = await self.randomize_teams(users)

            if pug_config.map_method == 'ban':
                map_pick = await self.ban_maps(message, pug_config.mpool, team_one[0], team_two[0])
            elif pug_config.map_method == 'vote':
                map_pick = await self.vote_maps(message, pug_config.mpool, users)
            else:  # map_method is random
                map_pick = await self.random_map(pug_config.mpool)
        except asyncio.TimeoutError:
            title = translate('match-took-too-long')
            burst_embed = self.bot.embed_template(title=title, color=self.bot.colors['red'])
            await message.edit(content='', embed=burst_embed)
            return False

        burst_embed = self.bot.embed_template(description=translate('match-looking-server'))
        await message.edit(content='', embed=burst_embed)

        spect_ids = await self.bot.db.get_spect_users(pug_config.id)
        spectators = [guild_config.guild.get_member(user_id) for user_id in spect_ids]

        try:
            match = await self.bot.api.create_match(team_one, team_two, spectators, map_pick[0], guild_config.auth)
        except Exception as e:
            description = translate('match-no-servers')
            burst_embed = self.bot.embed_template(title=translate('match-problem'),
                                                  description=description,
                                                  color=self.bot.colors['red'])
            await message.edit(embed=burst_embed)
            print_exception(type(e), e, e.__traceback__, file=sys.stderr)
            return False

        await self.bot.db.insert_matches(match.id)

        burst_embed = await self._embed_server(match, team_one, team_two, spectators, map_pick)
        await message.edit(embed=burst_embed)

        await self.create_teams_channels(match.id, team_one, team_two, pug_config, guild_config, message)

        if not self.check_matches.is_running():
            self.check_matches.start()

        return True

    @tasks.loop(seconds=10.0)
    async def check_matches(self):
        match_ids = await self.bot.db.get_all_matches()
        if match_ids:
            for match_id in match_ids:
                match = await get_match_config(self.bot, match_id)
                try:
                    api_matches = await self.bot.api.matches_status(match.guild_config.auth)
                except Exception as e:
                    print_exception(type(e), e, e.__traceback__, file=sys.stderr)
                    continue
                if match_id in api_matches:
                    await self.update_match(match_id, match, api_matches[match_id])
        else:
            self.check_matches.cancel()

    async def update_match(self, match_id, match, live):
        """"""
        scoreboard = await self.bot.api.match_scoreboard(match_id)
        if not scoreboard:
            if not live:
                await self.remove_teams_channels(match)
            return

        team1_info = await self.bot.api.get_team(scoreboard['team1_players'][0]['team_id'])
        team2_info = await self.bot.api.get_team(scoreboard['team2_players'][0]['team_id'])
        map_stats = await self.bot.api.map_stats(match_id)
        try:
            team1_name = team1_info['name']
            team2_name = team2_info['name']
        except (KeyError, TypeError):
            team1_name = team2_name = None
        
        # Generate leaderboard text
        description = ''
        for team in [scoreboard['team1_players'], scoreboard['team2_players']]:
            team.sort(key=lambda x: x['kills'], reverse=True)
            data = [['Player'] + [player['name'] for player in team],
                    ['Kills'] + [f"{player['kills']}" for player in team],
                    ['Assists'] + [f"{player['assists']}" for player in team],
                    ['Deaths'] + [f"{player['deaths']}" for player in team],
                    ['KDR'] + [f"{0 if player['deaths'] == 0 else player['kills']/player['deaths']:.2f}" for player in team],
                    ['Score'] + [f"{player['contribution_score']}" for player in team]]

            data[0] = [name if len(name) < 12 else name[:9] + '...' for name in data[0]]  # Shorten long names
            widths = list(map(lambda x: len(max(x, key=len)), data))
            aligns = ['left', 'center', 'center', 'center', 'center', 'center']
            z = zip(data, widths, aligns)
            formatted_data = [list(map(lambda x: align_text(x, width, align), col)) for col, width, align in z]
            formatted_data = list(map(list, zip(*formatted_data)))  # Transpose list for .format() string
            description += '```ml\n    {}  {}  {}  {}  {}  {} \n'.format(*formatted_data[0])

            for rank, player_row in enumerate(formatted_data[1:], start=1):
                description += ' {}. {}  {}  {}  {}  {}  {} \n'.format(rank, *player_row)

            description += '```\n'
        
        start_time = datetime.fromisoformat(map_stats["start_time"].replace("Z", "+00:00")).strftime("%Y-%m-%d  %H:%M:%S")
        description += f'**Start Time:** {start_time}\n'
        if map_stats['end_time']:
            end_time = datetime.fromisoformat(map_stats["end_time"].replace("Z", "+00:00")).strftime("%Y-%m-%d  %H:%M:%S")
            description += f'**End Time:** {end_time}\n'
        if not live:
            if map_stats['demoFile']:
                description += f'**[Download Demo]({self.bot.web_url}/api/demo/{map_stats["demoFile"]})**'

        if team1_name:
            match_score = f'{translate("match-id", match_id)}  Team {team1_name}  [{map_stats["team1_score"]}:{map_stats["team2_score"]}]  Team {team2_name}'
        else:
            try:
                match_score = match.message.embeds[0].author.name
            except NotFound:
                match_score = 'message deleted!'

        # Send scoreboard
        color = self.bot.colors['green'] if live else self.bot.colors['red']
        embed = self.bot.embed_template(description=description, color=color)
        embed.set_author(name=match_score,
                         url=f'{self.bot.web_url}/match/{match_id}',
                         icon_url=self.bot.all_maps[map_stats['map_name']].image_url)

        try:
            await match.message.edit(embed=embed)
        except NotFound:
            pass
        
        if not live:
            await self.remove_teams_channels(match)

    async def create_teams_channels(self, match_id, team_one, team_two, pug_config, guild_config, message):
        """"""
        guild = pug_config.guild
        category_position = guild.categories.index(pug_config.lobby_channel.category) + 1
        everyone_role = get(guild.roles, name='@everyone')

        match_catg = await guild.create_category_channel(translate("match-id", match_id), position=category_position)

        awaitables = [
            guild.create_voice_channel(name=translate("match-team", team_one[0].display_name),
                                       category=match_catg,
                                       user_limit=len(team_one)),
            guild.create_voice_channel(name=translate("match-team", team_two[0].display_name),
                                       category=match_catg,
                                       user_limit=len(team_two))
        ]
        channels = await asyncio.gather(*awaitables, loop=self.bot.loop, return_exceptions=True)

        team1_channel = channels[0]
        team2_channel = channels[1]

        awaitables = [
            team1_channel.set_permissions(everyone_role, connect=False, read_messages=True),
            team2_channel.set_permissions(everyone_role, connect=False, read_messages=True)
        ]

        for team in [team_one, team_two]:
            for user in team:
                if user in team_one:
                    awaitables.append(team1_channel.set_permissions(user, connect=True))
                    awaitables.append(user.move_to(team1_channel))
                else:
                    awaitables.append(team2_channel.set_permissions(user, connect=True))
                    awaitables.append(user.move_to(team2_channel))

        match_data = {
            'guild': pug_config.guild.id,
            'pug': pug_config.id,
            'message': message.id,
            'category': match_catg.id,
            'team1_channel': team1_channel.id,
            'team2_channel': team2_channel.id,
            'team1_name': team_one[0].display_name,
            'team2_name': team_two[0].display_name
        }

        awaitables.append(self.bot.db.update_match(match_id, **match_data))
        await asyncio.gather(*awaitables, loop=self.bot.loop, return_exceptions=True)

        await self.bot.db.insert_match_users(match_id, *[user.id for user in team_one], team='team1')
        await self.bot.db.insert_match_users(match_id, *[user.id for user in team_two], team='team2')

    async def remove_teams_channels(self, match):
        """"""
        guild = match.guild_config.guild
        banned_users = await self.bot.db.get_banned_users(guild.id)
        banned_users = [guild.get_member(user_id) for user_id in banned_users]

        awaitables = []
        for user in match.team1_users + match.team2_users:
            if user not in banned_users:
                awaitables.append(user.add_roles(match.guild_config.linked_role))
            awaitables.append(user.move_to(match.guild_config.afk_channel))
        await asyncio.gather(*awaitables, loop=self.bot.loop, return_exceptions=True)

        awaitables = [
            match.team1_channel.delete(),
            match.team2_channel.delete(),
            self.bot.db.delete_matches(match.id)
        ]
        await asyncio.gather(*awaitables, loop=self.bot.loop, return_exceptions=True)

        try:
            await match.category.delete()
        except NotFound:
            pass
