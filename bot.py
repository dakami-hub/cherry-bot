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

from db import init_db, get_setting, set_setting, add_admin, remove_admin, is_admin, is_superadmin, get_all_admins
from keyboard import fix_keyboard, should_fix
from tts import text_to_voice
import debts as debts_module
import ai
from download import download_tiktok_video, download_tiktok_audio

load_dotenv()
TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("No TELEGRAM_TOKEN in .env")

DOWNLOADER_URL = os.environ.get("DOWNLOADER_URL")          # пока не используется
DOWNLOADER_SECRET = os.environ.get("DOWNLOADER_SECRET")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SUPERADMIN_USERNAME = "dakamiwannadielmaowhatabozo"  # замените при необходимости

last_ai_reply = {}
init_db()

# При старте проверяем, есть ли суперадмин, если нет – добавляем (по username)
def ensure_superadmin():
    # Находим пользователя по username (нужно будет получить user_id из Telegram, но при старте мы не знаем)
    # Поэтому сделаем так: при первом обращении суперадмина по username он добавится автоматически.
    # Но для удобства добавим заглушку: если суперадмин не найден, он добавится при первой команде.
    pass

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
# Проверка прав администратора
def has_admin_rights(user_id: str) -> bool:
    """Возвращает True, если пользователь суперадмин или мини-админ."""
    return is_superadmin(user_id) or is_admin(user_id)

async def send_typing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )

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
    user_id = str(update.effective_user.id)
    user = update.effective_user

    # Автоматическое добавление суперадмина по username при первой команде
    if user.username and user.username.lower() == SUPERADMIN_USERNAME.lower():
        if not is_superadmin(user_id):
            add_admin(user_id, user.username, "superadmin")
            logger.info(f"Added superadmin {user.username} ({user_id})")

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
            "`!режим [cherry/normal]` — сменить режим (только админы)\n"
            "`!шанс [0-100]` — сменить шанс ответа (только админы)\n"
            "`!голосшанс [0-100]` — сменить шанс голосового ответа (только админы)\n"
            "`!датьправа @username` — добавить мини-админа (только суперадмин)\n"
            "`!забратьправа @username` — удалить мини-админа (только суперадмин)\n"
            "`!админы` — список админов (только суперадмин)\n"
            "`!команды` — этот список\n\n"
            f"*Текущий режим:* {mode}\n"
            f"*Шанс ответа:* {resp_chance}%\n"
            f"*Шанс голосового:* {voice_chance}%",
            parse_mode='Markdown'
        )

    # ---------- !режим (только админы) ----------
    elif cmd == "режим":
        if not has_admin_rights(user_id):
            await update.message.reply_text("⛔ Только для администраторов.")
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

    # ---------- !шанс (только админы) ----------
    elif cmd == "шанс":
        if not has_admin_rights(user_id):
            await update.message.reply_text("⛔ Только для администраторов.")
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

    # ---------- !голосшанс (только админы) ----------
    elif cmd == "голосшанс":
        if not has_admin_rights(user_id):
            await update.message.reply_text("⛔ Только для администраторов.")
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

    # ---------- !датьправа (только суперадмин) ----------
    elif cmd == "датьправа":
        if not is_superadmin(user_id):
            await update.message.reply_text("⛔ Только для суперадмина.")
            return
        if not args:
            await update.message.reply_text("❗ Укажи пользователя: !датьправа @username")
            return
        mention = args[0]
        if not mention.startswith('@'):
            await update.message.reply_text("Укажи пользователя через @username")
            return
        target_username = mention[1:]
        # Ищем пользователя в чате
        try:
            member = await context.bot.get_chat_member(update.effective_chat.id, mention)
            target_id = str(member.user.id)
            target_name = member.user.full_name
        except:
            await update.message.reply_text("Не удалось найти пользователя в этом чате.")
            return
        # Добавляем
        add_admin(target_id, target_username, "admin")
        await update.message.reply_text(f"✅ Пользователь {target_name} добавлен в админы.")

    # ---------- !забратьправа (только суперадмин) ----------
    elif cmd == "забратьправа":
        if not is_superadmin(user_id):
            await update.message.reply_text("⛔ Только для суперадмина.")
            return
        if not args:
            await update.message.reply_text("❗ Укажи пользователя: !забратьправа @username")
            return
        mention = args[0]
        if not mention.startswith('@'):
            await update.message.reply_text("Укажи пользователя через @username")
            return
        target_username = mention[1:]
        try:
            member = await context.bot.get_chat_member(update.effective_chat.id, mention)
            target_id = str(member.user.id)
        except:
            await update.message.reply_text("Не удалось найти пользователя в этом чате.")
            return
        # Нельзя удалить суперадмина
        if is_superadmin(target_id):
            await update.message.reply_text("❌ Нельзя удалить суперадмина.")
            return
        remove_admin(target_id)
        await update.message.reply_text(f"✅ Пользователь @{target_username} удалён из админов.")

    # ---------- !админы (только суперадмин) ----------
    elif cmd == "админы":
        if not is_superadmin(user_id):
            await update.message.reply_text("⛔ Только для суперадмина.")
            return
        admins = get_all_admins()
        if not admins:
            await update.message.reply_text("Нет администраторов.")
            return
        lines = ["👑 *Администраторы:*"]
        for uid, uname, role in admins:
            name = uname or uid
            if role == "superadmin":
                lines.append(f"⭐ {name} (суперадмин)")
            else:
                lines.append(f"🔹 {name}")
        await update.message.reply_text("\n".join(lines), parse_mode='Markdown')

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
            last_ai_reply[user_id] = answer
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
        creditor_id = user_id
        creditor_name = user.full_name
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
        debtor_id = user_id
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
            user_id
        )
        await update.message.reply_text(debts_str, parse_mode='Markdown')

    # ---------- !звук ----------
    elif cmd == "звук":
        if not args:
            await update.message.reply_text("❗ Напиши: !звук ссылка_на_видео")
            return
        url = args[0]
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

    if re.search(r'(tiktok\.com|vm\.tiktok\.com)', url):
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
    elif re.search(r'(vk\.com/video|vk\.com/clip|vk\.ru|youtu\.be|youtube\.com)', url):
        await update.message.reply_text("🔧 Функция скачивания для VK и YouTube в разработке. Пока что можно скачивать только TikTok.")
    else:
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
async def cherry_mode_response(update