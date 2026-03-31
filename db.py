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
            description TEXT,
            repaid INTEGER DEFAULT 0,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            chat_id TEXT,
            role TEXT,
            content TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            chat_id TEXT,
            key TEXT,
            value TEXT,
            PRIMARY KEY (chat_id, key)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS admin_users (
            user_id TEXT PRIMARY KEY,
            username TEXT,
            role TEXT
        )
    ''')
    conn.commit()
    conn.close()

def get_setting(chat_id: str, key: str, default: str = None) -> str:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE chat_id = ? AND key = ?", (chat_id, key))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(chat_id: str, key: str, value: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("REPLACE INTO settings (chat_id, key, value) VALUES (?, ?, ?)", (chat_id, key, value))
    conn.commit()
    conn.close()

def add_admin(user_id: str, username: str, role: str = "admin"):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("REPLACE INTO admin_users (user_id, username, role) VALUES (?, ?, ?)", (user_id, username, role))
    conn.commit()
    conn.close()

def remove_admin(user_id: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM admin_users WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def is_admin(user_id: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT 1 FROM admin_users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row is not None

def is_superadmin(user_id: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT role FROM admin_users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row and row[0] == "superadmin"

def get_all_admins():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id, username, role FROM admin_users")
    rows = c.fetchall()
    conn.close()
    return rows