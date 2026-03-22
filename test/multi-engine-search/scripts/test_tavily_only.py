#!/usr/bin/env python3
"""单独测试 Tavily fetcher：不经过聚合，直接看 Tavily 的返回。"""
import json
import os
import sys

# 确保从 scripts 目录加载
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fetchers.tavily import TavilyFetcher

def main():
    query = sys.argv[1] if len(sys.argv) > 1 else "Python 3.12"
    key = os.environ.get("TAVILY_API_KEY", "").strip()
    print(f"query: {query!r}", file=sys.stderr)
    print(f"TAVILY_API_KEY set: {bool(key)}", file=sys.stderr)

    fetcher = TavilyFetcher()
    source_id, items, err = fetcher.fetch(query)

    out = {
        "source_id": source_id,
        "error": err,
        "items_count": len(items),
        "items": items,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
