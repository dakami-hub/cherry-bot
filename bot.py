import os
import re
import logging
import random
import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes
)
from telegram.constants import ChatAction

from db import init_db, get_setting, set_setting
from keyboard import fix_keyboard, should_fix
from tts import text_to_voice
import debts as debts_module
import ai
from download import download_tiktok_video, download_tiktok_audio

load_dotenv()
TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("No TELEGRAM_TOKEN in .env")

DOWNLOADER_URL = os.environ.get("DOWNLOADER_URL")          # пока не используется, оставим на будущее
DOWNLOADER_SECRET = os.environ.get("DOWNLOADER_SECRET")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

ADMIN_USERNAME = "dakamiwannadielmaowhatabozo"  # замените при необходимости

last_ai_reply = {}
init_db()

# ------------------------------------------------------------
# Настройки
def get_mode(chat_id: str) -> str:
    return get_setting(chat_id, "mode", "cherry")

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
# Вспомогательные функции
async def send_typing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )

def is_admin(user) -> bool:
    return user.username and user.username.lower() == ADMIN_USERNAME.lower()

# ------------------------------------------------------------
# Команды /start, /help, /clear
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🍒 Привет! Я Черри.\n"
        "Умею:\n"
        "• Исправлять раскладку (авто или !тр)\n"
        "• Вести долги (!должен, !вернул, !долги)\n"
        "• Скачивать видео/аудио из TikTok (просто ссылка или !звук ссылка)\n"
        "• Общаться как человек (в режиме cherry) или через !ии (в любом режиме)\n"
        "• Получать ответ с интернетом через !smart\n"
        "• Озвучивать ответы (автоматически или !озвучь)\n\n"
        "Команды: /start, /clear, /help, !команды\n"
        "⚠️ VK и YouTube временно недоступны — в разработке."
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
# Обработчик всех команд с !
async def handle_prefix_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.startswith('!'):
        return

    parts = text.split()
    cmd = parts[0][1:].lower()
    args = parts[1:]
    chat_id = str(update.effective_chat.id)

    # ---------- !команды ----------
    if cmd in ["команды", "help", "помощь"]:
        mode = get_mode(chat_id)
        resp_chance = int(get_response_chance(chat_id) * 100)
        voice_chance = int(get_voice_chance(chat_id) * 100)
        await update.message.reply_text(
            f"🍒 *Список команд:*\n"
            "`!тр [текст]` — исправить раскладку\n"
            "`!должен @username сумма описание` — записать долг\n"
            "`!вернул @username сумма` — отметить возврат\n"
            "`!долги` — показать ваши долги\n"
            "`!звук ссылка` — скачать аудио из TikTok\n"
            "`!озвучь` — озвучить последний ответ\n"
            "`!ии текст` — поговорить с обычным ИИ (в любом режиме)\n"
            "`!smart текст` — получить ответ с поиском в интернете\n"
            "`!режим [cherry/normal]` — сменить режим (только админ)\n"
            "`!шанс [0-100]` — сменить шанс ответа (только админ)\n"
            "`!голосшанс [0-100]` — сменить шанс голосового ответа (только админ)\n"
            "`!команды` — этот список\n\n"
            f"*Текущий режим:* {mode}\n"
            f"*Шанс ответа:* {resp_chance}%\n"
            f"*Шанс голосового:* {voice_chance}%",
            parse_mode='Markdown'
        )

    # ---------- !режим (админ) ----------
    elif cmd == "режим":
        if not is_admin(update.effective_user):
            await update.message.reply_text("⛔ Только для администратора.")
            return
        if not args:
            await update.message.reply_text(f"Текущий режим: {get_mode(chat_id)}. Используй: !режим cherry или !режим normal")
            return
        new_mode = args[0].lower()
        if new_mode not in ["cherry", "normal"]:
            await update.message.reply_text("Режим должен быть cherry или normal")
            return
        set_mode(chat_id, new_mode)
        await update.message.reply_text(f"✅ Режим изменён на {new_mode} для этого чата")

    # ---------- !шанс (админ) ----------
    elif cmd == "шанс":
        if not is_admin(update.effective_user):
            await update.message.reply_text("⛔ Только для администратора.")
            return
        if not args:
            curr = int(get_response_chance(chat_id) * 100)
            await update.message.reply_text(f"Текущий шанс ответа: {curr}%")
            return
        try:
            val = float(args[0])
            if val < 0 or val > 100:
                raise ValueError
            set_response_chance(chat_id, val / 100.0)
            await update.message.reply_text(f"✅ Шанс ответа изменён на {val}% для этого чата")
        except:
            await update.message.reply_text("Укажи число от 0 до 100")

    # ---------- !голосшанс (админ) ----------
    elif cmd == "голосшанс":
        if not is_admin(update.effective_user):
            await update.message.reply_text("⛔ Только для администратора.")
            return
        if not args:
            curr = int(get_voice_chance(chat_id) * 100)
            await update.message.reply_text(f"Текущий шанс голосового ответа: {curr}%")
            return
        try:
            val = float(args[0])
            if val < 0 or val > 100:
                raise ValueError
            set_voice_chance(chat_id, val / 100.0)
            await update.message.reply_text(f"✅ Шанс голосового ответа изменён на {val}% для этого чата")
        except:
            await update.message.reply_text("Укажи число от 0 до 100")

    # ---------- !ии (обычный ассистент) ----------
    elif cmd == "ии":
        query = None
        if args:
            query = ' '.join(args)
        elif update.message.reply_to_message:
            query = update.message.reply_to_message.text
        if not query:
            await update.message.reply_text("Напиши: !ии текст (или ответь на сообщение)")
            return
        await send_typing(update, context)
        user_id = str(update.effective_user.id)
        reply = await ai.get_normal_response(chat_id, user_id, query)
        last_ai_reply[user_id] = reply
        await update.message.reply_text(reply)

    # ---------- !smart (умный ассистент с интернетом) ----------
    elif cmd == "smart":
        query = None
        if args:
            query = ' '.join(args)
        elif update.message.reply_to_message:
            query = update.message.reply_to_message.text
        if not query:
            await update.message.reply_text("Напиши: !smart вопрос (или ответь на сообщение)")
            return
        await send_typing(update, context)
        await update.message.reply_text("🔍 Ищу в интернете...")
        try:
            answer = await ai.get_smart_response(query)
            last_ai_reply[str(update.effective_user.id)] = answer
            await update.message.reply_text(answer)
        except Exception as e:
            logger.error(f"Smart command error: {e}")
            await update.message.reply_text("❌ Не удалось получить ответ. Попробуй позже.")

    # ---------- !тр ----------
    elif cmd == "тр":
        if args:
            fixed = fix_keyboard(' '.join(args))
            await update.message.reply_text(f"🔁 Исправлено: {fixed}")
        elif update.message.reply_to_message and update.message.reply_to_message.text:
            fixed = fix_keyboard(update.message.reply_to_message.text)
            await update.message.reply_text(f"🔁 Исправлено: {fixed}")
        else:
            await update.message.reply_text("Напиши: !тр текст (или ответь на сообщение)")

    # ---------- !должен ----------
    elif cmd == "должен":
        if len(args) < 3:
            await update.message.reply_text("❗ Формат: !должен @username сумма описание")
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
            chat_id,
            creditor_id, creditor_name,
            debtor_id, debtor_name,
            amount, description
        )
        await update.message.reply_text(f"✅ Записал: {debtor_name} должен {creditor_name} {amount} руб. ({description})")

    # ---------- !вернул ----------
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
            chat_id,
            creditor_id,
            debtor_id,
            amount
        )
        if success:
            await update.message.reply_text(f"✅ Отметил возврат {amount} руб.")
        else:
            await update.message.reply_text("❌ Не найден непогашенный долг с такой суммой.")

    # ---------- !долги ----------
    elif cmd == "долги":
        debts_str = debts_module.get_debts_for_user(
            chat_id,
            str(update.effective_user.id)
        )
        await update.message.reply_text(debts_str, parse_mode='Markdown')

    # ---------- !звук ----------
    elif cmd == "звук":
        if not args:
            await update.message.reply_text("❗ Напиши: !звук ссылка_на_видео")
            return
        url = args[0]
        # Проверяем тип ссылки
        if re.search(r'(tiktok\.com|vm\.tiktok\.com)', url):
            await send_typing(update, context)
            await update.message.reply_text("🎵 Скачиваю аудио из TikTok...")
            filepath = download_tiktok_audio(url)
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
        elif re.search(r'(vk\.com/video|vk\.com/clip|vk\.ru|youtu\.be|youtube\.com)', url):
            await update.message.reply_text("🔧 Функция скачивания аудио для VK и YouTube в разработке. Пока что можно скачивать только TikTok.")
        else:
            await update.message.reply_text("Ссылка должна быть на TikTok (tiktok.com или vm.tiktok.com)")

    # ---------- !озвучь ----------
    elif cmd == "озвучь":
        user_id = str(update.effective_user.id)
        if user_id not in last_ai_reply:
            await update.message.reply_text("Сначала получи ответ от ИИ (через !ии, !smart или в режиме cherry).")
            return
        text_to_say = last_ai_reply[user_id]
        await send_typing(update, context)
        try:
            voice_file = f"voice_{user_id}.mp3"
            await text_to_voice(text_to_say, voice_file)
            with open(voice_file, 'rb') as vf:
                await update.message.reply_voice(voice=vf)
            os.remove(voice_file)
        except Exception as e:
            logger.error(f"Voice command error: {e}")
            await update.message.reply_text("Не удалось создать голосовое сообщение.")

    else:
        pass  # неизвестная команда

# ------------------------------------------------------------
# Автоскачивание видео из TikTok
async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    url_match = re.search(r'(https?://\S+)', text)
    if not url_match:
        return
    url = url_match.group(0)

    # Обрабатываем только TikTok
    if re.search(r'(tiktok\.com|vm\.tiktok\.com)', url):
        # Если это команда !звук, не обрабатываем здесь
        if text.startswith('!звук'):
            return
        await send_typing(update, context)
        await update.message.reply_text("📥 Скачиваю видео из TikTok...")
        filepath = download_tiktok_video(url)
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
    # Заглушка для других платформ
    elif re.search(r'(vk\.com/video|vk\.com/clip|vk\.ru|youtu\.be|youtube\.com)', url):
        await update.message.reply_text("🔧 Функция скачивания для VK и YouTube в разработке. Пока что можно скачивать только TikTok.")
    else:
        # Не наша ссылка — игнорируем
        return

# ------------------------------------------------------------
# Автоисправление раскладки
async def auto_fix_layout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text or text.startswith('!'):
        return
    if await should_fix(text):
        fixed = fix_keyboard(text)
        if fixed != text:
            await update.message.reply_text(f"🔁 Возможно, вы имели в виду: {fixed}")

# ------------------------------------------------------------
# Режим Черри
async def cherry_mode_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text or text.startswith('!'):
        return
    if re.search(r'(https?://\S+)', text):
        return

    chat_id = str(update.effective_chat.id)
    if get_mode(chat_id) != "cherry":
        return

    user_id = str(update.effective_user.id)
    is_named = "черри" in text.lower()
    is_reply = update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id
    chance = get_response_chance(chat_id)

    if is_named or is_reply or random.random() < chance:
        await send_typing(update, context)
        reply = await ai.get_cherry_response(chat_id, user_id, text)
        last_ai_reply[user_id] = reply

        voice_chance = get_voice_chance(chat_id)
        if random.random() < voice_chance:
            try:
                voice_file = f"voice_{user_id}.mp3"
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
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("clear", clear_ai_history))

    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'^!'), handle_prefix_commands))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url), group=0)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, auto_fix_layout), group=1)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, cherry_mode_response), group=2)

    logger.info("Cherry Bot запущен")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()