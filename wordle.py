import random
import json
from db import get_wordle_session, save_wordle_session, delete_wordle_session

# Загрузка словаря из файла
def load_words():
    try:
        with open('words.txt', 'r', encoding='utf-8') as f:
            words = [line.strip().lower() for line in f if len(line.strip()) == 5]
        return words
    except:
        # Запасной список, если файл не найден
        return ['абзац', 'абрек', 'абрис', 'абхаз', 'абцуг', 'аваль', 'автол', 'автор', 'агитп', 'агора', 'адапт', 'адвок', 'аддон', 'адено', 'адепт', 'адрес', 'адрон', 'ажгон', 'азарт', 'азеот', 'азиат', 'азот', 'аист', 'айва', 'айран', 'айсор', 'акбар', 'аккор', 'акме', 'акро', 'аксон', 'актив', 'актор', 'акула', 'акцент', 'алба', 'алгол', 'алеут', 'алиби', 'алкаш', 'алкил', 'аллея', 'алмаз', 'алтей', 'алтын', 'алфит', 'алхим', 'алый', 'альт', 'альфа']

WORD_LIST = load_words()
WORD_LEN = 5
MAX_GUESSES = 6

def pick_word():
    return random.choice(WORD_LIST)

def check_guess(guess, target):
    """Возвращает список цветов для каждой буквы."""
    target_chars = list(target)
    guess_chars = list(guess)
    result = ['gray'] * WORD_LEN

    # Зелёные
    for i in range(WORD_LEN):
        if guess_chars[i] == target_chars[i]:
            result[i] = 'green'
            target_chars[i] = None
            guess_chars[i] = None

    # Жёлтые
    for i in range(WORD_LEN):
        if guess_chars[i] is not None and guess_chars[i] in target_chars:
            result[i] = 'yellow'
            target_chars[target_chars.index(guess_chars[i])] = None

    return result

def format_state(guessed_letters, target):
    """Форматирует текущее состояние игры для вывода."""
    lines = []
    for guess in guessed_letters:
        colors = check_guess(guess, target)
        line = []
        for c, col in zip(guess, colors):
            if col == 'green':
                line.append(f'🟩 {c} 🟩')
            elif col == 'yellow':
                line.append(f'🟨 {c} 🟨')
            else:
                line.append(f'⬛ {c} ⬛')
        lines.append(' '.join(line))
    return '\n'.join(lines)

def is_valid_word(word):
    return word in WORD_LIST

def create_new_game(user_id: str):
    word = pick_word()
    save_wordle_session(user_id, word, MAX_GUESSES, json.dumps([]), '')
    return word

def process_guess(user_id: str, guess: str):
    session = get_wordle_session(user_id)
    if not session:
        return None, None, None
    word, guesses_left, guessed_letters_json, _ = session
    guessed_letters = json.loads(guessed_letters_json) if guessed_letters_json else []
    if not is_valid_word(guess):
        return None, 'invalid', None
    guessed_letters.append(guess)
    guesses_left -= 1
    colors = check_guess(guess, word)
    state = format_state(guessed_letters, word)
    if guess == word:
        delete_wordle_session(user_id)
        return True, state, len(guessed_letters)
    elif guesses_left <= 0:
        delete_wordle_session(user_id)
        return False, state, word
    else:
        save_wordle_session(user_id, word, guesses_left, json.dumps(guessed_letters), state)
        return None, state, None

def get_remaining_guesses(user_id: str):
    session = get_wordle_session(user_id)
    if session:
        return session[1]
    return 0

def get_guesses(user_id: str):
    session = get_wordle_session(user_id)
    if session:
        _, _, guessed_letters_json, _ = session
        return json.loads(guessed_letters_json) if guessed_letters_json else []
    return []