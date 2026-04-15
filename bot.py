import os
import re
import logging
import random
import asyncio
import sqlite3
from datetime import datetime, date
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import yt_dlp
from telegram import Update, ChatMemberUpdated
from telegram.ext import Application, MessageHandler, filters, ContextTypes, ChatMemberHandler
from db import (
    init_db, add_debt, repay_debt, get_debts_for_user,
    save_chat_member, get_chat_members,
    set_daily_honor, get_daily_honors, is_honors_chosen_today, get_all_chats_with_members, DB_PATH
)
from keyboard import fix_keyboard

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("No TELEGRAM_TOKEN in environment")

init_db()

# -------------------- yt-dlp download --------------------
def get_ffmpeg_path():
    import glob
    candidates = glob.glob('/nix/store/*ffmpeg*/bin/ffmpeg')
    if candidates:
        return candidates[0]
    return 'ffmpeg'

def download_video(url: str) -> str | None:
    os.makedirs("downloads", exist_ok=True)
    opts = {
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'format': 'bestvideo[height<=720][ext=mp4][filesize<45M]+bestaudio[ext=m4a]/best[height<=720][ext=mp4][filesize<45M]/best',
        'merge_output_format': 'mp4',
        'ffmpeg_location': get_ffmpeg_path(),
    }
    if os.path.exists("cookies.txt"):
        opts['cookiefile'] = "cookies.txt"
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info)
    except Exception as e:
        logger.error(f"Video download error: {e}")
        return None

def download_audio(url: str) -> str | None:
    os.makedirs("downloads", exist_ok=True)
    opts = {
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'ffmpeg_location': get_ffmpeg_path(),
    }
    if os.path.exists("cookies.txt"):
        opts['cookiefile'] = "cookies.txt"
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            base = os.path.splitext(ydl.prepare_filename(info))[0]
            return base + '.mp3'
    except Exception as e:
        logger.error(f"Audio download error: {e}")
        return None

# -------------------- Обновление участников чатов --------------------
async def update_all_chat_members(app: Application):
    chats = get_all_chats_with_members()
    for chat_id in chats:
        try:
            members = []
            async for member in app.bot.get_chat_members(chat_id):
                if not member.user.is_bot:
                    members.append(member.user)
            for user in members:
                save_chat_member(chat_id, str(user.id), user.username or "", user.full_name or "")
            logger.info(f"Updated members for chat {chat_id}: {len(members)} users")
        except Exception as e:
            logger.warning(f"Cannot get members for chat {chat_id}: {e} (bot may not be admin)")

# -------------------- Ежедневные почести --------------------
HONOR_ROLES = ["huesos", "cherviviy", "pleshiviy", "smradniy"]
HONOR_EMOJI = {
    "huesos": "🍆",
    "cherviviy": "🐛",
    "pleshiviy": "🦲",
    "smradniy": "💨"
}
HONOR_NAMES = {
    "huesos": "хуесос",
    "cherviviy": "червивый",
    "pleshiviy": "плешивый",
    "smradniy": "смрадный"
}

async def assign_missing_roles(chat_id: str, context: ContextTypes.DEFAULT_TYPE):
    members = get_chat_members(chat_id)
    honors = get_daily_honors(chat_id)
    changed = False
    for user_id, username, full_name in members:
        if user_id not in honors:
            role = random.choice(HONOR_ROLES)
            set_daily_honor(chat_id, user_id, role)
            changed = True
    if changed:
        await send_honors_message(chat_id, context)

async def send_honors_message(chat_id: str, context: ContextTypes.DEFAULT_TYPE):
    honors = get_daily_honors(chat_id)
    members = get_chat_members(chat_id)
    msg_lines = []
    for user_id, username, full_name in members:
        role = honors.get(user_id)
        if role:
            mention = f"@{username}" if username else full_name
            emoji = HONOR_EMOJI.get(role, "❓")
            name_ru = HONOR_NAMES.get(role, role)
            msg_lines.append(f"{emoji} {mention} — {name_ru}")
    if msg_lines:
        msg = "🍆🐛🦲💨 Сегодняшние почести:\n" + "\n".join(msg_lines)
        await context.bot.send_message(chat_id=chat_id, text=msg)
    else:
        await context.bot.send_message(chat_id=chat_id, text="Не удалось определить почести.")

async def pick_daily_honors_for_chat(chat_id: str, context: ContextTypes.DEFAULT_TYPE):
    if is_honors_chosen_today(chat_id):
        await assign_missing_roles(chat_id, context)
        return
    members = get_chat_members(chat_id)
    if not members:
        logger.warning(f"No members in chat {chat_id}, cannot pick honors")
        return
    today = date.today().isoformat()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM daily_honors WHERE chat_id = ? AND chosen_date = ?", (chat_id, today))
    conn.commit()
    conn.close()
    for user_id, username, full_name in members:
        role = random.choice(HONOR_ROLES)
        set_daily_honor(chat_id, user_id, role)
    await send_honors_message(chat_id, context)

async def daily_honors_job(context: ContextTypes.DEFAULT_TYPE):
    chats = get_all_chats_with_members()
    for chat_id in chats:
        await pick_daily_honors_for_chat(chat_id, context)

async def run_initial_honors_selection(app: Application):
    chats = get_all_chats_with_members()
    for chat_id in chats:
        await pick_daily_honors_for_chat(chat_id, app)

async def track_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.chat_member
    if not result:
        return
    if result.new_chat_member.status == "member" and result.old_chat_member.status in ("left", "kicked"):
        chat_id = str(result.chat.id)
        user = result.new_chat_member.user
        if user.is_bot:
            return
        save_chat_member(chat_id, str(user.id), user.username or "", user.full_name or "")
        if is_honors_chosen_today(chat_id):
            honors = get_daily_honors(chat_id)
            if str(user.id) not in honors:
                role = random.choice(HONOR_ROLES)
                set_daily_honor(chat_id, str(user.id), role)
                await send_honors_message(chat_id, context)

# -------------------- Обработчик сообщений --------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()
    user_id = str(update.effective_user.id)
    user_name = update.effective_user.full_name or user_id
    username = update.effective_user.username or ""
    chat_id = str(update.effective_chat.id)

    save_chat_member(chat_id, user_id, username, user_name)

    # Почести (если новый день или недостаёт ролей)
    if not is_honors_chosen_today(chat_id):
        await pick_daily_honors_for_chat(chat_id, context)
    else:
        await assign_missing_roles(chat_id, context)

    # Случайный ответ (1% шанс)
    if random.random() < 0.01:
        if not text.startswith('!') and update.effective_user.id != context.bot.id:
            await update.message.reply_text("Завтра в 3")
            return

    # Ответ на слово "когда" (50% шанс)
    if re.search(r'\bкогда\b', text, re.IGNORECASE):
        if random.random() < 0.5:
            if not text.startswith('!') and update.effective_user.id != context.bot.id:
                await update.message.reply_text("Завтра в 3")
                return

    # ---------- !команды ----------
    if text == "!команды":
        help_text = (
            "📋 *Список команд:*\n\n"
            "🎵 `!звук ссылка` – скачать аудио из TikTok\n"
            "📥 `ссылка на TikTok` – скачать видео\n"
            "💰 `!должен @username сумма описание` – записать долг (вы должны)\n"
            "💸 `!вернул @username сумма [описание]` – отметить возврат долга\n"
            "📊 `!долги` – показать ваши долги (кому должны и кто вам)\n"
            "📊 `!долги @username` – показать долги указанного пользователя (кому он должен)\n"
            "🔁 `!нз текст` – исправить сбившуюся раскладку\n"
            "👥 `@all` – упомянуть всех участников чата\n"
            "🏆 `!почести` – показать сегодняшние почести для всех участников\n\n"
            "ℹ️ Бот автоматически скачивает видео по ссылке на TikTok."
        )
        await update.message.reply_text(help_text, parse_mode='Markdown')
        return

    # ---------- !почести ----------
    if text == "!почести":
        honors = get_daily_honors(chat_id)
        if not honors:
            await update.message.reply_text("Сегодня ещё никто не выбран. Подождите до полуночи или перезапустите бота.")
        else:
            members = get_chat_members(chat_id)
            msg_lines = []
            for uid, uname, fname in members:
                role = honors.get(uid)
                if role:
                    mention = f"@{uname}" if uname else fname
                    emoji = HONOR_EMOJI.get(role, "❓")
                    name_ru = HONOR_NAMES.get(role, role)
                    msg_lines.append(f"{emoji} {mention} — {name_ru}")
            if msg_lines:
                msg = "🍆🐛🦲💨 Текущие почести:\n" + "\n".join(msg_lines)
                await update.message.reply_text(msg)
            else:
                await update.message.reply_text("Не удалось определить почести.")
        return

    # ---------- !нз ----------
    if text.startswith("!нз"):
        args = text[3:].strip()
        if not args:
            await update.message.reply_text("Напиши: !нз текст (или ответь на сообщение)")
            return
        fixed = fix_keyboard(args)
        await update.message.reply_text(f"🔁 Исправлено: {fixed}")
        return

    # ---------- @all ----------
    if text.lower().startswith('@all'):
        members = get_chat_members(chat_id)
        if not members:
            await update.message.reply_text("Пока нет сохранённых участников. Напишите что-нибудь в чат, чтобы бот запомнил вас.")
            return
        mentions = []
        for uid, uname, fname in members:
            if uid == user_id:
                continue
            if uname:
                mentions.append(f"@{uname}")
            else:
                mentions.append(fname or uid)
        if not mentions:
            await update.message.reply_text("Нет других участников для упоминания.")
            return
        message = "Всем привет! " + " ".join(mentions)
        if len(message) > 4096:
            for i in range(0, len(mentions), 50):
                part = " ".join(mentions[i:i+50])
                await update.message.reply_text(f"Упоминания: {part}")
        else:
            await update.message.reply_text(message)
        return

    # ---------- !звук ----------
    if text.startswith('!звук'):
        url_match = re.search(r'(https?://\S+)', text)
        if not url_match:
            return
        url = url_match.group(0)
        if not re.search(r'(tiktok\.com|vm\.tiktok\.com)', url):
            return
        await update.message.reply_text("🎵 Скачиваю аудио...")
        filepath = download_audio(url)
        if filepath and os.path.exists(filepath):
            with open(filepath, 'rb') as f:
                await update.message.reply_audio(audio=f, title="audio.mp3")
            os.remove(filepath)
        else:
            await update.message.reply_text("Не удалось скачать аудио.")
        return

    # ---------- Долги (новые команды) ----------
    if text.startswith('!должен'):
        parts = text.split(maxsplit=3)
        if len(parts) < 3:
            return
        mention = parts[1]
        if not mention.startswith('@'):
            return
        try:
            amount = float(parts[2])
        except:
            return
        description = parts[3] if len(parts) > 3 else ""
        creditor_username = mention[1:]
        creditor_id = creditor_username
        creditor_name = creditor_username
        try:
            member = await context.bot.get_chat_member(chat_id, mention)
            creditor_id = str(member.user.id)
            creditor_name = member.user.full_name
        except:
            pass
        add_debt(chat_id, creditor_id, creditor_name, user_id, user_name, amount, description)
        await update.message.reply_text(f"✅ Записал: вы должны {creditor_name} {amount} руб. ({description})")
        return

    if text.startswith('!вернул'):
        parts = text.split(maxsplit=3)
        if len(parts) < 3:
            return
        mention = parts[1]
        if not mention.startswith('@'):
            return
        try:
            amount = float(parts[2])
        except:
            return
        description = parts[3] if len(parts) > 3 else "Без описания"
        creditor_username = mention[1:]
        creditor_id = creditor_username
        try:
            member = await context.bot.get_chat_member(chat_id, mention)
            creditor_id = str(member.user.id)
        except:
            pass
        success = repay_debt(chat_id, creditor_id, user_id, amount, description)
        if success:
            await update.message.reply_text(f"✅ Отметил возврат {amount} руб. для {creditor_username} ({description})")
        else:
            await update.message.reply_text("❌ Не найден активный долг с такой суммой или вы не должны этому пользователю.")
        return

    if text.startswith('!долги'):
        parts = text.split(maxsplit=1)
        if len(parts) == 2 and parts[1].startswith('@'):
            # !долги @username – долги указанного пользователя (где он должник)
            mention = parts[1]
            target_username = mention[1:]
            target_user_id = None
            target_user_name = target_username
            try:
                member = await context.bot.get_chat_member(chat_id, mention)
                target_user_id = str(member.user.id)
                target_user_name = member.user.full_name
            except:
                pass
            uid = target_user_id if target_user_id else target_username
            data = get_debts_for_user(chat_id, uid, mode="user")
            debts = data.get("debts", [])
            if not debts:
                await update.message.reply_text(f"У {target_user_name} нет активных долгов.")
            else:
                lines = [f"📋 Долги пользователя {target_user_name}:"]
                total = 0
                for creditor, amt, desc in debts:
                    lines.append(f"• {creditor}: {amt:.2f} руб. ({desc})")
                    total += amt
                lines.append(f"   Итого: {total:.2f} руб.")
                await update.message.reply_text("\n".join(lines))
        else:
            # !долги – свои долги (я должен + мне должны)
            data = get_debts_for_user(chat_id, user_id, mode="self")
            i_owe = data.get("i_owe", [])
            owe_me = data.get("owe_me", [])
            if not i_owe and not owe_me:
                await update.message.reply_text("Нет активных долгов.")
                return
            lines = []
            if i_owe:
                lines.append("📌 Вы должны:")
                total_i = 0
                for creditor, amt, desc in i_owe:
                    lines.append(f"• {creditor}: {amt:.2f} руб. ({desc})")
                    total_i += amt
                lines.append(f"   Итого: {total_i:.2f} руб.")
            if owe_me:
                lines.append("📌 Вам должны:")
                total_m = 0
                for debtor, amt, desc in owe_me:
                    lines.append(f"• {debtor}: {amt:.2f} руб. ({desc})")
                    total_m += amt
                lines.append(f"   Итого: {total_m:.2f} руб.")
            await update.message.reply_text("\n".join(lines))
        return

    # ---------- Скачивание видео по ссылке (только TikTok) ----------
    url_match = re.search(r'(https?://\S+)', text)
    if not url_match:
        return
    url = url_match.group(0)
    if not re.search(r'(tiktok\.com|vm\.tiktok\.com)', url):
        return
    await update.message.reply_text("📥 Скачиваю видео...")
    filepath = download_video(url)
    if filepath and os.path.exists(filepath):
        with open(filepath, 'rb') as f:
            await update.message.reply_video(video=f)
        os.remove(filepath)
    else:
        await update.message.reply_text("Не удалось скачать видео. Проверьте ссылку.")

# -------------------- Запуск --------------------
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(ChatMemberHandler(track_new_member, ChatMemberHandler.CHAT_MEMBER))

    loop = asyncio.get_event_loop()
    loop.create_task(update_all_chat_members(app))

    scheduler = AsyncIOScheduler(timezone=ZoneInfo("Asia/Yekaterinburg"))
    scheduler.add_job(daily_honors_job, 'cron', hour=0, minute=0, args=[app])
    scheduler.start()

    loop.create_task(run_initial_honors_selection(app))

    logger.info("Bot started")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()