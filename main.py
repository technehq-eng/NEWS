import feedparser
import requests
import time
import os
from datetime import datetime
from flask import Flask
from threading import Thread

# ===============================
# ENV VARIABLES (Railway)
# ===============================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
EIA_API_KEY = os.getenv("EIA_API_KEY")

print("BOT_TOKEN loaded:", bool(BOT_TOKEN))
print("CHAT_ID loaded:", bool(CHAT_ID))
print("EIA key loaded:", bool(EIA_API_KEY))

CHECK_INTERVAL = 300  # 5 minutes

# ===============================
# FLASK SERVER (Railway requirement)
# ===============================
app = Flask(__name__)

@app.route("/")
def home():
    return "Institutional Macro Scanner Running"

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
    message = (
        f"✅ Institutional Macro Scanner Connected\n"
        f"Time: {timestamp}\n"
        f"India + Global + Commodities Monitoring Active"
    )
    send_telegram(message)

# ===============================
# RSS SOURCES
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
    "NATURAL GAS": ["natural gas", "lng"],
    "CRUDE OIL": ["crude", "oil", "brent", "wti", "opec"],
    "SILVER / METALS": ["silver", "gold", "bullion"],
    "NIFTY / NSE": ["nifty", "nse"],
    "SENSEX / BSE": ["sensex", "bse"],
    "BANKING SECTOR": ["bank nifty", "bank stocks"],
    "IT SECTOR": ["infosys", "tcs", "wipro"],
    "RBI POLICY": ["rbi", "repo rate", "monetary policy"],
    "INDIA CPI / GDP": ["india inflation", "india gdp", "wpi"],
    "FED POLICY": ["federal reserve", "fomc", "powell"],
    "US CPI / GDP": ["us inflation", "us gdp", "nonfarm payrolls"],
    "ELECTION NEWS": ["election", "lok sabha", "senate"]
}

HIGH_IMPACT = [
    "cpi", "inflation", "gdp", "rate decision",
    "repo rate", "fomc", "inventory",
    "nonfarm payrolls", "election results",
    "monetary policy", "interest rate"
]

sent_news = set()
last_gas = None
last_crude = None

# ===============================
# IMPACT DETECTOR
# ===============================
def get_impact(title):
    title = title.lower()
    if any(word in title for word in HIGH_IMPACT):
        return "🔥 HIGH IMPACT"
    return "🟢 Macro Update"

# ===============================
# ASSET DETECTOR
# ===============================
def get_asset(title):
    title = title.lower()
    for asset, keywords in ASSET_KEYWORDS.items():
        if any(keyword in title for keyword in keywords):
            return asset
    return None

# ===============================
# RSS CHECK
# ===============================
def check_rss():
    for source_name, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)

            for entry in feed.entries[:30]:
                if entry.link in sent_news:
                    continue

                asset = get_asset(entry.title)
                if asset:
                    impact = get_impact(entry.title)
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    message = (
                        f"{impact}\n\n"
                        f"Asset: {asset}\n"
                        f"Source: {source_name}\n"
                        f"Time: {timestamp}\n\n"
                        f"{entry.title}\n\n"
                        f"{entry.link}"
                    )

                    send_telegram(message)
                    sent_news.add(entry.link)

        except Exception as e:
            print("Feed error:", source_name, e)

# ===============================
# EIA NATURAL GAS
# ===============================
def check_eia_gas():
    global last_gas
    if not EIA_API_KEY:
        return

    url = f"https://api.eia.gov/v2/natural-gas/stor/wkly/data/?api_key={EIA_API_KEY}&length=1"
    try:
        response = requests.get(url)
        data = response.json()
        latest = data["response"]["data"][0]["value"]

        if last_gas is None:
            last_gas = latest
        elif latest != last_gas:
            message = (
                f"🔥 HIGH IMPACT\n\n"
                f"Asset: NATURAL GAS\n"
                f"EIA Storage Update\n"
                f"Latest: {latest}\n"
                f"Previous: {last_gas}"
            )
            send_telegram(message)
            last_gas = latest
    except:
        pass

# ===============================
# EIA CRUDE
# ===============================
def check_eia_crude():
    global last_crude
    if not EIA_API_KEY:
        return

    url = f"https://api.eia.gov/v2/petroleum/stoc/wstk/data/?api_key={EIA_API_KEY}&length=1"
    try:
        response = requests.get(url)
        data = response.json()
        latest = data["response"]["data"][0]["value"]

        if last_crude is None:
            last_crude = latest
        elif latest != last_crude:
            message = (
                f"🔥 HIGH IMPACT\n\n"
                f"Asset: CRUDE OIL\n"
                f"EIA Inventory Update\n"
                f"Latest: {latest}\n"
                f"Previous: {last_crude}"
            )
            send_telegram(message)
            last_crude = latest
    except:
        pass

# ===============================
# BOT LOOP
# ===============================
def bot_loop():
    send_startup_message()

    while True:
        try:
            check_rss()
            check_eia_gas()
            check_eia_crude()
            time.sleep(CHECK_INTERVAL)
        except Exception as e:
            print("Main loop error:", e)
            time.sleep(60)

# ===============================
# START
# ===============================
if __name__ == "__main__":
    Thread(target=bot_loop, daemon=True).start()
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
