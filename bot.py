import os
import re
import logging
import random
import sqlite3
import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes
)
from telegram.constants import ChatAction

from db import (
    init_db, get_setting, set_setting, add_admin, remove_admin,
    is_admin, is_superadmin, get_all_admins, save_user, get_user_by_username
)
from keyboard import fix_keyboard, should_fix
from tts import text_to_voice
import debts as debts_module
import ai
from download import download_tiktok_video, download_tiktok_audio

load_dotenv()
TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("No TELEGRAM_TOKEN in .env")

DOWNLOADER_URL = os.environ.get("DOWNLOADER_URL")
DOWNLOADER_SECRET = os.environ.get("DOWNLOADER_SECRET")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Настройка суперадмина: можно задать ID в переменной окружения
SUPERADMIN_ID = os.environ.get("SUPERADMIN_ID")          # например, "1545514094"
SUPERADMIN_USERNAME = "dakamiwannadielmaowhatabozo"    # запасной вариант

last_ai_reply = {}
init_db()

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
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        "• Озвучивать ответы (автоматически или !озвучь)\n\n"
        "Команды: /start, /clear, /help, !команды\n"
        "⚠️ VK и YouTube временно недоступны — в разработке.",
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def clear_ai_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from db import DB_PATH
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
# Обработчик команд с !
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

    # Автоматическое добавление суперадмина
    if SUPERADMIN_ID and user_id == SUPERADMIN_ID:
        if not is_superadmin(user_id):
            add_admin(user_id, user.username or user.full_name or user_id, "superadmin")
            logger.info(f"Added superadmin by ID {user_id}")
    elif user.username and user.username.lower() == SUPERADMIN_USERNAME.lower():
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
            "`!ии текст` — поговорить с обычным ИИ\n"
            "`!smart текст` — ответ с поиском в интернете\n"
            "`!режим [cherry/normal]` — сменить режим (админы)\n"
            "`!шанс [0-100]` — сменить шанс ответа (админы)\n"
            "`!голосшанс [0-100]` — сменить шанс голосового ответа (админы)\n"
            "`!узнатьид @username` — показать ID пользователя\n"
            "`!датьправа @username` — добавить мини-админа (суперадмин)\n"
            "`!забратьправа @username` — удалить мини-админа (суперадмин)\n"
            "`!админы` — список админов (суперадмин)\n"
            "`!админкоманды` — подробная справка для админов\n"
            "`!команды` — этот список\n\n"
            f"*Текущий режим:* {mode}\n"
            f"*Шанс ответа:* {resp_chance}%\n"
            f"*Шанс голосового:* {voice_chance}%",
            parse_mode='Markdown'
        )

    # ---------- !режим ----------
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

    # ---------- !шанс ----------
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
        except Exception as e:
            await update.message.reply_text("Укажи число от 0 до 100")

    # ---------- !голосшанс ----------
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
        except Exception as e:
            await update.message.reply_text("Укажи число от 0 до 100")

    # ---------- !узнатьид ----------
    elif cmd == "узнатьид":
        if not args:
            await update.message.reply_text("❗ Укажи пользователя: !узнатьид @username")
            return
        mention = args[0]
        if not mention.startswith('@'):
            await update.message.reply_text("Укажи пользователя через @username")
            return
        target_username = mention[1:]
        row = get_user_by_username(target_username)
        if row:
            target_id, target_name = row
            await update.message.reply_text(f"ID пользователя {target_name}: `{target_id}`", parse_mode='Markdown')
        else:
            try:
                member = await context.bot.get_chat_member(update.effective_chat.id, mention)
                target_id = member.user.id
                target_name = member.user.full_name
                await update.message.reply_text(f"ID пользователя {target_name}: `{target_id}`", parse_mode='Markdown')
            except Exception as e:
                await update.message.reply_text(
                    "❌ Не удалось найти пользователя. "
                    "Убедитесь, что он участник чата и бот имеет права администратора.\n"
                    "Если пользователь писал мне в личные сообщения, он уже должен быть в базе. "
                    "Попробуйте повторить команду позже."
                )

    # ---------- !датьправа ----------
    elif cmd == "датьправа":
        if not is_superadmin(user_id):
            await update.message.reply_text("⛔ Только для суперадмина.")
            return
        if not args:
            await update.message.reply_text("❗ Укажи пользователя: !датьправа @username (или ID)")
            return
        mention = args[0]
        target_id = None
        target_name = None
        if mention.startswith('@'):
            username = mention[1:]
            row = get_user_by_username(username)
            if row:
                target_id, target_name = row
            else:
                try:
                    bot_member = await context.bot.get_chat_member(update.effective_chat.id, context.bot.id)
                    if bot_member.status not in ['administrator', 'creator']:
                        await update.message.reply_text(
                            "❌ Бот не является администратором чата. "
                            "Не могу получить информацию о пользователе.\n"
                            f"Попросите @{username} написать мне в личные сообщения, "
                            "чтобы я запомнил его, и повторите команду."
                        )
                        return
                    member = await context.bot.get_chat_member(update.effective_chat.id, mention)
                    target_id = str(member.user.id)
                    target_name = member.user.full_name
                except Exception as e:
                    await update.message.reply_text(
                        f"❌ Не удалось найти пользователя {mention} в этом чате.\n"
                        "Убедитесь, что он участник и бот имеет права администратора.\n"
                        "Альтернативно, попросите его написать мне в личные сообщения, "
                        "затем повторите команду."
                    )
                    return
        else:
            target_id = mention
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT full_name FROM known_users WHERE user_id = ?", (target_id,))
            row = c.fetchone()
            conn.close()
            target_name = row[0] if row else f"пользователь {target_id}"
        add_admin(target_id, target_name, "admin")
        await update.message.reply_text(f"✅ Пользователь {target_name} добавлен в админы.")

    # ---------- !забратьправа ----------
    elif cmd == "забратьправа":
        if not is_superadmin(user_id):
            await update.message.reply_text("⛔ Только для суперадмина.")
            return
        if not args:
            await update.message.reply_text("❗ Укажи пользователя: !забратьправа @username (или ID)")
            return
        mention = args[0]
        target_id = None
        if mention.startswith('@'):
            row = get_user_by_username(mention[1:])
            if row:
                target_id = row[0]
            else:
                try:
                    member = await context.bot.get_chat_member(update.effective_chat.id, mention)
                    target_id = str(member.user.id)
                except Exception as e:
                    await update.message.reply_text("Не удалось найти пользователя. Укажите ID.")
                    return
        else:
            target_id = mention
        if is_superadmin(target_id):
            await update.message.reply_text("❌ Нельзя удалить суперадмина.")
            return
        remove_admin(target_id)
        await update.message.reply_text(f"✅ Пользователь {target_id} удалён из админов.")

    # ---------- !админы ----------
    elif cmd == "админы":
        if not is_superadmin(user_id):
            await update.message.reply_text("⛔ Только для суперадмина.")
            return
        admins = get_all_admins()
        if not admins:
            await update.message.reply_text("Нет администраторов.")
            return
        lines = ["Администраторы:"]
        for uid, uname, role in admins:
            name = uname or uid
            if role == "superadmin":
                lines.append(f"⭐ {name} (суперадмин)")
            else:
                lines.append(f"🔹 {name}")
        await update.message.reply_text("\n".join(lines), parse_mode=None)  # убрали Markdown

    # ---------- !админкоманды ----------
    elif cmd == "админкоманды":
        if not has_admin_rights(user_id):
            await update.message.reply_text("⛔ Только для администраторов.")
            return
        admin_help_text = (
            "👑 *Подробные команды для администраторов:*\n\n"
            "`!режим [cherry|normal]` — переключить режим бота в текущем чате.\n"
            "   • `cherry` – токсичная девушка с ПРЛ, отвечает сама с шансом.\n"
            "   • `normal` – обычный ассистент, не отвечает сам, только по вызову.\n\n"
            "`!шанс [0-100]` — установить вероятность, с которой бот ответит сам (в режиме cherry).\n"
            "   • По умолчанию 40%. Влияет на случайные ответы.\n\n"
            "`!голосшанс [0-100]` — установить вероятность отправки голосового ответа.\n"
            "   • По умолчанию 30%. Применяется к ответам Черри и !ии.\n\n"
            "`!узнатьид @username` — получить числовой ID пользователя (для выдачи прав, если бот не видит username).\n"
            "`!датьправа @username` — добавить пользователя в мини-админы (только суперадмин).\n"
            "`!забратьправа @username` — удалить пользователя из мини-админов.\n"
            "`!админы` — список всех администраторов.\n"
            "`!админкоманды` — этот список.\n\n"
            "💡 *Обычные команды (доступны всем):*\n"
            "`!тр [текст]` — исправить раскладку\n"
            "`!должен @username сумма описание` — записать долг\n"
            "`!вернул @username сумма` — отметить возврат\n"
            "`!долги` — показать ваши долги\n"
            "`!звук ссылка` — скачать аудио из TikTok\n"
            "`!озвучь` — озвучить последний ответ\n"
            "`!ии текст` — обычный ИИ (без контекста)\n"
            "`!smart текст` — ИИ с поиском в интернете\n"
            "`!команды` — краткая справка\n\n"
            "⚠️ *Важно:* все настройки сохраняются отдельно для каждого чата."
        )
        await update.message.reply_text(admin_help_text, parse_mode='Markdown')

    # ---------- !ии ----------
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

    # ---------- !smart ----------
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
        except Exception as e:
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
        except Exception as e:
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
        debts_str = debts_module.get_debts_for_user(chat_id, user_id)
        await update.message.reply_text(debts_str, parse_mode=None)  # убрали Markdown

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
        pass

# ------------------------------------------------------------
# Автоскачивание видео
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

    # Сохраняем всех пользователей, кто пишет
    app.add_handler(MessageHandler(filters.ALL, save_user_handler), group=-1)

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