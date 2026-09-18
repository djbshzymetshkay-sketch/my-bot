import threading
import time
import json
import datetime
import os
import sys
import atexit
import requests
import pandas as pd
import telebot
from telebot import types
from pyxt.perp import Perp

# --- پیکربندی ---
apikeyval = os.environ.get("XT_API_KEY", "11bfe446-a063-4ee0-8871-d7ecfd612db6")
secretkeyval = os.environ.get("XT_SECRET_KEY", "f4442716939deb0ff2415e88503d26fc663c2738")
tokenval = os.environ.get("TOKEN", "8763614980:AAGIQXQtT7OkEmehPcaKeDYz6puNUjZeDGU")
chatidval = os.environ.get("CHAT_ID", "")
positionsfile = "active_positions.json"

symbols = ["btc_usdt", "eth_usdt", "sol_usdt", "xrp_usdt", "bnb_usdt", "doge_usdt", "ada_usdt",
           "avax_usdt", "link_usdt", "near_usdt", "dot_usdt", "ltc_usdt", "uni_usdt", "matic_usdt",
           "pepe_usdt", "shib_usdt", "apt_usdt", "ton_usdt", "fet_usdt", "render_usdt", "injective_usdt",
           "sui_usdt", "fil_usdt", "aave_usdt", "arb_usdt", "op_usdt", "xlm_usdt", "trx_usdt", "etc_usdt", "gala_usdt"]

bot = telebot.TeleBot(tokenval)
xt = Perp(host="https://fapi.xt.com", access_key=apikeyval, secret_key=secretkeyval)

datalock = threading.Lock()

def send_alert(message):
    if chatidval and tokenval:
        try:
            bot.send_message(chatidval, message)
        except Exception as e:
            print(f"❌ خطا در ارسال پیام به تلگرام: {e}")

def get_safe_balance():
    try:
        acc = xt.get_account_capital()
        data = acc[1] if isinstance(acc, tuple) and len(acc) > 1 else acc
        if isinstance(data, str):
            data = json.loads(data)
        if isinstance(data, dict):
            result = data.get('result') or data.get('data') or data
            if isinstance(result, list):
                for item in result:
                    if isinstance(item, dict) and str(item.get('coin') or '').lower() in ('usdt', 'usdt_perp'):
                        bal = item.get('walletBalance') or item.get('availableBalance') or item.get('balance')
                        if bal is not None: return float(bal)
            elif isinstance(result, dict):
                bal = result.get('walletBalance') or result.get('availableBalance') or result.get('balance')
                if bal is not None: return float(bal)
        return 0.0
    except Exception as e:
        print(f"🔴 خطای دقیق در دریافت موجودی: {e}")
        return 0.0

def safe_save_json(filepath, data):
    temp_file = filepath + ".tmp"
    try:
        with open(temp_file, 'w') as f:
            json.dump(data, f, indent=4)
        os.replace(temp_file, filepath)
    except Exception as e:
        print(f"⚠️ خطا در ذخیره فایل {filepath}: {e}")
        if os.path.exists(temp_file):
            try: os.remove(temp_file)
            except: pass

class Brain:
    def __init__(self):
        self.file = "brain_data.json"
        self.data = self.load()
    def load(self):
        if os.path.exists(self.file):
            try:
                with open(self.file, 'r') as f: return json.load(f)
            except: pass
        return {"win_rate": 0.5, "total_trades": 0}
    def save(self):
        with datalock:
            safe_save_json(self.file, self.data)
    def learn(self, success):
        with datalock:
            self.data['total_trades'] += 1
            factor = 1 if success else 0
            self.data['win_rate'] = (self.data['win_rate'] * (self.data['total_trades']-1) + factor) / self.data['total_trades']
        self.save()

def load_active_positions():
    if os.path.exists(positionsfile):
        try:
            with open(positionsfile, 'r') as f: return json.load(f)
        except: return {}
    return {}

def save_active_positions():
    with datalock:
        safe_save_json(positionsfile, active_positions)

brain = Brain()
active_positions = load_active_positions()
state = {
    "running": True,
    "capital_percent": 0.3,
    "leverage": 50,
    "daily_stats": {"trades": 0, "pnl": 0.0}
}

class MasterXTBot:
    def get_data(self, symbol):
        try:
            url = "https://fapi.xt.com/future/market/v1/public/q/agg-tickers"
            response = requests.get(url, timeout=5)
            data = response.json()
            result = data.get('result', [])
            for item in result:
                if item.get('s') == symbol:
                    curr_close = float(item.get('c', 0))
                    curr_open = float(item.get('o', curr_close))
                    df = pd.DataFrame({'open': [curr_open], 'close': [curr_close]})
                    return df
            return None
        except Exception as e:
            print(f"⚠️ خطا در دریافت اطلاعات بازار {symbol}: {e}")
            return None

    def analyze(self, df, symbol):
        if df is None or len(df) < 1:
            return None, "داده ناقص است"

        curr_close = float(df['close'].iloc[-1])
        curr_open = float(df['open'].iloc[-1])

        if curr_close >= curr_open:
            return "BUY", f"ورود موفق (قیمت: {curr_close})"

        return None, "کندل نزولی است"

    def execute_trade(self, symbol, reason, price):
        try:
            balance = get_safe_balance()
            if balance < 0.5:
                return

            with datalock:
                cap_percent = state['capital_percent']
                lev = state['leverage']

            # چاپ دقیق ارور تنظیم اهرم در لاگ
            try:
                xt.set_account_leverage(symbol=symbol, leverage=lev)
            except Exception as e:
                print(f"🔴 خطای دقیق تنظیم اهرم برای {symbol}: {e}")

            capital_in_trade = balance * cap_percent
            raw_qty = (capital_in_trade * lev) / price if price > 0 else 0
            quantity = round(raw_qty, 3)
            if quantity <= 0:
                quantity = 0.001

            # چاپ دقیق ارور ارسال سفارش خرید در لاگ
            try:
                xt.send_order(symbol=symbol, orderSide="BUY", orderType="MARKET", quantity=str(quantity), positionSide="LONG")
            except Exception as e:
                print(f"🔴 خطای دقیق ارسال سفارش خرید ({symbol}): {e}")
                try:
                    xt.send_order(symbol=symbol, order_side="BUY", order_type="MARKET", qty=str(quantity), position_side="LONG")
                except Exception as e2:
                    print(f"🔴 خطای دوم ارسال سفارش خرید ({symbol}): {e2}")
            
            tp1 = price * 1.012
            sl = price * 0.990

            with datalock:
                active_positions[symbol] = {"entry": price, "tp1": tp1, "sl": sl, "quantity": quantity}
                state['daily_stats']['trades'] += 1
            
            save_active_positions()
            send_alert(f"🚀 **پوزیشن باز شد!**\n- نماد: {symbol}\n- قیمت: {price}")
        except Exception as e:
            print(f"🔴 خطای کلی در اجرای معامله {symbol}: {e}")

def manage_positions():
    engine = MasterXTBot()
    while True:
        try:
            with datalock:
                current_positions = list(active_positions.items())

            if current_positions:
                for symbol, pos in current_positions:
                    df = engine.get_data(symbol)
                    if df is not None and not df.empty:
                        current_price = float(df.iloc[-1]['close'])
                        entry = pos['entry']
                        sl = pos['sl']
                        tp1 = pos['tp1']
                        quantity = pos['quantity']

                        if current_price <= sl or current_price >= tp1:
                            try:
                                xt.send_order(symbol=symbol, orderSide="SELL", orderType="MARKET", quantity=str(quantity), positionSide="LONG")
                            except Exception as e:
                                print(f"🔴 خطای دقیق بستن سفارش فروش ({symbol}): {e}")
                                try:
                                    xt.send_order(symbol=symbol, order_side="SELL", order_type="MARKET", qty=str(quantity), position_side="LONG")
                                except Exception as e2:
                                    print(f"🔴 خطای دوم بستن سفارش فروش ({symbol}): {e2}")

                            profit = (current_price - entry) * quantity
                            with datalock:
                                state['daily_stats']['pnl'] += profit
                            
                            success = current_price >= tp1
                            brain.learn(success)
                            
                            with datalock:
                                if symbol in active_positions:
                                    del active_positions[symbol]
                            
                            save_active_positions()
                            send_alert(f"🎯 بسته شد - نماد: {symbol} | سود/زیان: {profit:.2f} USDT")
            time.sleep(5)
        except Exception as e:
            print(f"⚠️ خطای حلقه مدیریت پوزیشن‌ها: {e}")
            time.sleep(10)

def trading_loop():
    engine = MasterXTBot()
    while True:
        try:
            with datalock:
                is_running = state['running']

            if is_running:
                for symbol in symbols:
                    with datalock:
                        in_positions = symbol in active_positions

                    if not in_positions:
                        df = engine.get_data(symbol)
                        if df is not None:
                            sig, reason = engine.analyze(df, symbol)
                            if sig == "BUY":
                                engine.execute_trade(symbol, reason, df.iloc[-1]['close'])
                                break
                        time.sleep(0.5)
            time.sleep(5)
        except Exception as e:
            print(f"⚠️ خطای حلقه معاملاتی: {e}")
            time.sleep(10)

def get_reply_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("🟢 شروع ربات"),
        types.KeyboardButton("🛑 توقف اضطراری"),
        types.KeyboardButton("⚙️ تنظیم ریسک و سرمایه"),
        types.KeyboardButton("💰 سود/زیان"),
        types.KeyboardButton("📊 پوزیشن‌ها"),
        types.KeyboardButton("🔍 موجودی"),
        types.KeyboardButton("🟢 وضعیت سیستم هوشمند")
    )
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "🤖 ربات آماده به کار است:", reply_markup=get_reply_keyboard())

@bot.message_handler(func=lambda msg: True)
def handle_text_buttons(message):
    text = message.text
    chat_id = message.chat.id

    if text == "🟢 شروع ربات":
        with datalock:
            state['running'] = True
        bot.send_message(chat_id, "🟢 ربات روشن شد.", reply_markup=get_reply_keyboard())
    elif text == "🛑 توقف اضطراری":
        with datalock:
            state['running'] = False
        bot.send_message(chat_id, "🔴 ربات متوقف شد.", reply_markup=get_reply_keyboard())
    elif text == "⚙️ تنظیم ریسک و سرمایه":
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
        markup.add(
            types.KeyboardButton("سرمایه: 25%"),
            types.KeyboardButton("سرمایه: 50%"),
            types.KeyboardButton("سرمایه: 100%"),
            types.KeyboardButton("اهرم: 10x"),
            types.KeyboardButton("اهرم: 20x"),
            types.KeyboardButton("اهرم: 50x"),
            types.KeyboardButton("اهرم: 100x"),
            types.KeyboardButton("🔙 بازگشت به منوی اصلی")
        )
        with datalock:
            cap_pct = int(state['capital_percent']*100)
            lev = state['leverage']
        bot.send_message(chat_id, f"⚙️ تنظیمات:\n- سرمایه: {cap_pct}%\n- اهرم: {lev}x", reply_markup=markup)
    elif text.startswith("سرمایه: "):
        try:
            val = int(text.replace("سرمایه: ", "").replace("%", ""))
            with datalock:
                state['capital_percent'] = val / 100.0
            bot.send_message(chat_id, f"✅ سرمایه تنظیم شد.", reply_markup=get_reply_keyboard())
        except:
            pass
    elif text.startswith("اهرم: "):
        try:
            val = int(text.replace("اهرم: ", "").replace("x", ""))
            with datalock:
                state['leverage'] = val
            bot.send_message(chat_id, f"✅ اهرم تنظیم شد.", reply_markup=get_reply_keyboard())
        except:
            pass
    elif text == "🔙 بازگشت به منوی اصلی":
        bot.send_message(chat_id, "منوی اصلی:", reply_markup=get_reply_keyboard())
    elif text == "🔍 موجودی":
        bal = get_safe_balance()
        bot.send_message(chat_id, f"💰 موجودی: {bal} USDT", reply_markup=get_reply_keyboard())
    elif text == "💰 سود/زیان":
        with datalock:
            pnl = state['daily_stats']['pnl']
            trades = state['daily_stats']['trades']
        bot.send_message(chat_id, f"📊 آمار:\nمعاملات: {trades}\nسود/زیان: {pnl:.2f} USDT", reply_markup=get_reply_keyboard())
    elif text == "📊 پوزیشن‌ها":
        with datalock:
            positions_snapshot = dict(active_positions)
        if not positions_snapshot:
            bot.send_message(chat_id, "📭 پوزیشنی فعال نیست.", reply_markup=get_reply_keyboard())
        else:
            msg = "📈 پوزیشن‌ها:\n" + "".join([f"- {s}\n" for s in positions_snapshot.keys()])
            bot.send_message(chat_id, msg, reply_markup=get_reply_keyboard())
    elif text == "🟢 وضعیت سیستم هوشمند":
        bot.send_message(chat_id, "🟢 سیستم فعال است.", reply_markup=get_reply_keyboard())

# راه‌اندازی تردهای موازی
threading.Thread(target=trading_loop, daemon=True).start()
threading.Thread(target=manage_positions, daemon=True).start()

if __name__ == "__main__":
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60, remove_webhook=True)
        except Exception as e:
            print(f"⚠️ خطای پولینگ تلگرام: {e}")
            time.sleep(5)
