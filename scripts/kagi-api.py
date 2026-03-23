#!/usr/bin/env python3
"""Kagi API CLI — search, summarize, enrich, and fastgpt from the command line.

Usage:
    python scripts/kagi-api.py search "query" [--limit N]
    python scripts/kagi-api.py summarize "https://url" [--engine muriel|cecil|agnes|daphne]
    python scripts/kagi-api.py summarize --text "text to summarize"
    python scripts/kagi-api.py fastgpt "question"
    python scripts/kagi-api.py enrich "query" [--type web|news]
    python scripts/kagi-api.py balance

Requires KAGI_API in .env or KAGI_API_KEY env var.
"""

import argparse
import json
import os
import sys

from dotenv import load_dotenv
from kagiapi import KagiClient


def get_client() -> KagiClient:
    load_dotenv()
    key = os.getenv("KAGI_API") or os.getenv("KAGI_API_KEY")
    if not key:
        print("Error: Set KAGI_API in .env or KAGI_API_KEY env var", file=sys.stderr)
        sys.exit(1)
    return KagiClient(key)


def cmd_search(args):
    kagi = get_client()
    results = kagi.search(args.query, limit=args.limit)

    if args.json:
        print(json.dumps(results, indent=2))
        return

    for r in results.get("data", []):
        if r["t"] == 0:
            print(f"[{r.get('rank', '-')}] {r['title']}")
            print(f"    {r['url']}")
            snippet = r.get("snippet", "")
            if snippet:
                clean = snippet.replace("<b>", "").replace("</b>", "")
                print(f"    {clean[:150]}")
            print()
        elif r["t"] == 1:
            print(f"Related: {', '.join(r.get('list', []))}\n")


def cmd_summarize(args):
    kagi = get_client()

    kwargs = {"engine": args.engine}
    if args.text:
        kwargs["text"] = args.text
    else:
        kwargs["url"] = args.query

    result = kagi.summarize(**kwargs)

    if args.json:
        print(json.dumps(result, indent=2))
        return

    output = result.get("data", {}).get("output", "")
    if output:
        print(output)
    else:
        print("No summary returned.", file=sys.stderr)

    balance = result.get("meta", {}).get("api_balance")
    if balance is not None:
        print(f"\n[balance: ${balance:.2f}]", file=sys.stderr)


def cmd_fastgpt(args):
    print("FastGPT is temporarily disabled (Kagi returns 500 errors).", file=sys.stderr)
    sys.exit(1)

    if args.json:
        print(json.dumps(result, indent=2))
        return

    data = result.get("data", {})
    print(data.get("output", "No output returned."))

    refs = data.get("references", [])
    if refs:
        print(f"\nReferences ({len(refs)}):")
        for r in refs:
            print(f"  - {r['title']}")
            print(f"    {r['url']}")

    balance = result.get("meta", {}).get("api_balance")
    if balance is not None:
        print(f"\n[balance: ${balance:.2f}]", file=sys.stderr)


def cmd_enrich(args):
    kagi = get_client()
    results = kagi.enrich(query=args.query)

    if args.json:
        print(json.dumps(results, indent=2))
        return

    for r in results.get("data", []):
        print(f"  {r['title']}")
        print(f"  {r['url']}")
        snippet = r.get("snippet", "")
        if snippet:
            print(f"  {snippet[:150]}")
        pub = r.get("published", "")
        if pub:
            print(f"  published: {pub}")
        print()

    balance = results.get("meta", {}).get("api_balance")
    if balance is not None:
        print(f"[balance: ${balance:.2f}]", file=sys.stderr)


def cmd_balance(args):
    kagi = get_client()
    # Use a cheap enrich call to check balance
    result = kagi.enrich(query="test")
    balance = result.get("meta", {}).get("api_balance")
    if balance is not None:
        print(f"${balance:.2f}")
    else:
        print("Could not retrieve balance.", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Kagi API CLI")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    sub = parser.add_subparsers(dest="command", required=True)

    # search
    p = sub.add_parser("search", help="Web search")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=10)
    p.set_defaults(func=cmd_search)

    # summarize
    p = sub.add_parser("summarize", help="Summarize a URL or text")
    p.add_argument("query", nargs="?", help="URL to summarize")
    p.add_argument("--text", help="Text to summarize (instead of URL)")
    p.add_argument("--engine", default="muriel", choices=["muriel", "cecil", "agnes", "daphne"])
    p.set_defaults(func=cmd_summarize)

    # fastgpt
    p = sub.add_parser("fastgpt", help="AI-powered answer with references")
    p.add_argument("query")
    p.set_defaults(func=cmd_fastgpt)

    # enrich
    p = sub.add_parser("enrich", help="Web content enrichment")
    p.add_argument("query")
    p.set_defaults(func=cmd_enrich)

    # balance
    p = sub.add_parser("balance", help="Check API credit balance")
    p.set_defaults(func=cmd_balance)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
