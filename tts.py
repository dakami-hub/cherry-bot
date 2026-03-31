import os
import logging
from gtts import gTTS

async def text_to_voice(text: str, filename: str) -> None:
    try:
        tts = gTTS(text=text, lang='ru')
        tts.save(filename)
    except Exception as e:
        logging.error(f"gTTS error: {e}")
        raise