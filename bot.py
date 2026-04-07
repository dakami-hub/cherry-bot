import os
import re
import logging
import random
import asyncio
from datetime import datetime, date
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import yt_dlp
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from db import (
    init_db, add_debt, repay_debt, get_debts_for_user,
    save_chat_member, get_chat_members,
    set_daily_honor, get_daily_honors, is_honors_chosen_today, get_all_chats_with_members
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

# -------------------- Ежедневные почести --------------------
async def pick_daily_honors_for_chat(chat_id: str, context: ContextTypes.DEFAULT_TYPE):
    members = get_chat_members(chat_id)
    if len(members) < 4:
        msg = f"⚠️ В чате недостаточно участников для выбора 4 разных почестей (нужно минимум 4). Сейчас в базе {len(members)} человек. Новые участники добавятся, когда напишут сообщение."
        await context.bot.send_message(chat_id=chat_id, text=msg)
        logger.warning(f"Not enough members in chat {chat_id}: {len(members)} < 4")
        return
    shuffled = members.copy()
    random.shuffle(shuffled)
    roles = {
        "huesos": shuffled[0],
        "cherviviy": shuffled[1],
        "pleshiviy": shuffled[2],
        "smradniy": shuffled[3]
    }
    for role, (uid, uname, fname) in roles.items():
        display_name = uname if uname else fname
        set_daily_honor(chat_id, role, uid, display_name)
    msg = (
        f"🍆 Сегодня хуесос — @{roles['huesos'][1] if roles['huesos'][1] else roles['huesos'][2]}\n"
        f"🐛 Сегодня червивый — @{roles['cherviviy'][1] if roles['cherviviy'][1] else roles['cherviviy'][2]}\n"
        f"🦲 Сегодня плешивый — @{roles['pleshiviy'][1] if roles['pleshiviy'][1] else roles['pleshiviy'][2]}\n"
        f"💨 Сегодня смрадный — @{roles['smradniy'][1] if roles['smradniy'][1] else roles['smradniy'][2]}"
    )
    await context.bot.send_message(chat_id=chat_id, text=msg)

async def daily_honors_job(context: ContextTypes.DEFAULT_TYPE):
    chats = get_all_chats_with_members()
    for chat_id in chats:
        if not is_honors_chosen_today(chat_id):
            await pick_daily_honors_for_chat(chat_id, context)

async def run_initial_honors_selection(app: Application):
    chats = get_all_chats_with_members()
    for chat_id in chats:
        if not is_honors_chosen_today(chat_id):
            await pick_daily_honors_for_chat(chat_id, app)

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

    # ---------- Проверка и обновление почестей, если новый день ----------
    if not is_honors_chosen_today(chat_id):
        await pick_daily_honors_for_chat(chat_id, context)

    # ---------- Случайный ответ (5% шанс) ----------
    if random.random() < 0.05:
        if not text.startswith('!') and update.effective_user.id != context.bot.id:
            await update.message.reply_text("Завтра в 3")
            return

    # ---------- Ответ на слово "когда" с шансом 50% ----------
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
            "💸 `!вернул @username сумма` – отметить возврат долга\n"
            "📊 `!долги` – показать ваши долги\n"
            "📊 `!долги @username` – показать долги другого пользователя\n"
            "🔁 `!нз текст` – исправить сбившуюся раскладку\n"
            "👥 `@all` – упомянуть всех участников чата\n"
            "🏆 `!почести` – показать сегодняшних хуесоса, червивого, плешивого и смрадного\n\n"
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
            huesos_name = honors.get('huesos', ('', '?'))[1]
            cherviviy_name = honors.get('cherviviy', ('', '?'))[1]
            pleshiviy_name = honors.get('pleshiviy', ('', '?'))[1]
            smradniy_name = honors.get('smradniy', ('', '?'))[1]
            msg = (
                f"🍆 Хуесос: @{huesos_name}\n"
                f"🐛 Червивый: @{cherviviy_name}\n"
                f"🦲 Плешивый: @{pleshiviy_name}\n"
                f"💨 Смрадный: @{smradniy_name}"
            )
            await update.message.reply_text(msg)
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

    # ---------- Долги ----------
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
        parts = text.split(maxsplit=2)
        if len(parts) < 2:
            return
        mention = parts[1]
        if not mention.startswith('@'):
            return
        try:
            amount = float(parts[2])
        except:
            return
        creditor_username = mention[1:]
        creditor_id = creditor_username
        try:
            member = await context.bot.get_chat_member(chat_id, mention)
            creditor_id = str(member.user.id)
        except:
            pass
        success = repay_debt(chat_id, creditor_id, user_id, amount)
        if success:
            await update.message.reply_text(f"✅ Отметил возврат {amount} руб.")
        else:
            await update.message.reply_text("❌ Не найден активный долг с такой суммой.")
        return

    if text.startswith('!долги'):
        parts = text.split(maxsplit=1)
        if len(parts) == 2 and parts[1].startswith('@'):
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
            debts_str = get_debts_for_user(chat_id, target_user_id if target_user_id else target_username)
            await update.message.reply_text(f"📋 Долги пользователя {target_user_name}:\n{debts_str}")
        else:
            debts_str = get_debts_for_user(chat_id, user_id)
            await update.message.reply_text(debts_str)
        return

    # ---------- Скачивание видео по ссылке ----------
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

    scheduler = AsyncIOScheduler(timezone=ZoneInfo("Asia/Yekaterinburg"))
    scheduler.add_job(daily_honors_job, 'cron', hour=0, minute=0, args=[app])
    scheduler.start()

    loop = asyncio.get_event_loop()
    loop.create_task(run_initial_honors_selection(app))

    logger.info("Bot started")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()