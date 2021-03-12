# 20200621_01_XkKXW-add-map-draft-columns.py

from yoyo import step
import os

__depends__ = {'20200513_01_kPWNp-create-base-tables'}

icons_dic = 'assets/maps/icons/'
maps = [icon.split('-')[1].split('.')[0] for icon in os.listdir(icons_dic)
        if icon.endswith('.png') and '-' in icon and os.stat(icons_dic + icon).st_size < 256000]
add_maps = drop_maps = 'ALTER TABLE pugs\n'
m = os.listdir('assets/maps/icons/')

for i, m in enumerate(maps, start=1):
    if i != len(maps):
        add_maps += f'ADD COLUMN {m} BOOL NOT NULL DEFAULT true,\n'
        drop_maps += f'DROP COLUMN {m},\n'
    else:
        add_maps += f'ADD COLUMN {m} BOOL NOT NULL DEFAULT true;'
        drop_maps += f'DROP COLUMN {m};'

steps = [
    step(
        'CREATE TYPE map_method AS ENUM(\'ban\', \'vote\', \'random\');',
        'DROP TYPE map_method;'
    ),
    step(
        (
            'ALTER TABLE pugs\n'
            'ADD COLUMN map_method map_method DEFAULT \'ban\';'
        ),
        (
            'ALTER TABLE pugs\n'
            'DROP COLUMN map_method;'
        )
    ),
    step(
        (
            add_maps
        ),
        (
            drop_maps
        )
    )
]