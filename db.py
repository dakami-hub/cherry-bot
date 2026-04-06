import sqlite3
import os
from datetime import date

DB_PATH = "/app/data/bot.db"

def init_db():
    os.makedirs("/app/data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS debts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT,
            creditor_id TEXT,
            creditor_name TEXT,
            debtor_id TEXT,
            debtor_name TEXT,
            amount REAL,
            description TEXT,
            repaid INTEGER DEFAULT 0,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS chat_members (
            chat_id TEXT,
            user_id TEXT,
            username TEXT,
            full_name TEXT,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (chat_id, user_id)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS daily_honors (
            chat_id TEXT,
            role TEXT,
            user_id TEXT,
            user_name TEXT,
            chosen_date TEXT,
            PRIMARY KEY (chat_id, role, chosen_date)
        )
    ''')
    conn.commit()
    conn.close()

# ---------- Долги (без изменений) ----------
def add_debt(chat_id: str, creditor_id: str, creditor_name: str,
             debtor_id: str, debtor_name: str, amount: float, description: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO debts (chat_id, creditor_id, creditor_name, debtor_id, debtor_name, amount, description)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (chat_id, creditor_id, creditor_name, debtor_id, debtor_name, amount, description))
    conn.commit()
    conn.close()

def repay_debt(chat_id: str, creditor_id: str, debtor_id: str, amount: float) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT id, amount FROM debts
        WHERE chat_id = ? AND creditor_id = ? AND debtor_id = ? AND repaid = 0
        ORDER BY date ASC
    ''', (chat_id, creditor_id, debtor_id))
    rows = c.fetchall()
    remaining = amount
    updated = False
    for row_id, debt_amount in rows:
        if remaining <= 0:
            break
        if debt_amount <= remaining:
            c.execute('UPDATE debts SET repaid = 1 WHERE id = ?', (row_id,))
            remaining -= debt_amount
            updated = True
        else:
            new_amount = debt_amount - remaining
            c.execute('UPDATE debts SET amount = ? WHERE id = ?', (new_amount, row_id))
            remaining = 0
            updated = True
    conn.commit()
    conn.close()
    return updated

def get_debts_for_user(chat_id: str, user_id: str) -> str:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT creditor_name, amount, description FROM debts
        WHERE chat_id = ? AND debtor_id = ? AND repaid = 0
    ''', (chat_id, user_id))
    i_owe = c.fetchall()
    c.execute('''
        SELECT debtor_name, amount, description FROM debts
        WHERE chat_id = ? AND creditor_id = ? AND repaid = 0
    ''', (chat_id, user_id))
    owe_me = c.fetchall()
    conn.close()
    if not i_owe and not owe_me:
        return "Нет активных долгов."
    lines = []
    if owe_me:
        lines.append("📌 Вам должны:")
        total = 0
        for name, amt, desc in owe_me:
            lines.append(f"• {name}: {amt:.2f} руб. ({desc})")
            total += amt
        lines.append(f"   Итого: {total:.2f} руб.")
    if i_owe:
        lines.append("📌 Вы должны:")
        total = 0
        for name, amt, desc in i_owe:
            lines.append(f"• {name}: {amt:.2f} руб. ({desc})")
            total += amt
        lines.append(f"   Итого: {total:.2f} руб.")
    return "\n".join(lines)

# ---------- Участники чатов ----------
def save_chat_member(chat_id: str, user_id: str, username: str, full_name: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO chat_members (chat_id, user_id, username, full_name, last_seen)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
    ''', (chat_id, user_id, username, full_name))
    conn.commit()
    conn.close()

def get_chat_members(chat_id: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT user_id, username, full_name FROM chat_members
        WHERE chat_id = ?
    ''', (chat_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_all_chats_with_members():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT DISTINCT chat_id FROM chat_members")
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]

# ---------- Ежедневные почести ----------
def set_daily_honor(chat_id: str, role: str, user_id: str, user_name: str):
    today = date.today().isoformat()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO daily_honors (chat_id, role, user_id, user_name, chosen_date)
        VALUES (?, ?, ?, ?, ?)
    ''', (chat_id, role, user_id, user_name, today))
    conn.commit()
    conn.close()

def get_daily_honors(chat_id: str):
    today = date.today().isoformat()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT role, user_id, user_name FROM daily_honors WHERE chat_id = ? AND chosen_date = ?", (chat_id, today))
    rows = c.fetchall()
    conn.close()
    result = {}
    for role, user_id, user_name in rows:
        result[role] = (user_id, user_name)
    return result

def is_honors_chosen_today(chat_id: str) -> bool:
    today = date.today().isoformat()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT 1 FROM daily_honors WHERE chat_id = ? AND chosen_date = ? LIMIT 1", (chat_id, today))
    row = c.fetchone()
    conn.close()
    return row is not None