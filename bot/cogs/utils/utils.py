# utils.py

import os
import re
import json
import math
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

from discord.ext import commands
from discord.utils import get


time_arg_pattern = re.compile(r'\b((?:(?P<days>[0-9]+)d)|(?:(?P<hours>[0-9]+)h)|(?:(?P<minutes>[0-9]+)m))\b')

load_dotenv()

with open('translations.json', encoding="utf8") as f:
    translations = json.load(f)


def translate(text, *args):
    try:
        return translations[os.environ['DISCORD_BOT_LANGUAGE']][text].format(*args)
    except (KeyError, ValueError):
        return translations['en'][text].format(*args)


def timedelta_str(tdelta):
    """ Convert time delta object to a worded string representation with only days, hours and minutes. """
    conversions = (('days', 86400), ('hours', 3600), ('minutes', 60))
    secs_left = int(tdelta.total_seconds())
    unit_strings = []

    for unit, conversion in conversions:
        unit_val, secs_left = divmod(secs_left, conversion)

        if unit_val != 0 or (unit == 'minutes' and len(unit_strings) == 0):
            unit_strings.append(f'{unit_val} {unit}')

    return ', '.join(unit_strings)


def unbantime(arg):
    # Parse the time arguments
    time_units = ('days', 'hours', 'minutes')
    time_delta_values = {}  # Holds the values for each time unit arg

    for match in time_arg_pattern.finditer(arg):  # Iterate over the time argument matches
        for time_unit in time_units:  # Figure out which time unit this match is for
            time_value = match.group(time_unit)  # Get the value for this unit

            if time_value is not None:  # Check if there is an actual group value
                time_delta_values[time_unit] = int(time_value)
                break  # There is only ever one group value per match

    # Set unban time if there were time arguments
    time_delta = timedelta(**time_delta_values)
    unban_time = None if time_delta_values == {} else datetime.now(timezone.utc) + time_delta
    return time_delta, unban_time


def align_text(text, length, align='center'):
    """ Center the text within whitespace of input length. """
    if length < len(text):
        return text

    whitespace = length - len(text)

    if align == 'center':
        pre = math.floor(whitespace / 2)
        post = math.ceil(whitespace / 2)
    elif align == 'left':
        pre = 0
        post = whitespace
    elif align == 'right':
        pre = whitespace
        post = 0
    else:
        raise ValueError('Align argument must be "center", "left" or "right"')

    return ' ' * pre + text + ' ' * post


class Map:
    """ A group of attributes representing a map. """

    def __init__(self, name, dev_name, emoji, image_url):
        """ Set attributes. """
        self.name = name
        self.dev_name = dev_name
        self.emoji = emoji
        self.image_url = image_url


async def create_emojis(bot, guild):
    """ Upload custom map emojis to guilds. """
    url_path = 'https://raw.githubusercontent.com/thboss/CSGO-PUGs-Bot/develop/assets/maps/icons/'
    icons_dic = 'assets/maps/icons/'
    icons = os.listdir(icons_dic)
    try:
        emojis = [e.name for e in guild.emojis]
    except IndexError:
        return

    for icon in icons:
        if icon.endswith('.png') and '-' in icon and os.stat(icons_dic + icon).st_size < 256000:
            emoji_name = icon.split('-')[0]
            emoji_dev = icon.split('-')[1].split('.')[0]
            if emoji_dev not in emojis:
                with open(icons_dic + icon, 'rb') as image:
                    emoji = await guild.create_custom_emoji(name=emoji_dev, image=image.read())
            else:
                emoji = get(guild.emojis, name=emoji_dev)

                bot.all_maps[emoji_dev] = Map(emoji_name,
                                              emoji_dev,
                                              f'<:{emoji_dev}:{emoji.id}>',
                                              f'{url_path}{icon.replace(" ", "%20")}')


async def check_setup(bot, ctx):
    """"""
    guild_config = await get_guild_config(bot, ctx.guild.id)
    if not any(guild_config.auth.values()) or not guild_config.linked_role:
        msg = translate('command-not-setup')
        raise commands.UserInputError(message=msg)

    return guild_config


async def check_pug(bot, ctx, queue_id):
    """"""
    try:
        pug_config = await get_pug_config(bot, queue_id, 'queue_channel')
    except TypeError:
        msg = translate('invalid-usage', bot.command_prefix[0], ctx.command.usage)
        raise commands.UserInputError(message=msg)

    if pug_config is None or ctx.guild != pug_config.guild:
        msg = translate('command-missing-mention-channel')
        raise commands.UserInputError(message=msg)

    return pug_config


class GuildConfig:
    """"""
    def __init__(self, guild, auth, linked_role, afk_channel):
        self.guild = guild
        self.auth = auth
        self.linked_role = linked_role
        self.afk_channel = afk_channel

    @classmethod
    def from_dict(cls, bot, guild_data: dict):
        """"""
        guild = bot.get_guild(guild_data['id'])
        auth = {
            'user_id': guild_data['user_id'],
            'api_key': guild_data['api_key']
        }
        return cls(guild,
                   auth,
                   guild.get_role(guild_data['linked_role']),
                   guild.afk_channel)


class PUGConfig:
    """"""
    def __init__(self, id, guild, queue_channel, lobby_channel, capacity,
                 team_method, captain_method, map_method, mpool):
        self.id = id
        self.guild = guild
        self.queue_channel = queue_channel
        self.lobby_channel = lobby_channel
        self.capacity = capacity
        self.team_method = team_method
        self.captain_method = captain_method
        self.map_method = map_method
        self.mpool = mpool

    @classmethod
    def from_dict(cls, bot, pug_data: dict):
        """"""
        guild = bot.get_guild(pug_data['guild'])
        return cls(pug_data['id'],
                   guild,
                   guild.get_channel(pug_data['queue_channel']),
                   guild.get_channel(pug_data['lobby_channel']),
                   pug_data['capacity'],
                   pug_data['team_method'],
                   pug_data['captain_method'],
                   pug_data['map_method'],
                   [m for m in bot.all_maps.values() if pug_data[m.dev_name]])


class MatchConfig:
    """"""
    def __init__(self, id, guild_config, pug_config, message, category, team1_channel,
                 team2_channel, team1_name, team2_name, team1_users, team2_users):
        self.id = id
        self.guild_config = guild_config
        self.pug_config = pug_config
        self.message = message
        self.category = category
        self.team1_channel = team1_channel
        self.team2_channel = team2_channel
        self.team1_name = team1_name
        self.team2_name = team2_name
        self.team1_users = team1_users
        self.team2_users = team2_users

    @classmethod
    async def from_dict(cls, bot, match_data: dict):
        """"""
        guild_config = await get_guild_config(bot, match_data['guild'])
        pug_config = await get_pug_config(bot, match_data['pug'])
        guild = guild_config.guild
        team1_users = await bot.db.get_match_users(match_data['id'], team='team1')
        team2_users = await bot.db.get_match_users(match_data['id'], team='team2')

        return cls(match_data['id'],
                   guild_config,
                   pug_config,
                   await pug_config.queue_channel.fetch_message(match_data['message']),
                   guild.get_channel(match_data['category']),
                   guild.get_channel(match_data['team1_channel']),
                   guild.get_channel(match_data['team2_channel']),
                   match_data['team1_name'],
                   match_data['team2_name'],
                   [guild.get_member(user_id) for user_id in team1_users],
                   [guild.get_member(user_id) for user_id in team2_users])


class UserConfig:
    """"""
    def __init__(self, discord, steam, flag):
        self.discord = discord
        self.steam = steam
        self.flag = flag

    @classmethod
    def from_dict(cls, user_data: dict):
        """"""
        return cls(user_data['discord_id'],
                   user_data['steam_id'],
                   user_data['flag'])


async def get_guild_config(bot, row_id):
    """"""
    try:
        guild_data = await bot.db.get_guild(row_id)
    except AttributeError:
        return
    return GuildConfig.from_dict(bot, guild_data)


async def get_pug_config(bot, row_id, column='id'):
    """"""
    try:
        pug_data = await bot.db.get_pug(row_id, column)
    except AttributeError:
        return
    return PUGConfig.from_dict(bot, pug_data)


async def get_match_config(bot, row_id):
    """"""
    try:
        match_data = await bot.db.get_match(row_id)
    except AttributeError:
        return
    return await MatchConfig.from_dict(bot, match_data)


async def get_user_config(bot, row_id, column='discord_id'):
    """"""
    try:
        user_data = await bot.db.get_user(row_id, column)
    except AttributeError:
        return
    return UserConfig.from_dict(user_data)
