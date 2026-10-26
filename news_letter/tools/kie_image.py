"""Generate a brand-styled image with kie.ai (default model: Nano Banana 2).

Usage:
    python tools/kie_image.py --prompt "subject only" --out .tmp/<slug>/img/hero.png [--aspect 16:9]
    python tools/kie_image.py --balance            # show remaining credits, spend nothing
    python tools/kie_image.py --prompt "..." --dry-run   # print the full prompt, spend nothing

The brand style from config/brand.json -> image_style (flat, ink + red, no text)
is appended to every prompt automatically, so pass only the subject.
Needs KIE_API_KEY in .env. Costs credits (~8 per 1K/2K Nano Banana 2 image).
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.kie.ai/api/v1"


def headers():
    load_dotenv(ROOT / ".env")
    key = os.getenv("KIE_API_KEY")
    if not key:
        sys.exit("KIE_API_KEY missing from .env")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def call(method, path, **kw):
    """kie.ai returns HTTP 200 even on errors, so the body's `code` is what counts.

    Retries flaky-network errors. A POST is only retried when the connection failed
    before the request was sent (ConnectionError), so a task is never submitted twice.
    """
    for attempt in range(4):
        try:
            r = requests.request(method, f"{API}{path}", headers=headers(), timeout=60, **kw)
            break
        except (requests.ConnectionError, requests.Timeout) as e:
            if attempt == 3 or (method == "POST" and isinstance(e, requests.Timeout)):
                raise
            print(f"network error ({type(e).__name__}), retrying in {5 * (attempt + 1)}s...")
            time.sleep(5 * (attempt + 1))
    r.raise_for_status()
    body = r.json()
    if body.get("code") != 200:
        sys.exit(f"kie.ai error {body.get('code')}: {body.get('msg')}")
    return body["data"]


def balance():
    return call("GET", "/chat/credit")


def generate(prompt, out, aspect, model, resolution, timeout_s=300):
    task = call("POST", "/jobs/createTask", json={
        "model": model,
        "input": {"prompt": prompt, "aspect_ratio": aspect, "resolution": resolution, "output_format": "png"},
    })
    task_id = task["taskId"]
    print(f"task {task_id} submitted; polling...")
    delay, waited = 3, 0
    while waited < timeout_s:
        time.sleep(delay)
        waited += delay
        info = call("GET", "/jobs/recordInfo", params={"taskId": task_id})
        state = info.get("state")
        if state == "success":
            urls = json.loads(info["resultJson"])["resultUrls"]
            Path(out).parent.mkdir(parents=True, exist_ok=True)
            Path(out).write_bytes(requests.get(urls[0], timeout=120).content)
            print(f"saved {out} ({info.get('creditsConsumed')} credits, {info.get('costTime')}s)")
            return
        if state == "fail":
            sys.exit(f"generation failed: {info.get('failCode')} {info.get('failMsg')}")
        delay = min(delay * 1.5, 15)
    sys.exit(f"timed out after {timeout_s}s; task {task_id} may still finish - check https://kie.ai/logs")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prompt", help="subject of the image; brand style is appended automatically")
    ap.add_argument("--out", help="output PNG path")
    ap.add_argument("--aspect", default="16:9", help="16:9 (hero, default), 21:9, 3:2, 1:1, 4:5 ...")
    ap.add_argument("--model", default="nano-banana-2")
    ap.add_argument("--resolution", default="1K", choices=["1K", "2K", "4K"])
    ap.add_argument("--balance", action="store_true", help="print remaining credits and exit")
    ap.add_argument("--dry-run", action="store_true", help="print the final prompt and balance, spend nothing")
    args = ap.parse_args()

    if args.balance:
        print(f"kie.ai credits remaining: {balance()}")
        return
    if not args.prompt or (not args.out and not args.dry_run):
        ap.error("--prompt and --out are required")

    style = json.loads((ROOT / "config" / "brand.json").read_text())["image_style"]
    prompt = f"{args.prompt.strip().rstrip('.')}. {style}"
    if args.dry_run:
        print(f"PROMPT:\n{prompt}\n\ncredits remaining: {balance()}")
        return
    print(f"credits before: {balance()}")
    generate(prompt, args.out, args.aspect, args.model, args.resolution)
    print(f"credits after: {balance()}")


if __name__ == "__main__":
    main()
