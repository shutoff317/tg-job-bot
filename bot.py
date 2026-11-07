"""
Telegram public channel -> jobs.json (sirf apply links)
Source: https://t.me/s/<channel>

Env vars (optional):
  SOURCE_CHANNEL  default: Freshers_job_updates_by_akhila
  PAGES           kitne preview pages padhne hain (default: 3)
  MAX_KEEP        jobs.json mein max links (default: 500)
  BOT_TOKEN       Telegram bot token (auto-post ke liye)
  TARGET_CHAT     aapka channel, jaise @mychannel
  MAX_POST        ek run mein max naye links (default: 5)
  POST_BACKLOG    "1" ho to pehle run mein purane links bhi post honge
"""
import json
import os
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

SOURCE = os.getenv("SOURCE_CHANNEL", "Freshers_job_updates_by_akhila").lstrip("@")
PAGES = int(os.getenv("PAGES", "3"))
MAX_KEEP = int(os.getenv("MAX_KEEP", "500"))
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
TARGET_CHAT = os.getenv("TARGET_CHAT", "")
MAX_POST = int(os.getenv("MAX_POST", "5"))
POST_BACKLOG = os.getenv("POST_BACKLOG", "") == "1"

DATA_FILE = Path(__file__).parent / "jobs.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JobFetchBot/1.0)"}

URL_RE = re.compile(r"https?://[^\s<>\"]+")
# in links ko skip karo (promo / shortener / social)
SKIP_LINK_RE = re.compile(
    r"t\.me|telegram\.me|bit\.ly|wa\.me|whatsapp\.com|instagram\.com|"
    r"youtube\.com|youtu\.be|facebook\.com|linkedin\.com/company|chat\.whatsapp",
    re.I,
)
# scam wale posts ko pura hata do
SCAM_RE = re.compile(
    r"registration fee|security deposit|pay\s*(rs|₹)|processing fee|"
    r"training fee|refundable|send money|paid kit",
    re.I,
)


def fetch_page(before=None):
    url = f"https://t.me/s/{SOURCE}"
    params = {"before": before} if before else None
    r = requests.get(url, params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


def parse_posts(html):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for msg in soup.select("div.tgme_widget_message[data-post]"):
        try:
            post_id = int(msg.get("data-post", "").split("/")[-1])
        except ValueError:
            continue
        node = msg.select_one("div.tgme_widget_message_text")
        if not node:
            continue
        text = node.get_text(" ")
        if SCAM_RE.search(text):
            continue

        links = [a["href"] for a in node.find_all("a", href=True)]
        links += URL_RE.findall(text)
        links = [u.rstrip(".,)") for u in links
                 if u.startswith("http") and not SKIP_LINK_RE.search(u)]
        links = list(dict.fromkeys(links))  # duplicate hatao, order rakho
        if not links:
            continue

        time_tag = msg.select_one("a.tgme_widget_message_date time")
        out.append({
            "id": post_id,
            "links": links,
            "date": time_tag.get("datetime") if time_tag else None,
        })
    more = soup.select_one("a.tme_messages_more[data-before]")
    return out, (more["data-before"] if more else None)


def load_existing():
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return []


def send_to_channel(link):
    r = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": TARGET_CHAT, "text": link},
        timeout=30,
    )
    if r.status_code == 429:
        time.sleep(r.json().get("parameters", {}).get("retry_after", 10) + 1)
        return send_to_channel(link)
    if not r.ok:
        print("Telegram error:", r.status_code, r.text, file=sys.stderr)
    return r.ok


def main():
    existing = load_existing()
    first_run = not existing
    known_ids = {j["id"] for j in existing}
    known_links = {l for j in existing for l in j["links"]}

    fresh, before = [], None
    for _ in range(PAGES):
        posts, before = parse_posts(fetch_page(before))
        fresh += posts
        if not before:
            break
        time.sleep(1)

    new_jobs = [p for p in fresh if p["id"] not in known_ids]
    new_jobs.sort(key=lambda j: j["id"])
    print(f"Fetched {len(fresh)} posts with links, {len(new_jobs)} new.")

    merged = {j["id"]: j for j in existing}
    merged.update({j["id"]: j for j in new_jobs})
    jobs = sorted(merged.values(), key=lambda j: j["id"], reverse=True)[:MAX_KEEP]
    DATA_FILE.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")

    if BOT_TOKEN and TARGET_CHAT and (not first_run or POST_BACKLOG):
        to_post = [l for j in new_jobs for l in j["links"] if l not in known_links]
        for link in to_post[-MAX_POST:]:
            if send_to_channel(link):
                print("Posted", link)
            time.sleep(4)


if __name__ == "__main__":
    main()
