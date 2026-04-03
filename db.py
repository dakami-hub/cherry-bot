import sqlite3
import os

DB_PATH = "/app/data/bot.db"

def init_db():
    os.makedirs("/app/data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Таблица долгов
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
    # Таблица участников чатов
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
    conn.commit()
    conn.close()

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
