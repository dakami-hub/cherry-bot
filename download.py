import yt_dlp
import os
import logging

COOKIES_FILE = "cookies.txt"

def download_video(url: str) -> str | None:
    """Скачивает видео в mp4 (до 50МБ, 720p) и возвращает путь."""
    os.makedirs("downloads", exist_ok=True)
    opts = {
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'quiet': True,
        'noplaylist': True,
        'cookiefile': COOKIES_FILE,
        'format': 'bestvideo[height<=720][ext=mp4][filesize<45M]+bestaudio[ext=m4a]/best[height<=720][ext=mp4][filesize<45M]/best',
        'merge_output_format': 'mp4',
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info)
    except Exception as e:
        logging.error(f"Download error: {e}")
        return None

def download_audio(url: str) -> str | None:
    """Скачивает аудио в mp3 и возвращает путь."""
    os.makedirs("downloads", exist_ok=True)
    opts = {
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'quiet': True,
        'noplaylist': True,
        'cookiefile': COOKIES_FILE,
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            base = os.path.splitext(ydl.prepare_filename(info))[0]
            return base + '.mp3'
    except Exception as e:
        logging.error(f"Audio download error: {e}")
        return None
