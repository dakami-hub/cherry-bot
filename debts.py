import sqlite3
from db import DB_PATH

def add_debt(chat_id: str, creditor_id: str, creditor_name: str,
             debtor_id: str, debtor_name: str, amount: float, description: str) -> None:
    """Добавляет новый долг."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO debts (chat_id, creditor_id, creditor_name, debtor_id, debtor_name, amount, description)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (chat_id, creditor_id, creditor_name, debtor_id, debtor_name, amount, description))
    conn.commit()
    conn.close()

def repay_debt(chat_id: str, creditor_id: str, debtor_id: str, amount: float) -> bool:
    """
    Погашает сумму amount с долгов кредитору. Списывает с самых старых долгов,
    уменьшая или помечая их как погашенные. Возвращает True, если сумма списана.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Получаем все непогашенные долги для этой пары (кредитор-должник), сортируем по дате (старые первыми)
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
            # Погашаем весь долг
            c.execute('UPDATE debts SET repaid = 1 WHERE id = ?', (row_id,))
            remaining -= debt_amount
            updated = True
        else:
            # Частичное погашение: уменьшаем сумму долга
            new_amount = debt_amount - remaining
            c.execute('UPDATE debts SET amount = ? WHERE id = ?', (new_amount, row_id))
            remaining = 0
            updated = True
    conn.commit()
    conn.close()
    return updated

def get_debts_for_user(chat_id: str, user_id: str) -> str:
    """
    Возвращает форматированный список долгов пользователя.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Долги, где я должник (debtor_id)
    c.execute('''
        SELECT creditor_name, amount, description FROM debts
        WHERE chat_id = ? AND debtor_id = ? AND repaid = 0
        ORDER BY date ASC
    ''', (chat_id, user_id))
    i_owe = c.fetchall()
    # Долги, где я кредитор (creditor_id)
    c.execute('''
        SELECT debtor_name, amount, description FROM debts
        WHERE chat_id = ? AND creditor_id = ? AND repaid = 0
        ORDER BY date ASC
    ''', (chat_id, user_id))
    owe_me = c.fetchall()
    conn.close()

    if not i_owe and not owe_me:
        return "📭 Нет активных долгов."

    lines = []
    # Долги, которые мне должны
    if owe_me:
        lines.append("📌 *Вам должны:*")
        total_owe_me = 0
        for debtor, amt, desc in owe_me:
            lines.append(f"• {debtor}: {amt:.2f} руб. ({desc})")
            total_owe_me += amt
        lines.append(f"   *Итого:* {total_owe_me:.2f} руб.")
    # Долги, которые я должен
    if i_owe:
        lines.append("📌 *Вы должны:*")
        total_i_owe = 0
        for creditor, amt, desc in i_owe:
            lines.append(f"• {creditor}: {amt:.2f} руб. ({desc})")
            total_i_owe += amt
        lines.append(f"   *Итого:* {total_i_owe:.2f} руб.")
    return "\n".join(lines)