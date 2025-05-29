import sqlite3
from datetime import datetime

DB_PATH = '../forum.db'

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

def add_column_if_not_exists(table, column, coltype):
    c.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in c.fetchall()]
    if column not in columns:
        c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
        print(f"Добавлен столбец {column} в {table}")
    else:
        print(f"Столбец {column} уже существует в {table}")

add_column_if_not_exists('topics', 'author_name', 'TEXT')
add_column_if_not_exists('files', 'filename', 'TEXT')
add_column_if_not_exists('files', 'author_name', 'TEXT')

# Добавляем тестовую тему
c.execute("INSERT INTO topics (number, title, text, direction, user_id, created_at, status, author_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
          (1, 'Тестовая тема', 'Текст тестовой темы', 'Программирование', 1, datetime.now(), 'pending', 'Иванов Иван'))
print('Добавлена тестовая тема.')

# Получаем список столбцов для files
c.execute("PRAGMA table_info(files)")
file_columns = [row[1] for row in c.fetchall()]
file_data = {
    'name': 'test.txt',
    'path': '/uploads/test.txt',
    'direction': 'Программирование',
    'user_id': 1,
    'created_at': datetime.now(),
    'status': 'pending',
    'filename': 'test.txt',
    'author_name': 'Иванов Иван'
}
insert_cols = [col for col in file_columns if col in file_data]
insert_vals = [file_data[col] for col in insert_cols]
qmarks = ','.join(['?'] * len(insert_cols))
c.execute(f"INSERT INTO files ({','.join(insert_cols)}) VALUES ({qmarks})", insert_vals)
print('Добавлен тестовый файл.')

conn.commit()
conn.close()
print('Миграция и тестовые данные добавлены.') 