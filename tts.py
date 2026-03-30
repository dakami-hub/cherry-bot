import edge_tts
import os
import asyncio
import logging

VOICE = "ru-RU-SvetlanaNeural"

async def text_to_voice(text: str, filename: str) -> None:
    """Сохраняет голос в файл."""
    communicate = edge_tts.Communicate(text, VOICE)
    await communicate.save(filename)
