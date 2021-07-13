# launcher.py

from bot.bot import PUGsBot

import argparse
from dotenv import load_dotenv
import os

load_dotenv()  # Load the environment variables in the local .env file


def run_bot():
    """ Parse the config file and run the bot. """
    bot_prefixes = os.environ['DISCORD_BOT_PREFIXES']
    # Get database object for bot
    db_connect_url = 'postgresql://{POSTGRESQL_USER}:{POSTGRESQL_PASSWORD}@{POSTGRESQL_HOST}/{POSTGRESQL_DB}'
    db_connect_url = db_connect_url.format(**os.environ)

    # Get environment variables
    bot_token = os.environ['DISCORD_BOT_TOKEN']
    api_url = os.environ['G5API_URL']

    if api_url.endswith('/'):
        api_url = api_url[:-1]
    
    try:
        league_url = os.environ['LEAGUE_URL']
    except KeyError:
        league_url = None
    # Instantiate bot and run
    bot = PUGsBot(bot_prefixes, bot_token, api_url, db_connect_url, league_url)
    bot.run()


if __name__ == '__main__':
    argparse.ArgumentParser(description='Run the CS:GO PUGs bot')
    run_bot()
