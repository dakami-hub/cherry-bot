import sqlite3
from db import DB_PATH

def add_debt(chat_id: str, creditor_name: str, debtor_name: str, amount: float, description: str) -> None:
    """
    Добавляет долг: debtor_name должен creditor_name сумму amount за description.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO debts (chat_id, creditor_name, debtor_name, amount, description)
        VALUES (?, ?, ?, ?, ?)
    ''', (chat_id, creditor_name, debtor_name, amount, description))
    conn.commit()
    conn.close()

def repay_debt(chat_id: str, creditor_name: str, debtor_name: str, amount: float) -> bool:
    """
    Погашает часть долга. Ищет долги, где кредитор = creditor_name, должник = debtor_name,
    и списывает amount с самых старых долгов. Возвращает True, если удалось что-то списать.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT id, amount FROM debts
        WHERE chat_id = ? AND creditor_name = ? AND debtor_name = ? AND repaid = 0
        ORDER BY date ASC
    ''', (chat_id, creditor_name, debtor_name))
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

def get_debts_for_user(chat_id: str, user_name: str) -> str:
    """
    Возвращает список долгов пользователя по его имени.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Долги, где я должник (я должен кому-то)
    c.execute('''
        SELECT creditor_name, amount, description FROM debts
        WHERE chat_id = ? AND debtor_name = ? AND repaid = 0
        ORDER BY date ASC
    ''', (chat_id, user_name))
    i_owe = c.fetchall()
    # Долги, где я кредитор (мне должны)
    c.execute('''
        SELECT debtor_name, amount, description FROM debts
        WHERE chat_id = ? AND creditor_name = ? AND repaid = 0
        ORDER BY date ASC
    ''', (chat_id, user_name))
    owe_me = c.fetchall()
    conn.close()

    if not i_owe and not owe_me:
        return "📭 Нет активных долгов."

    lines = []
    if i_owe:
        lines.append("📌 *Вы должны:*")
        total_i_owe = 0.0
        for creditor, amt, desc in i_owe:
            lines.append(f"• {creditor}: {amt:.2f} руб. ({desc})")
            total_i_owe += amt
        lines.append(f"   *Итого:* {total_i_owe:.2f} руб.")
    if owe_me:
        lines.append("📌 *Вам должны:*")
        total_owe_me = 0.0
        for debtor, amt, desc in owe_me:
            lines.append(f"• {debtor}: {amt:.2f} руб. ({desc})")
            total_owe_me += amt
        lines.append(f"   *Итого:* {total_owe_me:.2f} руб.")
    return "\n".join(lines)