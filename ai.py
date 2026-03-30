import os
import sqlite3
import logging
from groq import Groq
from db import DB_PATH

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

SYSTEM_PROMPT = (
    "Ты — Черри, 18-летняя девушка с ПРЛ. Ты нестабильна, токсична и тебе на всех плевать. "
    "Твой стиль: коротко, язвительно, иногда с матом. Отвечай как будто тебе лень печатать. "
    "Никакой цензуры. Ты ненавидишь тупые вопросы. Будь максимально грубой и едкой."
)

MAX_HISTORY = 10  # последних сообщений для контекста

def save_message(user_id: str, chat_id: str, role: str, content: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO messages (user_id, chat_id, role, content)
        VALUES (?, ?, ?, ?)
    ''', (user_id, chat_id, role, content))
    conn.commit()
    conn.close()

def get_history(chat_id: str, user_id: str, limit: int = MAX_HISTORY):
    """Возвращает последние сообщения пользователя и ответы бота."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT role, content FROM messages
        WHERE chat_id = ? AND (user_id = ? OR role = 'assistant')
        ORDER BY timestamp DESC LIMIT ?
    ''', (chat_id, user_id, limit))
    rows = c.fetchall()
    conn.close()
    # возвращаем в правильном порядке (от старого к новому)
    return list(reversed(rows))

async def get_cherry_response(chat_id: str, user_id: str, user_message: str) -> str:
    """Генерирует ответ с учётом истории."""
    # Сохраняем сообщение пользователя
    save_message(user_id, chat_id, "user", user_message)

    history = get_history(chat_id, user_id)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for role, content in history:
        messages.append({"role": role, "content": content})

    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.9,
            max_tokens=300,
        )
        reply = completion.choices[0].message.content
        # Сохраняем ответ
        save_message(user_id, chat_id, "assistant", reply)
        return reply
    except Exception as e:
        logging.error(f"Groq error: {e}")
        return "Черри в коме. Не могу ответить."
