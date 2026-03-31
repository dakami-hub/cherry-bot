import asyncio
import requests
from duckduckgo_search import DDGS

async def search_web(query: str, max_results: int = 10) -> str:
    """Выполняет поиск в DuckDuckGo и возвращает форматированные результаты."""
    try:
        with DDGS() as ddgs:
            results = []
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    'title': r['title'],
                    'body': r['body'],
                    'href': r['href']
                })
            if not results:
                return "Ничего не найдено."
            formatted = []
            for i, res in enumerate(results, 1):
                formatted.append(f"{i}. {res['title']}\n{res['body']}\n{res['href']}")
            return "\n\n".join(formatted)
    except Exception as e:
        return f"Ошибка поиска в DuckDuckGo: {e}"

async def search_google(query: str, max_results: int = 5, api_key: str = None, cx: str = None) -> str:
    """Выполняет поиск через Google Custom Search API (требует ключи)."""
    if not api_key or not cx:
        return "Ничего не найдено (Google Search не настроен)."
    try:
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            'key': api_key,
            'cx': cx,
            'q': query,
            'num': max_results,
            'hl': 'ru',
        }
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        if 'items' not in data:
            return "Ничего не найдено через Google."
        formatted = []
        for i, item in enumerate(data['items'], 1):
            title = item.get('title', '')
            snippet = item.get('snippet', '')
            link = item.get('link', '')
            formatted.append(f"{i}. {title}\n{snippet}\n{link}")
        return "\n\n".join(formatted)
    except Exception as e:
        return f"Ошибка поиска в Google: {e}"