import sqlite3
import os

DB_PATH = "/app/data/debts.db"

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
    """Погашает часть долга (списывает с самых старых)"""
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