"""
Telegram public channel -> jobs.json (+ optional auto-post to your own channel)

Source: https://t.me/s/<channel>  (public web preview, no login/API key needed)

Env vars (all optional):
  SOURCE_CHANNEL   channel username to read      (default: availablejobs4u)
  PAGES            how many preview pages to read (default: 3, ~20 posts each)
  MAX_KEEP         max jobs kept in jobs.json     (default: 500)
  BOT_TOKEN        Telegram bot token (from @BotFather)  -> enables auto-post
  TARGET_CHAT      your channel, e.g. @mychannel or -100123...
  MAX_POST         max new jobs posted per run    (default: 10)
  POST_BACKLOG     "1" to also post old posts on the very first run (default: off)
"""
import json
import os
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

SOURCE = os.getenv("SOURCE_CHANNEL", "freshernow").lstrip("@")
PAGES = int(os.getenv("PAGES", "3"))
MAX_KEEP = int(os.getenv("MAX_KEEP", "500"))
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
TARGET_CHAT = os.getenv("TARGET_CHAT", "")
MAX_POST = int(os.getenv("MAX_POST", "10"))
POST_BACKLOG = os.getenv("POST_BACKLOG", "") == "1"

DATA_FILE = Path(__file__).parent / "jobs.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JobFetchBot/1.0)"}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{9}(?!\d)")
URL_RE = re.compile(r"https?://[^\s<>\"]+")
LOC_RE = re.compile(r"location\s*[:：-]\s*([^\n]{2,80})", re.I)
PIN_RE = re.compile(r"📍\s*([^\n]{2,80})")
# promo / footer lines of the source channel that we don't want to copy
JUNK_LINE_RE = re.compile(r"follow us on|bit\.ly/|whatsapp & instagram", re.I)


def fetch_page(before=None):
    url = f"https://t.me/s/{SOURCE}"
    params = {"before": before} if before else None
    r = requests.get(url, params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


def clean_text(node):
    # keep line breaks from <br>
    for br in node.find_all("br"):
        br.replace_with("\n")
    text = node.get_text()
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln and not JUNK_LINE_RE.search(ln)]
    return "\n".join(lines).strip()


def parse_posts(html):
    soup = BeautifulSoup(html, "html.parser")
    posts = []
    for msg in soup.select("div.tgme_widget_message[data-post]"):
        data_post = msg.get("data-post", "")  # "availablejobs4u/1567"
        try:
            post_id = int(data_post.split("/")[-1])
        except ValueError:
            continue
        text_node = msg.select_one("div.tgme_widget_message_text")
        if not text_node:
            continue  # photo/video-only post
        text = clean_text(text_node)
        if len(text) < 30:
            continue
        time_tag = msg.select_one("a.tgme_widget_message_date time")
        date = time_tag.get("datetime") if time_tag else None

        links = []
        for a in text_node.find_all("a", href=True):
            h = a["href"]
            if h.startswith("http") and "bit.ly" not in h and "t.me" not in h:
                links.append(h)
        links += [u for u in URL_RE.findall(text) if "bit.ly" not in u and "t.me" not in u]

        loc = LOC_RE.search(text) or PIN_RE.search(text)
        first_line = text.splitlines()[0]
        title = re.sub(r"[^\w\s|&/,.+()\-–—₹]", "", first_line).strip(" |-–—") or first_line
        posts.append({
            "id": post_id,
            "title": title[:120],
            "location": loc.group(1).strip(" *") if loc else "",
            "text": text,
            "emails": sorted(set(EMAIL_RE.findall(text))),
            "phones": sorted(set(m.strip() for m in PHONE_RE.findall(text))),
            "links": sorted(set(links)),
            "date": date,
            "source": f"https://t.me/{SOURCE}/{post_id}",
        })
    next_before = None
    more = soup.select_one("a.tme_messages_more[data-before]")
    if more:
        next_before = more["data-before"]
    return posts, next_before


def load_existing():
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return []


def format_for_telegram(job):
    parts = [job["text"]]
    parts.append(f"\n🔗 Source: {job['source']}")
    msg = "\n".join(parts)
    return msg[:4000]


def send_to_channel(job):
    r = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={
            "chat_id": TARGET_CHAT,
            "text": format_for_telegram(job),
            "disable_web_page_preview": True,
        },
        timeout=30,
    )
    if r.status_code == 429:  # rate limited
        wait = r.json().get("parameters", {}).get("retry_after", 10)
        time.sleep(wait + 1)
        return send_to_channel(job)
    if not r.ok:
        print("Telegram error:", r.status_code, r.text, file=sys.stderr)
    return r.ok


def main():
    existing = load_existing()
    first_run = not existing
    known_ids = {j["id"] for j in existing}

    fresh, before = [], None
    for _ in range(PAGES):
        posts, before = parse_posts(fetch_page(before))
        fresh += posts
        if not before:
            break
        time.sleep(1)

    new_jobs = [p for p in fresh if p["id"] not in known_ids]
    new_jobs.sort(key=lambda j: j["id"])
    print(f"Fetched {len(fresh)} posts, {len(new_jobs)} new.")

    merged = {j["id"]: j for j in existing}
    merged.update({j["id"]: j for j in new_jobs})
    jobs = sorted(merged.values(), key=lambda j: j["id"], reverse=True)[:MAX_KEEP]
    DATA_FILE.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")

    # Optional auto-post to your own channel
    if BOT_TOKEN and TARGET_CHAT and (not first_run or POST_BACKLOG):
        for job in new_jobs[-MAX_POST:]:
            if send_to_channel(job):
                print("Posted", job["id"])
            time.sleep(4)  # stay well under Telegram rate limits


if __name__ == "__main__":
    main()
