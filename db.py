import sqlite3
import os
import logging

DB_PATH = "/app/data/bot.db"

def init_db():
    os.makedirs("/app/data", exist_ok=True)
    logging.info(f"Initializing database at {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS debts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT,
            creditor_name TEXT,
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
    c.execute('''
        CREATE TABLE IF NOT EXISTS known_users (
            user_id TEXT PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
    logging.info("Database initialized")

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

def save_user(user_id: str, username: str = None, full_name: str = None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO known_users (user_id, username, full_name, last_seen)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    ''', (user_id, username, full_name))
    conn.commit()
    conn.close()

def get_user_by_username(username: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id, full_name FROM known_users WHERE username = ?", (username,))
    row = c.fetchone()
    conn.close()
    return row

# ---------- Wordle functions ----------
def init_wordle_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS wordle_stats (
            user_id TEXT PRIMARY KEY,
            username TEXT,
            games_played INTEGER DEFAULT 0,
            games_won INTEGER DEFAULT 0,
            total_guesses INTEGER DEFAULT 0,
            current_streak INTEGER DEFAULT 0,
            max_streak INTEGER DEFAULT 0,
            last_game_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS wordle_sessions (
            user_id TEXT PRIMARY KEY,
            word TEXT,
            guesses_left INTEGER,
            guessed_letters TEXT,  -- JSON строка с попытками
            current_state TEXT,
            game_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def update_wordle_stats(user_id: str, username: str, won: bool, guesses: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT * FROM wordle_stats WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    if row:
        games_played = row[2] + 1
        games_won = row[3] + (1 if won else 0)
        total_guesses = row[4] + (guesses if won else 0)
        current_streak = (row[5] + 1) if won else 0
        max_streak = max(row[6], current_streak)
        c.execute('''
            UPDATE wordle_stats SET
                games_played = ?, games_won = ?, total_guesses = ?,
                current_streak = ?, max_streak = ?, last_game_time = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (games_played, games_won, total_guesses, current_streak, max_streak, user_id))
    else:
        games_played = 1
        games_won = 1 if won else 0
        total_guesses = guesses if won else 0
        current_streak = 1 if won else 0
        max_streak = current_streak
        c.execute('''
            INSERT INTO wordle_stats (user_id, username, games_played, games_won, total_guesses, current_streak, max_streak)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, username, games_played, games_won, total_guesses, current_streak, max_streak))
    conn.commit()
    conn.close()

def get_wordle_stats(user_id: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT username, games_played, games_won, total_guesses, current_streak, max_streak FROM wordle_stats WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    return row

def get_wordle_top(limit: int = 10):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT username, games_won, games_played, current_streak
        FROM wordle_stats
        WHERE games_won > 0
        ORDER BY games_won DESC, games_played ASC
        LIMIT ?
    ''', (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def save_wordle_session(user_id: str, word: str, guesses_left: int, guessed_letters: str, current_state: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        REPLACE INTO wordle_sessions (user_id, word, guesses_left, guessed_letters, current_state)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, word, guesses_left, guessed_letters, current_state))
    conn.commit()
    conn.close()

def get_wordle_session(user_id: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT word, guesses_left, guessed_letters, current_state FROM wordle_sessions WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    return row

def delete_wordle_session(user_id: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM wordle_sessions WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()