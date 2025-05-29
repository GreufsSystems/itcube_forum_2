import sqlite3
import pandas as pd
from datetime import datetime
import os

def get_db_path():
    """Получение пути к базе данных"""
    return os.path.abspath(os.path.join('data', 'logs.db'))

def view_bot_logs(limit=10, user_id=None, action=None):
    """Просмотр логов бота"""
    conn = sqlite3.connect(get_db_path())
    
    query = "SELECT * FROM bot_logs WHERE 1=1"
    params = []
    
    if user_id:
        query += " AND user_id = ?"
        params.append(user_id)
    if action:
        query += " AND action LIKE ?"
        params.append(f"%{action}%")
        
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    
    if df.empty:
        print("Логи не найдены")
        return
    
    # Форматируем timestamp для лучшей читаемости
    df['timestamp'] = pd.to_datetime(df['timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')
    
    print("\n=== Логи бота ===")
    print(df.to_string(index=False))
    print(f"\nВсего записей: {len(df)}")

def view_forum_logs(limit=10, ip=None, user_id=None, action=None, direction=None):
    """Просмотр логов форума"""
    conn = sqlite3.connect(get_db_path())
    
    query = "SELECT * FROM forum_logs WHERE 1=1"
    params = []
    
    if ip:
        query += " AND ip_address LIKE ?"
        params.append(f"%{ip}%")
    if user_id:
        query += " AND user_id = ?"
        params.append(user_id)
    if action:
        query += " AND action LIKE ?"
        params.append(f"%{action}%")
    if direction:
        query += " AND direction LIKE ?"
        params.append(f"%{direction}%")
        
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    
    if df.empty:
        print("Логи не найдены")
        return
    
    # Форматируем timestamp для лучшей читаемости
    df['timestamp'] = pd.to_datetime(df['timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')
    
    print("\n=== Логи форума ===")
    print(df.to_string(index=False))
    print(f"\nВсего записей: {len(df)}")

def get_statistics():
    """Получение статистики по логам"""
    conn = sqlite3.connect(get_db_path())
    
    # Статистика по действиям бота
    bot_stats = pd.read_sql_query("""
        SELECT action, COUNT(*) as count 
        FROM bot_logs 
        GROUP BY action 
        ORDER BY count DESC
    """, conn)
    
    # Статистика по действиям форума
    forum_stats = pd.read_sql_query("""
        SELECT action, COUNT(*) as count 
        FROM forum_logs 
        GROUP BY action 
        ORDER BY count DESC
    """, conn)
    
    # Статистика по направлениям
    direction_stats = pd.read_sql_query("""
        SELECT direction, COUNT(*) as count 
        FROM forum_logs 
        WHERE direction IS NOT NULL 
        GROUP BY direction 
        ORDER BY count DESC
    """, conn)
    
    conn.close()
    
    print("\n=== Статистика по действиям бота ===")
    print(bot_stats.to_string(index=False))
    
    print("\n=== Статистика по действиям форума ===")
    print(forum_stats.to_string(index=False))
    
    print("\n=== Статистика по направлениям ===")
    print(direction_stats.to_string(index=False))

def main():
    while True:
        print("\n=== Меню просмотра логов ===")
        print("1. Просмотр логов бота")
        print("2. Просмотр логов форума")
        print("3. Статистика")
        print("4. Выход")
        
        choice = input("\nВыберите действие (1-4): ")
        
        if choice == "1":
            print("\nПараметры фильтрации (оставьте пустым для пропуска):")
            user_id = input("ID пользователя: ")
            action = input("Действие: ")
            limit = input("Количество записей (по умолчанию 10): ")
            
            view_bot_logs(
                limit=int(limit) if limit else 10,
                user_id=int(user_id) if user_id else None,
                action=action if action else None
            )
            
        elif choice == "2":
            print("\nПараметры фильтрации (оставьте пустым для пропуска):")
            ip = input("IP-адрес: ")
            user_id = input("ID пользователя: ")
            action = input("Действие: ")
            direction = input("Направление: ")
            limit = input("Количество записей (по умолчанию 10): ")
            
            view_forum_logs(
                limit=int(limit) if limit else 10,
                ip=ip if ip else None,
                user_id=int(user_id) if user_id else None,
                action=action if action else None,
                direction=direction if direction else None
            )
            
        elif choice == "3":
            get_statistics()
            
        elif choice == "4":
            print("До свидания!")
            break
            
        else:
            print("Неверный выбор. Пожалуйста, выберите 1-4.")
        
        input("\nНажмите Enter для продолжения...")

if __name__ == "__main__":
    main() 