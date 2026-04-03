import os
import re
import logging
import requests
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from db import init_db, add_debt, repay_debt, get_debts_for_user, save_chat_member, get_chat_members
from keyboard import fix_keyboard

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("No TELEGRAM_TOKEN in environment")

COBALT_URL = os.environ.get("COBALT_URL", "https://cherry-cobalt.up.railway.app")
if not COBALT_URL:
    raise ValueError("No COBALT_URL in environment")

init_db()

# -------------------- Cobalt download --------------------
def download_with_cobalt(url: str, is_audio: bool = False):
    """
    Скачивает видео/аудио через Cobalt API.
    Возвращает (filepath, file_type) или (None, None).
    file_type: 'video', 'audio', 'photo', 'document'
    """
    try:
        # Формируем запрос к Cobalt
        payload = {
            "url": url,
            "downloadMode": "audio" if is_audio else "auto",
            "videoQuality": "720" if not is_audio else None,
            "audioFormat": "mp3" if is_audio else None,
        }
        # Убираем None значения
        payload = {k: v for k, v in payload.items() if v is not None}
        response = requests.post(f"{COBALT_URL}/api/json", json=payload, timeout=60)
        if response.status_code != 200:
            logger.error(f"Cobalt error: {response.status_code} {response.text}")
            return None, None
        data = response.json()
        if data.get("status") != "success":
            logger.error(f"Cobalt status error: {data}")
            return None, None
        file_url = data.get("url")
        if not file_url:
            return None, None

        # Скачиваем файл по прямой ссылке
        file_response = requests.get(file_url, stream=True, timeout=60)
        if file_response.status_code != 200:
            return None, None

        # Определяем тип контента по заголовку или расширению
        content_type = file_response.headers.get("content-type", "")
        if "video" in content_type:
            ext = "mp4"
            ftype = "video"
        elif "audio" in content_type:
            ext = "mp3"
            ftype = "audio"
        elif "image" in content_type:
            ext = "jpg"
            ftype = "photo"
        else:
            # Пробуем по расширению из URL
            if ".mp4" in file_url:
                ext = "mp4"
                ftype = "video"
            elif ".mp3" in file_url:
                ext = "mp3"
                ftype = "audio"
            else:
                ext = "bin"
                ftype = "document"

        os.makedirs("downloads", exist_ok=True)
        filename = f"downloads/cobalt_{abs(hash(url))}.{ext}"
        with open(filename, "wb") as f:
            for chunk in file_response.iter_content(chunk_size=8192):
                f.write(chunk)
        return filename, ftype
    except Exception as e:
        logger.error(f"Cobalt download error: {e}")
        return None, None

# -------------------- Обработчик сообщений --------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()
    user_id = str(update.effective_user.id)
    user_name = update.effective_user.full_name or user_id
    username = update.effective_user.username or ""
    chat_id = str(update.effective_chat.id)

    # Сохраняем участника в базу (для @all)
    save_chat_member(chat_id, user_id, username, user_name)

    # ---------- !команды ----------
    if text == "!команды":
        help_text = (
            "📋 *Список команд:*\n\n"
            "🎵 `!звук ссылка` – скачать аудио из TikTok, YouTube, VK\n"
            "📥 `ссылка на TikTok/YouTube/VK` – скачать видео/фото\n"
            "💰 `!должен @username сумма описание` – записать долг (вы должны)\n"
            "💸 `!вернул @username сумма` – отметить возврат долга\n"
            "📊 `!долги` – показать ваши долги\n"
            "🔁 `!нз текст` – исправить сбившуюся раскладку (ниггер заражен)\n"
            "👥 `@all` – упомянуть всех участников чата\n\n"
            "ℹ️ Бот автоматически скачивает контент по ссылке."
        )
        await update.message.reply_text(help_text, parse_mode='Markdown')
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
        message = "all! " + " ".join(mentions)
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
        # Не проверяем платформу – Cobalt сам разберётся
        await update.message.reply_text("🎵 Скачиваю аудио...")
        filepath, ftype = download_with_cobalt(url, is_audio=True)
        if filepath and os.path.exists(filepath):
            with open(filepath, 'rb') as f:
                await update.message.reply_audio(audio=f, title="audio.mp3")
            os.remove(filepath)
        else:
            await update.message.reply_text("Не удалось скачать аудио.")
        return

    # ---------- Долги (с !) ----------
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
        debts_str = get_debts_for_user(chat_id, user_id)
        await update.message.reply_text(debts_str)
        return

    # ---------- Скачивание по ссылке (автоопределение) ----------
    url_match = re.search(r'(https?://\S+)', text)
    if not url_match:
        return
    url = url_match.group(0)
    # Не фильтруем платформы – Cobalt сам определит
    await update.message.reply_text("📥 Скачиваю...")
    filepath, ftype = download_with_cobalt(url, is_audio=False)
    if not filepath or not os.path.exists(filepath):
        await update.message.reply_text("Не удалось скачать. Возможно, ссылка не поддерживается.")
        return

    # Отправляем в зависимости от типа
    if ftype == "video":
        with open(filepath, 'rb') as f:
            await update.message.reply_video(video=f)
    elif ftype == "audio":
        with open(filepath, 'rb') as f:
            await update.message.reply_audio(audio=f, title="audio.mp3")
    elif ftype == "photo":
        with open(filepath, 'rb') as f:
            await update.message.reply_photo(photo=f)
    else:
        with open(filepath, 'rb') as f:
            await update.message.reply_document(document=f)
    os.remove(filepath)

# -------------------- Запуск --------------------
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Bot started")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
