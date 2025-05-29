import sqlite3
import os

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'forum.db'))

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# Удаляем старые таблицы, если есть
c.execute('DROP TABLE IF EXISTS users')
c.execute('DROP TABLE IF EXISTS topics')
c.execute('DROP TABLE IF EXISTS files')
c.execute('DROP TABLE IF EXISTS messages')
c.execute('DROP TABLE IF EXISTS activation_keys')
c.execute('DROP TABLE IF EXISTS user_directions')
c.execute('DROP TABLE IF EXISTS telegram_bindings')
c.execute('DROP TABLE IF EXISTS telegram_link_codes')
c.execute('DROP TABLE IF EXISTS telegram_login_codes')
c.execute('DROP TABLE IF EXISTS login_logs')
c.execute('DROP TABLE IF EXISTS bot_logs')
c.execute('DROP TABLE IF EXISTS forum_logs')

# Создаём таблицы
c.execute('''
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    email TEXT UNIQUE,
    role TEXT DEFAULT 'user',
    first_name TEXT,
    last_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP,
    avatar_url TEXT
)
''')

c.execute('''
CREATE TABLE topics (
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

c.execute('''
CREATE TABLE files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    path TEXT,
    direction TEXT,
    user_id INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'approved',
    filename TEXT,
    author_name TEXT
)
''')

c.execute('''
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    text TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')

c.execute('''
CREATE TABLE activation_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE NOT NULL,
    direction TEXT,
    first_name TEXT,
    last_name TEXT,
    role TEXT,
    key_type TEXT,
    is_used INTEGER DEFAULT 0,
    used_by_user_id INTEGER,
    used_at DATETIME,
    expires_at DATETIME
)
''')

c.execute('''
CREATE TABLE user_directions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    direction TEXT
)
''')

c.execute('''
CREATE TABLE telegram_bindings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    telegram_id INTEGER,
    telegram_username TEXT
)
''')

c.execute('''
CREATE TABLE telegram_link_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    code TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')

c.execute('''
CREATE TABLE telegram_login_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    code TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')

c.execute('''
CREATE TABLE login_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT,
    ip_address TEXT,
    success INTEGER,
    reason TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')

c.execute('''
CREATE TABLE bot_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT,
    action TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')

c.execute('''
CREATE TABLE forum_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ip_address TEXT,
    user_id INTEGER,
    username TEXT,
    action TEXT,
    direction TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')

conn.commit()
conn.close()
print('База данных полностью пересоздана!') 