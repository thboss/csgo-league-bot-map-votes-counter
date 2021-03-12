# 20210225_01-add-matches-table.py

from yoyo import step


__depends__ = {'20200513_01_kPWNp-create-base-tables'}

steps = [
    step(
        (
            'CREATE TABLE matches(\n'
            '    id SMALLSERIAL PRIMARY KEY,\n'
            '    guild BIGINT DEFAULT NULL REFERENCES guilds (id) ON DELETE CASCADE,\n'
            '    pug SMALLINT DEFAULT NULL REFERENCES pugs (id) ON DELETE CASCADE,\n'
            '    message BIGINT DEFAULT NULL,\n'
            '    category BIGINT DEFAULT NULL,\n'
            '    team1_channel BIGINT DEFAULT NULL,\n'
            '    team2_channel BIGINT DEFAULT NULL,\n'
            '    team1_name VARCHAR(32) DEFAULT NULL,\n'
            '    team2_name VARCHAR(32) DEFAULT NULL\n'
            ');'
        ),
        'DROP TABLE matches;'
    ),
    step(
        'CREATE TYPE team AS ENUM(\'team1\', \'team2\');',
        'DROP TYPE team;'
    ),
    step(
        (
            'CREATE TABLE match_users(\n'
            '    match_id SMALLSERIAL REFERENCES matches (id) ON DELETE CASCADE,\n'
            '    user_id BIGSERIAL REFERENCES users (discord_id),\n'
            '    team team DEFAULT NULL,\n'
            '    CONSTRAINT match_user_pkey PRIMARY KEY (match_id, user_id)\n'
            ');'
        ),
        'DROP TABLE match_users;'
    )
]