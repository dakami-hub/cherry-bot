# ---------- Wordle tables ----------
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