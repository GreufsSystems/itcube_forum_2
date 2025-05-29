import os
import sys
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.error import TimedOut, NetworkError, TelegramError

# Добавляем путь к корневой директории проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database as db
import secrets
from database import get_telegram_link_code, delete_telegram_link_code, get_user_by_telegram_id, create_telegram_login_token
from config import TELEGRAM_BIND_BOT_TOKEN

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='telegram_bind_bot.log'
)
logger = logging.getLogger(__name__)

# Константы для оформления
EMOJI = {
    'welcome': '👋',
    'success': '✅',
    'error': '❌',
    'warning': '⚠️',
    'info': 'ℹ️',
    'link': '🔗',
    'key': '🔑',
    'user': '👤',
    'settings': '⚙️',
    'help': '❓',
    'logout': '🚪'
}

# Словарь для хранения временных кодов привязки
binding_codes = {}

def generate_binding_code(user_id):
    """Генерирует код для привязки аккаунта"""
    code = secrets.token_hex(3)  # 6-значный код
    binding_codes[code] = user_id
    return code

async def send_login_code(telegram_id, code):
    """Отправляет код для входа в Telegram"""
    bot = Bot(token=TELEGRAM_BIND_BOT_TOKEN)
    try:
        await bot.send_message(chat_id=telegram_id, text=f"Ваш код для входа на форум: <code>{code}</code>", parse_mode="HTML")
        return True
    except Exception as e:
        print(f"Ошибка при отправке кода входа: {e}")
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    existing_user = db.get_user_by_telegram_id(user.id)
    
    if existing_user:
        keyboard = [
            [InlineKeyboardButton(f"{EMOJI['link']} Войти на форум", callback_data='login')],
            [InlineKeyboardButton(f"{EMOJI['settings']} Отвязать аккаунт", callback_data='unbind')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"{EMOJI['welcome']} Привет, {user.first_name}!\n\n"
            f"{EMOJI['user']} Ваш аккаунт уже привязан к форуму.\n"
            f"{EMOJI['info']} Логин на форуме: {existing_user['username']}\n\n"
            "Выберите действие:",
            reply_markup=reply_markup
        )
    else:
        keyboard = [
            [InlineKeyboardButton(f"{EMOJI['help']} Как привязать аккаунт?", callback_data='help_bind')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"{EMOJI['welcome']} Привет, {user.first_name}!\n\n"
            f"{EMOJI['info']} Я помогу вам привязать ваш аккаунт Telegram к форуму.\n\n"
            f"{EMOJI['key']} Для привязки аккаунта выполните следующие шаги:\n"
            "1. Войдите в свой аккаунт на форуме\n"
            "2. Перейдите в настройки профиля\n"
            "3. Нажмите кнопку 'Привязать Telegram'\n"
            "4. Введите полученный код в этом чате командой /bind <код>\n\n"
            "Нужна помощь? Нажмите кнопку ниже:",
            reply_markup=reply_markup
        )

async def bind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /bind"""
    user = update.effective_user
    logger.info(f"Получена команда /bind от пользователя {user.id} (@{user.username})")
    
    if not context.args:
        keyboard = [
            [InlineKeyboardButton(f"{EMOJI['help']} Как получить код?", callback_data='help_code')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"{EMOJI['warning']} Пожалуйста, укажите код привязки.\n"
            f"{EMOJI['info']} Пример: /bind 123456\n\n"
            "Не знаете, где взять код? Нажмите кнопку ниже:",
            reply_markup=reply_markup
        )
        return

    code = context.args[0]
    logger.info(f"Попытка привязки с кодом: {code}")
    
    try:
        # Проверяем, не привязан ли уже аккаунт
        existing_user = db.get_user_by_telegram_id(user.id)
        if existing_user:
            keyboard = [
                [InlineKeyboardButton(f"{EMOJI['link']} Войти на форум", callback_data='login')],
                [InlineKeyboardButton(f"{EMOJI['settings']} Отвязать аккаунт", callback_data='unbind')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"{EMOJI['info']} Ваш аккаунт Telegram уже привязан к форуму.\n\n"
                f"{EMOJI['user']} Логин на форуме: {existing_user['username']}\n\n"
                "Выберите действие:",
                reply_markup=reply_markup
            )
            return

        # Проверяем код привязки через базу
        code_row = db.get_telegram_link_code(code)
        if not code_row:
            await update.message.reply_text(
                f"{EMOJI['error']} Неверный код привязки.\n\n"
                f"{EMOJI['warning']} Пожалуйста, проверьте код и попробуйте снова."
            )
            return

        user_id = code_row['user_id']
        logger.info(f"Код привязки найден для пользователя {user_id}")
        
        forum_user = db.get_user_by_id(user_id)
        if not forum_user:
            await update.message.reply_text(
                f"{EMOJI['error']} Ошибка: пользователь форума не найден."
            )
            return

        # Привязываем аккаунт
        logger.info(f"Попытка привязки Telegram {user.id} к пользователю форума {user_id}")
        if db.bind_telegram_account(user_id, user.id, user.username):
            db.delete_telegram_link_code(code)  # Удаляем использованный код
            logger.info(f"Успешная привязка аккаунта для пользователя {user_id}")
            
            keyboard = [
                [InlineKeyboardButton(f"{EMOJI['link']} Войти на форум", callback_data='login')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"{EMOJI['success']} Отлично! Ваш аккаунт Telegram успешно привязан к форуму.\n\n"
                f"{EMOJI['user']} Логин на форуме: {forum_user['username']}\n\n"
                "Теперь вы можете войти на форум:",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                f"{EMOJI['error']} Произошла ошибка при привязке аккаунта.\n\n"
                f"{EMOJI['warning']} Возможно, этот Telegram аккаунт уже привязан к другому пользователю."
            )
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при привязке аккаунта: {e}", exc_info=True)
        await update.message.reply_text(
            f"{EMOJI['error']} Произошла непредвиденная ошибка при привязке аккаунта.\n\n"
            f"{EMOJI['info']} Пожалуйста, попробуйте позже или обратитесь к администратору."
        )

async def unbind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /unbind"""
    user = update.effective_user
    binding = db.get_telegram_binding_by_user_id(user.id)
    
    if not binding:
        keyboard = [
            [InlineKeyboardButton(f"{EMOJI['help']} Как привязать аккаунт?", callback_data='help_bind')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"{EMOJI['warning']} Ваш аккаунт Telegram не привязан к форуму.\n\n"
            "Хотите привязать аккаунт? Нажмите кнопку ниже:",
            reply_markup=reply_markup
        )
        return

    keyboard = [
        [InlineKeyboardButton(f"{EMOJI['success']} Да, отвязать", callback_data='confirm_unbind')],
        [InlineKeyboardButton(f"{EMOJI['error']} Нет, отмена", callback_data='cancel_unbind')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"{EMOJI['warning']} Вы уверены, что хотите отвязать свой аккаунт Telegram от форума?\n\n"
        f"{EMOJI['info']} После отвязки вам придется заново привязывать аккаунт для входа через Telegram.",
        reply_markup=reply_markup
    )

async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /login"""
    user = update.effective_user
    forum_user = get_user_by_telegram_id(user.id)
    
    if not forum_user:
        keyboard = [
            [InlineKeyboardButton(f"{EMOJI['help']} Как привязать аккаунт?", callback_data='help_bind')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"{EMOJI['warning']} Ваш Telegram не привязан к аккаунту форума.\n\n"
            "Хотите привязать аккаунт? Нажмите кнопку ниже:",
            reply_markup=reply_markup
        )
        return
        
    token = create_telegram_login_token(forum_user['id'])
    site_url = os.getenv('SITE_URL', 'http://localhost:5000')
    login_link = f"{site_url}/login_telegram?token={token}"
    
    keyboard = [
        [InlineKeyboardButton(f"{EMOJI['link']} Войти на форум", url=login_link)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"{EMOJI['info']} Для входа на форум перейдите по ссылке ниже:\n\n"
        f"{EMOJI['warning']} Ссылка действительна 5 минут.\n\n"
        "Нажмите кнопку для входа:",
        reply_markup=reply_markup
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'login':
        await login_command(update, context)
    elif query.data == 'unbind':
        await unbind(update, context)
    elif query.data == 'help_bind':
        await query.message.reply_text(
            f"{EMOJI['info']} Как привязать аккаунт Telegram к форуму:\n\n"
            "1. Войдите в свой аккаунт на форуме\n"
            "2. Перейдите в настройки профиля\n"
            "3. Нажмите кнопку 'Привязать Telegram'\n"
            "4. Введите полученный код в этом чате командой /bind <код>"
        )
    elif query.data == 'help_code':
        await query.message.reply_text(
            f"{EMOJI['info']} Как получить код привязки:\n\n"
            "1. Войдите в свой аккаунт на форуме\n"
            "2. Перейдите в настройки профиля\n"
            "3. Нажмите кнопку 'Привязать Telegram'\n"
            "4. Скопируйте код, который появится на странице"
        )
    elif query.data == 'confirm_unbind':
        user = update.effective_user
        if db.unbind_telegram_account(user.id):
            keyboard = [
                [InlineKeyboardButton(f"{EMOJI['help']} Как привязать аккаунт?", callback_data='help_bind')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.message.edit_text(
                f"{EMOJI['success']} Ваш аккаунт Telegram успешно отвязан от форума.\n\n"
                "Хотите привязать аккаунт снова? Нажмите кнопку ниже:",
                reply_markup=reply_markup
            )
        else:
            await query.message.edit_text(
                f"{EMOJI['error']} Произошла ошибка при отвязке аккаунта.\n\n"
                f"{EMOJI['info']} Пожалуйста, попробуйте позже."
            )
    elif query.data == 'cancel_unbind':
        keyboard = [
            [InlineKeyboardButton(f"{EMOJI['link']} Войти на форум", callback_data='login')],
            [InlineKeyboardButton(f"{EMOJI['settings']} Отвязать аккаунт", callback_data='unbind')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.message.edit_text(
            f"{EMOJI['info']} Отвязка аккаунта отменена.\n\n"
            "Выберите действие:",
            reply_markup=reply_markup
        )

async def send_moderation_notification(telegram_id, topic_title, status, comment=None):
    """Отправляет уведомление о модерации темы в Telegram"""
    bot = Bot(token=TELEGRAM_BIND_BOT_TOKEN)
    max_retries = 3
    retry_delay = 5  # секунд
    
    for attempt in range(max_retries):
        try:
            if status == 'approved':
                message = f'{EMOJI["success"]} Ваша тема "{topic_title}" была одобрена модератором.'
            else:
                message = f'{EMOJI["error"]} Ваша тема "{topic_title}" была отклонена модератором.'
                if comment:
                    message += f'\n\n{EMOJI["info"]} Причина: {comment}'
            
            await bot.send_message(telegram_id, message)
            break
        except (TimedOut, NetworkError) as e:
            if attempt == max_retries - 1:
                logger.error(f"Не удалось отправить уведомление после {max_retries} попыток: {e}")
            else:
                logger.warning(f"Попытка {attempt + 1} не удалась, повтор через {retry_delay} сек: {e}")
                await asyncio.sleep(retry_delay)
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления: {e}")
            break
        finally:
            await bot.session.close()

def main():
    """Запуск бота"""
    if not TELEGRAM_BIND_BOT_TOKEN:
        logger.error("Не указан токен бота в config.py")
        return

    # Создаем приложение с настройками повторных попыток
    application = (
        Application.builder()
        .token(TELEGRAM_BIND_BOT_TOKEN)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .write_timeout(30.0)
        .pool_timeout(30.0)
        .build()
    )

    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("bind", bind))
    application.add_handler(CommandHandler("unbind", unbind))
    application.add_handler(CommandHandler("login", login_command))
    
    # Добавляем обработчик кнопок
    application.add_handler(CallbackQueryHandler(button_callback))

    # Добавляем обработчик ошибок
    application.add_error_handler(error_handler)

    # Запускаем бота с повторными попытками
    while True:
        try:
            application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
                close_loop=False
            )
        except (TimedOut, NetworkError) as e:
            logger.error(f"Ошибка подключения: {e}. Перезапуск через 5 секунд...")
            asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Непредвиденная ошибка: {e}")
            break

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик ошибок"""
    logger.error(f"Ошибка при обработке обновления {update}: {context.error}")
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                f"{EMOJI['error']} Произошла ошибка при обработке запроса.\n\n"
                f"{EMOJI['info']} Пожалуйста, попробуйте позже."
            )
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения об ошибке: {e}")

if __name__ == '__main__':
    main() 