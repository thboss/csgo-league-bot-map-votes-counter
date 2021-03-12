# launcher.py

from bot.bot import PUGsBot

import argparse
from dotenv import load_dotenv
import os

load_dotenv() # Load the environment variables in the local .env file

def run_bot():
    """ Parse the config file and run the bot. """
    # Get database object for bot
    db_connect_url = 'postgresql://{POSTGRESQL_USER}:{POSTGRESQL_PASSWORD}@{POSTGRESQL_HOST}/{POSTGRESQL_DB}'
    db_connect_url = db_connect_url.format(**os.environ)

    # Get environment variables
    bot_token = os.environ['DISCORD_BOT_TOKEN']
    api_url = os.environ['G5API_URL']

    if api_url.endswith('/'):
        api_url = api_url[:-1]
    # Instantiate bot and run
    bot = PUGsBot(bot_token, api_url, db_connect_url)
    bot.run()


if __name__ == '__main__':
    argparse.ArgumentParser(description='Run the CS:GO PUGs bot')
    run_bot()
