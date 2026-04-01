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
WORDLE_WEB_URL = os.environ.get("WORDLE_WEB_URL", "https://cherry-wordle-web-production.up.railway.app")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

maintenance_mode = False
SUPERADMIN_ID = os.environ.get("SUPERADMIN_ID")
SUPERADMIN_USERNAME = "dakamiwannadielmaowhatabozo"
last_ai_reply = {}
init_db()
init_wordle_db()

# ------------------------------------------------------------
# Настройки (оставляем как есть)
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

def has_admin_rights(user_id: str) -> bool:
    return is_superadmin(user_id) or is_admin(user_id)

async def send_typing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

# ------------------------------------------------------------
# Команды
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("start_command called")
    args = context.args
    if args and args[0] == "wordle":
        # ... код для wordle ...
        await update.message.reply_text("Wordle команда")
    else:
        await update.message.reply_text("Привет! Я Черри.")

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

async def save_user_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user:
        user = update.effective_user
        save_user(str(user.id), user.username, user.full_name)

# ------------------------------------------------------------
# Обработчик команд с !
async def handle_prefix_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("handle_prefix_commands called")
    # ... весь код команд (режим, шанс, долги, cherrywordle и т.д.) ...
    # Вместо полного кода вставим минимальный для проверки:
    await update.message.reply_text("Команда получена")

# ------------------------------------------------------------
# Автоскачивание видео
async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... код ...
    pass

async def auto_fix_layout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... код ...
    pass

async def cherry_mode_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... код ...
    pass

# ------------------------------------------------------------
def main():
    app = Application.builder().token(TOKEN).build()

    # Сохраняем всех пользователей
    app.add_handler(MessageHandler(filters.ALL, save_user_handler))

    # Команды
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("clear", clear_ai_history))

    # Все команды с !
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'^!'), handle_prefix_commands))

    # Обработка ссылок, автоисправление, режим Черри
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, auto_fix_layout))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, cherry_mode_response))

    logger.info("Cherry Bot запущен")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()