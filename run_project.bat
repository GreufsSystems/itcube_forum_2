@echo off
set TELEGRAM_BIND_BOT_TOKEN=8024104647:AAEnuw-i2mYHTPCCVRKt3DXJKggznMjQUmI
set TELEGRAM_BOT_USERNAME=@itcubeauthorization_bot

echo Starting Telegram Bot Project...

:: Activate virtual environment
echo Activating virtual environment...
call .\venv\Scripts\activate

:: Install requirements
echo Installing requirements...
pip install -r requirements.txt

:: Установка критичных зависимостей вручную (на всякий случай)
pip install bleach
pip install Flask-JWT-Extended

:: Запуск веб-сервера
start "Web Server" cmd /k "cd web && python app.py"

:: Запуск бота привязки
start "Telegram Bind Bot" cmd /k "cd bot && python telegram_bind_bot.py"

:: Запуск основного бота
start "Main Bot" cmd /k "cd bot && python bot.py"

echo Проект запущен!
echo Веб-сервер доступен по адресу: http://localhost:5000
echo Telegram бот: @itcubeauthorization_bot

echo Project components started successfully!
echo Bot and Web Server are running in separate PowerShell windows.
echo Press any key to close this window...
pause > nul 