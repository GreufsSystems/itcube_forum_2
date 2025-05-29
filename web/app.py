from flask import Flask, render_template, send_from_directory, request, jsonify, redirect, url_for, flash, session, make_response
import os
from dotenv import load_dotenv
import json
import glob
import sqlite3
from datetime import datetime, timedelta
import logging
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import sys
import socket
from werkzeug.utils import secure_filename
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_db_connection, add_user, get_user_by_username, get_user_by_id, update_last_login, get_all_users, delete_user as db_delete_user, update_user_role, generate_activation_key, get_all_activation_keys, use_activation_key, add_user_direction, get_telegram_binding_by_user_id, create_telegram_link_code, create_telegram_login_code, check_and_delete_telegram_login_code, get_telegram_login_code, log_login_attempt, get_telegram_login_token, delete_telegram_login_token, get_user_directions_by_user_id, get_teachers_and_admins, unbind_telegram_account, get_pending_messages, get_pending_files, moderate_message, moderate_file, get_message_moderation_history, get_file_moderation_history, get_pending_topics, moderate_topic, update_user_about, update_topic, get_approved_topics, get_topic_by_id, delete_topic, get_maintenance_mode, set_maintenance_mode
from bot.telegram_bind_bot import generate_binding_code, send_login_code
import asyncio
from aiogram import Bot
from deepseek_api import deepseek, DeepSeekAPIError

# Загружаем переменные окружения из .env файла
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Абсолютные пути к папкам и файлам
UPLOAD_FOLDER = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'uploads'))
DIRECTIONS_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'directions.json'))
DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'forum.db'))

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Добавляем фильтр для форматирования даты
@app.template_filter('datetimeformat')
def datetimeformat(value, format='%d.%m.%Y %H:%M'):
    from datetime import datetime, timedelta
    if not value:
        return ''
    if isinstance(value, (int, float)):
        value = datetime.fromtimestamp(value)
    elif isinstance(value, str):
        # Пробуем разные форматы
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d'):
            try:
                value = datetime.strptime(value, fmt)
                break
            except Exception:
                continue
        else:
            return value  # если не удалось преобразовать, вернуть как есть
    # Прибавляем 3 часа для МСК
    value = value + timedelta(hours=3)
    return value.strftime(format)

# Добавляем контекстный процессор для текущего года
@app.context_processor
def inject_now():
    return {'now': datetime.now()}

# Контекстный процессор для user
@app.context_processor
def inject_user():
    user = None
    if 'user_id' in session:
        user = get_user_by_id(session['user_id'])
    from flask import request
    return dict(user=user, active_page=request.endpoint)

# Декоратор для проверки авторизации
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Пожалуйста, войдите в систему', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Декоратор для проверки прав администратора
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            flash('У вас нет доступа к этой странице', 'error')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

# Декоратор для проверки прав модератора
def moderator_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') not in ['admin', 'moderator']:
            flash('У вас нет доступа к этой странице', 'error')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

@app.template_filter('nl2br')
def nl2br(value):
    if not value:
        return ''
    return value.replace('\n', '<br>')

@app.context_processor
def inject_maintenance_mode():
    from database import get_maintenance_mode
    return {'maintenance_mode': get_maintenance_mode()}

def init_db():
    """Инициализация базы данных"""
    conn = get_db_connection()
    c = conn.cursor()
    
    # Создаем таблицу для пользователей
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            role TEXT DEFAULT 'user',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Создаем таблицу для логов бота
    c.execute('''
        CREATE TABLE IF NOT EXISTS bot_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            action TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Создаем таблицу для логов форума
    c.execute('''
        CREATE TABLE IF NOT EXISTS forum_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_address TEXT,
            user_id INTEGER,
            username TEXT,
            action TEXT,
            direction TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Создаем таблицу settings
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Проверяем наличие записи о режиме технических работ
    c.execute('SELECT 1 FROM settings WHERE key = "maintenance_mode"')
    if not c.fetchone():
        c.execute('INSERT INTO settings (key, value) VALUES (?, ?)', ('maintenance_mode', 'false'))
    
    # Создаем таблицу activation_keys
    c.execute('''
        CREATE TABLE IF NOT EXISTS activation_keys (
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
    
    # Создаем таблицу topics
    c.execute('''
        CREATE TABLE IF NOT EXISTS topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            number INTEGER,
            title TEXT,
            text TEXT,
            direction TEXT,
            user_id INTEGER,
            status TEXT DEFAULT 'pending'
        )
    ''')
    
    # Проверяем наличие колонки status в topics
    c.execute("PRAGMA table_info(topics)")
    columns = [row[1] for row in c.fetchall()]
    if 'status' not in columns:
        c.execute("ALTER TABLE topics ADD COLUMN status TEXT DEFAULT 'pending'")
    
    # Проверяем наличие колонки status в files
    c.execute("PRAGMA table_info(files)")
    columns = [row[1] for row in c.fetchall()]
    if 'status' not in columns:
        c.execute("ALTER TABLE files ADD COLUMN status TEXT DEFAULT 'pending'")
    
    # Создаем таблицу topic_moderation для истории модерации тем
    c.execute('''
        CREATE TABLE IF NOT EXISTS topic_moderation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_id INTEGER NOT NULL,
            moderator_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            comment TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Создаем админа по умолчанию, если его нет
    c.execute('SELECT * FROM users WHERE username = ?', ('admin',))
    if not c.fetchone():
        admin_password = generate_password_hash('admin123')
        add_user('admin', admin_password, 'admin@itcube.ru', 'admin')
    
    conn.commit()
    conn.close()

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('PRAGMA table_info(users);')
    conn.close()

def log_bot_action(user_id, username, action):
    """Логирование действий в боте"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            'INSERT INTO bot_logs (user_id, username, action) VALUES (?, ?, ?)',
            (user_id, username, action)
        )
        conn.commit()
        logger.info(f"Bot action logged: user_id={user_id}, username={username}, action={action}")
    except Exception as e:
        logger.error(f"Error logging bot action: {e}")
    finally:
        conn.close()

def log_forum_action(ip_address, user_id=None, username=None, action=None, direction=None):
    """Логирование действий на форуме"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            'INSERT INTO forum_logs (ip_address, user_id, username, action, direction) VALUES (?, ?, ?, ?, ?)',
            (ip_address, user_id, username, action, direction)
        )
        conn.commit()
        logger.info(f"Forum action logged: ip={ip_address}, user_id={user_id}, username={username}, action={action}, direction={direction}")
    except Exception as e:
        logger.error(f"Error logging forum action: {e}")
    finally:
        conn.close()

# Инициализируем базу данных при запуске
init_db()

def load_directions():
    if os.path.exists(DIRECTIONS_PATH):
        with open(DIRECTIONS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def load_topics(selected_direction=None):
    topics = []
    topic_dirs = glob.glob(os.path.join(UPLOAD_FOLDER, 'topic_*'))
    print(f"Found topic directories: {topic_dirs}")
    
    # Словарь для хранения тем по направлениям
    topics_by_direction = {}
    
    for topic_dir in topic_dirs:
        topic_json = os.path.join(topic_dir, 'topic.json')
        meta_path = os.path.join(topic_dir, 'topic.meta')
        
        # Проверяем наличие обоих файлов
        if not (os.path.exists(topic_json) and os.path.exists(meta_path)):
            print(f"Missing files for {topic_dir}")
            continue

        try:
            # Сначала читаем направление из meta файла
            with open(meta_path, 'r', encoding='utf-8') as f:
                direction = f.read().strip()
                print(f"Topic direction: {direction}, Selected direction: {selected_direction}")

            # Если выбрано направление и оно не совпадает, пропускаем эту тему
            if selected_direction and direction != selected_direction:
                print(f"Skipping topic due to direction mismatch")
                continue

            # Читаем данные темы
            with open(topic_json, 'r', encoding='utf-8') as f:
                topic_data = json.load(f)
                topic_id = os.path.basename(topic_dir).replace('topic_', '')
                
                # Получаем время создания файла
                creation_time = os.path.getctime(topic_json)
                
                # Добавляем тему в соответствующий список направлений
                if direction not in topics_by_direction:
                    topics_by_direction[direction] = []
                
                topics_by_direction[direction].append({
                    'id': topic_id,
                    'title': topic_data['title'],
                    'text': topic_data['text'],
                    'direction': direction,
                    'attachments': topic_data.get('attachments', []),
                    'creation_time': creation_time
                })
                print(f"Added topic: {topic_data['title']}")
        except Exception as e:
            print(f"Error loading topic from {topic_dir}: {e}")
            continue
    
    # Сортируем темы по времени создания внутри каждого направления и добавляем нумерацию
    for direction in topics_by_direction:
        # Сортируем по времени создания (от старых к новым)
        sorted_topics = sorted(topics_by_direction[direction], key=lambda x: x['creation_time'])
        for i, topic in enumerate(sorted_topics, 1):
            topic['number'] = i
        topics.extend(sorted_topics)
    
    # Оставляем только одобренные темы
    topics = [t for t in topics if t.get('status', 'approved') == 'approved']
    return topics

@app.route('/')
def home():
    log_forum_action(
        ip_address=request.remote_addr,
        action='visit_home'
    )
    user = None
    if 'user_id' in session:
        user = get_user_by_id(session['user_id'])
    teachers, admins = get_teachers_and_admins()
    # Подсчёт онлайн-пользователей (последние 5 минут)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''SELECT DISTINCT user_id FROM forum_logs WHERE timestamp > datetime('now', '-5 minutes') AND user_id IS NOT NULL AND ip_address != '127.0.0.1' ''')
    online_users = [row[0] for row in c.fetchall()]
    c.execute('''SELECT COUNT(*) FROM forum_logs WHERE ip_address != '127.0.0.1' ''')
    visits_count = c.fetchone()[0]
    conn.close()
    online_count = len(online_users)
    return render_template('home.html', user=user, teachers=teachers, admins=admins, online_count=online_count, visits_count=visits_count)

@app.route('/forum')
@login_required
def forum():
    from database import get_approved_topics
    user_id = session.get('user_id')
    conn = get_db_connection()
    c = conn.cursor()
    user_directions = [row['direction'] for row in c.execute('SELECT direction FROM user_directions WHERE user_id = ?', (user_id,)).fetchall()]
    conn.close()
    selected_direction = request.args.get('direction', None)
    if selected_direction and selected_direction not in user_directions and session.get('role') != 'admin':
        flash('У вас нет доступа к этому направлению', 'error')
        return redirect(url_for('forum'))
    log_forum_action(
        ip_address=request.remote_addr,
        action='visit_forum',
        direction=selected_direction
    )
    print(f"Selected direction: {selected_direction}")
    files = []
    directions = load_directions()
    print(f"Available directions: {directions}")
    if session.get('role') == 'admin':
        available_directions = list(directions.keys())
    else:
        available_directions = [d for d in directions.keys() if d in user_directions]
    # Темы только из базы, только approved
    topics = get_approved_topics(selected_direction)
    print(f"Loaded topics: {len(topics)}")
    print(f"Loaded files: {len(files)}")
    return render_template('index.html', 
                         files=files,
                         topics=topics,
                         selected_direction=selected_direction,
                         directions=available_directions)

@app.route('/api/topics/<topic_id>')
def get_topic(topic_id):
    log_forum_action(
        ip_address=request.remote_addr,
        action='view_topic',
        direction=None
    )
    print(f"Selected topic: {topic_id}")
    
    topic_dir = os.path.join(UPLOAD_FOLDER, f'topic_{topic_id}')
    topic_json = os.path.join(topic_dir, 'topic.json')
    meta_path = os.path.join(topic_dir, 'topic.meta')
    
    if not os.path.exists(topic_json) or not os.path.exists(meta_path):
        return jsonify({'error': 'Topic not found'}), 404
        
    try:
        # Читаем направление
        with open(meta_path, 'r', encoding='utf-8') as f:
            direction = f.read().strip()
            
        # Читаем данные темы
        with open(topic_json, 'r', encoding='utf-8') as f:
            topic_data = json.load(f)
            topic_data['direction'] = direction
            return jsonify(topic_data)
    except Exception as e:
        print(f"Error reading topic {topic_id}: {e}")
        return jsonify({'error': 'Failed to read topic'}), 500

@app.route('/files/<path:filename>')
def download_file(filename):
    log_forum_action(
        ip_address=request.remote_addr,
        action='download_file',
        direction=None
    )
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        activation_key = request.form.get('activation_key')

        # Проверка данных
        if not username or not password or not activation_key:
            flash('Все поля должны быть заполнены', 'error')
            return redirect(url_for('register'))

        if len(password) < 6:
            flash('Пароль должен содержать не менее 6 символов', 'error')
            return redirect(url_for('register'))

        # Проверка существования пользователя
        if get_user_by_username(username):
            flash('Пользователь с таким логином уже существует', 'error')
            return redirect(url_for('register'))

        # Проверка ключа активации
        conn = get_db_connection()
        c = conn.cursor()
        key_row = c.execute('''
            SELECT * FROM activation_keys 
            WHERE key = ? AND is_used = 0 
            AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
        ''', (activation_key,)).fetchone()
        
        if not key_row:
            conn.close()
            flash('Ключ не найден, уже использован или истек срок его действия', 'error')
            return redirect(url_for('register'))
            
        first_name = key_row['first_name']
        last_name = key_row['last_name']
        direction = key_row['direction']
        role = key_row['role']

        # Создание пользователя
        hashed_password = generate_password_hash(password)
        user_created = add_user(username, hashed_password, None, role, first_name, last_name)
        if user_created:
            # Получить id нового пользователя
            user = get_user_by_username(username)
            add_user_direction(user['id'], direction)
            # Пометить ключ использованным
            c.execute('UPDATE activation_keys SET is_used = 1, used_by_user_id = ?, used_at = CURRENT_TIMESTAMP WHERE key = ?', 
                     (user['id'], activation_key))
            conn.commit()
            conn.close()
            flash(f'Регистрация завершена! Добро пожаловать, {first_name} {last_name}', 'success')
            return redirect(url_for('login'))
        else:
            conn.close()
            flash('Ошибка при регистрации', 'error')
            return redirect(url_for('register'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        tg_code = request.form.get('tg_code')
        resend = request.form.get('resend')
        ip = request.remote_addr

        user = get_user_by_username(username) if username else None

        # 1. Проверка логина и пароля
        if user and password and check_password_hash(user['password'], password):
            tg_binding = get_telegram_binding_by_user_id(user['id'])
            if tg_binding:
                if resend or not tg_code:
                    code = create_telegram_login_code(user['id'])
                    asyncio.run(send_login_code(tg_binding['telegram_id'], code))
                    log_login_attempt(user['id'], username, ip, False, '2FA code sent')
                    flash('На ваш Telegram отправлен код для входа. Введите его ниже.', 'info')
                    return render_template('login.html', username=username, tg_code_required=True)
                valid, expired = check_and_delete_telegram_login_code(user['id'], tg_code)
                if expired:
                    log_login_attempt(user['id'], username, ip, False, '2FA code expired')
                    flash('Код из Telegram просрочен. Запросите новый код.', 'error')
                    return render_template('login.html', username=username, tg_code_required=True)
                if not valid:
                    log_login_attempt(user['id'], username, ip, False, '2FA code invalid')
                    flash('Неверный код из Telegram', 'error')
                    return render_template('login.html', username=username, tg_code_required=True)
                log_login_attempt(user['id'], username, ip, True, '2FA success')
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['role'] = user['role']
                update_last_login(user['id'])
                flash('Вы успешно вошли в систему', 'success')
                return redirect(url_for('home'))
            log_login_attempt(user['id'], username, ip, True, 'login success')
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            update_last_login(user['id'])
            flash('Вы успешно вошли в систему', 'success')
            return redirect(url_for('home'))
        else:
            log_login_attempt(user['id'] if user else None, username, ip, False, 'invalid password or user')
            flash('Неверное имя пользователя или пароль', 'error')
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы успешно вышли из системы', 'success')
    return redirect(url_for('home'))

@app.route('/admin', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_panel():
    tab = request.args.get('tab', 'users')
    users = get_all_users()
    directions = load_directions()
    keys = get_all_activation_keys()
    message = None
    if request.method == 'POST' and request.form.get('tab') == 'keys':
        direction = request.form.get('direction')
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        role = request.form.get('role')
        key_type = request.form.get('key_type')
        
        if direction and direction in directions and first_name and last_name and role and key_type:
            key = generate_activation_key(direction, first_name, last_name, role, key_type)
            message = f'Ключ для направления "{direction}" успешно сгенерирован: {key} (Имя: {first_name}, Фамилия: {last_name}, Роль: {role}, Тип: {key_type})'
            return redirect(url_for('admin_panel', tab='keys', message=message))
        else:
            message = 'Все поля должны быть заполнены корректно.'
        keys = get_all_activation_keys()  # обновить список после генерации
        tab = 'keys'
    else:
        message = request.args.get('message')
    return render_template('admin.html', users=users, directions=directions, keys=keys, message=message, tab=tab)

@app.route('/admin/user/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user_route(user_id):
    if user_id == session.get('user_id'):
        flash('Вы не можете удалить свой аккаунт', 'error')
        return redirect(url_for('admin_panel'))
    
    if db_delete_user(user_id):
        flash('Пользователь успешно удален', 'success')
    else:
        flash('Ошибка при удалении пользователя', 'error')
    return redirect(url_for('admin_panel'))

@app.route('/admin/user/<int:user_id>/toggle-role', methods=['POST'])
@login_required
@admin_required
def toggle_user_role(user_id):
    if user_id == session.get('user_id'):
        flash('Вы не можете изменить свою роль', 'error')
        return redirect(url_for('admin_panel'))
    user = get_user_by_id(user_id)
    if not user:
        flash('Пользователь не найден', 'error')
        return redirect(url_for('admin_panel'))
    current_role = user['role']
    roles = ['user', 'teacher', 'moderator', 'admin']
    try:
        idx = roles.index(current_role)
        new_role = roles[(idx + 1) % len(roles)]
    except ValueError:
        new_role = 'user'
    if update_user_role(user_id, new_role):
        flash(f'Роль пользователя успешно изменена на {new_role}', 'success')
    else:
        flash('Ошибка при изменении роли пользователя', 'error')
    return redirect(url_for('admin_panel'))

@app.route('/admin/activation-keys', methods=['GET', 'POST'])
@login_required
@admin_required
def activation_keys_panel():
    directions = load_directions()
    message = None
    if request.method == 'POST':
        direction = request.form.get('direction')
        if direction and direction in directions:
            key = generate_activation_key(direction)
            message = f'Ключ для направления "{direction}" успешно сгенерирован: {key}'
        else:
            message = 'Некорректное направление.'
    keys = get_all_activation_keys()
    return render_template('activation_keys.html', directions=directions, keys=keys, message=message)

@app.route('/admin/activation-key/<int:key_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_activation_key(key_id):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        # First check if the key exists
        c.execute('SELECT id FROM activation_keys WHERE id = ?', (key_id,))
        if not c.fetchone():
            flash('Ключ не найден', 'error')
            return redirect(url_for('admin_panel', tab='keys'))
        
        # Delete the key
        c.execute('DELETE FROM activation_keys WHERE id = ?', (key_id,))
        conn.commit()
        flash('Ключ успешно удалён', 'success')
    except Exception as e:
        flash('Ошибка при удалении ключа', 'error')
        print(f"Error deleting key: {e}")
    finally:
        conn.close()
    return redirect(url_for('admin_panel', tab='keys'))

@app.route('/profile/about', methods=['POST'])
@login_required
def edit_about():
    user_id = session['user_id']
    about = request.form.get('about', '').strip()
    from database import update_user_about
    update_user_about(user_id, about)
    flash('Информация о себе обновлена.', 'success')
    return redirect(url_for('profile'))

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        flash('Пожалуйста, войдите в систему', 'error')
        return redirect(url_for('login'))

    user_id = session['user_id']
    user = get_user_by_id(user_id)
    telegram_binding = get_telegram_binding_by_user_id(user_id)
    user_directions = get_user_directions_by_user_id(user_id)
    message = None
    # Получаем ключи пользователя
    conn = get_db_connection()
    c = conn.cursor()
    user_keys = c.execute('SELECT * FROM activation_keys WHERE used_by_user_id = ?', (user_id,)).fetchall()
    conn.close()
    if not user:
        flash('Пользователь не найден', 'error')
        return redirect(url_for('index'))

    edit_about = request.args.get('edit_about') == '1'

    # --- ДОБАВЛЕНО: обработка загрузки аватара ---
    if request.method == 'POST' and 'avatar' in request.files:
        file = request.files['avatar']
        if file and file.filename:
            ext = os.path.splitext(file.filename)[1]
            filename = f"user_{user_id}_avatar{ext}"
            avatar_folder = os.path.join(app.root_path, 'static', 'avatars')
            os.makedirs(avatar_folder, exist_ok=True)
            file_path = os.path.join(avatar_folder, filename)
            file.save(file_path)
            # Сохраняем только имя файла в базу
            conn = get_db_connection()
            c = conn.cursor()
            c.execute('UPDATE users SET avatar_url = ? WHERE id = ?', (filename, user_id))
            conn.commit()
            conn.close()
            flash('Аватар успешно обновлён!', 'success')
            return redirect(url_for('profile'))
    # --- КОНЕЦ ДОБАВЛЕНИЯ ---

    return render_template('profile.html', 
                         user=user, 
                         message=message, 
                         telegram_binding=telegram_binding, 
                         user_directions=user_directions, 
                         user_keys=user_keys,
                         is_viewing_own_profile=True,
                         edit_about=edit_about)

@app.route('/confirm_unbind_telegram', methods=['GET', 'POST'])
def confirm_unbind_telegram():
    if 'user_id' not in session:
        flash('Пожалуйста, войдите в систему', 'error')
        return redirect(url_for('login'))
    if request.method == 'POST':
        return redirect(url_for('unbind_telegram'))
    return render_template('confirm_unbind_telegram.html')

@app.route('/unbind_telegram', methods=['POST'])
def unbind_telegram():
    if 'user_id' not in session:
        flash('Пожалуйста, войдите в систему', 'error')
        return redirect(url_for('login'))

    user_id = session['user_id']
    if unbind_telegram_account(user_id):
        flash('Двухфакторная авторизация через Telegram отключена. Теперь вы можете входить только по паролю.', 'success')
    else:
        flash('Ошибка при отвязке аккаунта Telegram', 'error')
    
    return redirect(url_for('profile'))

@app.route('/bind_telegram', methods=['GET', 'POST'])
def bind_telegram():
    if 'user_id' not in session:
        flash('Пожалуйста, войдите в систему', 'error')
        return redirect(url_for('login'))

    user_id = session['user_id']
    user = get_user_by_id(user_id)
    
    if not user:
        flash('Пользователь не найден', 'error')
        return redirect(url_for('index'))

    # Проверяем, не привязан ли уже аккаунт
    existing_binding = get_telegram_binding_by_user_id(user_id)
    if existing_binding:
        flash('Ваш аккаунт уже привязан к Telegram', 'info')
        return redirect(url_for('profile'))

    if request.method == 'POST':
        # Генерируем код привязки через базу
        binding_code = create_telegram_link_code(user_id)
        return render_template('bind_telegram.html', 
                             user=user, 
                             binding_code=binding_code,
                             bot_username=os.getenv('TELEGRAM_BOT_USERNAME', '@itcubeauthorization_bot'))

    return render_template('bind_telegram.html', user=user)

@app.route('/login_telegram')
def login_telegram():
    token = request.args.get('token')
    if not token:
        flash('Токен не указан', 'error')
        return redirect(url_for('login'))
    row = get_telegram_login_token(token)
    if not row:
        flash('Токен недействителен или истёк', 'error')
        return redirect(url_for('login'))
    # Проверяем срок действия токена (5 минут)
    created_at = row['created_at']
    try:
        created_at_dt = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S.%f')
    except ValueError:
        created_at_dt = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
    if datetime.now() - created_at_dt > timedelta(minutes=5):
        delete_telegram_login_token(token)
        flash('Токен истёк. Запросите новый через Telegram-бота.', 'error')
        return redirect(url_for('login'))
    # Всё ок — логиним пользователя
    user = get_user_by_id(row['user_id'])
    if not user:
        flash('Пользователь не найден', 'error')
        return redirect(url_for('login'))
    delete_telegram_login_token(token)
    session['user_id'] = user['id']
    session['username'] = user['username']
    session['role'] = user['role']
    update_last_login(user['id'])
    flash('Вы успешно вошли через Telegram!', 'success')
    return redirect(url_for('home'))

@app.route('/teacher_panel', methods=['GET', 'POST'])
@login_required
def teacher_panel():
    user_id = session.get('user_id')
    user = get_user_by_id(user_id)
    if user['role'] != 'teacher':
        flash('Доступ только для преподавателей', 'error')
        return redirect(url_for('home'))
    directions = get_user_directions_by_user_id(user_id)
    direction = directions[0] if directions else None
    message = None
    # Генерация ключа
    if request.method == 'POST':
        if 'first_name' in request.form and 'last_name' in request.form:
            first_name = request.form.get('first_name')
            last_name = request.form.get('last_name')
            if first_name and last_name and direction:
                key = generate_activation_key(direction, first_name, last_name)
                message = f'Ключ для направления "{direction}" успешно сгенерирован: {key} (Имя: {first_name}, Фамилия: {last_name})'
            else:
                message = 'Все поля должны быть заполнены.'
        elif 'topic_title' in request.form and 'topic_text' in request.form:
            title = request.form.get('topic_title')
            text = request.form.get('topic_text')
            
            if not (title and text and direction):
                message = 'Заполните все поля для создания темы.'
                return render_template('teacher_panel.html', user=user, direction=direction, keys=keys, message=message, topics=topics, files=files)
            
            conn = get_db_connection()
            c = conn.cursor()
            try:
                c.execute('INSERT INTO topics (number, title, text, direction, user_id, status) VALUES (?, ?, ?, ?, ?, ?)',
                          (0, title, text, direction, user_id, 'pending'))
                conn.commit()
                message = 'Тема успешно создана.'
            except Exception as e:
                message = f'Ошибка при создании темы: {e}'
            finally:
                conn.close()
        elif 'file' in request.files:
            # Загрузка файла
            file = request.files['file']
            if file and direction:
                filename = file.filename
                save_path = os.path.join(UPLOAD_FOLDER, filename)
                file.save(save_path)
                # Создаём .meta-файл с направлением
                meta_path = save_path + '.meta'
                with open(meta_path, 'w', encoding='utf-8') as f:
                    f.write(direction)
                conn = get_db_connection()
                c = conn.cursor()
                # ВСЕГДА статус 'pending' при добавлении файла
                c.execute('INSERT INTO files (name, path, direction, user_id, status) VALUES (?, ?, ?, ?, ?)',
                          (filename, save_path, direction, user_id, 'pending'))
                conn.commit()
                conn.close()
                message = 'Файл успешно загружен и отправлен на модерацию.'
            else:
                message = 'Выберите файл для загрузки.'
    # Ключи
    keys = [k for k in get_all_activation_keys() if k['direction'] == direction and (('role' in k and k['role'] == 'user') or ('role' not in k or k['role'] is None))]
    # Темы
    conn = get_db_connection()
    c = conn.cursor()
    topics = c.execute('SELECT * FROM topics WHERE direction = ? AND user_id = ? AND status = "approved"', (direction, user_id)).fetchall()
    files = c.execute('SELECT * FROM files WHERE direction = ? AND user_id = ? AND status = "approved"', (direction, user_id)).fetchall()
    conn.close()
    return render_template('teacher_panel.html', user=user, direction=direction, keys=keys, message=message, topics=topics, files=files)

@app.route('/api/online_count')
def api_online_count():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''SELECT DISTINCT user_id FROM forum_logs WHERE timestamp > datetime('now', '-5 minutes') AND user_id IS NOT NULL AND ip_address != '127.0.0.1' ''')
    online_users = [row[0] for row in c.fetchall()]
    conn.close()
    return jsonify({'online_count': len(online_users)})

@app.route('/topic/<int:topic_id>')
def view_topic(topic_id):
    from database import get_topic_by_id
    topic = get_topic_by_id(topic_id)
    if not topic or topic['status'] != 'approved':
        flash('Тема не найдена или не одобрена', 'error')
        return redirect(url_for('forum'))
    return render_template('topic.html', topic=topic)

@app.route('/moderation')
@login_required
@moderator_required
def moderation_panel():
    """Панель модерации"""
    pending_messages = get_pending_messages()
    pending_files = get_pending_files()
    return render_template('moderation.html', 
                         pending_messages=pending_messages,
                         pending_files=pending_files)

@app.route('/moderation/message/<int:message_id>', methods=['POST'])
@login_required
@moderator_required
def moderate_message_route(message_id):
    """Модерация сообщения"""
    status = request.form.get('status')
    comment = request.form.get('comment')
    
    if status not in ['approved', 'rejected']:
        flash('Неверный статус модерации', 'error')
        return redirect(url_for('moderation_panel'))
    
    if moderate_message(message_id, session['user_id'], status, comment):
        flash('Сообщение успешно промодерировано', 'success')
    else:
        flash('Ошибка при модерации сообщения', 'error')
    
    return redirect(url_for('moderation_panel'))

@app.route('/moderation/file/<int:file_id>', methods=['POST'])
@login_required
@moderator_required
def moderate_file_route(file_id):
    """Модерация файла"""
    status = request.form.get('status')
    comment = request.form.get('comment')
    
    if status not in ['approved', 'rejected']:
        flash('Неверный статус модерации', 'error')
        return redirect(url_for('moderation_panel'))
    
    if moderate_file(file_id, session['user_id'], status, comment):
        flash('Файл успешно промодерирован', 'success')
    else:
        flash('Ошибка при модерации файла', 'error')
    
    return redirect(url_for('moderation_panel'))

@app.route('/moderation/message/<int:message_id>/history')
@login_required
@moderator_required
def message_moderation_history(message_id):
    """История модерации сообщения"""
    history = get_message_moderation_history(message_id)
    return render_template('moderation_history.html', 
                         history=history,
                         item_type='message')

@app.route('/moderation/file/<int:file_id>/history')
@login_required
@moderator_required
def file_moderation_history(file_id):
    """История модерации файла"""
    history = get_file_moderation_history(file_id)
    return render_template('moderation_history.html', 
                         history=history,
                         item_type='file')

@app.route('/moderation/topics')
@login_required
def moderation_topics():
    """Страница со списком тем на модерацию"""
    user = get_user_by_id(session['user_id'])
    if user['role'] not in ['moderator', 'admin']:
        flash('У вас нет доступа к панели модерации', 'danger')
        return redirect(url_for('index'))
    
    # Получаем направление модератора
    user_directions = get_user_directions_by_user_id(user['id'])
    direction = user_directions[0] if user_directions else None
    
    # Получаем все темы на модерацию
    topics = get_pending_topics()
    # Фильтруем по направлению, если не админ
    if user['role'] != 'admin' and direction:
        topics = [t for t in topics if t['direction'] == direction]
    
    return render_template('moderation_topics.html', topics=topics)

@app.route('/moderation/topic/<int:topic_id>', methods=['GET', 'POST'])
@login_required
def moderate_topic_route(topic_id):
    """Страница модерации конкретной темы"""
    user = get_user_by_id(session['user_id'])
    if user['role'] not in ['moderator', 'admin']:
        flash('У вас нет доступа к панели модерации', 'danger')
        return redirect(url_for('index'))
    
    # Получаем тему
    topic = get_topic_by_id(topic_id)
    if not topic:
        flash('Тема не найдена', 'danger')
        return redirect(url_for('moderation_topics'))
        
    # Проверяем направление модератора
    user_directions = get_user_directions_by_user_id(user['id'])
    if topic['direction'] not in user_directions and user['role'] != 'admin':
        flash('У вас нет прав на модерацию тем этого направления', 'danger')
        return redirect(url_for('moderation_topics'))
    
    # Получаем историю модерации
    history = get_topic_moderation_history(topic_id)
    
    if request.method == 'POST':
        status = request.form.get('status')
        comment = request.form.get('comment', '').strip()
        
        if not status:
            flash('Выберите статус модерации', 'danger')
            return render_template('moderate_topic.html', topic=topic, history=history)
            
        if status == 'rejected' and not comment:
            flash('При отклонении темы необходимо указать причину', 'danger')
            return render_template('moderate_topic.html', topic=topic, history=history)
        
        # Обновляем тему, если были изменения
        new_title = request.form.get('title', '').strip()
        new_text = request.form.get('text', '').strip()
        
        if new_title != topic['title'] or new_text != topic['text']:
            if not update_topic(topic_id, new_title, new_text):
                flash('Ошибка при обновлении темы', 'danger')
                return render_template('moderate_topic.html', topic=topic, history=history)
        
        # Модерируем тему
        if moderate_topic(topic_id, user['id'], status, comment):
            flash('Решение по теме принято', 'success')
            return redirect(url_for('moderation_topics'))
        else:
            flash('Ошибка при сохранении решения', 'danger')
    
    return render_template('moderate_topic.html', topic=topic, history=history)

@app.route('/moderation/topic/<int:topic_id>/history')
@login_required
def topic_moderation_history(topic_id):
    """Страница с историей модерации темы"""
    user = get_user_by_id(session['user_id'])
    if user['role'] not in ['moderator', 'admin']:
        flash('У вас нет доступа к панели модерации', 'danger')
        return redirect(url_for('index'))
    
    # Получаем тему
    topic = get_topic_by_id(topic_id)
    if not topic:
        flash('Тема не найдена', 'danger')
        return redirect(url_for('moderation_topics'))
        
    # Получаем историю модерации
    history = get_topic_moderation_history(topic_id)
    
    return render_template('topic_moderation_history.html', topic=topic, history=history)

@app.route('/user/<int:user_id>')
def view_user_profile(user_id):
    user = get_user_by_id(user_id)
    if not user:
        flash('Пользователь не найден', 'error')
        return redirect(url_for('home'))
    
    telegram_binding = get_telegram_binding_by_user_id(user_id)
    user_directions = get_user_directions_by_user_id(user_id)
    
    return render_template('profile.html', 
                         user=user, 
                         telegram_binding=telegram_binding, 
                         user_directions=user_directions,
                         is_viewing_own_profile=False)

@app.route('/debug/about/<username>')
@login_required
def debug_about(username):
    if session.get('role') != 'admin':
        return 'Access denied', 403
    from database import get_user_by_username
    user = get_user_by_username(username)
    if not user:
        return f'User {username} not found', 404
    return f"about for {username}:<br><pre>{user['about']}</pre>"

@app.route('/debug/userid/<username>')
@login_required
def debug_userid(username):
    if session.get('role') != 'admin':
        return 'Access denied', 403
    from database import get_user_by_username
    user = get_user_by_username(username)
    if not user:
        return f'User {username} not found', 404
    return f"user_id for {username}: {user['id']}<br>about: <pre>{user['about']}</pre>"

@app.route('/debug/users_table_info')
@login_required
def debug_users_table_info():
    if session.get('role') != 'admin':
        return 'Access denied', 403
    import sqlite3
    from database import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('PRAGMA table_info(users)')
    columns = c.fetchall()
    conn.close()
    return '<br>'.join([str(col) for col in columns])

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_pending_topics():
    """Получает список тем, ожидающих модерации из базы данных"""
    conn = get_db_connection()
    c = conn.cursor()
    topics = c.execute('''
        SELECT t.*, u.username, u.first_name, u.last_name
        FROM topics t
        LEFT JOIN users u ON t.user_id = u.id
        WHERE t.status = 'pending'
        ORDER BY t.id DESC
    ''').fetchall()
    conn.close()
    return topics

def get_pending_files():
    files = []
    for name in os.listdir(UPLOAD_FOLDER):
        if name.startswith('file_'):
            file_dir = os.path.join(UPLOAD_FOLDER, name)
            json_path = os.path.join(file_dir, 'file.json')
            if os.path.exists(json_path):
                with open(json_path, encoding='utf-8') as f:
                    data = json.load(f)
                if data.get('status') == 'pending':
                    data['dir'] = file_dir
                    files.append(data)
    return files

@app.route('/moderation')
def moderation():
    topics = get_pending_topics()
    files = get_pending_files()
    return render_template('moderation.html', topics=topics, files=files)

@app.route('/moderate/topic', methods=['GET', 'POST'])
def moderate_topic_file():
    topic_dir = request.args.get('dir')
    action = request.args.get('action')
    comment = request.form.get('comment') if request.method == 'POST' else request.args.get('comment')
    json_path = os.path.join(topic_dir, 'topic.json')
    if os.path.exists(json_path):
        with open(json_path, encoding='utf-8') as f:
            data = json.load(f)
        if action == 'approve':
            data['status'] = 'approved'
            data['moderation_comment'] = ''
        elif action == 'reject':
            data['status'] = 'rejected'
            data['moderation_comment'] = comment or ''
            # Уведомление в Telegram
            user_id = data.get('user_id')
            if user_id:
                binding = get_telegram_binding_by_user_id(user_id)
                if binding and binding.get('telegram_id') and tg_bot:
                    asyncio.run(tg_bot.send_message(
                        binding['telegram_id'],
                        f'Ваша тема "{data.get("title")}" была отклонена модератором.\nПричина: {comment or "Не указано"}'
                    ))
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        flash('Статус темы обновлён')
    return redirect(url_for('moderation'))

@app.route('/moderate/file', methods=['GET', 'POST'])
def moderate_file():
    file_dir = request.args.get('dir')
    action = request.args.get('action')
    comment = request.form.get('comment') if request.method == 'POST' else request.args.get('comment')
    json_path = os.path.join(file_dir, 'file.json')
    if os.path.exists(json_path):
        with open(json_path, encoding='utf-8') as f:
            data = json.load(f)
        if action == 'approve':
            data['status'] = 'approved'
            data['moderation_comment'] = ''
        elif action == 'reject':
            data['status'] = 'rejected'
            data['moderation_comment'] = comment or ''
            # Уведомление в Telegram
            user_id = data.get('user_id')
            if user_id:
                binding = get_telegram_binding_by_user_id(user_id)
                if binding and binding.get('telegram_id') and tg_bot:
                    asyncio.run(tg_bot.send_message(
                        binding['telegram_id'],
                        f'Ваш файл "{data.get("file_name")}" был отклонён модератором.\nПричина: {comment or "Не указано"}'
                    ))
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        flash('Статус файла обновлён')
    return redirect(url_for('moderation'))

def get_topic_by_id(topic_id):
    """Возвращает тему по её id из базы данных (или из файлов, если используется файловое хранилище)"""
    conn = get_db_connection()
    c = conn.cursor()
    topic = c.execute('SELECT * FROM topics WHERE id = ?', (topic_id,)).fetchone()
    conn.close()
    if topic:
        return dict(topic)
    return None

def get_topic_moderation_history(topic_id):
    """Возвращает историю модерации темы по её id"""
    conn = get_db_connection()
    c = conn.cursor()
    history = c.execute('''
        SELECT m.*, u.username as moderator_name
        FROM topic_moderation m
        LEFT JOIN users u ON m.moderator_id = u.id
        WHERE m.topic_id = ?
        ORDER BY m.created_at ASC
    ''', (topic_id,)).fetchall()
    conn.close()
    return [dict(row) for row in history]

@app.route('/topic/<int:topic_id>/delete', methods=['POST'])
@login_required
def delete_topic_route(topic_id):
    """Удаление темы"""
    user = get_user_by_id(session['user_id'])
    topic = get_topic_by_id(topic_id)
    
    if not topic:
        flash('Тема не найдена', 'error')
        return redirect(url_for('forum'))
    
    # Проверяем права на удаление
    if user['role'] not in ['admin', 'moderator'] and topic['user_id'] != user['id']:
        flash('У вас нет прав на удаление этой темы', 'error')
        return redirect(url_for('forum'))
    
    if delete_topic(topic_id):
        flash('Тема успешно удалена', 'success')
    else:
        flash('Ошибка при удалении темы', 'error')
    
    return redirect(url_for('forum'))

@app.route('/admin/maintenance', methods=['GET', 'POST'])
@login_required
def maintenance_mode():
    if session.get('role') != 'admin':
        flash('У вас нет прав для доступа к этой странице', 'danger')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        enabled = request.form.get('maintenance_mode') == 'on'
        if set_maintenance_mode(enabled):
            flash('Режим технических работ успешно обновлен', 'success')
        else:
            flash('Ошибка при обновлении режима технических работ', 'danger')
        return redirect(url_for('maintenance_mode'))
    
    maintenance_mode = get_maintenance_mode()
    return render_template('admin/maintenance.html', maintenance_mode=maintenance_mode)

def check_browser_compatibility():
    """Проверка совместимости браузера"""
    try:
        # Проверяем наличие токена безопасности
        security_token = request.cookies.get('security_token')
        if not security_token:
            return False
            
        # Проверяем наличие флага в localStorage
        browser_check_complete = request.cookies.get('browser_check_complete')
        if not browser_check_complete:
            return False
            
        # Проверяем наличие активной сессии
        session_active = request.cookies.get('session_active')
        if not session_active:
            return False
            
        return True
    except Exception as e:
        logger.error(f"Error checking browser compatibility: {e}")
        return False

@app.before_request
def before_request():
    # Пропускаем статические файлы и страницу проверки браузера
    if request.endpoint and (
        request.endpoint.startswith('static') or 
        request.endpoint == 'browser_check' or
        request.endpoint == 'handle_browser_info'
    ):
        return
        
    # Разрешаем доступ админам
    if 'user_id' in session and session.get('role') == 'admin':
        return
        
    # Разрешаем доступ только с localhost (127.0.0.1)
    if request.remote_addr == '127.0.0.1':
        return
        
    # Проверяем режим технических работ
    if get_maintenance_mode():
        allowed_endpoints = ['maintenance_mode', 'logout', 'login']
        if not request.endpoint or request.endpoint not in allowed_endpoints:
            return render_template('maintenance_mode.html'), 503
            
    # Проверяем совместимость браузера
    if not check_browser_compatibility():
        return redirect(url_for('browser_check'))

@app.route('/api/browser-info', methods=['POST'])
def handle_browser_info():
    try:
        browser_info = request.json
        # Сохраняем информацию о браузере в сессии
        session['browser_info'] = browser_info
        logger.info(f"Browser info received: {browser_info}")
        return jsonify({'status': 'success'}), 200
    except Exception as e:
        logger.error(f"Error processing browser info: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

def get_all_ip_addresses():
    """Получает все возможные IP-адреса сервера"""
    ip_list = []
    try:
        # Получаем имя хоста
        hostname = socket.gethostname()
        # Получаем все IP-адреса
        ip_list = socket.gethostbyname_ex(hostname)[2]
        # Добавляем localhost и 127.0.0.1
        ip_list.extend(['127.0.0.1', 'localhost'])
        # Удаляем дубликаты
        ip_list = list(dict.fromkeys(ip_list))
    except Exception as e:
        logger.error(f"Ошибка при получении IP-адресов: {e}")
        ip_list = ['127.0.0.1', 'localhost']
    return ip_list

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500

@app.route('/browser-check')
def browser_check():
    return render_template('browser_check.html')

@app.route('/admin/browser-check-preview')
@login_required
@admin_required
def browser_check_preview():
    """Предпросмотр страницы проверки браузера для администраторов"""
    return render_template('browser_check.html', is_preview=True)

# --- Смена пароля ---
@app.route('/change_password', methods=['POST'])
@login_required
def change_password():
    user_id = session['user_id']
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    user = get_user_by_id(user_id)
    if not user or not check_password_hash(user['password'], current_password):
        flash('Текущий пароль неверный', 'error')
        return redirect(url_for('profile'))
    if new_password != confirm_password:
        flash('Новые пароли не совпадают', 'error')
        return redirect(url_for('profile'))
    if len(new_password) < 6:
        flash('Пароль должен содержать не менее 6 символов', 'error')
        return redirect(url_for('profile'))
    from database import update_user_password
    update_user_password(user_id, generate_password_hash(new_password))
    flash('Пароль успешно изменён', 'success')
    return redirect(url_for('profile'))

# --- AJAX-привязка Telegram ---
@app.route('/bind_telegram', methods=['POST'])
@login_required
def bind_telegram_ajax():
    user_id = session['user_id']
    user = get_user_by_id(user_id)
    if not user:
        return jsonify({'error': 'Пользователь не найден'}), 404
    existing_binding = get_telegram_binding_by_user_id(user_id)
    if existing_binding:
        return jsonify({'tg_success': True})
    binding_code = create_telegram_link_code(user_id)
    return jsonify({'binding_code': binding_code})

# --- Активация ключа через профиль ---
@app.route('/profile', methods=['POST'])
@login_required
def profile_post():
    if request.form.get('action') == 'activate_key':
        key = request.form.get('key')
        user_id = session['user_id']
        conn = get_db_connection()
        c = conn.cursor()
        key_row = c.execute('''
            SELECT * FROM activation_keys 
            WHERE key = ? AND is_used = 0 
            AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
        ''', (key,)).fetchone()
        if not key_row:
            conn.close()
            flash('Ключ не найден, уже использован или истек срок его действия', 'error')
            return redirect(url_for('profile'))
        direction = key_row['direction']
        c.execute('UPDATE activation_keys SET is_used = 1, used_by_user_id = ?, used_at = CURRENT_TIMESTAMP WHERE key = ?', (user_id, key))
        add_user_direction(user_id, direction)
        conn.commit()
        conn.close()
        flash(f'Ключ успешно активирован! Вам добавлено направление: {direction}', 'success')
        return redirect(url_for('profile'))
    # Если не активация ключа — обработка аватара (оставляем существующую логику)
    # --- ДОБАВЛЕНО: обработка загрузки аватара ---
    if request.method == 'POST' and 'avatar' in request.files:
        file = request.files['avatar']
        if file and file.filename:
            ext = os.path.splitext(file.filename)[1]
            filename = f"user_{user_id}_avatar{ext}"
            avatar_folder = os.path.join(app.root_path, 'static', 'avatars')
            os.makedirs(avatar_folder, exist_ok=True)
            file_path = os.path.join(avatar_folder, filename)
            file.save(file_path)
            # Сохраняем только имя файла в базу
            conn = get_db_connection()
            c = conn.cursor()
            c.execute('UPDATE users SET avatar_url = ? WHERE id = ?', (filename, user_id))
            conn.commit()
            conn.close()
            flash('Аватар успешно обновлён!', 'success')
            return redirect(url_for('profile'))
    # --- КОНЕЦ ДОБАВЛЕНИЯ ---
    # Остальной код профиля (копируем из GET-обработчика)
    user_id = session['user_id']
    user = get_user_by_id(user_id)
    telegram_binding = get_telegram_binding_by_user_id(user_id)
    user_directions = get_user_directions_by_user_id(user_id)
    message = None
    conn = get_db_connection()
    c = conn.cursor()
    user_keys = c.execute('SELECT * FROM activation_keys WHERE used_by_user_id = ?', (user_id,)).fetchall()
    conn.close()
    if not user:
        flash('Пользователь не найден', 'error')
        return redirect(url_for('index'))
    edit_about = request.args.get('edit_about') == '1'
    return render_template('profile.html', 
                         user=user, 
                         message=message, 
                         telegram_binding=telegram_binding, 
                         user_directions=user_directions, 
                         user_keys=user_keys,
                         is_viewing_own_profile=True,
                         edit_about=edit_about)

@app.route('/chat')
@login_required
def chat():
    return render_template('chat.html')

@app.route('/api/chat', methods=['POST'])
@login_required
def chat_api():
    data = request.get_json()
    message = data.get('message')
    
    if not message:
        return jsonify({'error': 'Сообщение не может быть пустым'}), 400
    
    # Получаем историю сообщений из сессии или создаем новую
    messages = session.get('chat_history', [])
    
    # Добавляем системное сообщение, если это первое сообщение
    if not messages:
        messages.append({
            "role": "system",
            "content": "Вы - полезный ассистент на русском языке. Отвечайте кратко и по существу."
        })
    
    # Добавляем сообщение пользователя
    messages.append({
        "role": "user",
        "content": message
    })
    
    try:
        # Получаем ответ от DeepSeek
        response = deepseek.get_chat_response(messages)
        
        # Добавляем ответ ассистента в историю
        messages.append({
            "role": "assistant",
            "content": response
        })
        
        # Сохраняем обновленную историю в сессии
        session['chat_history'] = messages
        
        return jsonify({'response': response})
        
    except DeepSeekAPIError as e:
        logger.error(f"DeepSeek API error: {str(e)}")
        return jsonify({'error': 'Произошла ошибка при обработке запроса. Пожалуйста, попробуйте позже.'}), 500
    except Exception as e:
        logger.error(f"Unexpected error in chat API: {str(e)}")
        return jsonify({'error': 'Произошла непредвиденная ошибка. Пожалуйста, попробуйте позже.'}), 500

@app.route('/api/chat/clear', methods=['POST'])
@login_required
def clear_chat_history():
    session.pop('chat_history', None)
    return jsonify({'status': 'success'})

if __name__ == '__main__':
    # Выводим все доступные IP-адреса
    ip_addresses = get_all_ip_addresses()
    print("\nСайт доступен по следующим адресам:")
    for ip in ip_addresses:
        print(f"  http://{ip}:80")
    print()  # Пустая строка для читаемости
    
    app.run(debug=True, host='0.0.0.0', port=80)
