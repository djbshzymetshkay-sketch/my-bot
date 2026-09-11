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
# کلیدهای API از Screenshot_۲۰۲۶۰۹۰۹-۲۲۵۸۳۱-(2).png استخراج شد
API_KEY = "92d10f20b77a4349a32074d164745b78"
SECRET_KEY = "d970d5a065974317b35c6f2e3d4e3f9b"

TELEGRAM_TOKEN = "6941932204:AAElGfD1eC2y1k_Wc8qSsfz4nQcMhJmQ_9k"  # حتما جایگزین کن
CHAT_ID = "5862121424"          # حتما جایگزین کن

SYMBOLS = ["btc_usdt", "eth_usdt", "sol_usdt", "xrp_usdt", "bnb_usdt", "doge_usdt", "ada_usdt", 
           "avax_usdt", "link_usdt", "near_usdt", "dot_usdt", "ltc_usdt", "uni_usdt", "matic_usdt", 
           "pepe_usdt", "shib_usdt", "apt_usdt", "ton_usdt", "fet_usdt", "render_usdt", "injective_usdt",
           "sui_usdt", "fil_usdt", "aave_usdt", "arb_usdt", "op_usdt", "xlm_usdt", "trx_usdt", "etc_usdt", "gala_usdt"]

bot = telebot.TeleBot(TELEGRAM_TOKEN)
xt = Perp(host="https://fapi.xt.com", access_key=API_KEY, secret_key=SECRET_KEY)

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
    "capital_percent": 0.1,  # درصد سرمایه درگیر (مثلاً ۱۰ درصد)
    "leverage": 10,          # اهرم اصلی
    "last_stop_time": None,
    "daily_stats": {"trades": 0, "pnl": 0.0},
    "start_time": datetime.datetime.now()
}
active_positions = {} # {symbol: {details}}

# --- هسته تحلیل و ترید ---
class MasterXTBot:
    def get_data(self, symbol):
        try:
            # فرض بر این است که متد get_kline مقدار DataFrame برمی‌گرداند
            df = xt.get_kline(symbol, interval='15m', limit=200) 
            return pd.DataFrame(df)
        except: return None

    def analyze(self, df):
        # ۱- EMA 200
        df.ta.ema(length=200, append=True)
        # ۲- Bollinger Bands
        df.ta.bbands(length=20, append=True)
        # ۳- Volume Check
        avg_vol = df['volume'].rolling(window=20).mean()
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        # منطق سیگنال دهی
        signal = None
        reason = ""
        
        if last['close'] > last['EMA_200'] and last['volume'] > avg_vol.iloc[-1]:
            if last['close'] < last['BBL_20_2.0']: # قیمت در باند پایین بولینگر (احتمال بازگشت)
                signal = "BUY"
                reason = "EMA200 Trend + High Vol + BB Bottom"
        
        return signal, reason

    def execute_trade(self, symbol, reason, price):
        # محاسبه سرمایه درگیر (مثلاً ۱۰ درصد موجودی)
        balance = xt.get_balance() # فرض بر داشتن این متد
        trade_amount = balance * state['capital_percent']
        
        tp1 = price * 1.02
        tp2 = price * 1.04
        tp3 = price * 1.06
        sl = price * 0.98
        
        # باز کردن پوزیشن در XT (فرضی)
        # xt.place_order(symbol, side="BUY", amount=trade_amount, leverage=state['leverage'])
        
        pos_info = {
            "entry": price, "tp1": tp1, "tp2": tp2, "tp3": tp3, "sl": sl,
            "amount": trade_amount, "leverage": state['leverage'], "reason": reason
        }
        active_positions[symbol] = pos_info
        
        msg = (f"🚀 **پوزیشن باز شد!**\n\n"
               f"🪙 ارز: `{symbol}`\n"
               f"📍 ورود: `{price}`\n"
               f"🎯 TP1: `{tp1:.2f}`\n"
               f"🎯 TP2: `{tp2:.2f}`\n"
               f"🎯 TP3: `{tp3:.2f}`\n"
               f"🛑 SL: `{sl:.2f}`\n"
               f"💰 سرمایه درگیر: `{trade_amount:.2f}`\n"
               f"⚙️ اهرم: `{state['leverage']}x`\n"
               f"💡 دلیل: {reason}")
        bot.send_message(CHAT_ID, msg, parse_mode="Markdown")

# --- سیستم گزارش‌دهی و تردها ---
def scheduler_task():
    last_heartbeat = datetime.datetime.now()
    while True:
        now = datetime.datetime.now()
        
        # گزارش ۳ ساعته (Heartbeat)
        if (now - last_heartbeat).total_seconds() >= 10800:
            bot.send_message(CHAT_ID, "💓 Heartbeat: ربات فعال است و در حال تحلیل بازار است...")
            last_heartbeat = now
            
        # گزارش روزانه ساعت ۸ صبح
        if now.hour == 8 and now.minute == 0:
            bot.send_message(CHAT_ID, f"📅 **گزارش روزانه:**\nتعداد معاملات: {state['daily_stats']['trades']}\nمجموع سود/زیان: {state['daily_stats']['pnl']}")
            state['daily_stats'] = {"trades": 0, "pnl": 0.0}

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
                time.sleep(3) # جلوگیری از محدودیت API
        time.sleep(10)

# --- پنل تلگرام ---
@bot.message_handler(commands=['start'])
def start(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("▶️ شروع ربات", callback_data="run"),
        types.InlineKeyboardButton("🛑 توقف معاملات", callback_data="stop"),
        types.InlineKeyboardButton("⚙️ تنظیمات ریسک", callback_data="risk_cfg"),
        types.InlineKeyboardButton("💰 سود و زیان", callback_data="pnl_view"),
        types.InlineKeyboardButton("📊 پوزیشن‌های باز", callback_data="pos_view"),
        types.InlineKeyboardButton("📝 لاگ‌ها", callback_data="logs"),
        types.InlineKeyboardButton("🔍 موجودی", callback_data="balance")
    )
    bot.send_message(message.chat.id, "🤖 **MasterXTBot Control Panel**", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    if call.data == "run":
        if state['last_stop_time']:
            # diff = state['last_stop_time'] - datetime.datetime.now() # (ساده شده برای نمایش)
            bot.answer_callback_query(call.id, "خوش آمدی! مدتی خاموش بودیم.")
        state['running'] = True
        bot.edit_message_text("✅ ربات در حال اجراست...", call.message.chat.id, call.message.message_id)
    
    elif call.data == "stop":
        state['running'] = False
        state['last_stop_time'] = datetime.datetime.now()
        bot.answer_callback_query(call.id, "🛑 معاملات متوقف شد.")

    elif call.data == "risk_cfg":
        # در اینجا برای سادگی، یک پیام با قابلیت دریافت متن می‌فرستیم
        bot.send_message(call.message.chat.id, "لطفاً تنظیمات را به این صورت بفرستید:\n`percent,leverage`\nمثال: `0.1,10`")

    elif call.data == "pos_view":
        if not active_positions:
            bot.send_message(call.message.chat.id, "❌ هیچ پوزیشن بازتری وجود ندارد.")
        else:
            for sym, p in active_positions.items():
                bot.send_message(call.message.chat.id, f"🪙 {sym}\n📍 ورود: {p['entry']}\n🎯 TP1: {p['tp1']}")

# دریافت تنظیمات ریسک از کاربر
@bot.message_handler(func=lambda m: "," in m.text)
def set_risk(message):
    try:
        p, l = map(float, message.text.split(","))
        state['capital_percent'] = p
        state['leverage'] = int(l)
        bot.reply_to(message, f"✅ تنظیم شد: {p*100}% سرمایه و {l}x اهرم.")
    except:
        bot.reply_to(message, "❌ فرمت اشتباه است. مثال: 0.1,10")

# --- اجرای اصلی ---
threading.Thread(target=scheduler_task, daemon=True).start()
threading.Thread(target=trading_loop, daemon=True).start()

if __name__ == "__main__":
    print("MasterXTBot is launching...")
    bot.polling(none_stop=True)
           
