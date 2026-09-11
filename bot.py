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

# --- پیکربندی اصلی ---
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

# --- کد دیباگ ---
print("DEBUG: Available methods in xt object:")
print(dir(xt))

# --- مدیریت حافظه و هوش مصنوعی ---
class Brain:
    def __init__(self):
        self.file = "brain_data.json"
        self.data = self.load()

    def load(self):
        if os.path.exists(self.file):
            with open(self.file, 'r') as f: return json.load(f)
        return {"win_rate": 0.5, "total_trades": 0, "history": []}

    def save(self):
        with open(self.file, 'w') as f: json.dump(self.data, f)

    def learn(self, success):
        self.data['total_trades'] += 1
        if success: self.data['win_rate'] = (self.data['win_rate'] * (self.data['total_trades']-1) + 1) / self.data['total_trades']
        else: self.data['win_rate'] = (self.data['win_rate'] * (self.data['total_trades']-1)) / self.data['total_trades']
        self.save()

brain = Brain()

# --- متغیرهای وضعیت ---
state = {
    "running": False,
    "capital_percent": 0.1,  
    "leverage": 10,          
    "last_stop_time": None,
    "daily_stats": {"trades": 0, "pnl": 0.0},
    "start_time": datetime.datetime.now()
}
active_positions = {} 

# --- هسته تحلیل و ترید ---
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
        signal = None
        reason = ""
        
        if last['close'] > last['EMA_200'] and last['volume'] > avg_vol.iloc[-1]:
            if last['close'] < last['BBL_20_2.0']: 
                signal = "BUY"
                reason = "EMA200 Trend + High Vol + BB Bottom"
        return signal, reason

    def execute_trade(self, symbol, reason, price):
        # این متد نیاز به متد صحیح دریافت موجودی دارد (پس از مشاهده دیباگ اصلاح می‌شود)
        try:
            balance = xt.get_balance() 
            trade_amount = balance * state['capital_percent']
        except:
            trade_amount = 10 
        
        pos_info = {"entry": price, "reason": reason, "tp1": price * 1.02}
        active_positions[symbol] = pos_info
        bot.send_message(CHAT_ID, f"🚀 پوزیشن {symbol} باز شد.")

# --- وظایف زمان‌بندی شده ---
def scheduler_task():
    last_heartbeat = datetime.datetime.now()
    while True:
        now = datetime.datetime.now()
        if (now - last_heartbeat).total_seconds() >= 10800:
            bot.send_message(CHAT_ID, "💓 Heartbeat: ربات فعال است...")
            last_heartbeat = now
        time.sleep(60)

def trading_loop():
    engine = MasterXTBot()
    while True:
        if state['running']:
            for symbol in SYMBOLS:
                df = engine.get_data(symbol)
                if df is not None:
                    signal, reason = engine.analyze(df)
                    if signal == "BUY" and symbol not in active_positions:
                        engine.execute_trade(symbol, reason, df.iloc[-1]['close'])
                time.sleep(3) 
        time.sleep(10)

# --- پنل تلگرام ---
@bot.message_handler(commands=['start'])
def start(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("▶️ شروع ربات", callback_data="run"),
        types.InlineKeyboardButton("🛑 توقف معاملات", callback_data="stop"),
        types.InlineKeyboardButton("⚙️ تنظیمات ریسک", callback_data="risk_cfg"),
        types.InlineKeyboardButton("🔍 موجودی", callback_data="balance")
    )
    bot.send_message(message.chat.id, "🤖 **MasterXTBot Control Panel**", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    if call.data == "run":
        state['running'] = True
        bot.answer_callback_query(call.id, "✅ ربات شروع شد.")
    elif call.data == "stop":
        state['running'] = False
        bot.answer_callback_query(call.id, "🛑 متوقف شد.")
    elif call.data == "balance":
        try:
            bal = xt.get_balance()
            bot.send_message(call.message.chat.id, f"💰 موجودی: {bal}")
        except Exception as e:
            bot.send_message(call.message.chat.id, f"⚠️ خطا: {str(e)}")

# --- اجرای اصلی ---
if __name__ == "__main__":
    threading.Thread(target=scheduler_task, daemon=True).start()
    threading.Thread(target=trading_loop, daemon=True).start()
    print("MasterXTBot is launching...")
    bot.polling(none_stop=True)
           
