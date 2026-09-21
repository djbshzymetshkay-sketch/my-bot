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
import telebot
from telebot import types
from pyxt.perp import Perp

# --- پیکربندی ---
apikeyval = os.environ.get("XT_API_KEY", "11bfe446-a063-4ee0-8871-d7ecfd612db6")
secretkeyval = os.environ.get("XT_SECRET_KEY", "f4442716939deb0ff2415e88503d26fc663c2738")
tokenval = os.environ.get("TOKEN")
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
            bot.send_message(chatidval, message, parse_mode="Markdown")
        except Exception:
            try:
                bot.send_message(chatidval, message)
            except:
                pass

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
        send_alert(f"⚠️ خطا در دریافت موجودی حساب:\n`{str(e)}`")
        return 0.0

def safe_save_json(filepath, data):
    temp_file = filepath + ".tmp"
    try:
        with open(temp_file, 'w') as f:
            json.dump(data, f, indent=4)
        os.replace(temp_file, filepath)
    except Exception as e:
        send_alert(f"⚠️ خطا در ذخیره فایل اطلاعات:\n`{str(e)}`")
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
        except Exception as e:
            send_alert(f"⚠️ خطا در خواندن پوزیشن‌های فعال:\n`{str(e)}`")
            return {}
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
            # از فرستادن خطای مکرر اینترنت در این بخش جلوگیری شده تا تلگرام اسپم نشود
            return None

    def analyze(self, df, symbol):
        if df is None or len(df) < 1:
            return None, "داده ناقص است"

        curr_close = float(df['close'].iloc[-1])
        curr_open = float(df['open'].iloc[-1])
        percent_change = ((curr_close - curr_open) / curr_open) * 100

        if percent_change >= 0.05:
            return "BUY", f"صعودی (+{percent_change:.2f}%)"
        elif percent_change <= -0.05:
            return "SELL", f"نزولی ({percent_change:.2f}%)"

        return None, "روند خنثی"

    def execute_trade(self, symbol, signal_type, reason, price):
        try:
            balance = get_safe_balance()
            if balance < 0.5:
                err_msg = f"⚠️ خطای معامله {symbol}: موجودی کافی نیست یا صفر است ({balance} USDT)"
                print(err_msg)
                send_alert(err_msg)
                return False

            with datalock:
                cap_percent = state['capital_percent']
                lev = state['leverage']

            try:
                if hasattr(xt, 'set_account_leverage'):
                    xt.set_account_leverage(symbol=symbol, leverage=lev)
            except Exception as e:
                print(f"Leverage warning: {e}")

            capital_in_trade = balance * cap_percent
            raw_qty = (capital_in_trade * lev) / price if price > 0 else 0
            quantity = round(raw_qty, 3)
            if quantity <= 0:
                quantity = 0.001

            position_side = "LONG" if signal_type == "BUY" else "SHORT"
            order_side = "BUY" if signal_type == "BUY" else "SELL"

            order_sent = False
            last_error = None
            
            # استفاده از کلمه درست order_side که از طریق لاگ به دست آمد
            kwargs = {
                "symbol": symbol,
                "order_side": order_side,
                "order_type": "MARKET",
                "quantity": str(quantity),
                "position_side": position_side
            }
            
            try:
                res = xt.send_order(**kwargs)
                if res:
                    order_sent = True
            except Exception as e:
                last_error = str(e)

            if not order_sent:
                err_msg = f"❌ خطای صرافی در باز کردن #{symbol.upper().replace('_', '/')}:\n`{last_error}`"
                print(err_msg)
                send_alert(err_msg)
                return False

            if signal_type == "BUY":
                tp1 = price * 1.010
                tp2 = price * 1.020
                tp3 = price * 1.030
                sl = price * 0.985
            else:
                tp1 = price * 0.990
                tp2 = price * 0.980
                tp3 = price * 0.970
                sl = price * 1.015

            with datalock:
                active_positions[symbol] = {
                    "entry": price, 
                    "tp1": tp1, 
                    "sl": sl, 
                    "quantity": quantity, 
                    "type": signal_type
                }
                state['daily_stats']['trades'] += 1
            
            save_active_positions()

            sym_clean = symbol.upper().replace('_', '/')
            side_text = "LONG 🟢" if signal_type == "BUY" else "SHORT 🔴"
            
            msg = (
                f"#{sym_clean}\n"
                f"{side_text}\n\n"
                f"📍 ENTRY : NOW ( market ) {price}\n\n"
                f"🛑 SL : {sl}\n"
                f"✅ TP :\n"
                f"  1️⃣ {tp1}\n"
                f"  2️⃣ {tp2}\n"
                f"  3️⃣ {tp3}\n\n"
                f"⚡ LEVERAGE : {lev}X\n"
                f"💬 دلیل: {reason}"
            )
            send_alert(msg)
            return True
        except Exception as e:
            err_msg = f"❌ خطای کلی در اجرای تابع معامله برای {symbol}:\n`{str(e)}`"
            print(err_msg)
            send_alert(err_msg)
            return False

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
                        pos_type = pos.get('type', 'BUY')

                        hit_exit = False
                        if pos_type == 'BUY':
                            if current_price <= sl or current_price >= tp1:
                                hit_exit = True
                        else: # SHORT
                            if current_price >= sl or current_price <= tp1:
                                hit_exit = True

                        if hit_exit:
                            close_side = "SELL" if pos_type == 'BUY' else "BUY"
                            close_pos_side = "LONG" if pos_type == 'BUY' else "SHORT"
                            
                            close_kwargs = {
                                "symbol": symbol,
                                "order_side": close_side,
                                "order_type": "MARKET",
                                "quantity": str(quantity),
                                "position_side": close_pos_side
                            }
                            
                            try:
                                xt.send_order(**close_kwargs)
                            except Exception as e:
                                send_alert(f"⚠️ خطا در بستن پوزیشن {symbol}:\n`{str(e)}`")

                            if pos_type == 'BUY':
                                profit = (current_price - entry) * quantity
                            else:
                                profit = (entry - current_price) * quantity

                            with datalock:
                                state['daily_stats']['pnl'] += profit
                            
                            success = profit > 0
                            brain.learn(success)
                            
                            with datalock:
                                if symbol in active_positions:
                                    del active_positions[symbol]
                            
                            save_active_positions()

                            sym_clean = symbol.upper().replace('_', '/')
                            status_emoji = "🟢 سود" if profit >= 0 else "🔴 زیان"
                            close_msg = (
                                f"🎯 **پوزیشن بسته شد**\n"
                                f"📌 نماد: #{sym_clean}\n"
                                f"📊 وضعیت: {status_emoji}\n"
                                f"💰 سود/زیان: `{profit:.2f} USDT`\n"
                                f"🏁 قیمت خروج: {current_price}"
                            )
                            send_alert(close_msg)
            time.sleep(5)
        except Exception as e:
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
                            if sig in ["BUY", "SELL"]:
                                opened = engine.execute_trade(symbol, sig, reason, df.iloc[-1]['close'])
                                if opened:
                                    break
                        time.sleep(0.5)
            time.sleep(5)
        except Exception as e:
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
    bot.send_message(message.chat.id, "🤖 ربات حرفه‌ای آماده است:", reply_markup=get_reply_keyboard())

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
        except Exception as e:
            bot.send_message(chat_id, f"⚠️ خطا در تنظیم سرمایه: {e}")
    elif text.startswith("اهرم: "):
        try:
            val = int(text.replace("اهرم: ", "").replace("x", ""))
            with datalock:
                state['leverage'] = val
            bot.send_message(chat_id, f"✅ اهرم تنظیم شد.", reply_markup=get_reply_keyboard())
        except Exception as e:
            bot.send_message(chat_id, f"⚠️ خطا در تنظیم اهرم: {e}")
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
            bot.send_message(chat_id, f"📭 پوزیشنی فعال نیست.", reply_markup=get_reply_keyboard())
        else:
            msg = "📈 پوزیشن‌ها:\n" + "".join([f"- {s} ({p.get('type')})\n" for s, p in positions_snapshot.items()])
            bot.send_message(chat_id, msg, reply_markup=get_reply_keyboard())
    elif text == "🟢 وضعیت سیستم هوشمند":
        bot.send_message(chat_id, "🟢 سیستم فعال و آماده به کار است.", reply_markup=get_reply_keyboard())

# راه‌اندازی تردهای موازی
threading.Thread(target=trading_loop, daemon=True).start()
threading.Thread(target=manage_positions, daemon=True).start()

if __name__ == "__main__":
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            # ارسال خطای قطع اتصال ربات تلگرام
            try:
                send_alert(f"⚠️ خطای پولینگ تلگرام:\n`{str(e)}`")
            except:
                pass
            time.sleep(5)
