import os
import re
import logging
import random
import sqlite3
import requests
import shutil
import json
import httpx
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes
)
from telegram.constants import ChatAction

from db import (
    init_db, get_setting, set_setting, add_admin, remove_admin,
    is_admin, is_superadmin, get_all_admins, save_user, get_user_by_username, DB_PATH,
    init_wordle_db, update_wordle_stats, get_wordle_stats, get_wordle_top
)
from keyboard import fix_keyboard, should_fix
from tts import text_to_voice
import debts as debts_module
import ai
from download import download_tiktok_video, download_tiktok_audio
import wordle

load_dotenv()
TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("No TELEGRAM_TOKEN in .env")

DOWNLOADER_URL = os.environ.get("DOWNLOADER_URL")
DOWNLOADER_SECRET = os.environ.get("DOWNLOADER_SECRET")

# URL веб-сервиса CherryWordle
WORDLE_WEB_URL = os.environ.get("WORDLE_WEB_URL", "https://cherry-wordle-web-production.up.railway.app")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Режим технических работ (глобальный)
maintenance_mode = False

# Настройка суперадмина: можно задать ID в переменной окружения
SUPERADMIN_ID = os.environ.get("SUPERADMIN_ID")          # например, "1545514094"
SUPERADMIN_USERNAME = "dakamiwannadielmaowhatabozo"    # запасной вариант

last_ai_reply = {}
init_db()
init_wordle_db()   # инициализация таблиц Wordle (внутренних, если используются; для веб-версии не обязательны)

# ------------------------------------------------------------
# Настройки
def get_mode(chat_id: str) -> str:
    return get_setting(chat_id, "mode", "normal")

def set_mode(chat_id: str, mode: str):
    set_setting(chat_id, "mode", mode)

def get_response_chance(chat_id: str) -> float:
    val = get_setting(chat_id, "response_chance", "0.4")
    return float(val)

def set_response_chance(chat_id: str, chance: float):
    set_setting(chat_id, "response_chance", str(chance))

def get_voice_chance(chat_id: str) -> float:
    val = get_setting(chat_id, "voice_chance", "0.3")
    return float(val)

def set_voice_chance(chat_id: str, chance: float):
    set_setting(chat_id, "voice_chance", str(chance))

# ------------------------------------------------------------
# Проверка прав
def has_admin_rights(user_id: str) -> bool:
    return is_superadmin(user_id) or is_admin(user_id)

async def send_typing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )

# ------------------------------------------------------------
# Команды
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if args and args[0] == "wordle":
        # Генерация кода для игры
        user = update.effective_user
        user_id = str(user.id)
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    f"{WORDLE_WEB_URL}/generate_code",
                    json={
                        "telegram_id": user_id,
                        "username": user.username or "",
                        "full_name": user.full_name or ""
                    },
                    timeout=10
                )
                if resp.status_code == 200:
                    data = resp.json()
                    code = data["code"]
                    await update.message.reply_text(
                        f"🎮 *CherryWordle*\n\n"
                        f"Перейдите по ссылке для игры: {WORDLE_WEB_URL}/game\n"
                        f"Введите код: `{code}`\n\n"
                        f"Код действителен 5 минут.",
                        parse_mode='Markdown'
                    )
                else:
                    await update.message.reply_text("❌ Ошибка генерации кода. Попробуйте позже.")
            except Exception as e:
                logger.error(f"Wordle start error: {e}")
                await update.message.reply_text("❌ Не удалось подключиться к серверу игры.")
    else:
        # Обычный /start
        await update.message.reply_text(
            "🍒 Привет! Я Черри.\n"
            "По умолчанию я в режиме *normal* — не отвечаю сама, только по командам.\n"
            "Чтобы включить мой токсичный режим, администратор может использовать `!режим cherry`.\n\n"
            "Умею:\n"
            "• Исправлять раскладку (авто или !тр)\n"
            "• Вести долги (!должен, !вернул, !долги)\n"
            "• Скачивать видео/аудио из TikTok (просто ссылка или !звук ссылка)\n"
            "• Общаться как человек (в режиме cherry) или через !ии (в любом режиме)\n"
            "• Получать ответ с интернетом через !smart\n"
            "• Озвучивать ответы (автоматически или !озвучь)\n"
            "• Играть в CherryWordle (!cherrywordle)\n\n"
            "Команды: /start, /clear, /help, !команды\n"
            "⚠️ VK и YouTube временно недоступны — в разработке.",
            parse_mode='Markdown'
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_command(update, context)

async def clear_ai_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM messages WHERE chat_id = ? AND user_id = ?",
              (str(update.effective_chat.id), str(update.effective_user.id)))
    conn.commit()
    conn.close()
    await update.message.reply_text("🧠 История диалога очищена.")

# ------------------------------------------------------------
# Обработчик всех сообщений — сохраняем пользователей
async def save_user_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user:
        user = update.effective_user
        save_user(str(user.id), user.username, user.full_name)

# ------------------------------------------------------------
# Проверка доступности сервисов для команды !тест (остаётся без изменений)
async def run_self_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запускает диагностику и отправляет результат суперадмину."""
    results = []
    # 1. Проверка базы данных
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("SELECT 1")
        conn.close()
        results.append("✅ База данных: OK")
    except Exception as e:
        results.append(f"❌ База данных: ошибка – {e}")

    # 2. Проверка Telegram API
    try:
        await context.bot.send_message(chat_id=update.effective_user.id, text="Тест Telegram API: OK")
        results.append("✅ Telegram API: OK")
    except Exception as e:
        results.append(f"❌ Telegram API: ошибка – {e}")

    # 3. Проверка Groq API
    try:
        groq_key = os.environ.get("GROQ_API_KEY")
        if not groq_key:
            results.append("⚠️ Groq API ключ не задан")
        else:
            import groq
            client = groq.Groq(api_key=groq_key)
            test_response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": "Ответь: 2+2"}],
                max_tokens=5
            )
            if test_response.choices:
                results.append("✅ Groq API: OK")
            else:
                results.append("❌ Groq API: пустой ответ")
    except Exception as e:
        results.append(f"❌ Groq API: ошибка – {e}")

    # 4. Проверка Tavily (если ключ есть)
    tavily_key = os.environ.get("TAVILY_API_KEY")
    if tavily_key:
        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=tavily_key)
            response = client.search(query="test", max_results=1)
            if response.get('results'):
                results.append("✅ Tavily API: OK")
            else:
                results.append("⚠️ Tavily API: работает, но результат пуст")
        except Exception as e:
            results.append(f"❌ Tavily API: ошибка – {e}")
    else:
        results.append("⚠️ Tavily API ключ не задан (не используется)")

    # 5. Проверка ffmpeg и yt-dlp
    try:
        ffmpeg_path = shutil.which('ffmpeg')
        if ffmpeg_path:
            results.append(f"✅ ffmpeg найден: {ffmpeg_path}")
        else:
            results.append("❌ ffmpeg не найден")
    except Exception as e:
        results.append(f"❌ Ошибка при проверке ffmpeg: {e}")

    try:
        import yt_dlp
        results.append(f"✅ yt-dlp версия: {yt_dlp.version.__version__}")
    except Exception as e:
        results.append(f"❌ yt-dlp: {e}")

    # 6. Проверка модуля скачивания TikTok
    try:
        from download import download_tiktok_video, download_tiktok_audio
        results.append("✅ Модуль download_tiktok импортирован")
    except Exception as e:
        results.append(f"❌ download_tiktok: {e}")

    # 7. Проверка прав суперадмина
    if is_superadmin(str(update.effective_user.id)):
        results.append("✅ Вы суперадмин (ID подтверждён)")
    else:
        results.append("⚠️ Вы не суперадмин (эта проверка запущена вами, но в базе вас нет – возможно, нужно добавить)")

    # Отправляем результат
    await update.message.reply_text("🔍 *Результаты самодиагностики:*\n" + "\n".join(results), parse_mode='Markdown')

# ------------------------------------------------------------
# Обработчик команд с !
async def handle_prefix_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global maintenance_mode

    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    if not text.startswith('!'):
        return

    parts = text.split()
    cmd = parts[0][1:].lower()
    args = parts[1:]
    chat_id = str(update.effective_chat.id)
    user_id = str(update.effective_user.id)
    user = update.effective_user

    # Автоматическое добавление суперадмина
    if SUPERADMIN_ID and user_id == SUPERADMIN_ID:
        if not is_superadmin(user_id):
            add_admin(user_id, user.username or user.full_name or user_id, "superadmin")
            logger.info(f"Added superadmin by ID {user_id}")
    elif user.username and user.username.lower() == SUPERADMIN_USERNAME.lower():
        if not is_superadmin(user_id):
            add_admin(user_id, user.username, "superadmin")
            logger.info(f"Added superadmin {user.username} ({user_id})")

    # Если режим обслуживания активен, разрешаем только команды техработ и тест, и только в личке от суперадмина
    if maintenance_mode:
        if not (update.effective_chat.type == 'private' and is_superadmin(user_id)):
            return
        if cmd not in ["техработы", "конецработ", "тест"]:
            await update.message.reply_text("🔧 Бот в режиме технического обслуживания. Другие команды временно отключены.")
            return

    # ---------- !техработы ----------
    if cmd == "техработы":
        if not is_superadmin(user_id):
            await update.message.reply_text("⛔ Только для суперадмина.")
            return
        maintenance_mode = True
        await update.message.reply_text("🔧 Режим технического обслуживания включён. Бот не будет отвечать в группах и другим пользователям. Только вы можете управлять им. Для выхода используйте !конецработ.")
        return

    # ---------- !конецработ ----------
    elif cmd == "конецработ":
        if not is_superadmin(user_id):
            await update.message.reply_text("⛔ Только для суперадмина.")
            return
        maintenance_mode = False
        await update.message.reply_text("✅ Режим технического обслуживания отключён. Бот вернулся к обычной работе.")
        return

    # ---------- !тест ----------
    elif cmd == "тест":
        if not is_superadmin(user_id):
            await update.message.reply_text("⛔ Только для суперадмина.")
            return
        await run_self_test(update, context)
        return

    # ---------- Остальные команды (выполняются только если режим обслуживания выключен) ----------
    # !команды
    if cmd in ["команды", "help", "помощь"]:
        mode = get_mode(chat_id)
        resp_chance = int(get_response_chance(chat_id) * 100)
        voice_chance = int(get_voice_chance(chat_id) * 100)
        await update.message.reply_text(
            f"🍒 *Список команд:*\n"
            "`!тр [текст]` — исправить раскладку\n"
            "`!должен @username сумма описание` — записать долг (вы должны этому пользователю)\n"
            "`!вернул @username сумма` — отметить возврат долга (вы возвращаете)\n"
            "`!долги` — показать ваши долги\n"
            "`!звук ссылка` — скачать аудио из TikTok\n"
            "`!озвучь` — озвучить последний ответ\n"
            "`!ии текст` — поговорить с обычным ИИ\n"
            "`!smart текст` — ответ с поиском в интернете\n"
            "`!cherrywordle` — играть в CherryWordle (ссылка на топ и получение кода)\n"
            "`!режим [cherry/normal]` — сменить режим (админы)\n"
            "`!шанс [0-100]` — сменить шанс ответа (админы)\n"
            "`!голосшанс [0-100]` — сменить шанс голосового ответа (админы)\n"
            "`!узнатьид @username` — показать ID пользователя\n"
            "`!датьправа @username` — добавить мини-админа (суперадмин)\n"
            "`!забратьправа @username` — удалить мини-админа (суперадмин)\n"
            "`!админы` — список админов (суперадмин)\n"
            "`!админкоманды` — подробная справка для админов\n"
            "`!техработы` — включить режим обслуживания (суперадмин)\n"
            "`!конецработ` — выключить режим обслуживания (суперадмин)\n"
            "`!тест` — самодиагностика (суперадмин)\n"
            "`!команды` — этот список\n\n"
            f"*Текущий режим:* {mode}\n"
            f"*Шанс ответа:* {resp_chance}%\n"
            f"*Шанс голосового:* {voice_chance}%",
            parse_mode='Markdown'
        )

    # ---------- !cherrywordle ----------
    elif cmd == "cherrywordle":
        top_url = f"{WORDLE_WEB_URL}/top"
        await update.message.reply_text(
            f"🍒 *CherryWordle*\n\n"
            f"Посмотрите топ игроков и начните игру:\n{top_url}\n\n"
            f"Нажмите кнопку «Играть» на странице, чтобы получить код.",
            parse_mode='Markdown'
        )

    # ---------- Остальные команды (без изменений) ----------
    # !режим, !шанс, !голосшанс, !узнатьид, !датьправа, !забратьправа, !админы, !админкоманды,
    # !ии, !smart, !тр, !должен, !вернул, !долги, !звук, !озвучь — оставляем как есть
    # Они уже были в предыдущей версии bot.py. Здесь я не повторяю их для краткости, но в полном файле они должны быть.

    # ... остальной код ...

# ------------------------------------------------------------
# Автоскачивание видео, автоисправление раскладки, режим Черри, WebApp handler (если есть) — всё без изменений.
# Они уже были в предыдущем bot.py и здесь не приводятся для краткости.

def main():
    app = Application.builder().token(TOKEN).build()

    # Сохраняем всех пользователей, кто пишет
    app.add_handler(MessageHandler(filters.ALL, save_user_handler), group=-1)

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("clear", clear_ai_history))

    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'^!'), handle_prefix_commands))

    # Обработка ссылок – должна быть до всех остальных текстовых
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url), group=0)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, auto_fix_layout), group=1)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, cherry_mode_response), group=2)

    logger.info("Cherry Bot запущен")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()