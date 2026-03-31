import yt_dlp
import os
import logging
import shutil
import glob

COOKIES_FILE = "cookies.txt"

def get_ffmpeg_path():
    """Ищет ffmpeg в системе."""
    # Поиск в nix store (для Railway Nixpack)
    ffmpeg_candidates = glob.glob('/nix/store/*ffmpeg*/bin/ffmpeg')
    if ffmpeg_candidates:
        logging.info(f"Found ffmpeg via glob: {ffmpeg_candidates[0]}")
        return ffmpeg_candidates[0]
    # shutil.which
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path:
        logging.info(f"Found ffmpeg via which: {ffmpeg_path}")
        return ffmpeg_path
    # Фиксированные пути
    possible_paths = [
        '/usr/bin/ffmpeg',
        '/usr/local/bin/ffmpeg',
        '/nix/var/nix/profiles/default/bin/ffmpeg',
    ]
    for path in possible_paths:
        if os.path.exists(path):
            logging.info(f"Found ffmpeg at {path}")
            return path
    logging.error("ffmpeg not found!")
    return None

def _get_common_opts():
    """Базовые опции для yt-dlp."""
    opts = {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'cookiefile': COOKIES_FILE,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
    }
    ffmpeg_path = get_ffmpeg_path()
    if ffmpeg_path:
        opts['ffmpeg_location'] = ffmpeg_path
    return opts

def download_video(url: str) -> str | None:
    """Скачивает видео в mp4 (до 50МБ, 720p)."""
    os.makedirs("downloads", exist_ok=True)
    opts = _get_common_opts()
    opts.update({
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'format': 'bestvideo[height<=720][ext=mp4][filesize<45M]+bestaudio[ext=m4a]/best[height<=720][ext=mp4][filesize<45M]/best',
        'merge_output_format': 'mp4',
    })
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info)
    except Exception as e:
        logging.error(f"Video download error: {e}")
        return None

def download_audio(url: str) -> str | None:
    """Скачивает аудио в mp3."""
    os.makedirs("downloads", exist_ok=True)
    opts = _get_common_opts()
    opts.update({
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    })
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            base = os.path.splitext(ydl.prepare_filename(info))[0]
            return base + '.mp3'
    except Exception as e:
        logging.error(f"Audio download error: {e}")
        return None