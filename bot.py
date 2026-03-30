import os
import re
import logging
import random
import asyncio
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes
)
from telegram.constants import ChatAction

from db import init_db
from keyboard import fix_keyboard
from download import download_video, download_audio
from tts import text_to_voice
import debts as debts_module
import ai

load_dotenv()
TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("No TELEGRAM_TOKEN in .env")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

RESPONSE_CHANCE = 0.4
last_ai_reply = {}

init_db()

# ------------------------------------------------------------
# Вспомогательные функции
async def send_typing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )

# ------------------------------------------------------------
# Обработчики команд Telegram (начинаются с /)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🍒 Привет! Я Черри.\n"
        "Умею:\n"
        "• Исправлять раскладку (авто или !тр)\n"
        "• Вести долги (!должен, !вернул, !долги)\n"
        "• Скачивать видео/аудио (ссылка или !звук ссылка)\n"
        "• Общаться как человек (просто пиши, можешь позвать по имени)\n"
        "• Озвучивать ответы (!озвучь)\n\n"
        "Команды: /start, /clear, /help, а также !команды"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def clear_ai_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import sqlite3
    from db import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM messages WHERE chat_id = ? AND user_id = ?",
              (str(update.effective_chat.id), str(update.effective_user.id)))
    conn.commit()
    conn.close()
    await update.message.reply_text("🧠 История диалога очищена.")

# ------------------------------------------------------------
# Обработчик команд с ! (кириллические)
async def handle_prefix_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.startswith('!'):
        return

    parts = text.split()
    cmd = parts[0][1:].lower()
    args = parts[1:]

    # --------------------------------------------------------
    # !команды / !help / !помощь
    if cmd in ["команды", "help", "помощь"]:
        await update.message.reply_text(
            "🍒 *Список команд:*\n"
            "`!тр [текст]` — исправить раскладку (если текст не указан, исправляет ответное сообщение)\n"
            "`!должен @username сумма описание` — записать долг\n"
            "`!вернул @username сумма` — отметить возврат долга\n"
            "`!долги` — показать ваши долги\n"
            "`!звук ссылка` — скачать аудио из видео\n"
            "`!озвучь` — озвучить последний ответ Черри\n"
            "`!команды` — показать этот список\n\n"
            "Также я автоматически исправляю сбившуюся раскладку и скачиваю видео по ссылке.\n"
            "Просто пишите мне, чтобы пообщаться, или зовите по имени «Черри».",
            parse_mode='Markdown'
        )

    # --------------------------------------------------------
    # !тр
    elif cmd == "тр":
        if args:
            fixed = fix_keyboard(' '.join(args))
            await update.message.reply_text(f"🔁 Исправлено: {fixed}")
        elif update.message.reply_to_message:
            original = update.message.reply_to_message.text
            if original:
                fixed = fix_keyboard(original)
                await update.message.reply_text(f"🔁 Исправлено: {fixed}")
            else:
                await update.message.reply_text("Ответь на текстовое сообщение.")
        else:
            await update.message.reply_text("Напиши: !тр текст (или ответь на сообщение)")

    # --------------------------------------------------------
    # !должен
    elif cmd == "должен":
        if len(args) < 3:
            await update.message.reply_text("❗ Формат: !должен @username сумма описание\nПример: !должен @petrov 500 за шаурму")
            return
        mention = args[0]
        if not mention.startswith('@'):
            await update.message.reply_text("Укажи пользователя через @username")
            return
        try:
            amount = float(args[1])
        except:
            await update.message.reply_text("Сумма должна быть числом.")
            return
        description = ' '.join(args[2:])
        creditor_id = str(update.effective_user.id)
        creditor_name = update.effective_user.full_name
        debtor_username = mention[1:]
        debtor_id = debtor_username
        debtor_name = debtor_username
        try:
            member = await context.bot.get_chat_member(update.effective_chat.id, mention)
            debtor_id = str(member.user.id)
            debtor_name = member.user.full_name
        except:
            pass
        debts_module.add_debt(
            str(update.effective_chat.id),
            creditor_id, creditor_name,
            debtor_id, debtor_name,
            amount, description
        )
        await update.message.reply_text(f"✅ Записал: {debtor_name} должен {creditor_name} {amount} руб. ({description})")

    # --------------------------------------------------------
    # !вернул
    elif cmd == "вернул":
        if len(args) < 2:
            await update.message.reply_text("❗ Формат: !вернул @username сумма")
            return
        mention = args[0]
        if not mention.startswith('@'):
            await update.message.reply_text("Укажи пользователя через @username")
            return
        try:
            amount = float(args[1])
        except:
            await update.message.reply_text("Сумма должна быть числом.")
            return
        creditor_username = mention[1:]
        debtor_id = str(update.effective_user.id)
        creditor_id = creditor_username
        try:
            member = await context.bot.get_chat_member(update.effective_chat.id, mention)
            creditor_id = str(member.user.id)
        except:
            pass
        success = debts_module.repay_debt(
            str(update.effective_chat.id),
            creditor_id,
            debtor_id,
            amount
        )
        if success:
            await update.message.reply_text(f"✅ Отметил возврат {amount} руб.")
        else:
            await update.message.reply_text("❌ Не найден непогашенный долг с такой суммой.")

    # --------------------------------------------------------
    # !долги
    elif cmd == "долги":
        debts_str = debts_module.get_debts_for_user(
            str(update.effective_chat.id),
            str(update.effective_user.id)
        )
        await update.message.reply_text(debts_str, parse_mode='Markdown')

    # --------------------------------------------------------
    # !звук
    elif cmd == "звук":
        if not args:
            await update.message.reply_text("❗ Напиши: !звук ссылка_на_видео")
            return
        url = args[0]
        if not re.search(r'(tiktok\.com|vk\.com|youtu\.be|youtube\.com)', url):
            await update.message.reply_text("Ссылка должна быть на TikTok, VK или YouTube.")
            return
        await send_typing(update, context)
        await update.message.reply_text("🎵 Скачиваю аудио...")
        filepath = download_audio(url)
        if filepath and os.path.exists(filepath):
            try:
                with open(filepath, 'rb') as f:
                    await update.message.reply_audio(audio=f, title="audio.mp3")
                os.remove(filepath)
            except Exception as e:
                logger.error(f"Send audio error: {e}")
                await update.message.reply_text("Не удалось отправить аудио.")
        else:
            await update.message.reply_text("Не удалось скачать аудио.")

    # --------------------------------------------------------
    # !озвучь
    elif cmd == "озвучь":
        user_id = str(update.effective_user.id)
        if user_id not in last_ai_reply:
            await update.message.reply_text("Сначала получи ответ от Черри (напиши что-нибудь).")
            return
        text_to_say = last_ai_reply[user_id]
        await send_typing(update, context)
        try:
            voice_file = f"voice_{user_id}.ogg"
            await text_to_voice(text_to_say, voice_file)
            with open(voice_file, 'rb') as vf:
                await update.message.reply_voice(voice=vf)
            os.remove(voice_file)
        except Exception as e:
            logger.error(f"Voice command error: {e}")
            await update.message.reply_text("Не удалось создать голосовое сообщение.")

    else:
        # Неизвестная команда — игнорируем
        pass

# ------------------------------------------------------------
# Скачивание по ссылке (авто)
async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    url_match = re.search(r'(https?://\S+)', text)
    if not url_match:
        return
    url = url_match.group(0)
    if not re.search(r'(tiktok\.com|vm\.tiktok\.com|vk\.com/video|youtu\.be|youtube\.com)', url):
        return
    if text.startswith('!звук'):
        return
    await send_typing(update, context)
    await update.message.reply_text("📥 Скачиваю видео...")
    filepath = download_video(url)
    if filepath and os.path.exists(filepath):
        try:
            with open(filepath, 'rb') as f:
                await update.message.reply_video(video=f, caption="Смотри, пока не удалили")
            os.remove(filepath)
        except Exception as e:
            logger.error(f"Send video error: {e}")
            await update.message.reply_text("Не удалось отправить видео.")
    else:
        await update.message.reply_text("Не удалось скачать видео. Проверь ссылку.")

# ------------------------------------------------------------
# Автоисправление раскладки
async def auto_fix_layout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text or text.startswith('!'):
        return
    fixed = fix_keyboard(text)
    if fixed != text:
        await update.message.reply_text(f"🔁 Возможно, вы имели в виду: {fixed}")

# ------------------------------------------------------------
# ИИ Черри
async def ai_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text or text.startswith('!'):
        return
    if re.search(r'(https?://\S+)', text):
        return

    chat_id = str(update.effective_chat.id)
    user_id = str(update.effective_user.id)
    is_named = "черри" in text.lower()
    is_reply = update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id

    if is_named or is_reply or random.random() < RESPONSE_CHANCE:
        await send_typing(update, context)
        reply = await ai.get_cherry_response(chat_id, user_id, text)
        last_ai_reply[user_id] = reply
        if random.random() < 0.3:
            try:
                voice_file = f"voice_{user_id}.ogg"
                await text_to_voice(reply, voice_file)
                with open(voice_file, 'rb') as vf:
                    await update.message.reply_voice(voice=vf)
                os.remove(voice_file)
            except Exception as e:
                logger.error(f"Voice error: {e}")
                await update.message.reply_text(reply)
        else:
            await update.message.reply_text(reply)

# ------------------------------------------------------------
# Основная функция
def main():
    app = Application.builder().token(TOKEN).build()

    # Обработчики команд с /
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("clear", clear_ai_history))

    # Обработчик команд с ! (кириллические)
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'^!'), handle_prefix_commands))

    # Автоскачивание видео по ссылке
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url), group=0)
    # Автоисправление раскладки
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, auto_fix_layout), group=1)
    # ИИ Черри (все остальные текстовые сообщения)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_response), group=2)

    logger.info("Cherry Bot запущен")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
