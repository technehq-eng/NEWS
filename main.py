import feedparser
import requests
import time
import os
from datetime import datetime
from flask import Flask
from threading import Thread

# ===============================
# ENV VARIABLES
# ===============================
BOT_TOKEN = os.getenv("8539685984:AAHaN767o8sxWRgLdCnE3bemtIciPkLxAhA")
CHAT_ID = os.getenv("-1003796565669")
EIA_API_KEY = os.getenv("ygYRxwb2VEOgKXiv6VYejVcQ6BHGvIkv0EO95gb5")

print("BOT_TOKEN loaded:", BOT_TOKEN is not None)
print("CHAT_ID loaded:", CHAT_ID is not None)

CHECK_INTERVAL = 300

# ===============================
# FLASK SERVER
# ===============================
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot running"

# ===============================
# TELEGRAM
# ===============================
def send_telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("Missing Telegram credentials")
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": message})

def send_startup_message():
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    send_telegram(f"✅ Multi-Market Scanner Connected\nTime: {timestamp}")

# ===============================
# RSS
# ===============================
RSS_FEEDS = {
    "Reuters": "https://www.reuters.com/arc/outboundfeeds/rss/?outputType=xml"
}

sent_news = set()

def check_rss():
    for source, url in RSS_FEEDS.items():
        feed = feedparser.parse(url)
        for entry in feed.entries[:10]:
            if entry.link not in sent_news:
                send_telegram(f"{entry.title}\n{entry.link}")
                sent_news.add(entry.link)

# ===============================
# BOT LOOP
# ===============================
def bot_loop():
    send_startup_message()
    while True:
        try:
            check_rss()
            time.sleep(CHECK_INTERVAL)
        except Exception as e:
            print("Loop Error:", e)
            time.sleep(60)

# ===============================
# START
# ===============================
if __name__ == "__main__":
    Thread(target=bot_loop, daemon=True).start()
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
