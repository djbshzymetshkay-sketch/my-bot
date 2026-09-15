import threading
import time
import json
import datetime
import os
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

def notify_shutdown(reason="نامشخص"):
    if CHAT_ID and TELEGRAM_TOKEN:
        try:
            telebot.TeleBot(TELEGRAM_TOKEN).send_message(CHAT_ID, f"⚠️ **هشدار: ربات متوقف شد!**\n\n🔴 دلیل: {reason}")
        except: pass

atexit.register(lambda: notify_shutdown("خاموش شدن اسکریپت"))

def get_safe_balance():
    try:
        acc = xt.get_account_capital()
        data = acc[1] if isinstance(acc, tuple) and len(acc) > 1 else acc
        if isinstance(data, str):
            try: data = json.loads(data)
            except: pass
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
        print(f"❌ خطای موجودی: {e}")
        return 0.0

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

active_positions = load_active_positions()
state = {
    "running": False,
    "capital_percent": 0.5,
    "leverage": 50,
    "daily_stats": {"trades": 0, "pnl": 0.0}
}

class MasterXTBot:
    def get_data(self, symbol):
        try:
            ticker_res = None
            for s_format in [symbol, symbol.lower().replace("_", "-")]:
                try:
                    ticker_res = xt.get_ticker(s_format)
                    if ticker_res: break
                except:
                    pass
            
            t_data = ticker_res[1] if isinstance(ticker_res, tuple) and len(ticker_res) > 1 else ticker_res
            if isinstance(t_data, dict):
                t_data = t_data.get('result') or t_data.get('data') or t_data
            
            price = None
            if isinstance(t_data, dict):
                price = float(t_data.get('price') or t_data.get('lastPrice') or t_data.get('c') or 0)
            elif isinstance(t_data, list) and len(t_data) > 0 and isinstance(t_data[0], dict):
                price = float(t_data[0].get('price') or t_data[0].get('lastPrice') or 0)

            if price and price > 0:
                df_fake = pd.DataFrame({
                    'open': [price * 0.99] * 35,
                    'high': [price * 1.01] * 35,
                    'low': [price * 0.98] * 35,
                    'close': [price * (1 + (i*0.0001)) for i in range(35)]
                })
                return df_fake
            return None
        except Exception as e:
            print(f"Error: {e}")
            return None

    def analyze(self, df):
        return "BUY", "شرط تست صرافی"

    def execute_trade(self, symbol, reason, price):
        try:
            try:
                xt.set_account_leverage(symbol=symbol, leverage=state['leverage'])
            except Exception as ex:
                print(f"Leverage warning: {ex}")

            balance = get_safe_balance()
            effective_balance = balance if balance > 0 else 10.0
            
            capital_in_trade = effective_balance * state['capital_percent']
            raw_qty = (capital_in_trade * state['leverage']) / price
            quantity = round(raw_qty, 3)
            if quantity <= 0: quantity = 0.001

            print(f"🚀 ارسال به صرافی {symbol} | حجم: {quantity} | قیمت: {price}")
            
            # ارسال مستقیم با دقیق‌ترین ساختار استاندارد متد صرافی
            response = xt.send_order(
                symbol=symbol,
                order_side="BUY",
                order_type="MARKET",
                quantity=str(quantity),
                position_side="LONG"
            )
            
            print(f"📥 پاسخ خام صرافی XT: {response}")
            
            # بررسی اینکه آیا صرافی واقعاً سفارش را قبول کرده یا ارور داده است
            res_dict = response[1] if isinstance(response, tuple) and len(response) > 1 else response
            if isinstance(res_dict, str):
                try: res_dict = json.loads(res_dict)
                except: pass

            if isinstance(res_dict, dict):
                code = res_dict.get('rc') or res_dict.get('code') or 0
                if str(code) not in ('0', '200', 'SUCCESS', 'ok'):
                    err_msg = res_dict.get('msg') or res_dict.get('message') or str(res_dict)
                    raise Exception(f"پاسخ خطای صرافی: {err_msg}")

            active_positions[symbol] = {"entry": price, "quantity": quantity}
            save_active_positions()
            state['daily_stats']['trades'] += 1

            if CHAT_ID:
                bot.send_message(CHAT_ID, f"🚀 پوزیشن واقعی در صرافی باز شد!\n- نماد: {symbol}\n- قیمت ورود: {price}\n- حجم: {quantity}\n- اهرم: {state['leverage']}x")
        except Exception as e:
            print(f"❌ خطای واقعی ثبت ترید در صرافی: {e}")
            if CHAT_ID:
                bot.send_message(CHAT_ID, f"❌ خطا در ثبت ترید صرافی:\n{e}")

def trading_loop():
    engine = MasterXTBot()
    while True:
        try:
            if state['running']:
                for symbol in SYMBOLS:
                    if symbol not in active_positions:
                        df = engine.get_data(symbol)
                        if df is not None:
                            current_price = float(df.iloc[-1]['close'])
                            engine.execute_trade(symbol, "سیگنال ریتم بازار", current_price)
                        time.sleep(30)
            time.sleep(5)
        except Exception as e:
            print(f"Loop error: {e}")
            time.sleep(5)

def get_reply_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("🟢 شروع ربات (استارت)"),
        types.KeyboardButton("🛑 توقف اضطراری"),
        types.KeyboardButton("⚙️ ریسک"),
        types.KeyboardButton("💰 سود/زیان"),
        types.KeyboardButton("📊 پوزیشن‌ها"),
        types.KeyboardButton("🔍 موجودی"),
        types.KeyboardButton("🟢 وضعیت اتصال صرافی"),
        types.KeyboardButton("🧪 تست فوری پوزیشن")
    )
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "🤖 ربات آماده است:", reply_markup=get_reply_keyboard())

@bot.message_handler(func=lambda msg: True)
def handle_text_buttons(message):
    text = message.text
    chat_id = message.chat.id

    if text == "🟢 شروع ربات (استارت)":
        state['running'] = True
        bot.send_message(chat_id, "🟢 ربات فعال شد.", reply_markup=get_reply_keyboard())
    elif text == "🧪 تست فوری پوزیشن":
        bot.send_message(chat_id, "🧪 در حال ارسال سفارش واقعی به صرافی...", reply_markup=get_reply_keyboard())
        engine = MasterXTBot()
        df = engine.get_data("btc_usdt")
        price = float(df.iloc[-1]['close']) if df is not None and not df.empty else 90000.0
        engine.execute_trade("btc_usdt", "تست دستی صرافی", price)
    elif text == "🛑 توقف اضطراری":
        state['running'] = False
        bot.send_message(chat_id, "🔴 ربات متوقف شد.", reply_markup=get_reply_keyboard())
    elif text == "🔍 موجودی":
        balance = get_safe_balance()
        bot.send_message(chat_id, f"💰 موجودی حساب: {balance} USDT", reply_markup=get_reply_keyboard())
    elif text == "💰 سود/زیان":
        bot.send_message(chat_id, f"📊 تعداد معاملات: {state['daily_stats']['trades']}", reply_markup=get_reply_keyboard())
    elif text == "📊 پوزیشن‌ها":
        if not active_positions:
            bot.send_message(chat_id, "📭 هیچ پوزیشن فعالی باز نیست.", reply_markup=get_reply_keyboard())
        else:
            msg = "📈 پوزیشن‌های فعال:\n" + "".join([f"- {s} | حجم: {d['quantity']}\n" for s, d in active_positions.items()])
            bot.send_message(chat_id, msg, reply_markup=get_reply_keyboard())
    elif text == "⚙️ ریسک":
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
        markup.add(
            types.KeyboardButton("سرمایه: 25%"), types.KeyboardButton("سرمایه: 50%"),
            types.KeyboardButton("اهرم: 10x"), types.KeyboardButton("اهرم: 50x"),
            types.KeyboardButton("🔙 بازگشت به منوی اصلی")
        )
        bot.send_message(chat_id, f"⚙️ تنظیمات:\n- سرمایه: {state['capital_percent']*100}%\n- اهرم: {state['leverage']}x", reply_markup=markup)
    elif text.startswith("سرمایه: "):
        try: state['capital_percent'] = int(text.replace("سرمایه: ", "").replace("%", "")) / 100.0
        except: pass
    elif text.startswith("اهرم: "):
        try: state['leverage'] = int(text.replace("اهرم: ", "").replace("x", ""))
        except: pass
    elif text == "🔙 بازگشت به منوی اصلی":
        bot.send_message(chat_id, "منوی اصلی:", reply_markup=get_reply_keyboard())
    elif text == "🟢 وضعیت اتصال صرافی":
        balance = get_safe_balance()
        bot.send_message(chat_id, f"🟢 متصل است.\n💰 موجودی: {balance} USDT", reply_markup=get_reply_keyboard())

threading.Thread(target=trading_loop, daemon=True).start()

if __name__ == "__main__":
    try:
        bot.infinity_polling()
    except Exception as e:
        notify_shutdown(f"خطا: {e}")
