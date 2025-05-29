import sqlite3
import os

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'forum.db'))

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

def add_column_if_not_exists(table, column, coltype):
    c.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in c.fetchall()]
    if column not in columns:
        print(f"Добавляю столбец {column} в таблицу {table}")
        c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
    else:
        print(f"Столбец {column} уже существует в {table}")

# Для topics
add_column_if_not_exists('topics', 'moderated_at', 'TIMESTAMP')
add_column_if_not_exists('topics', 'moderator_id', 'INTEGER')
add_column_if_not_exists('topics', 'moderation_comment', 'TEXT')

# Для topic_moderation_history
add_column_if_not_exists('topic_moderation_history', 'moderated_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')

conn.commit()
conn.close()
print('Миграция завершена.') 