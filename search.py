import os
import logging
from tavily import TavilyClient

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")
if not TAVILY_API_KEY:
    logging.warning("TAVILY_API_KEY not set, smart search will not work")

client = TavilyClient(api_key=TAVILY_API_KEY) if TAVILY_API_KEY else None

async def search_tavily(query: str, max_results: int = 10) -> str:
    if not client:
        return "Tavily API не настроен. Добавьте TAVILY_API_KEY в переменные окружения."
    try:
        response = client.search(
            query=query,
            search_depth="basic",
            max_results=max_results,
            include_answer=True,
            include_domains=None,
            exclude_domains=None
        )
        parts = []
        if response.get('answer'):
            parts.append(f"📌 *Краткий ответ:* {response['answer']}\n")
        results = response.get('results', [])
        if results:
            parts.append("🔍 *Найдено в интернете:*")
            for i, res in enumerate(results, 1):
                title = res.get('title', '')
                content = res.get('content', '')
                url = res.get('url', '')
                parts.append(f"{i}. *{title}*\n{content}\n{url}")
        if not parts:
            return "Ничего не найдено."
        return "\n\n".join(parts)
    except Exception as e:
        logging.error(f"Tavily search error: {e}")
        return f"Ошибка поиска: {e}"