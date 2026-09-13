import threading
import time
import json
import datetime
import os
import sys
import atexit
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

SYMBOLS = ["btc_usdt", "eth_usdt", "sol_usdt", "xrp_usdt", "bnb_usdt", "doge_usdt", "ada_usdt", 
           "avax_usdt", "link_usdt", "near_usdt", "dot_usdt", "ltc_usdt", "uni_usdt", "matic_usdt", 
           "pepe_usdt", "shib_usdt", "apt_usdt", "ton_usdt", "fet_usdt", "render_usdt", "injective_usdt",
           "sui_usdt", "fil_usdt", "aave_usdt", "arb_usdt", "op_usdt", "xlm_usdt", "trx_usdt", "etc_usdt", "gala_usdt"]

bot = telebot.TeleBot(TELEGRAM_TOKEN)
xt = Perp(host="https://fapi.xt.com", access_key=API_KEY, secret_key=SECRET_KEY)

# --- سیستم هشدار خاموشی ربات ---
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
            
        if isinstance(data, dict) and 'result' in data:
            result_list = data['result']
            if isinstance(result_list, list):
                for item in result_list:
                    if isinstance(item, dict) and item.get('coin') == 'usdt':
                        bal = item.get('walletBalance') or item.get('availableBalance')
                        if bal is not None:
                            return float(bal)
        return 1.56
    except Exception as e:
        print(f"Error fetching balance: {e}")
        return 1.56

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
    "running": True,  # یکسره روشن
    "capital_percent": 0.5,
    "leverage": 50,
    "last_stop_time": None,
    "daily_stats": {"trades": 0, "pnl": 0.0}
}

class MasterXTBot:
    def get_data(self, symbol):
        try:
            df = xt.get_kline(symbol, interval='5m', limit=50)
            if df is None:
                return None
            return pd.DataFrame(df)
        except: 
            return None

    def analyze(self, df):
        if df is None or len(df) < 25:
            return None, ""
        
        close = df['close'].astype(float)
        volume = df['volume'].astype(float)

        ema9 = close.ewm(span=9, adjust=False).mean()
        ema21 = close.ewm(span=21, adjust=False).mean()

        delta = close.diff()
        gain = delta.where(delta > 0, 0.0).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-10)
        rsi = 100 - (100 / (1 + rs))

        curr_ema9 = ema9.iloc[-1]
        prev_ema9 = ema9.iloc[-2]
        curr_ema21 = ema21.iloc[-1]
        prev_ema21 = ema21.iloc[-2]
        curr_rsi = rsi.iloc[-1]

        vol_avg = volume.rolling(10).mean().iloc[-1]
        vol_ok = volume.iloc[-1] > (vol_avg * 0.7 if pd.notna(vol_avg) else 0)

        cross_up = (prev_ema9 <= prev_ema21) and (curr_ema9 > curr_ema21)
        rsi_buy = curr_rsi < 45

        if (cross_up or rsi_buy) and vol_ok:
            reasons = []
            if cross_up: reasons.append("EMA9/21 CrossUp")
            if rsi_buy: reasons.append(f"RSI({curr_rsi:.1f})<45")
            return "BUY", " + ".join(reasons) + " + VolOK"
        return None, ""

    def execute_trade(self, symbol, reason, price):
        try:
            try:
                xt.set_account_leverage(symbol=symbol, leverage=state['leverage'])
            except:
                pass

            balance = get_safe_balance()
            capital_in_trade = balance * state['capital_percent']
            quantity = (capital_in_trade * state['leverage']) / price
            
            try:
                xt.send_order(symbol=symbol, orderSide="BUY", orderType="MARKET", quantity=quantity)
            except Exception as api_err:
                if CHAT_ID:
                    bot.send_message(CHAT_ID, f"⚠️ خطای API صرافی (Min Notional/Margin) در {symbol}: {api_err}")
                return

            tp1 = price * 1.01
            tp2 = price * 1.02
            tp3 = price * 1.03
            sl = price * 0.98
            
            active_positions[symbol] = {"entry": price, "tp1": tp1, "tp2": tp2, "tp3": tp3, "sl": sl, "quantity": quantity}
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

def scheduler_task():
    last_heartbeat = datetime.datetime.now()
    while True:
        now = datetime.datetime.now()
        if CHAT_ID and (now - last_heartbeat).total_seconds() >= 600:
            bot.send_message(CHAT_ID, "💓 ربات یکسره روشن و در حال پایش (5m)...")
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
                            engine.execute_trade(symbol, reason, df.iloc[-1]['close'])
                    time.sleep(1.0)
            time.sleep(3)
        except Exception as e:
            print(f"Loop error: {e}")
            time.sleep(5)

@bot.message_handler(commands=['start'])
def start(message):
    send_control_panel(message.chat.id)

def send_control_panel(chat_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    # بدون دکمه شروع، بقیه کلیدها سر جایشان
    markup.add(
        types.InlineKeyboardButton("🛑 توقف اضطراری", callback_data="stop"),
        types.InlineKeyboardButton("⚙️ ریسک", callback_data="risk_menu"),
        types.InlineKeyboardButton("💰 سود/زیان", callback_data="pnl"),
        types.InlineKeyboardButton("📊 پوزیشن‌ها", callback_data="pos"),
        types.InlineKeyboardButton("🔍 موجودی", callback_data="bal")
    )
    bot.send_message(chat_id, "🤖 MasterXTBot پنل کنترل (فعال و یکسره 5m):", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    if call.data == "stop":
        state['running'] = False
        state['last_stop_time'] = datetime.datetime.now()
        bot.answer_callback_query(call.id, "🛑 متوقف شد.")
        if CHAT_ID:
            bot.send_message(CHAT_ID, "🔴 ربات توسط شما متوقف شد.")
    elif call.data == "bal":
        try:
            balance = get_safe_balance()
            bot.send_message(call.message.chat.id, f"💰 موجودی حساب: {balance} USDT")
        except Exception as e:
            bot.send_message(call.message.chat.id, f"خطا در دریافت موجودی: {e}")
    elif call.data == "pnl":
        pnl = state['daily_stats']['pnl']
        trades = state['daily_stats']['trades']
        bot.send_message(call.message.chat.id, f"📊 آمار امروز:\nتعداد معاملات: {trades}\nسود/زیان مجموع: {pnl} USDT\nنرخ موفقیت مغز هوشمند: {brain.data['win_rate']*100:.1f}%")
    elif call.data == "pos":
        if not active_positions:
            bot.send_message(call.message.chat.id, "📭 هیچ پوزیشن فعالی وجود ندارد.")
        else:
            pos_msg = "📈 پوزیشن‌های باز:\n"
            for sym, data in active_positions.items():
                pos_msg += f"- {sym} | ورود: {data['entry']} | اهرم: {state['leverage']}x\n"
            bot.send_message(call.message.chat.id, pos_msg)
    elif call.data == "risk_menu":
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("درصد سرمایه: 25%", callback_data="set_cap_25"),
            types.InlineKeyboardButton("درصد سرمایه: 50%", callback_data="set_cap_50"),
            types.InlineKeyboardButton("درصد سرمایه: 100%", callback_data="set_cap_100"),
            types.InlineKeyboardButton("اهرم: 10x", callback_data="set_lev_10"),
            types.InlineKeyboardButton("اهرم: 20x", callback_data="set_lev_20"),
            types.InlineKeyboardButton("اهرم: 50x", callback_data="set_lev_50"),
            types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")
        )
        bot.edit_message_text(
            f"⚙️ تنظیمات ریسک فعلی:\n"
            f"- درصد سرمایه درگیر: {state['capital_percent']*100}%\n"
            f"- اهرم (لوریج): {state['leverage']}x\n\n"
            f"یک گزینه را برای تغییر انتخاب کنید:",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup
        )
    elif call.data.startswith("set_cap_"):
        val = int(call.data.split("_")[2])
        state['capital_percent'] = val / 100.0
        bot.answer_callback_query(call.id, f"✅ درصد سرمایه روی {val}% تنظیم شد.")
        handle_query(type('obj', (object,), {'data': 'risk_menu', 'message': call.message, 'id': call.id}()))
    elif call.data.startswith("set_lev_"):
        val = int(call.data.split("_")[2])
        state['leverage'] = val
        bot.answer_callback_query(call.id, f"✅ اهرم روی {val}x تنظیم شد.")
        handle_query(type('obj', (object,), {'data': 'risk_menu', 'message': call.message, 'id': call.id}()))
    elif call.data == "back_main":
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🛑 توقف اضطراری", callback_data="stop"),
            types.InlineKeyboardButton("⚙️ ریسک", callback_data="risk_menu"),
            types.InlineKeyboardButton("💰 سود/زیان", callback_data="pnl"),
            types.InlineKeyboardButton("📊 پوزیشن‌ها", callback_data="pos"),
            types.InlineKeyboardButton("🔍 موجودی", callback_data="bal")
        )
        bot.edit_message_text("🤖 MasterXTBot پنل کنترل:", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)

threading.Thread(target=scheduler_task, daemon=True).start()
threading.Thread(target=trading_loop, daemon=True).start()

if __name__ == "__main__":
    try:
        bot.infinity_polling()
    except Exception as e:
        notify_shutdown(f"خطای بحرانی در polling: {e}")
