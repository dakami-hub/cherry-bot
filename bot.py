import os
import re
import logging
import yt_dlp
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("No TELEGRAM_TOKEN in environment")

# Путь к ffmpeg
def get_ffmpeg_path():
    import glob
    candidates = glob.glob('/nix/store/*ffmpeg*/bin/ffmpeg')
    if candidates:
        return candidates[0]
    return 'ffmpeg'

def download_tiktok(url: str):
    """Универсальная функция для скачивания. Возвращает список файлов и тип контента."""
    os.makedirs("downloads", exist_ok=True)
    # Опции для получения информации, но без скачивания
    info_opts = {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'extract_flat': False,
        'skip_download': True,
        'force_generic_extractor': False,
    }
    try:
        with yt_dlp.YoutubeDL(info_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Проверяем, является ли пост фото-слайдшоу
            # У yt-dlp нет прямого индикатора, но можно проверить по форматам
            is_photo = False
            formats = info.get('formats', [])
            if len(formats) == 1 and formats[0].get('vcodec') == 'none':
                is_photo = True
            
            if is_photo:
                # Для фото: ищем ссылки на изображения
                # В info['entries'] могут быть отдельные фото или в 'thumbnails'
                # Упрощенный вариант: скачиваем первый формат как есть
                # В yt-dlp 2024.12.03+ фото скачиваются как отдельные файлы
                # Используем --write-all-thumbnails для карусели
                opts = {
                    'outtmpl': 'downloads/%(id)s_%(title)s_%(counter)d.%(ext)s',
                    'quiet': True,
                    'no_warnings': True,
                    'noplaylist': True,
                    'write_all_thumbnails': True,
                    'skip_download': False,
                }
                with yt_dlp.YoutubeDL(opts) as ydl:
                    # yt-dlp сам определит, что это фото, и скачает все изображения
                    result = ydl.download([url])
                # После скачивания нужно вернуть список файлов
                files = [f for f in os.listdir('downloads') if os.path.isfile(os.path.join('downloads', f))]
                return files, 'photo'
            else:
                # Для видео
                opts = {
                    'outtmpl': 'downloads/%(id)s.%(ext)s',
                    'quiet': True,
                    'no_warnings': True,
                    'noplaylist': True,
                    'format': 'bestvideo[height<=720][ext=mp4][filesize<45M]+bestaudio[ext=m4a]/best[height<=720][ext=mp4][filesize<45M]/best',
                    'merge_output_format': 'mp4',
                    'ffmpeg_location': get_ffmpeg_path(),
                }
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])
                    info = ydl.extract_info(url, download=False)
                    filename = ydl.prepare_filename(info)
                    return [filename], 'video'
    except Exception as e:
        logger.error(f"TikTok download error: {e}")
        return None, None

def download_audio(url: str) -> str | None:
    """Скачивает аудио в mp3."""
    os.makedirs("downloads", exist_ok=True)
    opts = {
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
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

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    url_match = re.search(r'(https?://\S+)', text)
    if not url_match:
        await update.message.reply_text("Отправьте ссылку на TikTok или используйте команду !звук ссылка")
        return
    url = url_match.group(0)

    # Проверяем, что ссылка действительно на TikTok
    if not re.search(r'(tiktok\.com|vm\.tiktok\.com)', url):
        await update.message.reply_text("Пожалуйста, отправьте ссылку на TikTok (tiktok.com или vm.tiktok.com)")
        return

    # Команда !звук
    if text.startswith('!звук'):
        await update.message.reply_text("🎵 Скачиваю аудио...")
        filepath = download_audio(url)
        if filepath and os.path.exists(filepath):
            with open(filepath, 'rb') as f:
                await update.message.reply_audio(audio=f, title="audio.mp3")
            os.remove(filepath)
        else:
            await update.message.reply_text("Не удалось скачать аудио. Проверьте ссылку.")
        return

    # Основная логика для видео/фото
    await update.message.reply_text("📥 Обрабатываю ссылку...")
    files, content_type = download_tiktok(url)
    if not files:
        await update.message.reply_text("Не удалось скачать контент. Проверьте ссылку.")
        return

    if content_type == 'video':
        # Отправляем видео
        for f in files:
            if os.path.exists(f):
                with open(f, 'rb') as video_file:
                    await update.message.reply_video(video=video_file, caption="Вот ваше видео")
                os.remove(f)
    elif content_type == 'photo':
        # Отправляем все фотографии как медиа-группу (альбом)
        media_group = []
        for f in files:
            if os.path.exists(f):
                media_group.append({'type': 'photo', 'media': open(f, 'rb')})
        if media_group:
            await update.message.reply_media_group(media_group)
            # Закрываем и удаляем файлы после отправки
            for item in media_group:
                item['media'].close()
                os.remove(item['media'].name)
        else:
            await update.message.reply_text("Не удалось найти фотографии для отправки.")
    else:
        await update.message.reply_text("Неизвестный тип контента.")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("TikTok Downloader Bot started")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()