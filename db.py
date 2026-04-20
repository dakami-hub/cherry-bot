import sqlite3
import os

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
            original_amount REAL,
            description TEXT,
            repaid INTEGER DEFAULT 0,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS repayments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            debt_id INTEGER,
            amount REAL,
            description TEXT,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(debt_id) REFERENCES debts(id)
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
    conn.commit()
    conn.close()
    # Миграция: добавляем колонку original_amount, если её нет
    migrate_db()

def migrate_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("PRAGMA table_info(debts)")
    columns = [col[1] for col in c.fetchall()]
    if "original_amount" not in columns:
        c.execute("ALTER TABLE debts ADD COLUMN original_amount REAL DEFAULT 0")
    c.execute("UPDATE debts SET original_amount = amount WHERE original_amount IS NULL")
    conn.commit()
    conn.close()

# ---------- Долги ----------
def add_debt(chat_id: str, creditor_id: str, creditor_name: str,
             debtor_id: str, debtor_name: str, amount: float, description: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO debts (chat_id, creditor_id, creditor_name, debtor_id, debtor_name, amount, original_amount, description)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (chat_id, creditor_id, creditor_name, debtor_id, debtor_name, amount, amount, description))
    conn.commit()
    conn.close()

def repay_debt(chat_id: str, creditor_id: str, debtor_id: str, amount: float, description: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT id, amount FROM debts
        WHERE chat_id = ? AND creditor_id = ? AND debtor_id = ? AND repaid = 0
        ORDER BY date ASC
        LIMIT 1
    ''', (chat_id, creditor_id, debtor_id))
    row = c.fetchone()
    if not row:
        conn.close()
        return False
    debt_id, current_amount = row
    c.execute('''
        INSERT INTO repayments (debt_id, amount, description)
        VALUES (?, ?, ?)
    ''', (debt_id, amount, description))
    if amount >= current_amount:
        c.execute('UPDATE debts SET repaid = 1, amount = 0 WHERE id = ?', (debt_id,))
    else:
        new_amount = current_amount - amount
        c.execute('UPDATE debts SET amount = ? WHERE id = ?', (new_amount, debt_id))
    conn.commit()
    conn.close()
    return True

def get_debts_for_user(chat_id: str, user_id: str, mode: str = "self") -> dict:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if mode == "self":
        c.execute('''
            SELECT creditor_name, amount, description FROM debts
            WHERE chat_id = ? AND debtor_id = ? AND repaid = 0
            ORDER BY date ASC
        ''', (chat_id, user_id))
        i_owe = c.fetchall()
        c.execute('''
            SELECT debtor_name, amount, description FROM debts
            WHERE chat_id = ? AND creditor_id = ? AND repaid = 0
            ORDER BY date ASC
        ''', (chat_id, user_id))
        owe_me = c.fetchall()
        conn.close()
        return {"i_owe": i_owe, "owe_me": owe_me}
    else:
        c.execute('''
            SELECT creditor_name, amount, description FROM debts
            WHERE chat_id = ? AND debtor_id = ? AND repaid = 0
            ORDER BY date ASC
        ''', (chat_id, user_id))
        debts = c.fetchall()
        conn.close()
        return {"debts": debts}

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