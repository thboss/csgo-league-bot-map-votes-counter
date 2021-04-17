# api.py

import aiohttp
import asyncio
import json
import logging
import datetime


class PlayerStats:
    """"""
    def __init__(self, json_data, web_url=None):
        """"""
        self.steam = json_data['steamId']
        self.discord = json_data['discord']
        self.name = json_data['name']
        self.kills = json_data['kills']
        self.deaths = json_data['deaths']
        self.assists = json_data['assists']
        self.k1 = json_data['k1']
        self.k2 = json_data['k2']
        self.k3 = json_data['k3']
        self.k4 = json_data['k4']
        self.k5 = json_data['k5']
        self.v1 = json_data['v1']
        self.v2 = json_data['v2']
        self.v3 = json_data['v3']
        self.v4 = json_data['v4']
        self.v5 = json_data['v5']
        self.trp = json_data['trp']
        self.fba = json_data['fba']
        self.total_damage = json_data['total_damage']
        self.hsk = json_data['hsk']
        self.hsp = json_data['hsp'] + '%'
        self.average_rating = float(json_data['average_rating'])
        self.wins = json_data['wins']
        self.total_maps = json_data['total_maps']
        self.win_percent = f'{self.wins / self.total_maps * 100:.2f}%' if self.total_maps else '0.00%'
        self.kdr = f'{self.kills / self.deaths:.2f}' if self.deaths else '0.00'
        self.profile = f'{web_url}/user/{self.steam}'


def new_player(steam):
    """"""
    return {
        'steamId': steam,
        'name': 'Unknown',
        'kills': 0,
        'deaths': 0,
        'assists': 0,
        'k1': 0,
        'k2': 0,
        'k3': 0,
        'k4': 0,
        'k5': 0,
        'v1': 0,
        'v2': 0,
        'v3': 0,
        'v4': 0,
        'v5': 0,
        'trp': 0,
        'fba': 0,
        'total_damage': 0,
        'hsk': 0,
        'hsp': '0.00',
        'average_rating': '0.00',
        'wins': 0,
        'total_maps': 0
    }


class MatchServer:
    """ Represents a match server with the contents returned by the API. """

    def __init__(self, match, server, web_url=None):
        """ Set attributes. """
        self.id = match['id']
        self.ip = server['ip_string']
        self.port = server['port']
        self.web_url = web_url

    @property
    def connect_url(self):
        """ Format URL to connect to server. """
        return f'steam://connect/{self.ip}:{self.port}'

    @property
    def connect_command(self):
        """ Format console command to connect to server. """
        return f'connect {self.ip}:{self.port}'

    @property
    def match_page(self):
        """ Generate the matches G5API page link. """
        if self.web_url:
            return f'{self.web_url}/match/{self.id}'


async def start_request_log(session, ctx, params):
    """"""
    ctx.start = asyncio.get_event_loop().time()
    logger = logging.getLogger('PUGs.api')
    logger.info(f'Sending {params.method} request to {params.url}')


async def end_request_log(session, ctx, params):
    """"""
    logger = logging.getLogger('PUGs.api')
    elapsed = asyncio.get_event_loop().time() - ctx.start
    logger.info(f'Response received from {params.url} ({elapsed:.2f}s)\n'
                f'    Status: {params.response.status}\n'
                f'    Reason: {params.response.reason}')
    resp_json = await params.response.json()
    logger.debug(f'Response JSON from {params.url}: {resp_json}')


class ApiHelper:
    """ Class to contain API request wrapper functions. """

    def __init__(self, bot, loop, web_url):
        """ Set attributes. """
        self.bot = bot
        self.web_url = web_url
        self.logger = logging.getLogger('PUGs.api')

        # Register trace config handlers
        trace_config = aiohttp.TraceConfig()
        trace_config.on_request_start.append(start_request_log)
        trace_config.on_request_end.append(end_request_log)

        # Start session
        self.logger.info('Starting API helper client session')
        self.session = aiohttp.ClientSession(loop=loop, json_serialize=lambda x: json.dumps(x, ensure_ascii=False))

    async def close(self):
        """ Close the API helper's session. """
        self.logger.info('Closing API helper client session')
        await self.session.close()

    async def is_user(self, user_id):
        """"""
        url = f'{self.web_url}/api/users'

        async with self.session.get(url=url) as resp:
            resp_data = await resp.json()
            return user_id in [user['id'] for user in resp_data['users']]

    async def check_auth(self, auth):
        """"""
        url = f'{self.web_url}/api'
        data = {
            'user_id': auth['user_id'],
            'user_api': auth['api_key'],
        }

        async with self.session.get(url=url, json=[data]) as resp:
            return '/auth/steam' not in str(resp.url)

    async def create_team(self, users, auth):
        """"""
        user_ids = [user.id for user in users]
        users_data = await self.bot.db.get_users(user_ids)
        users_data.sort(key=lambda x: user_ids.index(x[0]))

        auth_names = {
            users_data[index][1]: {
                'name': user.display_name,
                'captain': int(users.index(user) == 0)
            } for index, user in enumerate(users)
        }

        url = f'{self.web_url}/api/teams'
        data = {
            'user_id': auth['user_id'],
            'user_api': auth['api_key'],
            'name': users[0].display_name,
            'flag': users_data[0][2],
            'public_team': 0,
            'auth_name': auth_names
        }

        async with self.session.post(url=url, json=[data]) as resp:
            resp_data = await resp.json()
            return resp_data['id']

    async def private_servers(self, auth):
        """"""
        url = f'{self.web_url}/api/servers/myservers'
        data = {
            'user_id': auth['user_id'],
            'user_api': auth['api_key'],
        }

        async with self.session.get(url=url, json=[data]) as resp:
            resp_data = await resp.json()
            return [server for server in resp_data['servers'] if not server['in_use']]

    async def matches_status(self, auth):
        """"""
        url = f'{self.web_url}/api/matches/mymatches'
        data = {
            'user_id': auth['user_id'],
            'user_api': auth['api_key'],
        }

        async with self.session.get(url=url, json=[data]) as resp:
            resp_data = await resp.json()
            return {match['id']: match['end_time'] is None for match in resp_data['matches']}

    async def get_team(self, team_id):
        """"""
        url = f'{self.web_url}/api/teams/{team_id}'

        async with self.session.get(url=url) as resp:
            resp_data = await resp.json()
            try:
                return resp_data['team']
            except KeyError:
                pass

    async def map_stats(self, match_id, map_number=0):
        url = f'{self.web_url}/api/mapstats/{match_id}/{map_number}'

        async with self.session.get(url=url) as resp:
            resp_data = await resp.json()
            try:
                return resp_data['mapstat']
            except KeyError:
                pass

    async def match_scoreboard(self, match_id):
        """"""
        url = f'{self.web_url}/api/playerstats/match/{match_id}'
        
        async with self.session.get(url=url) as resp:
            resp_data = await resp.json()
            try:
                players = resp_data['playerstats']
            except KeyError:
                pass
            else:
                p1 = players[0]['team_id']
                team1_players, team2_players = [], []
                for player in players:
                    if player['team_id'] == p1:
                        team1_players.append(player)
                    else:
                        team2_players.append(player)

                return {'team1_players': team1_players, 'team2_players': team2_players}

    async def server_status(self, server_id, auth):
        """"""
        url = f'{self.web_url}/api/servers/{server_id}/status'
        data = {
            'user_id': auth['user_id'],
            'user_api': auth['api_key'],
        }

        async with self.session.get(url=url, json=[data]) as resp:
            return resp.status < 400

    async def create_match(self, team_one, team_two, spectators, map_pick, auth):
        """"""
        team1_id = await self.create_team(team_one, auth)
        team2_id = await self.create_team(team_two, auth)
        servers = await self.private_servers(auth)
        match_server = None
        for server in servers:
            if await self.server_status(server['id'], auth):
                match_server = server
                break

        if not match_server:
            raise ValueError('No servers!')

        total_players = len(team_one) + len(team_two)

        url = f'{self.web_url}/api/matches'
        data = {
            'user_id': auth['user_id'],
            'user_api': auth['api_key'],
            'server_id': match_server['id'],
            'team1_id': team1_id,
            'team2_id': team2_id,
            'title': '[PUG] Map {MAPNUMBER} of {MAXMAPS}',
            'is_pug': 1,
            'start_time': datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            'ignore_server': 0,
            'max_maps': 1,
            'veto_mappool': map_pick.dev_name,
            'skip_veto': 1,
            'veto_first': 'team1',
            'side_type': 'always_knife',
            'players_per_team': total_players // 2,
            'min_players_to_ready': total_players // 2,
            'match_cvars': {
                'sv_hibernate_when_empty': 0,
                'game_mode': 1 if total_players > 6 else 2,
                'get5_live_cfg': 'get5/live_competitive.cfg' if total_players > 6 else 'get5/live_wingman.cfg',
                'get5_time_to_start': 300,  # warmup 5 minutes
                'get5_kick_when_no_match_loaded': 1,
                'get5_end_match_on_empty_server': 1
            }
        }

        if spectators:
            spec_ids = [spec.id for spec in spectators]
            spects_data = await self.bot.db.get_users(spec_ids)
            spects_data.sort(key=lambda x: spec_ids.index(x[0]))
            data['spectator_auths'] = {spects_data[index][1]: spec.desplay_name for index, spec in enumerate(spectators)}

        async with self.session.post(url=url, json=[data]) as resp:
            return MatchServer(await resp.json(), match_server, self.web_url)

    async def cancel_match(self, match_id, auth):
        """"""
        url = f'{self.web_url}/api/matches/{match_id}/cancel'
        data = {
            'user_id': auth['user_id'],
            'user_api': auth['api_key'],
            'match_id': match_id
        }

        async with self.session.get(url=url, json=[data]) as resp:
            return resp.status

    async def add_match_player(self, user_data, match_id, team, auth):
        """"""
        url = f'{self.web_url}/api/matches/{match_id}/{"addspec" if team == "spec" else "adduser"}'
        data = {
            'user_id': auth['user_id'],
            'user_api': auth['api_key'],
            'steam_id': user_data.steam,
            'team_id': team,
            'nickname': user_data.discord.display_name
        }

        async with self.session.put(url=url, json=[data]) as resp:
            return resp.status

    async def remove_match_player(self, user_data, match_id, auth):
        """"""
        url = f'{self.web_url}/api/matches/{match_id}/removeuser'
        data = {
            'user_id': auth['user_id'],
            'user_api': auth['api_key'],
            'steam_id': user_data.steam,
        }

        async with self.session.put(url=url, json=[data]) as resp:
            return resp.status

    async def pause_match(self, match_id, auth):
        """"""
        url = f'{self.web_url}/api/matches/{match_id}/pause'
        data = {
            'user_id': auth['user_id'],
            'user_api': auth['api_key']
        }

        async with self.session.get(url=url, json=[data]) as resp:
            return resp.status

    async def unpause_match(self, match_id, auth):
        """"""
        url = f'{self.web_url}/api/matches/{match_id}/unpause'
        data = {
            'user_id': auth['user_id'],
            'user_api': auth['api_key']
        }

        async with self.session.get(url=url, json=[data]) as resp:
            return resp.status

    async def player_stats(self, user_data):
        """"""
        url = f'{self.web_url}/api/playerstats/{user_data.steam}/pug'

        async with self.session.get(url=url) as resp:
            resp_data = await resp.json()
            try:
                resp_data['pugstats']['discord'] = user_data.discord.id
                return PlayerStats(resp_data['pugstats'], self.web_url)
            except KeyError:
                return PlayerStats(new_player(user_data.steam), self.web_url)

    async def leaderboard(self, users):
        """"""
        users_data = await self.bot.db.get_users([user.id for user in users])
        if not users_data:
            return
        users_dict = dict(zip([data[1] for data in users_data], [data[0] for data in users_data]))

        url = f'{self.web_url}/api/leaderboard/players/pug'

        async with self.session.get(url=url) as resp:
            resp_data = await resp.json()
            players = list(filter(lambda x: x['steamId'] in list(users_dict.keys()), resp_data['leaderboard']))

            for steam_id in list(users_dict.keys()):
                if steam_id not in [p['steamId'] for p in players]:
                    players.append(new_player(steam_id))

            for player in players:
                player['discord'] = list(map(users_dict.get, [player['steamId']]))[0]

            players.sort(key=lambda x: list(users_dict.keys()).index(x['steamId']))
            return [PlayerStats(player, self.web_url) for player in players]
