import feedparser
import requests
import time
import os
import json
import logging
from datetime import datetime
from flask import Flask
from threading import Thread

# ===============================
# LOGGING SETUP
# ===============================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ===============================
# PERSISTENT STORAGE
# ===============================
STATE_FILE = "state.json"

def load_state():
    global sent_news, bias
    try:
        with open(STATE_FILE, "r") as f:
            data = json.load(f)
            sent_news = set(data.get("sent_news", []))
            bias.update(data.get("bias", {}))
            logging.info("State loaded successfully.")
    except Exception as e:
        logging.warning(f"State load failed: {e}")

def save_state():
    try:
        with open(STATE_FILE, "w") as f:
            json.dump({
                "sent_news": list(sent_news),
                "bias": bias
            }, f)
    except Exception as e:
        logging.error(f"State save failed: {e}")

# ===============================
# ENV
# ===============================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
EIA_API_KEY = os.getenv("EIA_API_KEY")

CHECK_INTERVAL = 300
BIAS_INTERVAL = 1800

# ===============================
# FLASK
# ===============================
app = Flask(__name__)

@app.route("/")
def home():
    return "Institutional Multi-Asset Intelligence Engine Running"

@app.route("/health")
def health():
    return {
        "status": "running",
        "time": str(datetime.now())
    }

# ===============================
# TELEGRAM
# ===============================
def send_telegram(message, buttons=None):
    if not BOT_TOKEN or not CHAT_ID:
        logging.error("Telegram ENV variables missing.")
        return

    try:
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

        response = requests.post(url, json=payload, timeout=10)
        logging.info(f"Telegram status: {response.status_code}")

    except Exception as e:
        logging.error(f"Telegram send failed: {e}")

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
# ASSET KEYWORDS
# ===============================
ASSET_KEYWORDS = {
    "NIFTY": ["nifty", "india stocks"],
    "SENSEX": ["sensex"],
    "BANKING": ["bank nifty", "bank stocks"],
    "CRUDE": ["crude", "brent", "wti", "opec"],
    "NATURAL GAS": ["natural gas", "lng"],
    "SILVER": ["silver"],
    "MACRO": ["gdp", "inflation", "cpi", "repo rate", "fomc"],
    "FII FLOW": ["foreign investors", "fii", "foreign inflows"]
}

BULLISH_WORDS = ["rate cut", "stimulus", "inflation falls", "growth rises", "dovish", "surplus"]
BEARISH_WORDS = ["rate hike", "inflation rises", "slowdown", "recession", "hawkish", "deficit"]
HIGH_IMPACT = ["cpi", "gdp", "repo", "fomc", "inflation", "monetary policy", "rate decision"]

# ===============================
# STATE
# ===============================
sent_news = set()
bias = {k: 0 for k in ASSET_KEYWORDS.keys()}
last_bias_time = datetime.now()
last_gamma_alert_time = None

# ===============================
# LOGIC
# ===============================
def classify_sentiment(title):
    t = title.lower()
    score = 0
    if any(w in t for w in BULLISH_WORDS):
        score += 1
    if any(w in t for w in BEARISH_WORDS):
        score -= 1
    return score

def detect_asset(title):
    t = title.lower()
    for asset, words in ASSET_KEYWORDS.items():
        if any(w in t for w in words):
            return asset
    return None

def probability_score(score, weight=1):
    base = 50
    adjusted = base + (score * 8 * weight)
    return max(5, min(95, adjusted))

def volatility_spike_model():
    total = (
        abs(bias.get("NIFTY", 0)) +
        abs(bias.get("MACRO", 0)) +
        abs(bias.get("CRUDE", 0)) +
        abs(bias.get("BANKING", 0))
    )

    if total >= 10:
        return "🚨 VOLATILITY EXPLOSION RISK", total
    elif total >= 7:
        return "⚡ VOLATILITY SPIKE RISK", total
    elif total >= 4:
        return "🔶 Elevated Volatility", total
    else:
        return "🟢 Normal Volatility", total

def gamma_blast_detector():
    now = datetime.now()
    _, vol_score = volatility_spike_model()
    nifty_score = abs(bias.get("NIFTY", 0))

    morning_window = (now.hour == 9 and 15 <= now.minute <= 59)
    afternoon_window = (now.hour == 13) or (now.hour == 14 and now.minute <= 30)

    return nifty_score >= 3 and vol_score >= 7 and (morning_window or afternoon_window)

# ===============================
# RSS
# ===============================
def check_rss():
    for source, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:40]:
                if entry.link in sent_news:
                    continue

                asset = detect_asset(entry.title)
                if not asset:
                    continue

                score = classify_sentiment(entry.title)
                bias[asset] += score
                save_state()

                impact = "🔥 HIGH IMPACT" if any(w in entry.title.lower() for w in HIGH_IMPACT) else "🟢 Update"

                msg = (
                    f"{impact}\n"
                    f"<b>{asset}</b>\n\n"
                    f"{entry.title}\n\n"
                    f"{entry.link}"
                )

                send_telegram(msg, buttons=[[{"text": "Open Link", "url": entry.link}]])
                sent_news.add(entry.link)
                save_state()

        except Exception as e:
            logging.error(f"RSS Error: {e}")

# ===============================
# MARKET SUMMARY
# ===============================
def send_bias_summary():
    global last_bias_time
    if (datetime.now() - last_bias_time).seconds >= BIAS_INTERVAL:
        summary = "📊 <b>MARKET BIAS SUMMARY</b>\n\n"
        for asset, score in bias.items():
            summary += f"{asset}: {score} | {probability_score(score)}%\n"

        vol_label, vol_score = volatility_spike_model()
        summary += f"\n\nVolatility Model: {vol_label} (Score: {vol_score})"

        send_telegram(summary)
        last_bias_time = datetime.now()

# ===============================
# MAIN LOOP
# ===============================
def bot_loop():
    global last_gamma_alert_time
    send_telegram("🚀 Institutional Scanner Started (Hardened)")

    while True:
        check_rss()
        send_bias_summary()

        if gamma_blast_detector():
            if not last_gamma_alert_time or (datetime.now() - last_gamma_alert_time).seconds > 900:
                send_telegram(
                    "💥 <b>GAMMA BLAST SETUP DETECTED</b>\n"
                    "High directional pressure + volatility spike.\n"
                    "Prepare for momentum expansion."
                )
                last_gamma_alert_time = datetime.now()

        time.sleep(CHECK_INTERVAL)

# ===============================
# AUTO RESTART WRAPPER
# ===============================
def start_bot():
    while True:
        try:
            bot_loop()
        except Exception as e:
            logging.critical(f"BOT CRASHED: {e}")
            send_telegram(f"⚠️ BOT CRASHED: {e}")
            time.sleep(10)

# ===============================
# START THREAD (GUNICORN SAFE)
# ===============================
load_state()
Thread(target=start_bot, daemon=True).start()

# ===============================
# LOCAL DEV
# ===============================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
