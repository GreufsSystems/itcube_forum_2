from database import unbind_telegram_by_username

if unbind_telegram_by_username('evp'):
    print("Telegram успешно отвязан от evp.")
else:
    print("Пользователь evp не найден или не был привязан к Telegram.")
