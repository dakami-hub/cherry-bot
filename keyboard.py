import re
import os
import logging
from groq import Groq

LAT_TO_RUS = {
    'q': 'й', 'w': 'ц', 'e': 'у', 'r': 'к', 't': 'е', 'y': 'н', 'u': 'г', 'i': 'ш', 'o': 'щ', 'p': 'з',
    '[': 'х', ']': 'ъ', 'a': 'ф', 's': 'ы', 'd': 'в', 'f': 'а', 'g': 'п', 'h': 'р', 'j': 'о', 'k': 'л',
    'l': 'д', ';': 'ж', "'": 'э', 'z': 'я', 'x': 'ч', 'c': 'с', 'v': 'м', 'b': 'и', 'n': 'т', 'm': 'ь',
    ',': 'б', '.': 'ю', '/': '.', '`': 'ё', '~': 'Ё', '!': '!', '@': '"', '#': '№', '$': ';', '%': '%',
    '^': ':', '&': '?', '*': '*', '(': '(', ')': ')', '-': '-', '_': '_', '+': '+', '=': '=', '\\': '\\'
}

_lang_cache = {}

def _is_likely_english(text: str) -> bool:
    clean = re.sub(r'[^a-zA-Z\s]', '', text)
    words = clean.split()
    if len(words) < 3:
        return False
    vowels = set('aeiouy')
    for w in words:
        if not any(c in vowels for c in w.lower()):
            return False
    return True

async def should_fix(text: str) -> bool:
    if not text:
        return False
    for c in text:
        if 'а' <= c.lower() <= 'я' or c in 'ёЁ':
            return False
    if re.match(r'^https?://', text) or re.search(r'\.(com|ru|net|org|tv|tiktok|youtube|vk|xyz|club|site)\b', text):
        return False
    if len(text) < 10:
        return True
    if text in _lang_cache:
        return _lang_cache[text] == 'ru'
    try:
        client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Определи, является ли следующий текст английским (en) или русским текстом, набранным в неправильной раскладке (ru). Ответь только одним словом: en или ru."},
                {"role": "user", "content": text}
            ],
            temperature=0,
            max_tokens=10
        )
        result = response.choices[0].message.content.strip().lower()
        if result == 'ru':
            _lang_cache[text] = 'ru'
            return True
        else:
            _lang_cache[text] = 'en'
            return False
    except Exception as e:
        logging.error(f"Groq language check error: {e}")
        result = _is_likely_english(text)
        _lang_cache[text] = 'en' if result else 'ru'
        return not result

def fix_keyboard(text: str) -> str:
    result = []
    for ch in text:
        lower = ch.lower()
        if lower in LAT_TO_RUS:
            new = LAT_TO_RUS[lower]
            if ch.isupper():
                new = new.upper()
            result.append(new)
        else:
            result.append(ch)
    return ''.join(result)