import yt_dlp
import os
import logging
import shutil
import glob

COOKIES_FILE = "cookies.txt"

def get_ffmpeg_path():
    # 1. Поиск в nix store
    ffmpeg_candidates = glob.glob('/nix/store/*ffmpeg*/bin/ffmpeg')
    if ffmpeg_candidates:
        logging.info(f"Found ffmpeg via glob: {ffmpeg_candidates[0]}")
        return ffmpeg_candidates[0]
    # 2. shutil.which
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path:
        logging.info(f"Found ffmpeg via which: {ffmpeg_path}")
        return ffmpeg_path
    # 3. Фиксированные пути
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

def download_video(url: str) -> str | None:
    os.makedirs("downloads", exist_ok=True)
    opts = {
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'quiet': True,
        'noplaylist': True,
        'cookiefile': COOKIES_FILE,
        'format': 'bestvideo[height<=720][ext=mp4][filesize<45M]+bestaudio[ext=m4a]/best[height<=720][ext=mp4][filesize<45M]/best',
        'merge_output_format': 'mp4',
    }
    ffmpeg_path = get_ffmpeg_path()
    if ffmpeg_path:
        opts['ffmpeg_location'] = ffmpeg_path
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info)
    except Exception as e:
        logging.error(f"Download error: {e}")
        return None

def download_audio(url: str) -> str | None:
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
    ffmpeg_path = get_ffmpeg_path()
    if ffmpeg_path:
        opts['ffmpeg_location'] = ffmpeg_path
    else:
        logging.error("Cannot extract audio: ffmpeg missing")
        return None
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            base = os.path.splitext(ydl.prepare_filename(info))[0]
            return base + '.mp3'
    except Exception as e:
        logging.error(f"Audio download error: {e}")
        return None