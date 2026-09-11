import os
import threading
import time
import json
import datetime
import pandas as pd
import pandas_ta as ta
import telebot
from telebot import types
from pyxt.perp import Perp

# --- تنظیمات اولیه ---
TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_HERE" # توکن ربات تلگرام خود را اینجا وارد کن
bot = telebot.TeleBot(TELEGRAM_TOKEN)
CHAT_ID = "YOUR_CHAT_ID_HERE" # آیدی عددی تلگرام خودت را اینجا وارد کن

SYMBOLS = ["btc_usdt", "eth_usdt", "sol_usdt", "xrp_usdt", "bnb_usdt", "doge_usdt", "ada_usdt", 
           "avax_usdt", "link_usdt", "near_usdt", "dot_usdt", "ltc_usdt", "uni_usdt", "matic_usdt", 
           "pepe_usdt", "shib_usdt", "apt_usdt", "ton_usdt", "fet_usdt", "render_usdt", "injective_usdt",
           "sui_usdt", "fil_usdt", "aave_usdt", "arb_usdt", "op_usdt", "xlm_usdt", "trx_usdt", "etc_usdt", "gala_usdt"]

USER_SETTINGS = {"leverage": 10, "risk_percent": 0.01}
is_bot_running = False
STOP_TIME = None

class MasterXTBot:
    def __init__(self):
        self.api_key = "11bfe446-a063-4ee0-8871-d7ecfd612db6"
        self.secret_key = "f4442716939deb0ff2415e88503d26fc663c2738"
        self.xt_perp = Perp(host="https://fapi.xt.com", access_key=self.api_key, secret_key=self.secret_key)
        self.memory_file = "trade_memory.json"

    def load_memory(self):
        if os.path.exists(self.memory_file):
            with open(self.memory_file, 'r') as f: return json.load(f)
        return []

    def save_trade_to_memory(self, trade_data):
        memory = self.load_memory()
        memory.append(trade_data)
        with open(self.memory_file, 'w') as f: json.dump(memory, f)

    def analyze_market(self, symbol):
        # دریافت داده‌های کندل (مثال فرضی برای دریافت دیتای واقعی)
        df = pd.DataFrame({'close': [100]*200, 'volume': [1000]*200}) 
        df.ta.ema(length=200, append=True)
        df.ta.bbands(length=20, append=True)
        
        last = df.iloc[-1]
        # منطق استراتژی: EMA200 + Volume + BB
        if last['close'] > last['EMA_200'] and last['volume'] > 500:
            return {"signal": "BUY", "price": last['close'], "reason": "Trend & Vol Confirm"}
        return None

    def execute_trade(self, symbol, analysis):
        # محاسبه TP1, TP2, TP3 و SL
        entry = analysis['price']
        tp1 = entry * 1.02
        tp2 = entry * 1.04
        tp3 = entry * 1.06
        sl = entry * 0.98
        
        trade_details = f"🚀 پوزیشن جدید: {symbol}\n" \
                        f"نقطه ورود: {entry}\n" \
                        f"TP1: {tp1} | TP2: {tp2} | TP3: {tp3}\n" \
                        f"SL: {sl}\n" \
                        f"سرمایه: {USER_SETTINGS['risk_percent']*100}%\n" \
                        f"اهرم: {USER_SETTINGS['leverage']}x\n" \
                        f"دلیل: {analysis['reason']}"
        
        self.save_trade_to_memory({"symbol": symbol, "time": str(datetime.datetime.now()), "analysis": analysis})
        return trade_details

# --- منطق تلگرام و تردها ---

def send_menu(message):
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("▶️ شروع ربات", callback_data="start_bot"),
               types.InlineKeyboardButton("🛑 توقف معاملات", callback_data="stop_bot"))
    markup.row(types.InlineKeyboardButton("⚙️ تنظیمات ریسک", callback_data="settings"),
               types.InlineKeyboardButton("💰 مشاهده PnL", callback_data="check_pnl"))
    markup.row(types.InlineKeyboardButton("📊 پوزیشن‌های باز", callback_data="positions"),
               types.InlineKeyboardButton("📝 مشاهده لاگ‌ها", callback_data="logs"))
    bot.send_message(message.chat.id, "🤖 پنل مدیریت MasterXTBot:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    global is_bot_running, STOP_TIME
    if call.data == "start_bot":
        is_bot_running = True
        downtime = (datetime.datetime.now() - STOP_TIME).total_seconds()/3600 if STOP_TIME else 0
        bot.send_message(call.message.chat.id, f"✅ ربات فعال شد. (مدت زمان خاموشی: {downtime:.2f} ساعت)")
    elif call.data == "stop_bot":
        is_bot_running = False
        STOP_TIME = datetime.datetime.now()
        bot.send_message(call.message.chat.id, "🛑 تمام معاملات متوقف شدند.")
    # سایر هندلرها (PnL و ...) نیز به همین صورت پیاده می‌شوند

# --- حلقه اصلی گزارش‌دهی ---
def scheduler_thread():
    last_heartbeat = datetime.datetime.now()
    while True:
        now = datetime.datetime.now()
        # گزارش ۳ ساعته
        if (now - last_heartbeat).total_seconds() >= 10800:
            bot.send_message(CHAT_ID, "💓 Heartbeat: ربات فعال است و در حال اسکن بازار.")
            last_heartbeat = now
        # گزارش ۸ صبح
        if now.hour == 8 and now.minute == 0:
            bot.send_message(CHAT_ID, "📅 گزارش روزانه: سود/زیان امروز مشخص شد.")
        time.sleep(60)

# شروع ترد گزارش‌دهی
threading.Thread(target=scheduler_thread, daemon=True).start()

@bot.message_handler(commands=['start'])
def main_start(message):
    send_menu(message)

bot.polling(none_stop=True)
           
