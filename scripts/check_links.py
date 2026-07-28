#!/usr/bin/env python3
"""
Simple dead-link checker for URLs listed in qazwsx1.txt.
Saves JSON results to results/link_check_results.json and prints a summary.

Usage: python3 scripts/check_links.py
"""
import re
import json
import os
import sys
from urllib.parse import urlparse

try:
    import requests
except Exception:
    print("The 'requests' library is required. Install with: pip install -r requirements.txt")
    sys.exit(2)

INPUT_FILE = "qazwsx1.txt"
OUTPUT_DIR = "results"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "link_check_results.json")
TIMEOUT = 10

URL_RE = re.compile(r"https?://[^,\s]+|rtmp?://[^,\s]+")


def normalize_url(url):
    return url.strip()


def check_url(url):
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        return {"scheme": scheme, "status": "unsupported", "status_code": None, "error": None}

    headers = {"User-Agent": "link-checker/1.0 (+https://github.com)"}
    try:
        # Try HEAD first
        resp = requests.head(url, allow_redirects=True, timeout=TIMEOUT, headers=headers)
        code = resp.status_code
        if code >= 400:
            # Try GET as some servers don't respond to HEAD
            resp = requests.get(url, stream=True, allow_redirects=True, timeout=TIMEOUT, headers=headers)
            code = resp.status_code
        status = "ok" if code < 400 else "dead"
        return {"scheme": scheme, "status": status, "status_code": code, "error": None}
    except requests.exceptions.RequestException as e:
        return {"scheme": scheme, "status": "error", "status_code": None, "error": str(e)}


def parse_lines(lines):
    results = []
    for idx, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line:
            continue
        # Ignore header lines containing #genre# or emoji-only labels
        if "," not in line:
            # try to find any URL in the line
            m = URL_RE.search(line)
            if m:
                name = line[:m.start()].strip() or None
                url = m.group(0)
            else:
                continue
        else:
            name_part, url_part = line.split(",", 1)
            name = name_part.strip()
            url = URL_RE.search(url_part)
            if url:
                url = url.group(0)
            else:
                url = url_part.strip()

        url = normalize_url(url)
        check = check_url(url)
        results.append({
            "line": idx,
            "name": name,
            "url": url,
            "scheme": check.get("scheme"),
            "status": check.get("status"),
            "status_code": check.get("status_code"),
            "error": check.get("error"),
        })
    return results


def main():
    if not os.path.exists(INPUT_FILE):
        print(f"Input file '{INPUT_FILE}' not found in repository root. Please place it next to this script.")
        sys.exit(1)

    with open(INPUT_FILE, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    results = parse_lines(lines)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        json.dump(results, out, ensure_ascii=False, indent=2)

    # Summary
    total = len(results)
    dead = sum(1 for r in results if r["status"] in ("dead", "error"))
    unsupported = sum(1 for r in results if r["status"] == "unsupported")
    ok = total - dead - unsupported

    print("Link check complete")
    print(f"Total URLs checked: {total}")
    print(f"OK: {ok}, Dead/Error: {dead}, Unsupported: {unsupported}")
    print(f"Results written to: {OUTPUT_FILE}")

    # Exit code non-zero if any dead/error
    if dead > 0:
        sys.exit(3)


if __name__ == "__main__":
    main()
