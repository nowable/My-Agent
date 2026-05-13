import requests

from . import config

TAVILY_URL = "https://api.tavily.com/search"


def search(query, num=5):
    if not config.TAVILY_API_KEY:
        return "[搜索不可用] 未配置 TAVILY_API_KEY"

    try:
        resp = requests.post(TAVILY_URL, json={
            "api_key": config.TAVILY_API_KEY,
            "query": query,
            "max_results": num,
            "include_answer": False,
        }, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return f"[搜索失败] {e}"

    results = data.get("results", [])
    if not results:
        return "[搜索无结果]"

    lines = []
    for r in results:
        title = r.get("title", "")
        content = r.get("content", "")
        url = r.get("url", "")
        lines.append(f"{title}\n{content}\n{url}")

    return "\n\n".join(lines)
