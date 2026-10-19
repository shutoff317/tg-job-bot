# Telegram Job Bot

Public Telegram channel (`t.me/s/<channel>`) se job posts nikalta hai, `jobs.json` me save karta hai,
aur chaho to apne Telegram channel me auto-post bhi karta hai. GitHub Actions se har 3 ghante me chalta hai.

## Setup (5 min)
1. Is folder ko GitHub repo me push karo.
2. Repo → **Settings → Actions → General → Workflow permissions** → *Read and write permissions* ON.
3. **Actions** tab → *Fetch jobs* → **Run workflow**. `jobs.json` repo me ban jayega.

Source channel badalna ho to `.github/workflows/fetch-jobs.yml` me `SOURCE_CHANNEL` change karo.

## Apne Telegram channel me auto-post (optional)
1. @BotFather se bot banao, token lo.
2. Bot ko apne channel me **admin** banao (Post messages permission).
3. Repo → **Settings → Secrets and variables → Actions** me add karo:
   - `BOT_TOKEN` = bot token
   - `TARGET_CHAT` = `@yourchannel` (ya `-100...` id)
4. Pehli run me purane posts post nahi hote (spam se bachne ke liye), sirf naye posts jaate hain.
   Purane bhi chahiye to env me `POST_BACKLOG=1` set karo.

## Website / Blogger par dikhana
`jobs.json` ka raw link (CORS allowed):
`https://raw.githubusercontent.com/<username>/<repo>/main/jobs.json`

```js
fetch("https://raw.githubusercontent.com/<username>/<repo>/main/jobs.json")
  .then(r => r.json())
  .then(jobs => jobs.slice(0, 20).forEach(j => {
    document.getElementById("jobs").innerHTML +=
      `<h3>${j.title}</h3><p>${j.location}</p><a href="mailto:${j.emails[0] || ''}">Apply</a>`;
  }));
```
(Ya GitHub Pages on karke wahi file use karo.)

## Local run
```
pip install -r requirements.txt
python bot.py
```

## Dhyan rakho
- Doosre channel ka content copy karne se pehle owner se permission lo ya source credit do (`source` field har job me hai).
- Job posts third-party recruiters ke hote hain, verify karke hi share karo.
- Telegram preview page ka HTML badla to `parse_posts()` update karna padega.
