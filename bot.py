import threading
import time
import json
import datetime
import os
import pandas as pd
import pandas_ta as ta
import telebot
from telebot import types
from pyxt.perp import Perp

# --- پیکربندی ---
API_KEY = "92d10f20b77a4349a32074d164745b78"
SECRET_KEY = "d970d5a065974317b35c6f2e3d4e3f9b"
TELEGRAM_TOKEN = os.environ.get("TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

SYMBOLS = ["btc_usdt", "eth_usdt", "sol_usdt", "xrp_usdt", "bnb_usdt", "doge_usdt", "ada_usdt", 
           "avax_usdt", "link_usdt", "near_usdt", "dot_usdt", "ltc_usdt", "uni_usdt", "matic_usdt", 
           "pepe_usdt", "shib_usdt", "apt_usdt", "ton_usdt", "fet_usdt", "render_usdt", "injective_usdt",
           "sui_usdt", "fil_usdt", "aave_usdt", "arb_usdt", "op_usdt", "xlm_usdt", "trx_usdt", "etc_usdt", "gala_usdt"]

bot = telebot.TeleBot(TELEGRAM_TOKEN)
xt = Perp(host="https://fapi.xt.com", access_key=API_KEY, secret_key=SECRET_KEY)

# --- سیستم مغز هوشمند ---
class Brain:
    def __init__(self):
        self.file = "brain_data.json"
        self.data = self.load()
    def load(self):
        if os.path.exists(self.file):
            with open(self.file, 'r') as f: return json.load(f)
        return {"win_rate": 0.5, "total_trades": 0}
    def save(self):
        with open(self.file, 'w') as f: json.dump(self.data, f)
    def learn(self, success):
        self.data['total_trades'] += 1
        factor = 1 if success else 0
        self.data['win_rate'] = (self.data['win_rate'] * (self.data['total_trades']-1) + factor) / self.data['total_trades']
        self.save()

brain = Brain()
active_positions = {}
state = {
    "running": False,
    "capital_percent": 0.1,  
    "leverage": 10,          
    "last_stop_time": None,
    "daily_stats": {"trades": 0, "pnl": 0.0}
}

class MasterXTBot:
    def get_data(self, symbol):
        try:
            df = xt.get_kline(symbol, interval='15m', limit=200)
            return pd.DataFrame(df)
        except: return None

    def analyze(self, df):
        df.ta.ema(length=200, append=True)
        df.ta.bbands(length=20, append=True)
        avg_vol = df['volume'].rolling(window=20).mean()
        last = df.iloc[-1]
        
        # استراتژی: قیمت بالای EMA200 + حجم بالا + لمس باند پایین (BB)
        if last['close'] > last['EMA_200'] and last['volume'] > avg_vol.iloc[-1] and last['close'] < last['BBL_20_2.0']:
            return "BUY", "EMA200 Trend + High Vol + BB Bottom"
        return None, ""

    def execute_trade(self, symbol, reason, price):
        try:
            # دریافت موجودی با متد جدید
            acc = xt.get_account_capital()
            balance = float(acc.get('usdt', 0))
            
            # محاسبات
            capital_in_trade = balance * state['capital_percent']
            tp1 = price * 1.01
            tp2 = price * 1.02
            tp3 = price * 1.03
            sl = price * 0.98
            
            # ثبت در دیکشنری
            active_positions[symbol] = {"entry": price, "tp1": tp1, "tp2": tp2, "tp3": tp3, "sl": sl}
            state['daily_stats']['trades'] += 1
            
            # پیام تلگرام
            msg = (f"🚀 پوزیشن جدید: {symbol}\n"
                   f"💰 قیمت ورود: {price}\n"
                   f"🎯 TP1: {tp1:.4f} | TP2: {tp2:.4f} | TP3: {tp3:.4f}\n"
                   f"🛑 حد ضرر: {sl:.4f}\n"
                   f"📊 سرمایه درگیر: {capital_in_trade:.2f} USDT\n"
                   f"⚡️ اهرم: {state['leverage']}x\n"
                   f"🧠 دلیل: {reason}")
            bot.send_message(CHAT_ID, msg)
        except Exception as e:
            bot.send_message(CHAT_ID, f"❌ خطای ثبت ترید {symbol}: {e}")

# --- وظایف زمان‌بندی شده ---
def scheduler_task():
    last_heartbeat = datetime.datetime.now()
    while True:
        now = datetime.datetime.now()
        # گزارش ۳ ساعته (Heartbeat)
        if (now - last_heartbeat).total_seconds() >= 10800:
            bot.send_message(CHAT_ID, "💓 ربات زنده است و در حال تحلیل بازار...")
            last_heartbeat = now
        # گزارش ۸ صبح
        if now.hour == 8 and now.minute == 0:
            bot.send_message(CHAT_ID, f"📅 گزارش روزانه: {state['daily_stats']}")
            state['daily_stats'] = {"trades": 0, "pnl": 0.0}
        time.sleep(60)

def trading_loop():
    engine = MasterXTBot()
    while True:
        if state['running']:
            for symbol in SYMBOLS:
                df = engine.get_data(symbol)
                if df is not None:
                    sig, reason = engine.analyze(df)
                    if sig == "BUY" and symbol not in active_positions:
                        engine.execute_trade(symbol, reason, df.iloc[-1]['close'])
                time.sleep(2)
        time.sleep(10)

# --- تلگرام ---
@bot.message_handler(commands=['start'])
def start(message):
    # پیام بازگشت بعد از خاموشی
    if state['last_stop_time']:
        downtime = datetime.datetime.now() - state['last_stop_time']
        bot.send_message(CHAT_ID, f"👋 بازگشت بخیر! ربات برای {downtime} خاموش بود.")
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("▶️ شروع", callback_data="run"),
        types.InlineKeyboardButton("🛑 توقف", callback_data="stop"),
        types.InlineKeyboardButton("⚙️ ریسک", callback_data="risk"),
        types.InlineKeyboardButton("💰 سود/زیان", callback_data="pnl"),
        types.InlineKeyboardButton("📊 پوزیشن‌ها", callback_data="pos"),
        types.InlineKeyboardButton("🔍 موجودی", callback_data="bal")
    )
    bot.send_message(message.chat.id, "🤖 MasterXTBot پنل کنترل:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    if call.data == "run":
        state['running'] = True
        bot.answer_callback_query(call.id, "✅ ربات شروع شد.")
    elif call.data == "stop":
        state['running'] = False
        state['last_stop_time'] = datetime.datetime.now()
        bot.answer_callback_query(call.id, "🛑 متوقف شد.")
    elif call.data == "bal":
        try:
            acc = xt.get_account_capital()
            bot.send_message(call.message.chat.id, f"💰 موجودی: {acc.get('usdt', 0)} USDT")
        except: bot.send_message(call.message.chat.id, "خطا در دریافت موجودی.")
    # (سایر بخش‌های مدیریت دکمه‌ها را اینجا اضافه کن)

# اجرای تردها
threading.Thread(target=scheduler_task, daemon=True).start()
threading.Thread(target=trading_loop, daemon=True).start()

if __name__ == "__main__":
    bot.polling(none_stop=True)
                
