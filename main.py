import feedparser

import requests

import time

import os

from datetime import datetime

from flask import Flask

from threading import Thread



# ===============================

# ENV VARIABLES (SET THESE IN RAILWAY SETTINGS)

# ===============================

BOT_TOKEN = os.environ.get("8539685984:AAHaN767o8sxWRgLdCnE3bemtIciPkLxAhA")

CHAT_ID = os.environ.get("-1003796565669")

EIA_API_KEY = os.environ.get("ygYRxwb2VEOgKXiv6VYejVcQ6BHGvIkv0EO95gb5")



CHECK_INTERVAL = 300  # 5 minutes



# ===============================

# FLASK SERVER (REQUIRED FOR RAILWAY)

# ===============================

app = Flask(__name__)



@app.route("/")

def home():

    return "Bot is running 24/7"



# ===============================

# RSS SOURCES

# ===============================

RSS_FEEDS = {

    "Reuters": "https://www.reuters.com/arc/outboundfeeds/rss/?outputType=xml",

    "PIB India": "https://pib.gov.in/RssMain.aspx?ModId=3&Lang=1"

}



ASSET_KEYWORDS = {

    "NATURAL GAS": ["natural gas", "lng"],

    "CRUDE OIL": ["crude", "oil", "brent", "wti", "opec"],

    "SILVER / METALS": ["silver", "gold", "bullion"],

    "NIFTY / NSE": ["nifty", "nse"],

    "SENSEX / BSE": ["sensex", "bse"],

    "BANKING SECTOR": ["bank nifty", "bank stocks"],

    "IT SECTOR": ["infosys", "tcs", "wipro"],

    "RBI POLICY": ["rbi", "repo rate"],

    "INDIA CPI / GDP": ["india inflation", "india gdp"],

    "FED POLICY": ["federal reserve", "fomc", "powell"],

    "US CPI / GDP": ["us inflation", "us gdp", "nonfarm payrolls"],

    "ELECTION NEWS": ["election", "lok sabha", "senate"]

}



HIGH_IMPACT = [

    "cpi", "inflation", "gdp", "rate decision",

    "repo rate", "fomc", "inventory",

    "nonfarm payrolls", "election results"

]



sent_news = set()



# ===============================

# TELEGRAM FUNCTION

# ===============================

def send_telegram(message):

    if not BOT_TOKEN or not CHAT_ID:

        print("Telegram ENV variables not set.")

        return



    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    try:

        requests.post(url, data={

            "chat_id": CHAT_ID,

            "text": message

        })

    except Exception as e:

        print("Telegram Error:", e)



def send_startup_message():

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    message = f"✅ Multi-Market Scanner Connected\nTime: {timestamp}"

    send_telegram(message)



# ===============================

# LOGIC

# ===============================

def get_asset(title):

    for asset, keywords in ASSET_KEYWORDS.items():

        if any(word in title for word in keywords):

            return asset

    return None



def get_impact(title):

    if any(word in title for word in HIGH_IMPACT):

        return "🔥 HIGH IMPACT"

    return "🟢 News"



def check_rss():

    for source_name, url in RSS_FEEDS.items():

        feed = feedparser.parse(url)



        for entry in feed.entries[:30]:

            title = entry.title.lower()



            if entry.link not in sent_news:

                asset = get_asset(title)



                if asset:

                    impact = get_impact(title)

                    message = (

                        f"{impact}\n\n"

                        f"Asset: {asset}\n"

                        f"Source: {source_name}\n\n"

                        f"{entry.title}\n\n"

                        f"{entry.link}"

                    )

                    send_telegram(message)

                    sent_news.add(entry.link)



# ===============================

# BACKGROUND BOT LOOP

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

# START APP + BOT THREAD

# ===============================

if __name__ == "__main__":



    # Start bot in background thread

    bot_thread = Thread(target=bot_loop)

    bot_thread.daemon = True

    bot_thread.start()



    # Start Flask server (Railway requires open port)

    port = int(os.environ.get("PORT", 8080))

    app.run(host="0.0.0.0", port=port)
