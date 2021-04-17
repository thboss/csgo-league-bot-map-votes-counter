[![HitCount](http://hits.dwyl.io/csgo-league/csgo-league-bot.svg)](http://hits.dwyl.io/csgo-league/csgo-league-bot)
[![Maintenance](https://img.shields.io/badge/Maintained%3F-yes-green.svg)](https://github.com/csgo-league/csgo-league-bot/graphs/commit-activity)
[![GitHub release](https://img.shields.io/github/release/csgo-league/csgo-league-bot.svg)](https://github.com/csgo-league/csgo-league-bot/releases/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat-square)](http://makeapullrequest.com)
[![Open Source Love svg3](https://badges.frapsoft.com/os/v3/open-source.svg?v=103)](https://github.com/csgo-league)

# CS:GO PUGs Bot
A Discord bot to manage CS:GO PUGs. Connects to [G5API](https://github.com/PhlexPlexico/G5API).


# Author
[cameronshinn](https://github.com/cameronshinn) - Developer / Maintainer


## Setup
1. First you must have a bot instance to run this script on. Follow Discord's tutorial [here](https://discord.onl/2019/03/21/how-to-set-up-a-bot-application/) on how to set one up. Be sure to invite it to a server before launch the bot.

   * The required permissions is `administrator`.
   * Enable the "server members intent" for your bot, as shown [here](https://discordpy.readthedocs.io/en/latest/intents.html#privileged-intents).

2. Install libpq-dev (Linux only?). This is needed to install the psycopg2 Python package.

    * Linux command is `sudo apt-get install libpq-dev`.

3. Run `pip3 install -r requirements.txt` in the repository's root directory to get the necessary libraries.

4. Install PostgreSQL 9.5 or higher.

    * Linux command is `sudo apt-get install postgresql`.
    * Windows users can download [here](https://www.postgresql.org/download/windows).

5. Run the psql tool with `sudo -u postgres psql` and create a database by running the following commands:

    ```sql
    CREATE ROLE PUGs WITH LOGIN PASSWORD 'yourpassword';
    CREATE DATABASE PUGs OWNER PUGs;
    ```

    Be sure to replace `'yourpassword'` with your own desired password.

    Quit psql with `\q`

6. Create an environment file named `.env` with in the repository's root directory. Fill this template with the requisite information you've gathered...

    ```py
    DISCORD_BOT_TOKEN= #Bot token from the Discord developer portal
    DISCORD_BOT_LANGUAGE=en # Bot language (key from translations.json), E.g. "en"
    DISCORD_BOT_PREFIXES= # Bot commands prefixes, E.g. "! q! Q! > ?"

    G5API_URL= # URL where the web panel is hosted

    POSTGRESQL_USER= # "PUGs" (if you used the same username)
    POSTGRESQL_PASSWORD= # The DB password you set
    POSTGRESQL_DB= # "PUGs" (if you used the same DB name)
    POSTGRESQL_HOST= # The IP address of the DB server (127.0.0.1 if running on the same system as the bot)
    ```

7. Apply the database migrations by running `python3 migrate.py up`.

8. Run the launcher Python script by running, `python3 launcher.py`.

## Contributions

### Code Style
This project adheres to the [PEP8 style guide](https://www.python.org/dev/peps/pep-0008/) with 120 character line limits.

### Branches
Create a branch if you're working on an issue with the issue number and name like so: `100_Title-Separated-By-Dashes`.

### Commit Messages
Phrase commits in the present tense, e.g. `Fix bug` instead of `Fixed bug`.
