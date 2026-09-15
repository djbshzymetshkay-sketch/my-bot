import threading
import time
import json
import datetime
import os
import sys
import atexit
import inspect
import requests
import pandas as pd
import pandas_ta as ta
import telebot
from telebot import types
from pyxt.perp import Perp

# --- پیکربندی ---
API_KEY = "11bfe446-a063-4ee0-8871-d7ecfd612db6"
SECRET_KEY = "f4442716939deb0ff2415e88503d26fc663c2738"
TELEGRAM_TOKEN = os.environ.get("TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
POSITIONS_FILE = "active_positions.json"

SYMBOLS = ["btc_usdt", "eth_usdt", "sol_usdt", "xrp_usdt", "bnb_usdt", "doge_usdt", "ada_usdt", 
           "avax_usdt", "link_usdt", "near_usdt", "dot_usdt", "ltc_usdt", "uni_usdt", "matic_usdt", 
           "pepe_usdt", "shib_usdt", "apt_usdt", "ton_usdt", "fet_usdt", "render_usdt", "injective_usdt",
           "sui_usdt", "fil_usdt", "aave_usdt", "arb_usdt", "op_usdt", "xlm_usdt", "trx_usdt", "etc_usdt", "gala_usdt"]

bot = telebot.TeleBot(TELEGRAM_TOKEN)
xt = Perp(host="https://fapi.xt.com", access_key=API_KEY, secret_key=SECRET_KEY)

# --- دیباگ پیشرفته: بررسی Signature متدهای کلیدی SDK ---
print("🔍 --- [دیباگ] بررسی ورودی‌های متدهای کلیدی SDK ---")
for m_name in ['دریافت_سرمایه_حساب', 'تنظیم_اهرم_حساب', 'ارسال_فعال_سفارش']:
    if hasattr(xt, m_name):
        try:
            sig = inspect.signature(getattr(xt, m_name))
            print(f"📌 {m_name} ➔ Signature: {sig}")
        except Exception as e:
            print(f"📌 {m_name} signature check error: {e}")
print("🔍 -------------------------------------------------")

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
        acc = xt.دریافت_سرمایه_حساب()
        print(f"🔍 [Debug Balance Raw]: {repr(acc)}")
        
        data = acc
        if isinstance(acc, tuple):
            for item in acc:
                if isinstance(item, (dict, list)):
                    data = item
                    break
        
        items_to_check = []
        if isinstance(data, dict):
            for key in ['result', 'data', 'list', 'accounts']:
                if key in data:
                    sub = data[key]
                    if isinstance(sub, list): items_to_check.extend(sub)
                    elif isinstance(sub, dict): items_to_check.append(sub)
            items_to_check.append(data)
        elif isinstance(data, list):
            items_to_check.extend(data)
            
        usdt_val = None
        fallback_val = None
        
        for item in items_to_check:
            if isinstance(item, dict):
                coin = str(item.get('coin') or item.get('currency') or item.get('asset') or '').lower()
                bal_val = None
                for k in ['walletBalance', 'availableBalance', 'balance', 'equity', 'usdt', 'amount']:
                    if k in item and item[k] is not None:
                        try:
                            v = float(item[k])
                            bal_val = v
                            break
                        except: pass
                
                if bal_val is not None:
                    if 'usdt' in coin or coin == '':
                        if usdt_val is None or bal_val > 0:
                            usdt_val = bal_val
                    if fallback_val is None:
                        fallback_val = bal_val

        if usdt_val is not None:
            return float(usdt_val)
        if fallback_val is not None:
            return float(fallback_val)
            
        print(f"⚠️ نتوانست موجودی را پارس کند، خروجی: {data}")
        return 0.0
    except Exception as e:
        print(f"Error fetching balance: {e}")
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
            with open(POSITIONS_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading positions file: {e}")
            return {}
    return {}

def save_active_positions():
    try:
        with open(POSITIONS_FILE, 'w') as f:
            json.dump(active_positions, f)
    except Exception as e:
        print(f"Error saving positions file: {e}")

brain = Brain()
active_positions = load_active_positions()
state = {
    "running": True,
    "capital_percent": 0.5,
    "leverage": 50,
    "last_stop_time": None,
    "daily_stats": {"trades": 0, "pnl": 0.0}
}

class MasterXTBot:
    def get_data(self, symbol):
        try:
            url = f"https://fapi.xt.com/v1/market/kline?symbol={symbol}&interval=5m&limit=50"
            res = requests.get(url, timeout=10).json()
            
            data = res
            if isinstance(data, dict) and 'result' in data:
                data = data['result']
            elif isinstance(data, dict) and 'data' in data:
                data = data['data']
                
            if not data or not isinstance(data, list):
                return None
            
            df = pd.DataFrame(data)
            if df.empty:
                return None
                
            if 'c' in df.columns:
                df['close'] = df['c'].astype(float)
            elif 'close' in df.columns:
                df['close'] = df['close'].astype(float)
            elif len(df.columns) >= 5:
                df['close'] = df.iloc[:, 4].astype(float)
            else:
                return None
                
            return df
        except Exception as e:
            print(f"❌ خطا در get_data برای {symbol}: {e}")
            return None

    def analyze(self, df):
        if df is None or len(df) < 25 or 'close' not in df.columns:
            return None, ""
        
        close = df['close']
        ema9 = close.ewm(span=9, adjust=False).mean()
        ema21 = close.ewm(span=21, adjust=False).mean()

        curr_ema9 = ema9.iloc[-1]
        prev_ema9 = ema9.iloc[-2]
        curr_ema21 = ema21.iloc[-1]
        prev_ema21 = ema21.iloc[-2]

        cross_up = (prev_ema9 <= prev_ema21) and (curr_ema9 > curr_ema21)
        if cross_up:
            return "BUY", "EMA9/21 CrossUp (Optimized Fast Mode)"
        return None, ""

    def execute_trade(self, symbol, reason, price):
        try:
            try:
                xt.تنظیم_اهرم_حساب(symbol=symbol, leverage=state['leverage'])
            except Exception as lev_err:
                print(f"⚠️ هشدار تنظیم اهرم برای {symbol}: {lev_err}")

            balance = get_safe_balance()
            capital_in_trade = (balance if balance > 0 else 10.0) * state['capital_percent']
            quantity = (capital_in_trade * state['leverage']) / price if price > 0 else 0
            
            try:
                xt.ارسال_فعال_سفارش(symbol=symbol, orderSide="BUY", orderType="MARKET", quantity=quantity)
            except Exception as api_err:
                if CHAT_ID:
                    bot.send_message(CHAT_ID, f"⚠️ خطای API صرافی در {symbol}: {api_err}")
                return

            tp1 = price * 1.01
            tp2 = price * 1.02
            tp3 = price * 1.03
            sl = price * 0.98
            
            active_positions[symbol] = {"entry": price, "tp1": tp1, "tp2": tp2, "tp3": tp3, "sl": sl, "quantity": quantity}
            save_active_positions()
            state['daily_stats']['trades'] += 1
            
            msg = (f"🚀 پوزیشن جدید: {symbol} (5m)\n"
                   f"💰 قیمت ورود: {price}\n"
                   f"🎯 TP1: {tp1:.4f} | TP2: {tp2:.4f} | TP3: {tp3:.4f}\n"
                   f"🛑 حد ضرر: {sl:.4f}\n"
                   f"📊 سرمایه درگیر: {capital_in_trade:.2f} USDT\n"
                   f"⚡️ اهرم: {state['leverage']}x\n"
                   f"🧠 دلیل: {reason}")
            if CHAT_ID:
                bot.send_message(CHAT_ID, msg)
        except Exception as e:
            if CHAT_ID:
                bot.send_message(CHAT_ID, f"❌ خطای ثبت ترید {symbol}: {e}")

def manage_positions():
    engine = MasterXTBot()
    while True:
        try:
            if active_positions:
                for symbol, pos in list(active_positions.items()):
                    df = engine.get_data(symbol)
                    if df is not None and not df.empty:
                        current_price = float(df.iloc[-1]['close'])
                        entry = pos['entry']
                        sl = pos['sl']
                        tp1 = pos['tp1']
                        quantity = pos['quantity']
                        
                        if current_price <= sl:
                            try:
                                xt.ارسال_فعال_سفارش(symbol=symbol, orderSide="SELL", orderType="MARKET", quantity=quantity)
                                del active_positions[symbol]
                                save_active_positions()
                                state['daily_stats']['pnl'] -= (entry - current_price) * quantity
                                brain.learn(False)
                                if CHAT_ID:
                                    bot.send_message(CHAT_ID, f"🛑 حد ضرر فعال شد! معامله {symbol} بسته شد.\n💰 قیمت خروج: {current_price}")
                            except Exception as e:
                                print(f"Error closing SL for {symbol}: {e}")
                                
                        elif current_price >= tp1:
                            try:
                                xt.ارسال_فعال_سفارش(symbol=symbol, orderSide="SELL", orderType="MARKET", quantity=quantity)
                                del active_positions[symbol]
                                save_active_positions()
                                profit = (current_price - entry) * quantity
                                state['daily_stats']['pnl'] += profit
                                brain.learn(True)
                                if CHAT_ID:
                                    bot.send_message(CHAT_ID, f"🎯 حد سود (TP1) تاچ شد! معامله {symbol} بسته شد.\n💰 سود تقریبی: {profit:.2f} USDT")
                            except Exception as e:
                                print(f"Error closing TP for {symbol}: {e}")
            time.sleep(5)
        except Exception as e:
            print(f"Position management error: {e}")
            time.sleep(10)

def scheduler_task():
    last_heartbeat = datetime.datetime.now()
    while True:
        now = datetime.datetime.now()
        if CHAT_ID and (now - last_heartbeat).total_seconds() >= 600:
            bot.send_message(CHAT_ID, "💓 ربات یکسره روشن و در حال پایش بازار (5m)...")
            last_heartbeat = now
        time.sleep(30)

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
                            price_val = df.iloc[-1]['close']
                            if price_val > 0:
                                engine.execute_trade(symbol, reason, price_val)
                    time.sleep(0.5)
            time.sleep(2)
        except Exception as e:
            print(f"Loop error: {e}")
            time.sleep(5)

def get_reply_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("🛑 توقف اضطراری"),
        types.KeyboardButton("⚙️ ریسک"),
        types.KeyboardButton("💰 سود/زیان"),
        types.KeyboardButton("📊 پوزیشن‌ها"),
        types.KeyboardButton("🔍 موجودی"),
        types.KeyboardButton("📊 آمار معاملات امروز"),
        types.KeyboardButton("📈 تحلیل لحظه‌ای بازار"),
        types.KeyboardButton("🟢 وضعیت اتصال صرافی")
    )
    markup.row(types.KeyboardButton("🔄 ریست اتصال (رفع Conflict)"))
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.chat.id, 
        "🤖 MasterXTBot هوشمند همراه با بازرسی امن متدها فعال شد:", 
        reply_markup=get_reply_keyboard()
    )

@bot.message_handler(func=lambda msg: True)
def handle_text_buttons(message):
    text = message.text
    chat_id = message.chat.id
    
    if text == "🛑 توقف اضطراری":
        state['running'] = False
        state['last_stop_time'] = datetime.datetime.now()
        bot.send_message(chat_id, "🔴 ربات متوقف شد.", reply_markup=get_reply_keyboard())
    elif text == "🔍 موجودی":
        try:
            balance = get_safe_balance()
            bot.send_message(chat_id, f"💰 موجودی حساب: {balance} USDT", reply_markup=get_reply_keyboard())
        except Exception as e:
            bot.send_message(chat_id, f"خطا در دریافت موجودی: {e}", reply_markup=get_reply_keyboard())
    elif text in ["💰 سود/زیان", "📊 آمار معاملات امروز"]:
        pnl = state['daily_stats']['pnl']
        trades = state['daily_stats']['trades']
        win_rate = brain.data.get('win_rate', 0.5) * 100
        bot.send_message(chat_id, f"📊 آمار امروز:\nتعداد معاملات: {trades}\nسود/زیان مجموع: {pnl:.2f} USDT\nنرخ موفقیت: {win_rate:.1f}%", reply_markup=get_reply_keyboard())
    elif text in ["📊 پوزیشن‌ها", "📈 تحلیل لحظه‌ای بازار"]:
        if not active_positions:
            bot.send_message(chat_id, "📭 هیچ پوزیشن فعالی باز نیست.", reply_markup=get_reply_keyboard())
        else:
            pos_msg = "📈 پوزیشن‌های فعال:\n"
            for sym, data in active_positions.items():
                pos_msg += f"- {sym} | ورود: {data.get('entry')} | اهرم: {state['leverage']}x\n"
            bot.send_message(chat_id, pos_msg, reply_markup=get_reply_keyboard())
    elif text == "⚙️ ریسک":
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
        bot.send_message(
            chat_id, 
            f"⚙️ تنظیمات ریسک فعلی:\n- درصد سرمایه درگیر: {int(state['capital_percent']*100)}%\n- اهرم: {state['leverage']}x\n\nگزینه جدید را انتخاب کنید:",
            reply_markup=markup
        )
    elif text.startswith("سرمایه: "):
        try:
            val = int(text.replace("سرمایه: ", "").replace("%", ""))
            state['capital_percent'] = val / 100.0
            bot.send_message(chat_id, f"✅ درصد سرمایه روی {val}% تنظیم شد.", reply_markup=get_reply_keyboard())
        except Exception:
            bot.send_message(chat_id, "خطا در تنظیم سرمایه.", reply_markup=get_reply_keyboard())
    elif text.startswith("اهرم: "):
        try:
            val = int(text.replace("اهرم: ", "").replace("x", ""))
            state['leverage'] = val
            bot.send_message(chat_id, f"✅ اهرم روی {val}x تنظیم شد.", reply_markup=get_reply_keyboard())
        except Exception:
            bot.send_message(chat_id, "خطا در تنظیم اهرم.", reply_markup=get_reply_keyboard())
    elif text == "🔙 بازگشت به منوی اصلی":
        bot.send_message(chat_id, "منوی اصلی:", reply_markup=get_reply_keyboard())
    elif text == "🟢 وضعیت اتصال صرافی":
        try:
            balance = get_safe_balance()
            bot.send_message(chat_id, f"🟢 اتصال برقرار است.\n💰 موجودی کیف پول: {balance} USDT", reply_markup=get_reply_keyboard())
        except Exception as e:
            bot.send_message(chat_id, f"🔴 خطا در اتصال صرافی: {e}", reply_markup=get_reply_keyboard())
    elif text == "🔄 ریست اتصال (رفع Conflict)":
        try:
            bot.remove_webhook()
            bot.send_message(chat_id, "🔄 وب‌هوک/پویینگ ریست شد.", reply_markup=get_reply_keyboard())
        except Exception as e:
            bot.send_message(chat_id, f"خطا در ریست: {e}", reply_markup=get_reply_keyboard())

threading.Thread(target=scheduler_task, daemon=True).start()
threading.Thread(target=trading_loop, daemon=True).start()
threading.Thread(target=manage_positions, daemon=True).start()

if __name__ == "__main__":
    while True:
        try:
            bot.remove_webhook()
            time.sleep(1)
            bot.infinity_polling(timeout=60, long_polling_timeout=30)
        except Exception as e:
            print(f"Polling crashed: {e}, restarting in 5s...")
            time.sleep(5)
