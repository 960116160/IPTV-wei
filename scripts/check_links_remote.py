#!/usr/bin/env python3
# scripts/check_links_remote.py
# usage: python3 scripts/check_links_remote.py qazwsx1.txt --workers 20 --timeout 8 --out results/link_check_results.csv

import sys, csv, json, argparse, requests, concurrent.futures, urllib.parse, os
from requests.exceptions import RequestException

def normalize_name_url(line):
    s = line.strip()
    if not s or s.startswith('#') or s.startswith('🎞️') or s.startswith('🐼'):
        return None
    if ',' not in s:
        return None
    name, url = s.split(',',1)
    return name.strip(), url.strip()

def static_checks(url):
    issues = []
    if url.count('?') > 1:
        issues.append("MULTIPLE_QUESTION_MARKS")
    parsed = urllib.parse.urlparse(url)
    if not parsed.scheme:
        issues.append("NO_SCHEME")
    if parsed.scheme and parsed.scheme.lower() not in ("http","https","rtmp","rtsp","mms","ftp"):
        issues.append("UNKNOWN_SCHEME")
    # detect non-ascii in path
    try:
        parsed.path.encode('ascii')
    except UnicodeEncodeError:
        issues.append("NON_ASCII_PATH")
    return issues

def check_http(url, timeout, verify):
    try:
        resp = requests.head(url, allow_redirects=True, timeout=timeout, verify=verify)
        code = resp.status_code
        final_url = resp.url
        if code >= 400:
            resp2 = requests.get(url, stream=True, allow_redirects=True, timeout=timeout, verify=verify)
            code = resp2.status_code
            final_url = resp2.url
        return {"ok": True, "status_code": code, "final_url": final_url, "error": ""}
    except RequestException as e:
        # try GET as last resort
        try:
            resp = requests.get(url, stream=True, allow_redirects=True, timeout=timeout, verify=verify)
            return {"ok": True, "status_code": resp.status_code, "final_url": resp.url, "error": ""}
        except RequestException as e2:
            return {"ok": False, "status_code": None, "final_url": None, "error": str(e2)}

def worker(item, timeout, verify):
    name, url = item
    stat_issues = static_checks(url)
    parsed = urllib.parse.urlparse(url)
    scheme = parsed.scheme.lower() if parsed.scheme else ""
    result = {
        "name": name,
        "url": url,
        "scheme": scheme,
        "static_issues": stat_issues,
        "checked": False,
        "status_code": None,
        "final_url": None,
        "error": None,
    }
    if scheme in ("http","https"):
        r = check_http(url, timeout, verify)
        result["checked"] = True
        result["status_code"] = r.get("status_code")
        result["final_url"] = r.get("final_url")
        result["error"] = r.get("error")
    else:
        result["checked"] = False
        result["error"] = "UNSUPPORTED_SCHEME" if scheme else "MISSING_SCHEME"
    return result

def load_lines(path_or_url):
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        resp = requests.get(path_or_url, timeout=10)
        resp.raise_for_status()
        text = resp.text.splitlines()
    else:
        with open(path_or_url, encoding='utf-8', errors='ignore') as f:
            text = f.readlines()
    items = []
    for L in text:
        t = normalize_name_url(L)
        if t:
            items.append(t)
    return items


def ensure_dir_for_file(path):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("input", help="local file path or raw github url to qazwsx1.txt")
    p.add_argument("--workers", type=int, default=10)
    p.add_argument("--timeout", type=int, default=8)
    p.add_argument("--verify", action="store_true", help="verify SSL certificates (default: False)")
    p.add_argument("--out", default="link_check_results.csv")
    p.add_argument("--json", default="link_check_summary.json")
    args = p.parse_args()

    items = load_lines(args.input)
    print(f"Found {len(items)} entries to check (http/https tested; others marked unsupported).")

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(worker, it, args.timeout, args.verify): it for it in items}
        for fut in concurrent.futures.as_completed(futures):
            res = fut.result()
            results.append(res)

    # ensure output dirs
    ensure_dir_for_file(args.out)
    ensure_dir_for_file(args.json)

    # write CSV
    fieldnames = ["name","url","scheme","static_issues","checked","status_code","final_url","error"]
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in results:
            row = {k: r.get(k) for k in fieldnames}
            row["static_issues"] = ";".join(r.get("static_issues") or [])
            w.writerow(row)
    # write summary json
    summary = {"total": len(results), "bad_static": [], "http_fail": [], "unsupported": []}
    for r in results:
        if r["static_issues"]:
            summary["bad_static"].append({"name": r["name"], "url": r["url"], "issues": r["static_issues"]})
        if r["scheme"] in ("http","https") and (not r["checked"] or (r["status_code"] is None) or (r["status_code"]>=400)):
            summary["http_fail"].append({"name": r["name"], "url": r["url"], "status_code": r["status_code"], "error": r["error"]})
        if r["scheme"] not in ("http","https"):
            summary["unsupported"].append({"name": r["name"], "url": r["url"], "scheme": r["scheme"], "error": r["error"]})
    ensure_dir_for_file(args.json)
    with open(args.json, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("Finished. CSV:", args.out, "JSON summary:", args.json)
    print("Summary: total=", summary["total"], "; bad_static=", len(summary["bad_static"]), "; http_fail=", len(summary["http_fail"]), "; unsupported=", len(summary["unsupported"]))

    # exit non-zero if there are HTTP failures or bad static issues (so workflow can detect)
    if len(summary["http_fail"])>0 or len(summary["bad_static"])>0:
        sys.exit(2)

if __name__ == "__main__":
    main()
