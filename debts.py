import sqlite3
from db import DB_PATH

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
        SELECT id FROM debts
        WHERE chat_id = ? AND creditor_id = ? AND debtor_id = ? AND amount = ? AND repaid = 0
        ORDER BY date ASC LIMIT 1
    ''', (chat_id, creditor_id, debtor_id, amount))
    row = c.fetchone()
    if row:
        c.execute('UPDATE debts SET repaid = 1 WHERE id = ?', (row[0],))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

def get_debts_for_user(chat_id: str, user_id: str) -> str:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT creditor_name, SUM(amount) FROM debts
        WHERE chat_id = ? AND debtor_id = ? AND repaid = 0
        GROUP BY creditor_id
    ''', (chat_id, user_id))
    i_owe = c.fetchall()
    c.execute('''
        SELECT debtor_name, SUM(amount) FROM debts
        WHERE chat_id = ? AND creditor_id = ? AND repaid = 0
        GROUP BY debtor_id
    ''', (chat_id, user_id))
    owe_me = c.fetchall()
    conn.close()

    if not i_owe and not owe_me:
        return "📭 Нет активных долгов."

    lines = []
    if owe_me:
        lines.append("📌 *Вам должны:*")
        for name, total in owe_me:
            lines.append(f"• {name}: {total:.2f} руб.")
    if i_owe:
        lines.append("📌 *Вы должны:*")
        for name, total in i_owe:
            lines.append(f"• {name}: {total:.2f} руб.")
    return "\n".join(lines)