import asyncio
from duckduckgo_search import DDGS

async def search_web(query: str, max_results: int = 5) -> str:
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
        return f"Ошибка поиска: {e}"