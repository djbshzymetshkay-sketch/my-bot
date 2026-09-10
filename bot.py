import os
import threading
import time
import logging
import pandas as pd
import pandas_ta as ta
import requests
import telebot
from telebot import types
from pyxt.perp import Perp

# تنظیمات لاگ‌نویسی
logging.basicConfig(filename='bot_logs.log', level=logging.INFO, format='%(asctime)s - %(message)s')

TELEGRAM_TOKEN = os.getenv("TOKEN")
bot = telebot.TeleBot(TELEGRAM_TOKEN) if TELEGRAM_TOKEN else None

# متغیر برای کنترل وضعیت ربات
is_bot_running = False

SYMBOLS = ["btc_usdt", "eth_usdt", "sol_usdt", "xrp_usdt", "bnb_usdt", 
           "doge_usdt", "ada_usdt", "avax_usdt", "link_usdt", "near_usdt"]

class MasterXTBot:
    def __init__(self):
        self.api_key = "11bfe446-a063-4ee0-8871-d7ecfd612db6"
        self.secret_key = "f4442716939deb0ff2415e88503d26fc663c2738"
        self.xt_perp = Perp(host="https://fapi.xt.com", access_key=self.api_key, secret_key=self.secret_key)

    def analyze_market(self, df):
        df.ta.ema(length=200, append=True)
        df.ta.bbands(length=20, std=2, append=True) 
        df['vol_sma'] = df['volume'].rolling(20).mean()
        
        last = df.iloc[-1]
        is_uptrend = last['close'] > last['EMA_200']
        is_downtrend = last['close'] < last['EMA_200']
        vol_strong = last['volume'] > (last['vol_sma'] * 1.2)
        
        if is_uptrend and vol_strong and last['close'] > last['BBL_20_2.0']:
            return {"status": "success", "signal": "BUY", "price": last['close']}
        elif is_downtrend and vol_strong and last['close'] < last['BBU_20_2.0']:
            return {"status": "success", "signal": "SELL", "price": last['close']}
        return {"status": "neutral"}

    def execute_trade(self, symbol, signal, price):
        try:
            self.xt_perp.send_order(symbol=symbol.replace("_", ""), price=price, amount=0.01,
                                    order_side="BUY" if signal == "BUY" else "SELL",
                                    order_type="MARKET", position_side="LONG" if signal == "BUY" else "SHORT")
            return f"✅ {symbol} ({signal}) انجام شد."
        except Exception as e:
            return f"❌ خطا در {symbol}: {str(e)}"

def run_bot_loop(chat_id):
    global is_bot_running
    bot_core = MasterXTBot()
    bot.send_message(chat_id, "⚙️ اسکنر فعال شد...")
    while is_bot_running:
        for symbol in SYMBOLS:
            if not is_bot_running: break
            try:
                url = f"https://fapi.xt.com/future/market/v1/public/q/kline?symbol={symbol.replace('_', '')}&interval=15m&limit=50"
                res = requests.get(url, timeout=10).json()
                if "result" in res:
                    df = pd.DataFrame([{"close": float(c["c"]), "volume": float(c["v"])} for c in res["result"]])
                    analysis = bot_core.analyze_market(df)
                    if analysis["status"] == "success":
                        msg = bot_core.execute_trade(symbol, analysis["signal"], analysis["price"])
                        bot.send_message(chat_id, msg)
                time.sleep(2)
            except Exception as e:
                logging.error(f"خطا در {symbol}: {e}")
        time.sleep(60)

# --- مدیریت دستورات و دکمه‌ها ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🚀 شروع ربات", callback_data="start_bot"))
    markup.add(types.InlineKeyboardButton("📊 مشاهده لاگ‌ها", callback_data="check_logs"))
    markup.add(types.InlineKeyboardButton("⛔ توقف ربات", callback_data="stop_bot"))
    bot.send_message(message.chat.id, "سلام امیر! ربات در خدمتته. یکی رو انتخاب کن:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    global is_bot_running
    if call.data == "start_bot":
        if not is_bot_running:
            is_bot_running = True
            threading.Thread(target=run_bot_loop, args=(call.message.chat.id,), daemon=True).start()
            bot.answer_callback_query(call.id, "ربات روشن شد!")
        else:
            bot.answer_callback_query(call.id, "ربات از قبل روشنه.")

    elif call.data == "stop_bot":
        is_bot_running = False
        bot.answer_callback_query(call.id, "ربات متوقف شد.")
        bot.send_message(call.message.chat.id, "⛔ ربات با موفقیت متوقف شد.")

    elif call.data == "check_logs":
        try:
            with open("bot_logs.log", "r") as f:
                logs = f.readlines()[-10:] # ۵ خط آخر
            bot.send_message(call.message.chat.id, "📜 **آخرین وضعیت لاگ‌ها:**\n" + "".join(logs))
        except:
            bot.send_message(call.message.chat.id, "فایل لاگی پیدا نشد.")

if bot:
    bot.infinity_polling()
                                    
