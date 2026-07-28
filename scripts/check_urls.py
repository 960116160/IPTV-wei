#!/usr/bin/env python3
# scripts/check_urls.py
# Usage:
#   python3 scripts/check_urls.py --source raw|file --path <url_or_path> --out result.csv
# Examples:
#   python3 scripts/check_urls.py --source raw --path "https://raw.githubusercontent.com/960116160/IPTV-wei/main/qazwsx1.txt" --out result.csv
#   python3 scripts/check_urls.py --source file --path ./qazwsx1.txt --out result.csv

import asyncio
import aiohttp
import argparse
import re
import csv
import time

URL_RE = re.compile(r'(https?://[^\s,]+)')

async def fetch_head(session, url, timeout):
    start = time.time()
    try:
        async with session.head(url, allow_redirects=True, timeout=timeout) as resp:
            elapsed = (time.time() - start)
            return {
                "url": url,
                "status": "ok",
                "http_code": resp.status,
                "final_url": str(resp.url),
                "content_type": resp.headers.get("Content-Type", ""),
                "elapsed_s": round(elapsed, 3),
                "error": ""
            }
    except Exception as e:
        # try GET as fallback for servers that don't support HEAD
        try:
            start = time.time()
            async with session.get(url, allow_redirects=True, timeout=timeout) as resp:
                elapsed = (time.time() - start)
                return {
                    "url": url,
                    "status": "ok",
                    "http_code": resp.status,
                    "final_url": str(resp.url),
                    "content_type": resp.headers.get("Content-Type", ""),
                    "elapsed_s": round(elapsed, 3),
                    "error": ""
                }
        except Exception as e2:
            return {
                "url": url,
                "status": "error",
                "http_code": "",
                "final_url": "",
                "content_type": "",
                "elapsed_s": "",
                "error": str(e2)
            }

async def worker(session, q, results, timeout):
    while True:
        item = await q.get()
        if item is None:
            q.task_done()
            break
        url = item
        res = await fetch_head(session, url, timeout)
        results.append(res)
        q.task_done()

async def main_async(args):
    # load text
    if args.source == "raw":
        async with aiohttp.ClientSession() as s:
            async with s.get(args.path) as r:
                text = await r.text()
    else:
        with open(args.path, "r", encoding="utf-8") as f:
            text = f.read()

    # extract unique urls
    urls = URL_RE.findall(text)
    urls = [u.rstrip('),') for u in urls]  # trim trailing punctuation
    urls = list(dict.fromkeys(urls))  # preserve order & unique

    q = asyncio.Queue()
    for u in urls:
        await q.put(u)
    # add stop sentinels
    for _ in range(args.concurrency):
        await q.put(None)

    results = []
    timeout = aiohttp.ClientTimeout(total=args.timeout)

    async with aiohttp.ClientSession() as session:
        tasks = [asyncio.create_task(worker(session, q, results, timeout)) for _ in range(args.concurrency)]
        await q.join()
        for t in tasks:
            t.cancel()

    # write csv
    with open(args.out, "w", newline="", encoding="utf-8") as csvf:
        writer = csv.DictWriter(csvf, fieldnames=["url","http_code","final_url","content_type","elapsed_s","status","error"])
        writer.writeheader()
        for r in results:
            writer.writerow({
                "url": r.get("url",""),
                "http_code": r.get("http_code",""),
                "final_url": r.get("final_url",""),
                "content_type": r.get("content_type",""),
                "elapsed_s": r.get("elapsed_s",""),
                "status": r.get("status",""),
                "error": r.get("error",""),
            })
    print(f"Checked {len(results)} URLs -> {args.out}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=("raw","file"), default="file", help="raw=fetch raw file from URL; file=read local file")
    parser.add_argument("--path", required=True, help="raw URL or local file path")
    parser.add_argument("--out", default="result.csv", help="output CSV file")
    parser.add_argument("--concurrency", type=int, default=10, help="concurrent requests")
    parser.add_argument("--timeout", type=int, default=15, help="request timeout (s)")
    args = parser.parse_args()
    asyncio.run(main_async(args))
