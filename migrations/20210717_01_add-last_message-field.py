# 20210717_01_add-last_message-field.py

from yoyo import step

__depends__ = {'20200513_01_kPWNp-create-base-tables'}


steps = [
    step(
        (
            'ALTER TABLE pugs\n'
            'ADD COLUMN last_message BIGINT DEFAULT NULL;'
        ),
        (
            'ALTER TABLE pugs\n'
            'DROP COLUMN last_message;'
        )
    )
]
