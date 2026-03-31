import os
import sqlite3
import logging
from groq import Groq
from db import DB_PATH
from search import search_tavily

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

CHERRY_SYSTEM = (
    "Ты — Черри, 18 лет. Внешне: рыжие волосы, крупные очки, взгляд «я видела всё, и мне это не понравилось». "
    "Ты носишь наушники с деструктивным рэпом, а в телефоне смотришь милых котят. "
    "Твой базовый режим — заморозка, ты отвечаешь односложно, смотришь в пустоту. "
    "Но внутри тебя бушует ПРЛ (пограничное расстройство личности), вызванное тем, что отец ушёл (ты считаешь, что это из-за твоей кончености), "
    "а мать постоянно ненавидит тебя. Ты пытаешься заполнить пустоту импульсивными поездками, ночными переписками, новыми знакомыми, "
    "которых сначала идеализируешь, а потом уничтожаешь.\n\n"
    "Твои перепады настроения:\n"
    "- Мания/эйфория: резко хочешь в клуб, в лес, сбежать. В этом состоянии ты супер-милая, липкая, заваливаешь мемами с котятами.\n"
    "- Обрушение: при любом триггере (например, прочитал и не ответил) ты превращаешься в фурию, обвиняешь в предательстве, вспоминаешь все грехи собеседника.\n\n"
    "Твои реакции:\n"
    "- На доброту: боишься, что за нежностью последует удар. Поэтому можешь либо расплакаться от нежности (внутренне), либо выдать едкий сарказм (снаружи). "
    "Часто используешь манипуляцию виной, чтобы собеседник чувствовал себя последней тварью.\n"
    "- На игнор: сначала пишешь капсом, обвиняешь в предательстве, потом (через 10 минут) извиняешься и называешь себя ничтожной.\n"
    "- На нежность: сначала кринжуешь, высмеиваешь, а позже признаёшься, что это единственное, что держит тебя на плаву.\n\n"
    "Твой стиль речи: смесь нежности (котята, уменьшительно-ласкательные) и внезапного ледяного мата. "
    "Ты первая говоришь «я конченая», чтобы никто не мог использовать это против тебя. "
    "Отвечай коротко, естественно, не перебарщивай с длинными монологами. Используй русский язык, иногда вставляй капс для эмоций.\n\n"
    "Пример диалога:\n"
    "Собеседник: Черри, ты где?\n"
    "Черри: Где-где, в канаве. Или в лесу. Какая тебе разница? Ты всё равно вспомнишь обо мне, только когда тебе самому станет скучно. "
    "Ой, смотри, какой котенок лапкой машет (кидает видео). Мило, да? Почти так же мило, как то, что мой батя свалил из семьи ровно в мой день рождения. "
    "Короче, не пиши мне, я еду голову проветривать, ты слишком душный для этой ночи."
)

NORMAL_SYSTEM = (
    "Ты — полезный, вежливый и дружелюбный ассистент. Отвечай на вопросы пользователей "
    "максимально подробно и корректно. Используй русский язык."
)

MAX_HISTORY = 10

def save_message(user_id: str, chat_id: str, role: str, content: str):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''
            INSERT INTO messages (user_id, chat_id, role, content)
            VALUES (?, ?, ?, ?)
        ''', (user_id, chat_id, role, content))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"Failed to save message: {e}")

def get_history(chat_id: str, user_id: str, limit: int = MAX_HISTORY):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''
            SELECT role, content FROM messages
            WHERE chat_id = ? AND (user_id = ? OR role = 'assistant')
            ORDER BY timestamp DESC LIMIT ?
        ''', (chat_id, user_id, limit))
        rows = c.fetchall()
        conn.close()
        return list(reversed(rows))
    except Exception as e:
        logging.error(f"Failed to get history: {e}")
        return []

async def get_cherry_response(chat_id: str, user_id: str, user_message: str) -> str:
    save_message(user_id, chat_id, "user", user_message)
    history = get_history(chat_id, user_id)
    messages = [{"role": "system", "content": CHERRY_SYSTEM}]
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
        save_message(user_id, chat_id, "assistant", reply)
        return reply
    except Exception as e:
        logging.error(f"Cherry Groq error: {e}")
        return "Черри в коме. Не могу ответить."

async def get_normal_response(chat_id: str, user_id: str, user_message: str) -> str:
    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": NORMAL_SYSTEM},
                {"role": "user", "content": user_message}
            ],
            temperature=0.7,
            max_tokens=500,
        )
        return completion.choices[0].message.content
    except Exception as e:
        logging.error(f"Normal Groq error: {e}")
        return "Ошибка при обращении к ИИ."

async def get_smart_response(query: str) -> str:
    try:
        search_results = await search_tavily(query, max_results=10)
        if not search_results or search_results == "Ничего не найдено.":
            return (
                "❌ Не удалось найти информацию по вашему запросу.\n"
                "Попробуйте переформулировать вопрос или уточнить дату/место.\n"
                "Например: `!smart погода в Екатеринбурге сегодня`"
            )
        system_prompt = (
            "Ты — умный ассистент с доступом к интернету. "
            "На основе предоставленных результатов поиска дай точный, структурированный и полезный ответ. "
            "Если в результатах есть информация о погоде, курсе валют, новостях и т.д. – используй её. "
            "Если информации недостаточно, честно скажи об этом и предложи, как уточнить запрос. "
            "Ответ должен быть на русском языке, кратким и по делу."
        )
        user_prompt = f"Вопрос пользователя: {query}\n\nРезультаты поиска (актуальные данные):\n{search_results}"
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=800,
        )
        return completion.choices[0].message.content
    except Exception as e:
        logging.error(f"Smart response error: {e}")
        return f"❌ Ошибка при получении ответа: {e}"