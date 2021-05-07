# 20200513_01_kPWNp-create-base-tables.py

from yoyo import step

__depends__ = {}

steps = [
    step(
        'CREATE TYPE team_method AS ENUM(\'captains\', \'autobalance\', \'random\');',
        'DROP TYPE team_method;'
    ),
    step(
        'CREATE TYPE captain_method AS ENUM(\'volunteer\', \'rank\', \'random\');',
        'DROP TYPE captain_method;'
    ),
    step(
        (
            'CREATE TABLE guilds(\n'
            '    id BIGSERIAL PRIMARY KEY,\n'
            '    user_id SMALLINT DEFAULT NULL,\n'
            '    api_key VARCHAR(65) DEFAULT NULL,\n'
            '    linked_role BIGINT DEFAULT NULL,\n'
            '    prematch_channel BIGINT DEFAULT NULL\n'
            ');'
        ),
        'DROP TABLE guilds;'
    ),
    step(
        (
            'CREATE TABLE pugs(\n'
            '    id SMALLSERIAL PRIMARY KEY,\n'
            '    guild BIGINT DEFAULT NULL REFERENCES guilds (id) ON DELETE CASCADE,\n'
            '    queue_channel BIGINT DEFAULT NULL,\n'
            '    lobby_channel BIGINT DEFAULT NULL,\n'
            '    capacity SMALLINT DEFAULT 10,\n'
            '    team_method team_method DEFAULT \'captains\',\n'
            '    captain_method captain_method DEFAULT \'random\'\n'
            ');'
        ),
        'DROP TABLE pugs;'
    ),
    step(
        (
            'CREATE TABLE users('
            '    discord_id BIGSERIAL PRIMARY KEY,\n'
            '    steam_id VARCHAR(18) DEFAULT NULL,\n'
            '    flag VARCHAR(3) DEFAULT NULL\n'
            ');'
        ),
        'DROP TABLE users;'
    ),
    step(
        (
            'CREATE TABLE queued_users(\n'
            '    pug_id BIGSERIAL REFERENCES pugs (id) ON DELETE CASCADE,\n'
            '    user_id BIGSERIAL REFERENCES users (discord_id) ON DELETE CASCADE,\n'
            '    CONSTRAINT queued_user_pkey PRIMARY KEY (pug_id, user_id)\n'
            ');'
        ),
        'DROP TABLE queued_users;'
    ),
    step(
        (
            'CREATE TABLE spect_users(\n'
            '    pug_id BIGSERIAL REFERENCES pugs (id) ON DELETE CASCADE,\n'
            '    user_id BIGSERIAL REFERENCES users (discord_id) ON DELETE CASCADE,\n'
            '    CONSTRAINT spect_user_pkey PRIMARY KEY (pug_id, user_id)\n'
            ');'
        ),
        'DROP TABLE spect_users;'
    ),
    step(
        (
            'CREATE TABLE banned_users(\n'
            '    guild_id BIGSERIAL REFERENCES guilds (id) ON DELETE CASCADE,\n'
            '    user_id BIGSERIAL REFERENCES users (discord_id),\n'
            '    unban_time TIMESTAMP WITH TIME ZONE DEFAULT null,\n'
            '    CONSTRAINT banned_user_pkey PRIMARY KEY (guild_id, user_id)\n'
            ');'
        ),
        'DROP TABLE banned_users;'
    )
]
