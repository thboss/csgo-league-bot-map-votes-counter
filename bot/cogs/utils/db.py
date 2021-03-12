# db.py


import asyncio
import asyncpg
import os
import logging


class DBHelper:
    """ Class to contain database query wrapper functions. """

    def __init__(self, connect_url):
        """ Set attributes. """
        loop = asyncio.get_event_loop()
        self.logger = logging.getLogger('csgoleague.db')
        self.logger.info('Creating database connection pool')
        self.pool = loop.run_until_complete(asyncpg.create_pool(connect_url))

    async def close(self):
        """"""
        self.logger.info('Closing database connection pool')
        await self.pool.close()

    @staticmethod
    def _get_record_attrs(records, key):
        """ Get key list of attributes from list of Record objects. """
        return list(map(lambda r: r[key], records))

    async def _get_row(self, table, row_id, column):
        """ Generic method to get table row by object id. """
        statement = (
            f'SELECT * FROM {table}\n'
            f'    WHERE {column} = $1'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(statement, row_id)

        return {col: val for col, val in row.items()}

    async def _update_row(self, table, row_id, **data):
        """ Generic method to update table row by object id. """
        cols = list(data.keys())
        col_vals = ',\n    '.join(f'{col} = ${num}' for num, col in enumerate(cols, start=2))
        ret_vals = ',\n    '.join(cols)
        statement = (
            f'UPDATE {table}\n'
            f'    SET {col_vals}\n'
            '    WHERE id = $1\n'
            f'    RETURNING {ret_vals};'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                updated_vals = await connection.fetch(statement, row_id, *[data[col] for col in cols])

        return {col: val for rec in updated_vals for col, val in rec.items()}

    async def insert_guilds(self, *guild_ids):
        """ Add a list of guilds into the guilds table and return the ones successfully added. """
        rows = [(guild_id, None, None, None, None, None, None) for guild_id in guild_ids]
        statement = (
            'INSERT INTO guilds (id)\n'
            '    (SELECT id FROM unnest($1::guilds[]))\n'
            '    ON CONFLICT (id) DO NOTHING\n'
            '    RETURNING id;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                inserted = await connection.fetch(statement, rows)

        return self._get_record_attrs(inserted, 'id')

    async def delete_guilds(self, *guild_ids):
        """ Remove a list of guilds from the guilds table and return the ones successfully removed. """
        statement = (
            'DELETE FROM guilds\n'
            '    WHERE id::BIGINT = ANY($1::BIGINT[])\n'
            '    RETURNING id;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                deleted = await connection.fetch(statement, guild_ids)

        return self._get_record_attrs(deleted, 'id')

    async def sync_guilds(self, *guild_ids):
        """ Synchronizes the guilds table with the guilds in the bot. """
        insert_rows = [(guild_id, None, None, None, None, None, None) for guild_id in guild_ids]
        insert_statement = (
            'INSERT INTO guilds (id)\n'
            '    (SELECT id FROM unnest($1::guilds[]))\n'
            '    ON CONFLICT (id) DO NOTHING\n'
            '    RETURNING id;'
        )
        delete_statement = (
            'DELETE FROM guilds\n'
            '    WHERE id::BIGINT != ALL($1::BIGINT[])\n'
            '    RETURNING id;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                inserted = await connection.fetch(insert_statement, insert_rows)
                deleted = await connection.fetch(delete_statement, guild_ids)

        return self._get_record_attrs(inserted, 'id'), self._get_record_attrs(deleted, 'id')

    async def insert_pugs(self):
        """ Add a list of pugs into the pugs table and return the ones successfully added. """
        statement = (
            'INSERT INTO pugs (id) VALUES (DEFAULT)\n'
            '    RETURNING id;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                inserted = await connection.fetch(statement)

        return self._get_record_attrs(inserted, 'id')

    async def delete_pugs(self, *pug_ids):
        """ Remove a list of pugs from the pugs table and return the ones successfully removed. """
        statement = (
            'DELETE FROM pugs\n'
            '    WHERE id::BIGINT = ANY($1::BIGINT[])\n'
            '    RETURNING id;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                deleted = await connection.fetch(statement, pug_ids)

        return self._get_record_attrs(deleted, 'id')

    async def get_guild_pugs(self, guild_id):
        """ Get all pugs of the guild from the guild_pugs table. """
        statement = (
            'SELECT id FROM pugs\n'
            '    WHERE guild = $1;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                pugs = await connection.fetch(statement, guild_id)

        return self._get_record_attrs(pugs, 'id')

    async def get_users(self, *user_ids):
        """ Delete multiple users of a guild from the queued_users table. """
        statement = (
            'SELECT * FROM users\n'
            '    WHERE discord_id = ANY($1::BIGINT[]);'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                user = await connection.fetch(statement, user_ids)

        return list(zip(self._get_record_attrs(user, 'steam_id'), self._get_record_attrs(user, 'flag')))

    async def insert_users(self, discord_id, steam_id, flag):
        """ Insert multiple users into the users table. """
        statement = (
            'INSERT INTO users (discord_id, steam_id, flag)\n'
            '    (SELECT * FROM unnest($1::users[]))\n'
            '    ON CONFLICT (discord_id) DO NOTHING\n'
            '    RETURNING discord_id;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                inserted = await connection.fetch(statement, [(discord_id, steam_id, flag)])

        return self._get_record_attrs(inserted, 'discord_id')

    async def delete_users(self, *discord_ids):
        """ Delete multiple users from the users table. """
        statement = (
            'DELETE FROM users\n'
            '    WHERE discord_id::BIGINT = ANY($1::BIGINT[])\n'
            '    RETURNING discord_id;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                deleted = await connection.fetch(statement, discord_ids)

        return self._get_record_attrs(deleted, 'discord_id')

    async def get_queued_users(self, pug_id):
        """ Get all the queued users of the guild from the queued_users table. """
        statement = (
            'SELECT user_id FROM queued_users\n'
            '    WHERE pug_id = $1;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                pug = await connection.fetch(statement, pug_id)

        return self._get_record_attrs(pug, 'user_id')

    async def insert_queued_users(self, pug_id, *user_ids):
        """ Insert multiple users of a guild into the queued_users table. """
        statement = (
            'INSERT INTO queued_users (pug_id, user_id)\n'
            '    (SELECT * FROM unnest($1::queued_users[]));'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(statement, [(pug_id, user_id) for user_id in user_ids])

    async def delete_queued_users(self, pug_id, *user_ids):
        """ Delete multiple users of a guild from the queued_users table. """
        statement = (
            'DELETE FROM queued_users\n'
            '    WHERE pug_id = $1 AND user_id = ANY($2::BIGINT[])\n'
            '    RETURNING user_id;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                deleted = await connection.fetch(statement, pug_id, user_ids)

        return self._get_record_attrs(deleted, 'user_id')

    async def clear_queued_users(self, pug_id):
        """ Delete all users of a guild from the queued_users table. """
        statement = (
            'DELETE FROM queued_users\n'
            '    WHERE pug_id = $1\n'
            '    RETURNING user_id;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                deleted = await connection.fetch(statement, pug_id)

        return self._get_record_attrs(deleted, 'user_id')

    async def get_spect_users(self, pug_id):
        """ Get all the queued users of the guild from the spect_users table. """
        statement = (
            'SELECT user_id FROM spect_users\n'
            '    WHERE pug_id = $1;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                pug = await connection.fetch(statement, pug_id)

        return self._get_record_attrs(pug, 'user_id')

    async def insert_spect_users(self, pug_id, *user_ids):
        """ Insert multiple users of a guild into the spect_users table. """
        statement = (
            'INSERT INTO spect_users (pug_id, user_id)\n'
            '    (SELECT * FROM unnest($1::spect_users[]));'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(statement, [(pug_id, user_id) for user_id in user_ids])

    async def delete_spect_users(self, pug_id, *user_ids):
        """ Delete multiple users of a guild from the spect_users table. """
        statement = (
            'DELETE FROM spect_users\n'
            '    WHERE pug_id = $1 AND user_id = ANY($2::BIGINT[])\n'
            '    RETURNING user_id;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                deleted = await connection.fetch(statement, pug_id, user_ids)

        return self._get_record_attrs(deleted, 'user_id')

    async def get_banned_users(self, guild_id):
        """ Get all the banned users of the guild from the banned_users table. """
        select_statement = (
            'SELECT * FROM banned_users\n'
            '    WHERE guild_id = $1;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                guild = await connection.fetch(select_statement, guild_id)

        return dict(zip(self._get_record_attrs(guild, 'user_id'), self._get_record_attrs(guild, 'unban_time')))

    async def get_unbanned_users(self, guild_id):
        """ Get all the banned users of the guild from the banned_users table. """
        delete_statement = (
            'DELETE FROM banned_users\n'
            '    WHERE guild_id = $1 AND CURRENT_TIMESTAMP > unban_time\n'
            '    RETURNING user_id;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                deleted = await connection.fetch(delete_statement, guild_id)

        return self._get_record_attrs(deleted, 'user_id')

    async def insert_banned_users(self, guild_id, *user_ids, unban_time=None):
        """ Insert multiple users of a guild into the banned_users table"""
        statement = (
            'INSERT INTO banned_users (guild_id, user_id, unban_time)\n'
            '    VALUES($1, $2, $3)\n'
            '    ON CONFLICT (guild_id, user_id) DO UPDATE\n'
            '    SET unban_time = EXCLUDED.unban_time;'
        )

        insert_rows = [(guild_id, user_id, unban_time) for user_id in user_ids]

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                await connection.executemany(statement, insert_rows)

    async def delete_banned_users(self, guild_id, *user_ids):
        """ Delete multiple users of a guild from the banned_users table. """
        statement = (
            'DELETE FROM banned_users\n'
            '    WHERE guild_id = $1 AND user_id = ANY($2::BIGINT[])\n'
            '    RETURNING user_id;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                deleted = await connection.fetch(statement, guild_id, user_ids)

        return self._get_record_attrs(deleted, 'user_id')

    async def insert_matches(self, *match_ids):
        """ Insert multiple matches into the matches table. """
        rows = [(match_id, None, None, None, None, None, None, None, None,) for match_id in match_ids]
        statement = (
            'INSERT INTO matches (id)\n'
            '    (SELECT id FROM unnest($1::matches[]))\n'
            '    ON CONFLICT (id) DO NOTHING\n'
            '    RETURNING id;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                inserted = await connection.fetch(statement, rows)

        return self._get_record_attrs(inserted, 'id')

    async def delete_matches(self, *match_ids):
        """ Delete multiple matches from the matches table. """
        statement = (
            'DELETE FROM matches\n'
            '    WHERE id::SMALLINT = ANY($1::SMALLINT[])\n'
            '    RETURNING id;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                deleted = await connection.fetch(statement, match_ids)

        return self._get_record_attrs(deleted, 'id')

    async def get_match_users(self, match_id, team):
        """ Get all the match users of the match from the match_users table. """
        statement = (
            'SELECT user_id FROM match_users\n'
            '    WHERE match_id = $1 AND team = $2;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                match = await connection.fetch(statement, match_id, team)

        return self._get_record_attrs(match, 'user_id')

    async def get_all_matches_users(self):
        """ Get all the match users from the match_users table. """
        statement = (
            'SELECT user_id FROM match_users;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                users = await connection.fetch(statement)

        return self._get_record_attrs(users, 'user_id')

    async def insert_match_users(self, match_id, *user_ids, team=None):
        """ Insert multiple users of a guild into the banned_users table"""
        statement = (
            'INSERT INTO match_users (match_id, user_id, team)\n'
            '    VALUES($1, $2, $3);'
        )

        insert_rows = [(match_id, user_id, team) for user_id in user_ids]

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                await connection.executemany(statement, insert_rows)

    async def clear_match_users(self, match_id):
        """ Delete all users of a match from the match_users table. """
        statement = (
            'DELETE FROM match_users\n'
            '    WHERE match_id = $1\n'
            '    RETURNING user_id;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                deleted = await connection.fetch(statement, match_id)

        return self._get_record_attrs(deleted, 'user_id')

    async def get_all_matches(self):
        """ Get a match's row from the matches table. """
        statement = (
            'SELECT id FROM matches;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetch(statement)

        return self._get_record_attrs(row, 'id')

    async def get_pug(self, row_id, column='id'):
        """ Get a pug's row from the pugs table. """
        return await self._get_row('pugs', row_id, column)

    async def update_pug(self, pug_id, **data):
        """ Update a pug's row in the pugs table. """
        return await self._update_row('pugs', pug_id, **data)

    async def get_guild(self, guild_id, column='id'):
        """ Get a guild's row from the guilds table. """
        return await self._get_row('guilds', guild_id, column)

    async def get_user(self, user_id, column='discord_id'):
        """ Get a guild's row from the guilds table. """
        return await self._get_row('users', user_id, column)

    async def update_guild(self, guild_id, **data):
        """ Update a guild's row in the guilds table. """
        return await self._update_row('guilds', guild_id, **data)

    async def get_match(self, match_id, column='id'):
        """ Get a match's row from the matches table. """
        return await self._get_row('matches', match_id, column)

    async def update_match(self, match_id, **data):
        """ Update a match's row in the matches table. """
        return await self._update_row('matches', match_id, **data)
