import feedparser
import requests
import time
import os
from datetime import datetime
from flask import Flask
from threading import Thread

# ===============================
# ENV
# ===============================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
EIA_API_KEY = os.getenv("EIA_API_KEY")

CHECK_INTERVAL = 300
BIAS_INTERVAL = 1800

# ===============================
# FLASK (Railway requirement)
# ===============================
app = Flask(__name__)

@app.route("/")
def home():
    return "Institutional Multi-Asset Intelligence Engine Running"

# ===============================
# TELEGRAM (with inline buttons)
# ===============================
def send_telegram(message, buttons=None):
    if not BOT_TOKEN or not CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }

    if buttons:
        payload["reply_markup"] = {
            "inline_keyboard": buttons
        }

    requests.post(url, json=payload)

# ===============================
# SOURCES
# ===============================
RSS_FEEDS = {
    "Reuters": "https://www.reuters.com/arc/outboundfeeds/rss/?outputType=xml",
    "PIB India": "https://pib.gov.in/RssMain.aspx?ModId=3&Lang=1",
    "RBI": "https://www.rbi.org.in/Scripts/RSS.aspx?Id=26",
    "SEBI": "https://www.sebi.gov.in/sebirss.xml",
    "Federal Reserve": "https://www.federalreserve.gov/feeds/press_monetary.xml",
    "US BLS": "https://www.bls.gov/feed/news_release.xml",
    "US BEA": "https://www.bea.gov/rss/rss.xml",
    "OPEC": "https://www.opec.org/opec_web/en/press_room/rss.xml"
}

# ===============================
# ASSETS
# ===============================
ASSET_KEYWORDS = {
    "NIFTY": ["nifty", "india stocks"],
    "SENSEX": ["sensex"],
    "BANKING": ["bank nifty", "bank stocks"],
    "CRUDE": ["crude", "brent", "wti", "opec"],
    "NATURAL GAS": ["natural gas", "lng"],
    "SILVER": ["silver"],
    "MACRO": ["gdp", "inflation", "cpi", "repo rate", "fomc"]
}

BULLISH_WORDS = ["rate cut", "stimulus", "inflation falls", "growth rises", "dovish"]
BEARISH_WORDS = ["rate hike", "inflation rises", "slowdown", "recession", "hawkish"]

HIGH_IMPACT = ["cpi", "gdp", "repo", "fomc", "inflation", "monetary policy"]

sent_news = set()

bias = {
    "NIFTY": 0,
    "CRUDE": 0,
    "NATURAL GAS": 0,
    "MACRO": 0
}

last_bias_time = datetime.now()
last_premarket_sent = None

# ===============================
# SENTIMENT
# ===============================
def classify_sentiment(title):
    t = title.lower()
    score = 0
    if any(w in t for w in BULLISH_WORDS):
        score += 1
    if any(w in t for w in BEARISH_WORDS):
        score -= 1
    return score

# ===============================
# ASSET DETECTOR
# ===============================
def detect_asset(title):
    t = title.lower()
    for asset, words in ASSET_KEYWORDS.items():
        if any(w in t for w in words):
            return asset
    return None

# ===============================
# PROBABILITY ENGINE (Heuristic)
# ===============================
def probability_score(score):
    base = 50
    return max(5, min(95, base + score * 10))

# ===============================
# EIA DATA
# ===============================
def check_eia():
    if not EIA_API_KEY:
        return

    try:
        gas_url = f"https://api.eia.gov/v2/natural-gas/stor/wkly/data/?api_key={EIA_API_KEY}&length=1"
        crude_url = f"https://api.eia.gov/v2/petroleum/stoc/wstk/data/?api_key={EIA_API_KEY}&length=1"

        gas = requests.get(gas_url).json()["response"]["data"][0]["value"]
        crude = requests.get(crude_url).json()["response"]["data"][0]["value"]

        send_telegram(f"🛢 EIA Update\nGas: {gas}\nCrude: {crude}")

    except:
        pass

# ===============================
# RSS PROCESSING
# ===============================
def check_rss():
    for source, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)

            for entry in feed.entries[:20]:
                if entry.link in sent_news:
                    continue

                asset = detect_asset(entry.title)
                if not asset:
                    continue

                score = classify_sentiment(entry.title)
                bias[asset] = bias.get(asset, 0) + score

                prob = probability_score(bias[asset])

                sentiment_label = "🟢 Bullish" if score > 0 else "🔴 Bearish" if score < 0 else "⚪ Neutral"
                impact = "🔥 HIGH IMPACT" if any(w in entry.title.lower() for w in HIGH_IMPACT) else "🟢 Update"

                msg = (
                    f"{impact}\n"
                    f"<b>{asset}</b>\n"
                    f"Sentiment: {sentiment_label}\n"
                    f"Bias Score: {bias[asset]}\n"
                    f"Probability: {prob}%\n\n"
                    f"{entry.title}\n\n"
                    f"{entry.link}"
                )

                send_telegram(msg, buttons=[[{"text": "Open Link", "url": entry.link}]])
                sent_news.add(entry.link)

        except:
            pass

# ===============================
# MARKET SUMMARY
# ===============================
def send_bias_summary():
    global last_bias_time
    if (datetime.now() - last_bias_time).seconds >= BIAS_INTERVAL:

        summary = "📊 MARKET BIAS SUMMARY\n\n"
        for asset, score in bias.items():
            summary += f"{asset}: {score} | Prob: {probability_score(score)}%\n"

        send_telegram(summary)

        last_bias_time = datetime.now()

# ===============================
# PRE-MARKET SUMMARY (8:45 AM IST)
# ===============================
def send_premarket_summary():
    global last_premarket_sent
    now = datetime.now()

    if now.hour == 8 and now.minute >= 45:
        if last_premarket_sent != now.date():
            summary = "🌅 INDIA PRE-MARKET BIAS\n\n"
            for asset, score in bias.items():
                summary += f"{asset}: {score} | {probability_score(score)}%\n"

            send_telegram(summary)
            last_premarket_sent = now.date()

# ===============================
# MAIN LOOP
# ===============================
def bot_loop():
    send_telegram("🚀 Institutional Scanner Started")

    while True:
        try:
            check_rss()
            check_eia()
            send_bias_summary()
            send_premarket_summary()
            time.sleep(CHECK_INTERVAL)
        except:
            time.sleep(60)

# ===============================
# START
# ===============================
if __name__ == "__main__":
    Thread(target=bot_loop, daemon=True).start()
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
