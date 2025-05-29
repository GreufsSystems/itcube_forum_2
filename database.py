import sqlite3
from datetime import datetime, timedelta
import os
import secrets
import logging
import asyncio

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='database.log'
)
logger = logging.getLogger(__name__)

# Абсолютный путь к базе данных
DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), 'forum.db'))

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()

    # Создаем таблицу пользователей
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT UNIQUE,
            role TEXT DEFAULT 'user',
            first_name TEXT,
            last_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            telegram_id INTEGER UNIQUE,
            telegram_username TEXT
        )
    ''')

    # Создаем таблицу тем с полем статуса
    c.execute('''
        CREATE TABLE IF NOT EXISTS topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            number INTEGER NOT NULL,
            title TEXT NOT NULL,
            text TEXT NOT NULL,
            direction TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_id INTEGER,
            status TEXT NOT NULL DEFAULT 'pending',
            moderated_at TIMESTAMP,
            moderator_id INTEGER,
            moderation_comment TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (moderator_id) REFERENCES users (id)
        )
    ''')

    # Создаем таблицу файлов
    c.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            path TEXT NOT NULL,
            direction TEXT NOT NULL,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_id INTEGER,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Создаем таблицу сообщений
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_id INTEGER,
            topic_id INTEGER,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (topic_id) REFERENCES topics (id)
        )
    ''')

    # Создаем таблицу ключей активации
    c.execute('''
        CREATE TABLE IF NOT EXISTS activation_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            direction TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'student',
            key_type TEXT NOT NULL DEFAULT 'permanent',
            is_used INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            used_by_user_id INTEGER,
            used_at TIMESTAMP,
            first_name TEXT,
            last_name TEXT,
            expires_at TIMESTAMP,
            FOREIGN KEY (used_by_user_id) REFERENCES users (id)
        )
    ''')

    # Создаем таблицу направлений пользователя
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_directions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            direction TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Создаем таблицу привязок Telegram
    c.execute('''
        CREATE TABLE IF NOT EXISTS telegram_bindings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            telegram_id INTEGER UNIQUE NOT NULL,
            telegram_username TEXT,
            bind_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Создаем таблицу для модерации сообщений
    c.execute('''
        CREATE TABLE IF NOT EXISTS message_moderation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL,
            moderator_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            comment TEXT,
            moderated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (message_id) REFERENCES messages (id),
            FOREIGN KEY (moderator_id) REFERENCES users (id)
        )
    ''')

    # Создаем таблицу для модерации файлов
    c.execute('''
        CREATE TABLE IF NOT EXISTS file_moderation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            moderator_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            comment TEXT,
            moderated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (file_id) REFERENCES files (id),
            FOREIGN KEY (moderator_id) REFERENCES users (id)
        )
    ''')

    # Создаем таблицу для кодов привязки
    c.execute('''
        CREATE TABLE IF NOT EXISTS telegram_link_codes (
            code TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Создаем таблицу для токенов входа
    c.execute('''
        CREATE TABLE IF NOT EXISTS telegram_login_tokens (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Создаем таблицу для истории модерации тем
    c.execute('''
        CREATE TABLE IF NOT EXISTS topic_moderation_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_id INTEGER NOT NULL,
            moderator_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            comment TEXT,
            moderated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (topic_id) REFERENCES topics (id),
            FOREIGN KEY (moderator_id) REFERENCES users (id)
        )
    ''')

    conn.commit()
    conn.close()

def add_user(username, password, email, role='user', first_name=None, last_name=None):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO users (username, password, email, role, first_name, last_name)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (username, password, email, role, first_name, last_name))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_user_by_username(username):
    conn = get_db_connection()
    c = conn.cursor()
    user = c.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()
    return user

def get_user_by_id(user_id):
    conn = get_db_connection()
    c = conn.cursor()
    user = c.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    return user

def update_last_login(user_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        UPDATE users 
        SET last_login = CURRENT_TIMESTAMP 
        WHERE id = ?
    ''', (user_id,))
    conn.commit()
    conn.close()

def get_all_users():
    conn = get_db_connection()
    c = conn.cursor()
    users = c.execute('SELECT id, username, first_name, last_name, email, role, created_at, last_login FROM users').fetchall()
    conn.close()
    return users

def delete_user(user_id):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.commit()
        return True
    except sqlite3.Error:
        return False
    finally:
        conn.close()

def update_user_role(user_id, new_role):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute('UPDATE users SET role = ? WHERE id = ?', (new_role, user_id))
        conn.commit()
        return True
    except sqlite3.Error:
        return False
    finally:
        conn.close()

def generate_activation_key(direction, first_name, last_name, role='student', key_type='permanent'):
    key = secrets.token_urlsafe(12)
    conn = get_db_connection()
    c = conn.cursor()
    
    # Если ключ временный, устанавливаем срок действия 1 год
    expires_at = None
    if key_type == 'temporary':
        expires_at = datetime.now() + timedelta(days=365)
    
    c.execute('''
        INSERT INTO activation_keys 
        (key, direction, first_name, last_name, role, key_type, expires_at) 
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (key, direction, first_name, last_name, role, key_type, expires_at))
    
    conn.commit()
    conn.close()
    return key

def get_all_activation_keys():
    conn = get_db_connection()
    c = conn.cursor()
    keys = c.execute('SELECT * FROM activation_keys ORDER BY created_at DESC').fetchall()
    conn.close()
    return keys

def use_activation_key(key, user_id):
    conn = get_db_connection()
    c = conn.cursor()
    
    # Проверяем, не истек ли срок действия ключа
    key_data = c.execute('''
        SELECT * FROM activation_keys 
        WHERE key = ? AND is_used = 0 
        AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
    ''', (key,)).fetchone()
    
    if not key_data:
        conn.close()
        return False
    
    c.execute('''
        UPDATE activation_keys
        SET is_used = 1, used_by_user_id = ?, used_at = CURRENT_TIMESTAMP
        WHERE key = ? AND is_used = 0
    ''', (user_id, key))
    
    updated = c.rowcount
    conn.commit()
    conn.close()
    return updated > 0

def add_user_direction(user_id, direction):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('INSERT INTO user_directions (user_id, direction) VALUES (?, ?)', (user_id, direction))
    conn.commit()
    conn.close()

def ensure_telegram_tables():
    """Проверяет и создает необходимые таблицы для работы с Telegram и недостающие столбцы в users"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        # Проверяем наличие колонок в таблице users
        c.execute("PRAGMA table_info(users)")
        columns = [row['name'] for row in c.fetchall()]

        # Добавляем недостающие колонки
        if 'telegram_id' not in columns:
            logger.info("Добавление колонки telegram_id в таблицу users")
            c.execute("ALTER TABLE users ADD COLUMN telegram_id INTEGER")
        if 'telegram_username' not in columns:
            logger.info("Добавление колонки telegram_username в таблицу users")
            c.execute("ALTER TABLE users ADD COLUMN telegram_username TEXT")
        if 'avatar_url' not in columns:
            logger.info("Добавление колонки avatar_url в таблицу users")
            c.execute("ALTER TABLE users ADD COLUMN avatar_url TEXT")
        if 'about' not in columns:
            logger.info("Добавление колонки about в таблицу users")
            c.execute("ALTER TABLE users ADD COLUMN about TEXT")

        # Создаем таблицу telegram_bindings, если её нет
        c.execute('''
            CREATE TABLE IF NOT EXISTS telegram_bindings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                telegram_id INTEGER UNIQUE NOT NULL,
                telegram_username TEXT,
                bind_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')

        conn.commit()
        logger.info("Таблицы для Telegram и users успешно проверены и созданы")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при создании таблиц для Telegram: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

# Вызываем функцию при импорте модуля
ensure_telegram_tables()

def bind_telegram_account(user_id, telegram_id, telegram_username):
    """
    Привязывает аккаунт Telegram к пользователю
    :param user_id: ID пользователя в базе данных
    :param telegram_id: ID пользователя в Telegram
    :param telegram_username: Имя пользователя в Telegram
    :return: True если успешно, False если ошибка
    """
    logger.info(f"Начало привязки аккаунта: user_id={user_id}, telegram_id={telegram_id}, username={telegram_username}")
    
    conn = get_db_connection()
    c = conn.cursor()
    try:
        # Проверяем существование пользователя
        user = c.execute('SELECT id FROM users WHERE id = ?', (user_id,)).fetchone()
        if not user:
            logger.error(f"Пользователь с ID {user_id} не найден")
            return False

        # Проверяем, не привязан ли уже этот Telegram ID
        existing = c.execute('SELECT id FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
        if existing and existing['id'] != user_id:
            logger.error(f"Telegram ID {telegram_id} уже привязан к пользователю {existing['id']}")
            return False

        # Начинаем транзакцию
        c.execute('BEGIN TRANSACTION')
        
        try:
            # Обновляем данные пользователя
            logger.info(f"Обновление данных пользователя {user_id}")
            c.execute('''
                UPDATE users 
                SET telegram_id = ?, telegram_username = ? 
                WHERE id = ?
            ''', (telegram_id, telegram_username, user_id))
            
            # Добавляем запись в таблицу привязок
            logger.info(f"Добавление записи в telegram_bindings для пользователя {user_id}")
            c.execute('''
                INSERT OR REPLACE INTO telegram_bindings 
                (user_id, telegram_id, telegram_username) 
                VALUES (?, ?, ?)
            ''', (user_id, telegram_id, telegram_username))
            
            # Подтверждаем транзакцию
            conn.commit()
            logger.info(f"Успешная привязка аккаунта для пользователя {user_id}")
            return True
            
        except sqlite3.Error as e:
            # Откатываем транзакцию в случае ошибки
            conn.rollback()
            logger.error(f"Ошибка SQL при привязке аккаунта: {e}")
            return False
            
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при привязке аккаунта: {e}")
        return False
    finally:
        conn.close()
        logger.info("Соединение с базой данных закрыто")

def get_user_by_telegram_id(telegram_id):
    conn = get_db_connection()
    c = conn.cursor()
    binding = c.execute('''
        SELECT u.* FROM users u
        JOIN telegram_bindings t ON u.id = t.user_id
        WHERE t.telegram_id = ?
    ''', (telegram_id,)).fetchone()
    conn.close()
    return binding

def get_telegram_binding_by_user_id(user_id):
    conn = get_db_connection()
    c = conn.cursor()
    binding = c.execute('SELECT * FROM telegram_bindings WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    return binding

def unbind_telegram_account(telegram_id):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute('''
            UPDATE users SET telegram_id = NULL, telegram_username = NULL WHERE telegram_id = ?
        ''', (telegram_id,))
        conn.commit()
        return True
    except sqlite3.Error:
        return False
    finally:
        conn.close()

# Инициализация базы данных при импорте модуля
if not os.path.exists(DB_PATH):
    init_db()

# --- ДОБАВЛЕНО: создание таблицы telegram_bindings, если её нет ---
def ensure_telegram_bindings_table():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS telegram_bindings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            telegram_id INTEGER UNIQUE NOT NULL,
            telegram_username TEXT,
            bind_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    conn.commit()
    conn.close()

# Вызов при импорте модуля
ensure_telegram_bindings_table()
# --- КОНЕЦ ДОБАВЛЕНИЯ ---

def ensure_telegram_link_codes_table():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS telegram_link_codes (
            code TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

ensure_telegram_link_codes_table()

# Функция для создания кода
def create_telegram_link_code(user_id):
    code = secrets.token_hex(3)
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('INSERT INTO telegram_link_codes (code, user_id) VALUES (?, ?)', (code, user_id))
    conn.commit()
    conn.close()
    return code

def get_telegram_link_code(code):
    conn = get_db_connection()
    c = conn.cursor()
    row = c.execute('SELECT * FROM telegram_link_codes WHERE code = ?', (code,)).fetchone()
    conn.close()
    return row

def delete_telegram_link_code(code):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('DELETE FROM telegram_link_codes WHERE code = ?', (code,))
    conn.commit()
    conn.close()

def ensure_telegram_login_codes_table():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS telegram_login_codes (
            user_id INTEGER PRIMARY KEY,
            code TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

ensure_telegram_login_codes_table()

def create_telegram_login_code(user_id):
    code = secrets.token_hex(3)
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('REPLACE INTO telegram_login_codes (user_id, code) VALUES (?, ?)', (user_id, code))
    conn.commit()
    conn.close()
    return code

def get_telegram_login_code(user_id):
    conn = get_db_connection()
    c = conn.cursor()
    row = c.execute('SELECT * FROM telegram_login_codes WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    return row

def check_and_delete_telegram_login_code(user_id, code, max_age_minutes=5):
    conn = get_db_connection()
    c = conn.cursor()
    row = c.execute('SELECT * FROM telegram_login_codes WHERE user_id = ?', (user_id,)).fetchone()
    valid = False
    expired = False
    if row:
        created_at = row['created_at']
        try:
            created_at_dt = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S.%f')
        except ValueError:
            created_at_dt = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
        # Используем UTC-время для сравнения
        now_utc = datetime.utcnow()
        if row['code'] == code:
            if now_utc - created_at_dt > timedelta(minutes=max_age_minutes):
                expired = True
            else:
                valid = True
            c.execute('DELETE FROM telegram_login_codes WHERE user_id = ?', (user_id,))
            conn.commit()
    conn.close()
    return valid, expired

def ensure_login_logs_table():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS login_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            ip TEXT,
            success INTEGER,
            reason TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

ensure_login_logs_table()

def log_login_attempt(user_id, username, ip, success, reason):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('INSERT INTO login_logs (user_id, username, ip, success, reason) VALUES (?, ?, ?, ?, ?)',
              (user_id, username, ip, int(success), reason))
    conn.commit()
    conn.close()

def get_telegram_login_token(token):
    conn = get_db_connection()
    c = conn.cursor()
    row = c.execute('SELECT * FROM telegram_login_tokens WHERE token = ?', (token,)).fetchone()
    conn.close()
    return row

def delete_telegram_login_token(token):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('DELETE FROM telegram_login_tokens WHERE token = ?', (token,))
    conn.commit()
    conn.close()

def create_telegram_login_token(user_id):
    token = secrets.token_urlsafe(32)
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('INSERT INTO telegram_login_tokens (token, user_id) VALUES (?, ?)', (token, user_id))
    conn.commit()
    conn.close()
    return token

def unbind_telegram_by_username(username):
    conn = get_db_connection()
    c = conn.cursor()
    user = c.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
    if user:
        c.execute('DELETE FROM telegram_bindings WHERE user_id = ?', (user['id'],))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

def get_user_directions_by_user_id(user_id):
    conn = get_db_connection()
    c = conn.cursor()
    rows = c.execute('SELECT direction FROM user_directions WHERE user_id = ?', (user_id,)).fetchall()
    conn.close()
    return [row['direction'] for row in rows]

def get_teachers_and_admins():
    conn = get_db_connection()
    c = conn.cursor()
    teachers = c.execute('''
        SELECT u.id, u.username, u.first_name, u.last_name, u.role, u.avatar_url, u.about, ud.direction
        FROM users u
        LEFT JOIN user_directions ud ON u.id = ud.user_id
        WHERE u.role = 'teacher'
    ''').fetchall()
    admins = c.execute('''
        SELECT u.id, u.username, u.first_name, u.last_name, u.role, u.avatar_url, u.about
        FROM users u
        WHERE u.role = 'admin' AND u.username != 'admin'
    ''').fetchall()
    conn.close()
    return teachers, admins

def ensure_activation_keys_columns():
    conn = get_db_connection()
    c = conn.cursor()
    # Получаем список столбцов
    c.execute("PRAGMA table_info(activation_keys)")
    columns = [row['name'] for row in c.fetchall()]
    # Добавляем недостающие столбцы
    if 'role' not in columns:
        c.execute("ALTER TABLE activation_keys ADD COLUMN role TEXT NOT NULL DEFAULT 'student'")
    if 'key_type' not in columns:
        c.execute("ALTER TABLE activation_keys ADD COLUMN key_type TEXT NOT NULL DEFAULT 'permanent'")
    if 'expires_at' not in columns:
        c.execute("ALTER TABLE activation_keys ADD COLUMN expires_at TIMESTAMP")
    conn.commit()
    conn.close()

# Вызов при импорте модуля
ensure_activation_keys_columns()

def moderate_message(message_id, moderator_id, status, comment=None):
    """
    Модерирует сообщение
    :param message_id: ID сообщения
    :param moderator_id: ID модератора
    :param status: Статус модерации ('approved', 'rejected')
    :param comment: Комментарий модератора
    :return: True если успешно, False если ошибка
    """
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO message_moderation (message_id, moderator_id, status, comment)
            VALUES (?, ?, ?, ?)
        ''', (message_id, moderator_id, status, comment))
        conn.commit()
        return True
    except sqlite3.Error:
        return False
    finally:
        conn.close()

def moderate_file(file_id, moderator_id, status, comment=None):
    """
    Модерирует файл
    :param file_id: ID файла
    :param moderator_id: ID модератора
    :param status: Статус модерации ('approved', 'rejected')
    :param comment: Комментарий модератора
    :return: True если успешно, False если ошибка
    """
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO file_moderation (file_id, moderator_id, status, comment)
            VALUES (?, ?, ?, ?)
        ''', (file_id, moderator_id, status, comment))
        conn.commit()
        return True
    except sqlite3.Error:
        return False
    finally:
        conn.close()

def get_pending_messages():
    """
    Получает список сообщений, ожидающих модерации
    :return: Список сообщений
    """
    conn = get_db_connection()
    c = conn.cursor()
    messages = c.execute('''
        SELECT m.*, u.username, u.first_name, u.last_name
        FROM messages m
        LEFT JOIN message_moderation mod ON m.id = mod.message_id
        JOIN users u ON m.user_id = u.id
        WHERE mod.id IS NULL
        ORDER BY m.created_at DESC
    ''').fetchall()
    conn.close()
    return messages

def get_pending_files():
    """
    Получает список файлов, ожидающих модерации
    :return: Список файлов
    """
    conn = get_db_connection()
    c = conn.cursor()
    files = c.execute('''
        SELECT f.*, u.username, u.first_name, u.last_name
        FROM files f
        LEFT JOIN file_moderation mod ON f.id = mod.file_id
        JOIN users u ON f.user_id = u.id
        WHERE mod.id IS NULL
        ORDER BY f.uploaded_at DESC
    ''').fetchall()
    conn.close()
    return files

def get_message_moderation_history(message_id):
    """
    Получает историю модерации сообщения
    :param message_id: ID сообщения
    :return: История модерации
    """
    conn = get_db_connection()
    c = conn.cursor()
    history = c.execute('''
        SELECT mod.*, u.username as moderator_username
        FROM message_moderation mod
        JOIN users u ON mod.moderator_id = u.id
        WHERE mod.message_id = ?
        ORDER BY mod.moderated_at DESC
    ''', (message_id,)).fetchall()
    conn.close()
    return history

def get_file_moderation_history(file_id):
    """
    Получает историю модерации файла
    :param file_id: ID файла
    :return: История модерации
    """
    conn = get_db_connection()
    c = conn.cursor()
    history = c.execute('''
        SELECT mod.*, u.username as moderator_username
        FROM file_moderation mod
        JOIN users u ON mod.moderator_id = u.id
        WHERE mod.file_id = ?
        ORDER BY mod.moderated_at DESC
    ''', (file_id,)).fetchall()
    conn.close()
    return history

def get_pending_topics(direction=None):
    """Получает список тем, ожидающих модерации"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        if direction:
            topics = c.execute('''
                SELECT t.*, u.username, u.first_name, u.last_name
                FROM topics t
                JOIN users u ON t.user_id = u.id
                WHERE t.status = 'pending' AND t.direction = ?
                ORDER BY t.created_at DESC
            ''', (direction,)).fetchall()
        else:
            topics = c.execute('''
                SELECT t.*, u.username, u.first_name, u.last_name
                FROM topics t
                JOIN users u ON t.user_id = u.id
                WHERE t.status = 'pending'
                ORDER BY t.created_at DESC
            ''').fetchall()
        return topics
    finally:
        conn.close()

def get_topic_by_id(topic_id):
    """Получает тему по ID с информацией об авторе"""
    conn = get_db_connection()
    c = conn.cursor()
    topic = c.execute('''
        SELECT t.*, u.username, u.first_name, u.last_name
        FROM topics t
        LEFT JOIN users u ON t.user_id = u.id
        WHERE t.id = ?
    ''', (topic_id,)).fetchone()
    conn.close()
    return topic

def get_topic_moderation_history(topic_id):
    """Получает историю модерации темы"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        history = c.execute('''
            SELECT mh.*, u.username, u.first_name, u.last_name
            FROM topic_moderation_history mh
            JOIN users u ON mh.moderator_id = u.id
            WHERE mh.topic_id = ?
            ORDER BY mh.moderated_at DESC
        ''', (topic_id,)).fetchall()
        return history
    finally:
        conn.close()

def moderate_topic(topic_id, moderator_id, status, comment=None):
    """Модерирует тему"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        # Обновляем статус темы
        c.execute('''
            UPDATE topics 
            SET status = ?, 
                moderated_at = CURRENT_TIMESTAMP,
                moderator_id = ?,
                moderation_comment = ?
            WHERE id = ?
        ''', (status, moderator_id, comment, topic_id))
        
        # Добавляем запись в историю модерации
        c.execute('''
            INSERT INTO topic_moderation_history 
            (topic_id, moderator_id, status, comment)
            VALUES (?, ?, ?, ?)
        ''', (topic_id, moderator_id, status, comment))
        
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Ошибка при модерации темы: {e}")
        return False
    finally:
        conn.close()

def get_approved_topics(direction=None, user_id=None):
    """Получает список одобренных тем"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        query = '''
            SELECT t.*, u.username, u.first_name, u.last_name
            FROM topics t
                JOIN users u ON t.user_id = u.id
            WHERE t.status = 'approved'
        '''
        params = []
        if direction:
            query += ' AND t.direction = ?'
            params.append(direction)
        if user_id:
            query += ' AND t.user_id = ?'
            params.append(user_id)
        query += ' ORDER BY t.created_at DESC'
        topics = c.execute(query, params).fetchall()
        return topics
    finally:
        conn.close()

def update_topic(topic_id, title=None, text=None):
    """Обновляет тему (для модератора)"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        updates = []
        params = []
        if title is not None:
            updates.append('title = ?')
            params.append(title)
        if text is not None:
            updates.append('text = ?')
            params.append(text)
        if not updates:
            return False
        query = f'''
            UPDATE topics 
            SET {', '.join(updates)}
            WHERE id = ?
        '''
        params.append(topic_id)
        c.execute(query, params)
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Ошибка при обновлении темы: {e}")
        return False
    finally:
        conn.close()

# Создаем таблицу для истории модерации тем при инициализации базы
def init_topic_moderation_tables():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Добавляем колонки для модерации в таблицу topics
    c.execute('PRAGMA table_info(topics)')
    columns = [row[1] for row in c.fetchall()]
    
    if 'moderated_at' not in columns:
        c.execute('ALTER TABLE topics ADD COLUMN moderated_at DATETIME')
    if 'moderated_by' not in columns:
        c.execute('ALTER TABLE topics ADD COLUMN moderated_by INTEGER')
    
    # Создаем таблицу для истории модерации
    c.execute('''
        CREATE TABLE IF NOT EXISTS topic_moderation_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_id INTEGER NOT NULL,
            moderator_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            comment TEXT,
            moderated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (topic_id) REFERENCES topics (id),
            FOREIGN KEY (moderator_id) REFERENCES users (id)
        )
    ''')
    
    conn.commit()
    conn.close()

# Вызываем инициализацию при импорте модуля
init_topic_moderation_tables()

def update_user_about(user_id, about):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute('UPDATE users SET about = ? WHERE id = ?', (about, user_id))
        conn.commit()
        return True
    except sqlite3.Error:
        return False
    finally:
        conn.close()

def update_user_direction(user_id, direction):
    """Обновление направления пользователя"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute('UPDATE users SET direction = ? WHERE id = ?', (direction, user_id))
        conn.commit()
        return True
    except sqlite3.Error:
        return False
    finally:
        conn.close()

def get_teachers_and_admins_list():
    """
    Получает список ID преподавателей и администраторов из базы данных
    :return: Список ID пользователей с ролями teacher и admin
    """
    conn = get_db_connection()
    c = conn.cursor()
    users = c.execute('''
        SELECT id, telegram_id, role 
        FROM users 
        WHERE role IN ('teacher', 'admin') AND telegram_id IS NOT NULL
    ''').fetchall()
    conn.close()
    return [user['telegram_id'] for user in users] 

def delete_topic(topic_id):
    """Удаляет тему из базы данных"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        # Удаляем тему
        c.execute('DELETE FROM topics WHERE id = ?', (topic_id,))
        # Удаляем историю модерации темы
        c.execute('DELETE FROM topic_moderation_history WHERE topic_id = ?', (topic_id,))
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Ошибка при удалении темы: {e}")
        return False
    finally:
        conn.close()

def get_maintenance_mode():
    """Получает статус режима технических работ форума"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute('SELECT value FROM settings WHERE key = "maintenance_mode"')
        result = c.fetchone()
        return bool(result and result['value'] == 'true')
    except sqlite3.Error:
        return False
    finally:
        conn.close()

def set_maintenance_mode(enabled):
    """Устанавливает режим технических работ форума"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        # Проверяем существование записи
        c.execute('SELECT 1 FROM settings WHERE key = "maintenance_mode"')
        if c.fetchone():
            c.execute('UPDATE settings SET value = ? WHERE key = "maintenance_mode"', 
                     ('true' if enabled else 'false',))
        else:
            c.execute('INSERT INTO settings (key, value) VALUES (?, ?)',
                     ('maintenance_mode', 'true' if enabled else 'false'))
        conn.commit()
        return True
    except sqlite3.Error:
        return False
    finally:
        conn.close()

def ensure_settings_table():
    """Создает таблицу настроек, если она не существует"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

# Вызываем при импорте модуля
ensure_settings_table() 