import sqlite3

DB_PATH = '../forum.db'

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# Создание таблицы topics
c.execute('''
CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number INTEGER,
    title TEXT,
    text TEXT,
    direction TEXT,
    user_id INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'approved'
)
''')
print('Таблица topics создана или уже существует.')

# Создание таблицы files
c.execute('''
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    path TEXT,
    direction TEXT,
    user_id INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'approved'
)
''')
print('Таблица files создана или уже существует.')

conn.commit()
conn.close()
print('Создание таблиц завершено.') 