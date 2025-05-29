import sqlite3

DB_PATH = '../forum.db'

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# Выводим список всех таблиц
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [row[0] for row in c.fetchall()]
print('Таблицы в базе:', tables)

for table in tables:
    c.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in c.fetchall()]
    print(f'Столбцы в {table}:', columns)

def add_column_if_not_exists(table, column, coltype, default):
    c.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in c.fetchall()]
    if column not in columns:
        c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype} DEFAULT '{default}'")
        print(f"Добавлен столбец {column} в {table}")
    else:
        print(f"Столбец {column} уже существует в {table}")

add_column_if_not_exists('topics', 'status', 'TEXT', 'approved')
add_column_if_not_exists('files', 'status', 'TEXT', 'approved')

conn.commit()
conn.close()
print('Миграция завершена.') 