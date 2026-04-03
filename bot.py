import os
import re
import logging
import yt_dlp
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from db import init_db, add_debt, repay_debt, get_debts_for_user, save_chat_member, get_chat_members

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("No TELEGRAM_TOKEN in environment")

init_db()

# -------------------- TikTok download --------------------
def get_ffmpeg_path():
    import glob
    candidates = glob.glob('/nix/store/*ffmpeg*/bin/ffmpeg')
    if candidates:
        return candidates[0]
    return 'ffmpeg'

def download_tiktok(url: str):
    os.makedirs("downloads", exist_ok=True)
    cookies_file = "cookies.txt" if os.path.exists("cookies.txt") else None
    opts = {
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'cookiefile': cookies_file,
        'ffmpeg_location': get_ffmpeg_path(),
    }
    if '/photo/' in url:
        opts['format'] = 'best'
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                if os.path.exists(filename):
                    return [filename], 'photo'
                return None, None
        except Exception as e:
            logger.error(f"Photo download error: {e}")
            return None, None
    else:
        opts['format'] = 'bestvideo[height<=720][ext=mp4][filesize<45M]+bestaudio[ext=m4a]/best[height<=720][ext=mp4][filesize<45M]/best'
        opts['merge_output_format'] = 'mp4'
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                return [filename], 'video'
        except Exception as e:
            logger.error(f"Video download error: {e}")
            return None, None

def download_audio(url: str) -> str | None:
    os.makedirs("downloads", exist_ok=True)
    cookies_file = "cookies.txt" if os.path.exists("cookies.txt") else None
    opts = {
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'cookiefile': cookies_file,
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'ffmpeg_location': get_ffmpeg_path(),
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            base = os.path.splitext(ydl.prepare_filename(info))[0]
            return base + '.mp3'
    except Exception as e:
        logger.error(f"Audio download error: {e}")
        return None

# -------------------- Обработчик сообщений --------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()
    user_id = str(update.effective_user.id)
    user_name = update.effective_user.full_name or user_id
    username = update.effective_user.username or ""
    chat_id = str(update.effective_chat.id)

    # Сохраняем участника в базу
    save_chat_member(chat_id, user_id, username, user_name)

    # Команда @all
    if text.lower().startswith('@all'):
        members = get_chat_members(chat_id)
        if not members:
            await update.message.reply_text("Пока нет сохранённых участников. Напишите что-нибудь в чат, чтобы бот запомнил вас.")
            return
        mentions = []
        for uid, uname, full_name in members:
            # Не упоминаем самого отправителя
            if uid == user_id:
                continue
            if uname:
                mentions.append(f"@{uname}")
            else:
                mentions.append(full_name or uid)
        if not mentions:
            await update.message.reply_text("Нет других участников для упоминания.")
            return
        # Отправляем сообщение
        message = "Всем привет! " + " ".join(mentions)
        if len(message) > 4096:
            for i in range(0, len(mentions), 50):
                part = " ".join(mentions[i:i+50])
                await update.message.reply_text(f"Упоминания: {part}")
        else:
            await update.message.reply_text(message)
        return

    # Команда !звук
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

    # Система долгов (без восклицательного знака)
    lower_text = text.lower()
    if lower_text.startswith('должен'):
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

    if lower_text.startswith('вернул'):
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

    if lower_text.startswith('долги'):
        debts_str = get_debts_for_user(chat_id, user_id)
        await update.message.reply_text(debts_str)
        return

    # Скачивание TikTok
    url_match = re.search(r'(https?://\S+)', text)
    if not url_match:
        return
    url = url_match.group(0)
    if not re.search(r'(tiktok\.com|vm\.tiktok\.com)', url):
        return
    await update.message.reply_text("📥 Скачиваю...")
    files, content_type = download_tiktok(url)
    if not files:
        await update.message.reply_text("Не удалось скачать. Возможно, ссылка требует авторизации (нужны куки).")
        return
    if content_type == 'video':
        for f in files:
            if os.path.exists(f):
                with open(f, 'rb') as vid:
                    await update.message.reply_video(video=vid)
                os.remove(f)
    elif content_type == 'photo':
        media_group = []
        for f in files:
            if os.path.exists(f):
                media_group.append({'type': 'photo', 'media': open(f, 'rb')})
        if media_group:
            await update.message.reply_media_group(media_group)
            for item in media_group:
                item['media'].close()
                os.remove(item['media'].name)
        else:
            await update.message.reply_text("Не удалось отправить фото.")

# -------------------- Запуск --------------------
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Bot started")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
