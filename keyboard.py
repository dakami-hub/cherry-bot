import re

LAT_TO_RUS = {
    'q': 'й', 'w': 'ц', 'e': 'у', 'r': 'к', 't': 'е', 'y': 'н', 'u': 'г', 'i': 'ш', 'o': 'щ', 'p': 'з',
    '[': 'х', ']': 'ъ', 'a': 'ф', 's': 'ы', 'd': 'в', 'f': 'а', 'g': 'п', 'h': 'р', 'j': 'о', 'k': 'л',
    'l': 'д', ';': 'ж', "'": 'э', 'z': 'я', 'x': 'ч', 'c': 'с', 'v': 'м', 'b': 'и', 'n': 'т', 'm': 'ь',
    ',': 'б', '.': 'ю', '/': '.', '`': 'ё', '~': 'Ё', '!': '!', '@': '"', '#': '№', '$': ';', '%': '%',
    '^': ':', '&': '?', '*': '*', '(': '(', ')': ')', '-': '-', '_': '_', '+': '+', '=': '=', '\\': '\\'
}

def is_likely_mistyped(text: str) -> bool:
    """Возвращает True, только если текст похож на сбитую раскладку (нет русских букв, не ссылка)."""
    if not text:
        return False
    # Если есть хоть одна русская буква — не трогаем
    for c in text:
        if 'а' <= c.lower() <= 'я' or c in 'ёЁ':
            return False
    # Не обрабатываем ссылки
    if re.match(r'^https?://', text) or re.search(r'\.(com|ru|net|org|tv|tiktok|youtube|vk|xyz|club|site)\b', text):
        return False
    # Если нет русских букв, но есть латиница — считаем сбитой
    for c in text:
        if 'a' <= c.lower() <= 'z':
            return True
    return False

def fix_keyboard(text: str) -> str:
    """Переводит текст из латиницы в русскую раскладку, если нужно."""
    if not is_likely_mistyped(text):
        return text
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