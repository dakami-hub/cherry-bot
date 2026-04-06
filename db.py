import sqlite3
import os
from datetime import date

DB_PATH = "/app/data/bot.db"

def init_db():
    os.makedirs("/app/data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # ... (остальные таблицы: debts, chat_members) ...
    c.execute('''
        CREATE TABLE IF NOT EXISTS daily_victim (
            chat_id TEXT,
            victim_id TEXT,
            victim_name TEXT,
            chosen_date TEXT,
            PRIMARY KEY (chat_id, chosen_date)
        )
    ''')
    conn.commit()
    conn.close()

# ... (функции для debts и chat_members остаются без изменений) ...

# ---------- Daily victim ----------
def get_daily_victim(chat_id: str, target_date: str = None):
    if target_date is None:
        target_date = date.today().isoformat()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT victim_id, victim_name FROM daily_victim WHERE chat_id = ? AND chosen_date = ?", (chat_id, target_date))
    row = c.fetchone()
    conn.close()
    return row

def set_daily_victim(chat_id: str, victim_id: str, victim_name: str):
    today = date.today().isoformat()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO daily_victim (chat_id, victim_id, victim_name, chosen_date) VALUES (?, ?, ?, ?)",
              (chat_id, victim_id, victim_name, today))
    conn.commit()
    conn.close()

def is_victim_chosen_today(chat_id: str) -> bool:
    return get_daily_victim(chat_id) is not None

def get_all_chats_with_members():
    """Возвращает список chat_id, в которых есть участники (из таблицы chat_members)."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT DISTINCT chat_id FROM chat_members")
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]