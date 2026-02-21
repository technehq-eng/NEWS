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
# FLASK
# ===============================
app = Flask(__name__)

@app.route("/")
def home():
    return "Institutional Multi-Asset Intelligence Engine Running"

# ===============================
# TELEGRAM
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
# IMPACT MAPPING ENGINE
# ===============================
IMPACT_MAP = {
    "NIFTY": ("Equity Liquidity", ["BANKING", "SENSEX"]),
    "BANKING": ("Interest Rate Sensitive", ["NIFTY"]),
    "CRUDE": ("Input Cost Risk", ["NIFTY"]),
    "NATURAL GAS": ("Commodity Volatility", ["MCX GAS"]),
    "MACRO": ("Macro Liquidity", ["NIFTY", "BANKING"]),
    "FII FLOW": ("Capital Flow", ["NIFTY"])
}

# ===============================
# STATE
# ===============================
sent_news = set()
bias = {k: 0 for k in ASSET_KEYWORDS.keys()}
last_bias_time = datetime.now()
last_premarket_sent = None
last_projection_sent = None

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
# DETECT ASSET
# ===============================
def detect_asset(title):
    t = title.lower()
    for asset, words in ASSET_KEYWORDS.items():
        if any(w in t for w in words):
            return asset
    return None

# ===============================
# PROBABILITY ENGINE
# ===============================
def probability_score(score, weight=1):
    base = 50
    adjusted = base + (score * 8 * weight)
    return max(5, min(95, adjusted))

# ===============================
# BIAS STRENGTH LABEL
# ===============================
def bias_strength_label(score):
    abs_score = abs(score)
    if abs_score >= 4:
        return "Extreme"
    elif abs_score == 3:
        return "Strong"
    elif abs_score == 2:
        return "Moderate"
    elif abs_score == 1:
        return "Mild"
    else:
        return "Neutral"

# ===============================
# INDEX VOLATILITY MODE
# ===============================
def index_volatility_mode(index_name):
    score = bias.get(index_name, 0)
    macro = bias.get("MACRO", 0)
    crude = bias.get("CRUDE", 0)
    combined = abs(score) + abs(macro) + abs(crude)

    if combined >= 5:
        return "⚡ EXPANSION MODE"
    elif combined >= 3:
        return "🔶 Elevated Volatility"
    else:
        return "🟢 Normal Volatility"

# ===============================
# INDEX PROJECTION (UPDATED)
# ===============================
def index_projection(index_name):
    score = bias.get(index_name, 0) + bias.get("MACRO", 0)
    strength = bias_strength_label(score)
    prob = probability_score(score, weight=2)

    if score > 2:
        direction = "Bullish Bias"
        gap_up = prob
        gap_down = 100 - prob
        plan = "Buy dips above VWAP"
    elif score < -2:
        direction = "Bearish Bias"
        gap_down = prob
        gap_up = 100 - prob
        plan = "Watch opening range breakdown"
    else:
        direction = "Neutral / Range"
        gap_up = 50
        gap_down = 50
        plan = "Wait for breakout confirmation"

    vol_mode = index_volatility_mode(index_name)

    return score, strength, gap_up, gap_down, direction, plan, vol_mode

# ===============================
# NEXT DAY PROJECTION (UPDATED)
# ===============================
def next_day_projection():
    global last_projection_sent
    now = datetime.now()

    if now.hour == 15 and now.minute >= 15:
        if last_projection_sent == now.date():
            return

        nifty_score, nifty_strength, nifty_up, nifty_down, nifty_dir, nifty_plan, nifty_vol = index_projection("NIFTY")
        sensex_score, sensex_strength, sensex_up, sensex_down, sensex_dir, sensex_plan, sensex_vol = index_projection("SENSEX")

        def format_score(score):
            if score > 0:
                return f"<font color='green'>+{score}</font>"
            elif score < 0:
                return f"<font color='red'>{score}</font>"
            else:
                return f"<font color='gray'>{score}</font>"

        msg = (
            f"📌 <b>NEXT DAY INDEX PROJECTION (3:15 PM)</b>\n\n"

            f"🔵 NIFTY 50\n"
            f"Score: {format_score(nifty_score)} ({nifty_strength})\n"
            f"📈 Gap Up Probability: {nifty_up}%\n"
            f"📉 Gap Down Probability: {nifty_down}%\n"
            f"Volatility Mode: {nifty_vol}\n"
            f"Projection: <b>{nifty_dir}</b>\n"
            f"Plan: {nifty_plan}\n\n"

            f"🟣 SENSEX\n"
            f"Score: {format_score(sensex_score)} ({sensex_strength})\n"
            f"📈 Gap Up Probability: {sensex_up}%\n"
            f"📉 Gap Down Probability: {sensex_down}%\n"
            f"Volatility Mode: {sensex_vol}\n"
            f"Projection: <b>{sensex_dir}</b>\n"
            f"Plan: {sensex_plan}"
        )

        send_telegram(msg)
        last_projection_sent = now.date()

# ===============================
# EIA
# ===============================
def check_eia():
    if not EIA_API_KEY:
        return
    try:
        gas_url = f"https://api.eia.gov/v2/natural-gas/stor/wkly/data/?api_key={EIA_API_KEY}&length=1"
        crude_url = f"https://api.eia.gov/v2/petroleum/stoc/wstk/data/?api_key={EIA_API_KEY}&length=1"

        gas = requests.get(gas_url).json()["response"]["data"][0]["value"]
        crude = requests.get(crude_url).json()["response"]["data"][0]["value"]

        send_telegram(f"🛢 <b>EIA Inventory Update</b>\nGas: {gas}\nCrude: {crude}")
    except:
        pass

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

                impact = "🔥 HIGH IMPACT" if any(w in entry.title.lower() for w in HIGH_IMPACT) else "🟢 Update"

                msg = (
                    f"{impact}\n"
                    f"<b>{asset}</b>\n\n"
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
        summary = "📊 <b>MARKET BIAS SUMMARY</b>\n\n"
        for asset, score in bias.items():
            summary += f"{asset}: {score} | {probability_score(score)}%\n"
        send_telegram(summary)
        last_bias_time = datetime.now()

# ===============================
# PREMARKET
# ===============================
def send_premarket_summary():
    global last_premarket_sent
    now = datetime.now()
    if now.hour == 8 and now.minute >= 45:
        if last_premarket_sent != now.date():
            summary = "🌅 <b>INDIA PRE-MARKET BIAS</b>\n\n"
            for asset, score in bias.items():
                summary += f"{asset}: {score} | {probability_score(score)}%\n"
            send_telegram(summary)
            last_premarket_sent = now.date()

# ===============================
# LOOP
# ===============================
def bot_loop():
    send_telegram("🚀 Institutional Scanner Started")

    while True:
        try:
            check_rss()
            check_eia()
            send_bias_summary()
            send_premarket_summary()
            next_day_projection()
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
