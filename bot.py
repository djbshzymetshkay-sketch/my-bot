import threading
import time
import json
import datetime
import os
import sys
import atexit
import pandas as pd
import telebot
from telebot import types
from pyxt.perp import Perp

# --- پیکربندی ---
API_KEY = os.environ.get("XT_API_KEY", "11bfe446-a063-4ee0-8871-d7ecfd612db6")
SECRET_KEY = os.environ.get("XT_SECRET_KEY", "f4442716939deb0ff2415e88503d26fc663c2738")
TELEGRAM_TOKEN = os.environ.get("TOKEN", "8763614980:AAGIQXQtT7OkEmehPcaKeDYz6puNUjZeDGU")
CHAT_ID = os.environ.get("CHAT_ID")
POSITIONS_FILE = "active_positions.json"

SYMBOLS = ["btc_usdt", "eth_usdt", "sol_usdt", "xrp_usdt", "bnb_usdt", "doge_usdt", "ada_usdt",
           "avax_usdt", "link_usdt", "near_usdt", "dot_usdt", "ltc_usdt", "uni_usdt", "matic_usdt",
           "pepe_usdt", "shib_usdt", "apt_usdt", "ton_usdt", "fet_usdt", "render_usdt", "injective_usdt",
           "sui_usdt", "fil_usdt", "aave_usdt", "arb_usdt", "op_usdt", "xlm_usdt", "trx_usdt", "etc_usdt", "gala_usdt"]

bot = telebot.TeleBot(TELEGRAM_TOKEN)
xt = Perp(host="https://fapi.xt.com", access_key=API_KEY, secret_key=SECRET_KEY)

def notify_shutdown(reason="نامشخص (ریست سرور یا توقف دستی)"):
    if CHAT_ID and TELEGRAM_TOKEN:
        try:
            emergency_bot = telebot.TeleBot(TELEGRAM_TOKEN)
            emergency_bot.send_message(CHAT_ID, f"⚠️ **هشدار: ربات متوقف شد!**\n\n🔴 دلیل توقف: {reason}")
        except Exception as e:
            print(f"Error sending shutdown message: {e}")

atexit.register(lambda: notify_shutdown("خاموش شدن عادی یا بسته‌شدن اسکریپت"))

def get_safe_balance():
    try:
        acc = xt.get_account_capital()
        data = acc
        if isinstance(acc, tuple) and len(acc) > 1:
            data = acc[1]
        if isinstance(data, str):
            try: data = json.loads(data)
            except: pass
        if isinstance(data, dict):
            result = data.get('result') or data.get('data') or data
            if isinstance(result, list):
                for item in result:
                    if isinstance(item, dict):
                        coin = str(item.get('coin') or item.get('currency') or '').lower()
                        if coin in ('usdt', 'usdt_perp'):
                            bal = item.get('walletBalance') or item.get('availableBalance') or item.get('balance')
                            if bal is not None:
                                val = float(bal)
                                if val > 0: return val
            elif isinstance(result, dict):
                for k, v in result.items():
                    if isinstance(v, dict):
                        bal = v.get('walletBalance') or v.get('availableBalance') or v.get('balance')
                        if bal is not None and float(bal) > 0: return float(bal)
                bal = result.get('walletBalance') or result.get('availableBalance') or result.get('balance')
                if bal is not None: return float(bal)
        return 0.0
    except Exception as e:
        print(f"❌ خطای دریافت موجودی: {e}")
        return 0.0

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

def load_active_positions():
    if os.path.exists(POSITIONS_FILE):
        try:
            with open(POSITIONS_FILE, 'r') as f: return json.load(f)
        except: return {}
    return {}

def save_active_positions():
    try:
        with open(POSITIONS_FILE, 'w') as f: json.dump(active_positions, f)
    except: pass

brain = Brain()
active_positions = load_active_positions()

# ⚠️ ربات در حالت پیش‌فرض متوقف است تا زمانی که خودتان استارت کنید
state = {
    "running": False,
    "capital_percent": 0.5,
    "leverage": 50,
    "daily_stats": {"trades": 0, "pnl": 0.0}
}

class MasterXTBot:
    def get_data(self, symbol):
        try:
            res = xt.get_kline(symbol, interval='5m', limit=50)
            if not res: return None
            data = res
            if isinstance(res, tuple) and len(res) > 1: data = res[1]
            if isinstance(data, dict): data = data.get('result') or data.get('data') or data
            df = pd.DataFrame(data)
            if df.empty: return None
            if not isinstance(data, pd.DataFrame) and len(df.columns) == 1 and isinstance(df.iloc[0, 0], (list, tuple)):
                df = pd.DataFrame(df.iloc[:, 0].tolist(), columns=['time', 'open', 'high', 'low', 'close', 'volume'])
            df.rename(columns={'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 'v': 'volume', 'Close': 'close', 'C': 'close'}, inplace=True)
            if 'close' not in df.columns: return None
            df['close'] = df['close'].astype(float)
            return df
        except: return None

    def analyze(self, df):
        if df is None or len(df) < 30 or 'close' not in df.columns: return None, ""
        close = df['close']
        ema9 = close.ewm(span=9, adjust=False).mean()
        ema21 = close.ewm(span=21, adjust=False).mean()
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        curr_close = close.iloc[-1]
        curr_ema9 = ema9.iloc[-1]
        curr_ema21 = ema21.iloc[-1]
        curr_rsi = rsi.iloc[-1] if not rsi.empty else 50

        if curr_ema9 > curr_ema21 and curr_close > curr_ema9 and curr_rsi < 75:
            return "BUY", f"Trend Up (EMA9>21) & RSI: {curr_rsi:.1f}"
        return None, ""

    def execute_trade(self, symbol, reason, price):
        try:
            try: xt.set_account_leverage(symbol=symbol, leverage=state['leverage'])
            except: pass

            balance = get_safe_balance()
            effective_balance = balance if balance > 0 else 10.0
            capital_in_trade = effective_balance * state['capital_percent']
            quantity = round((capital_in_trade * state['leverage']) / price, 3)

            if quantity <= 0: return

            order_res = xt.send_order(symbol=symbol, orderSide="BUY", orderType="MARKET", quantity=str(quantity), positionSide="LONG")
            
            tp1 = price * 1.01
            sl = price * 0.98
            active_positions[symbol] = {"entry": price, "tp1": tp1, "sl": sl, "quantity": quantity}
            save_active_positions()
            state['daily_stats']['trades'] += 1

            if CHAT_ID:
                bot.send_message(CHAT_ID, f"🚀 پوزیشن جدید: {symbol}\n💰 ورود: {price}\n⚡️ اهرم: {state['leverage']}x\n📊 حجم: {quantity}")
        except Exception as e:
            if CHAT_ID: bot.send_message(CHAT_ID, f"❌ خطای ترید {symbol}: {e}")

def manage_positions():
    engine = MasterXTBot()
    while True:
        try:
            if active_positions:
                for symbol, pos in list(active_positions.items()):
                    df = engine.get_data(symbol)
                    if df is not None and not df.empty:
                        current_price = float(df.iloc[-1]['close'])
                        if current_price <= pos['sl'] or current_price >= pos['tp1']:
                            xt.send_order(symbol=symbol, orderSide="SELL", orderType="MARKET", quantity=str(pos['quantity']), positionSide="LONG")
                            del active_positions[symbol]
                            save_active_positions()
            time.sleep(5)
        except: time.sleep(10)

def trading_loop():
    engine = MasterXTBot()
    while True:
        try:
            if state['running']:
                for symbol in SYMBOLS:
                    df = engine.get_data(symbol)
                    if df is not None:
                        sig, reason = engine.analyze(df)
                        if sig == "BUY" and symbol not in active_positions:
                            engine.execute_trade(symbol, reason, df.iloc[-1]['close'])
                    time.sleep(0.5)
            else:
                time.sleep(3) # اگر متوقف بود منتظر می‌ماند
        except: time.sleep(5)

def get_reply_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("🟢 شروع ربات (استارت)"),
        types.KeyboardButton("🛑 توقف اضطراری"),
        types.KeyboardButton("⚙️ تنظیمات ریسک و اهرم"),
        types.KeyboardButton("💰 موجودی و سود"),
        types.KeyboardButton("📊 پوزیشن‌های فعال"),
        types.KeyboardButton("🟢 وضعیت اتصال صرافی")
    )
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.chat.id,
        "🤖 ربات آماده است. برای شروع فعالیت دکمه '🟢 شروع ربات (استارت)' را بزنید:",
        reply_markup=get_reply_keyboard()
    )

@bot.message_handler(func=lambda msg: True)
def handle_text_buttons(message):
    text = message.text
    chat_id = message.chat.id

    if text == "🟢 شروع ربات (استارت)":
        state['running'] = True
        bot.send_message(chat_id, f"🟢 ربات با موفقیت فعال شد!\n⚡️ اهرم تنظیم‌شده: {state['leverage']}x\n💰 درصد سرمایه: {state['capital_percent']*100}%\n\nدر حال پایش بازار...", reply_markup=get_reply_keyboard())
    elif text == "🛑 توقف اضطراری":
        state['running'] = False
        bot.send_message(chat_id, "🔴 ربات متوقف شد.", reply_markup=get_reply_keyboard())
    elif text == "⚙️ تنظیمات ریسک و اهرم":
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
        markup.add(
            types.KeyboardButton("سرمایه: 25%"),
            types.KeyboardButton("سرمایه: 50%"),
            types.KeyboardButton("سرمایه: 100%"),
            types.KeyboardButton("اهرم: 10x"),
            types.KeyboardButton("اهرم: 20x"),
            types.KeyboardButton("اهرم: 50x"),
            types.KeyboardButton("🔙 بازگشت به منوی اصلی")
        )
        bot.send_message(chat_id, f"⚙️ تنظیمات فعلی:\n- سرمایه: {state['capital_percent']*100}%\n- اهرم: {state['leverage']}x", reply_markup=markup)
    elif text.startswith("سرمایه: "):
        try:
            val = int(text.replace("سرمایه: ", "").replace("%", ""))
            state['capital_percent'] = val / 100.0
            bot.send_message(chat_id, f"✅ درصد سرمایه روی {val}% تنظیم شد.", reply_markup=get_reply_keyboard())
        except: pass
    elif text.startswith("اهرم: "):
        try:
            val = int(text.replace("اهرم: ", "").replace("x", ""))
            state['leverage'] = val
            bot.send_message(chat_id, f"✅ اهرم روی {val}x تنظیم شد.", reply_markup=get_reply_keyboard())
        except: pass
    elif text == "🔙 بازگشت به منوی اصلی":
        bot.send_message(chat_id, "منوی اصلی:", reply_markup=get_reply_keyboard())
    elif text == "💰 موجودی و سود":
        balance = get_safe_balance()
        pnl = state['daily_stats']['pnl']
        bot.send_message(chat_id, f"💰 موجودی: {balance} USDT\n📊 سود/زیان امروز: {pnl} USDT", reply_markup=get_reply_keyboard())
    elif text == "📊 پوزیشن‌های فعال":
        if not active_positions: bot.send_message(chat_id, "📭 هیچ پوزیشنی باز نیست.", reply_markup=get_reply_keyboard())
        else:
            msg = "📈 پوزیشن‌ها:\n" + "".join([f"- {s} (ورود: {d['entry']})\n" for s, d in active_positions.items()])
            bot.send_message(chat_id, msg, reply_markup=get_reply_keyboard())
    elif text == "🟢 وضعیت اتصال صرافی":
        balance = get_safe_balance()
        bot.send_message(chat_id, f"🟢 صرافی متصل است.\n💰 موجودی: {balance} USDT", reply_markup=get_reply_keyboard())

threading.Thread(target=trading_loop, daemon=True).start()
threading.Thread(target=manage_positions, daemon=True).start()

if __name__ == "__main__":
    try:
        bot.infinity_polling()
    except Exception as e:
        notify_shutdown(f"خطا: {e}")
