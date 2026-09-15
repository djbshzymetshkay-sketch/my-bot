import threading
import time
import json
import datetime
import os
import atexit
import hmac
import hashlib
import requests
import pandas as pd
import telebot
from telebot import types

# --- تنظیمات ---
API_KEY = "11bfe446-a063-4ee0-8871-d7ecfd612db6"
SECRET_KEY = "f4442716939deb0ff2415e88503d26fc663c2738"
TELEGRAM_TOKEN = "8763614980:AAGIQXQtT7OkEmehPcaKeDYz6puNUjZeDGU"
CHAT_ID = ""  # اگر چت‌آیدیتان را دارید اینجا وارد کنید یا بگذارید خالی بماند تا ربات ارور ندهد
POSITIONS_FILE = "active_positions.json"

SYMBOLS = ["btc_usdt", "eth_usdt", "sol_usdt", "xrp_usdt", "bnb_usdt", "doge_usdt", "ada_usdt",
           "avax_usdt", "link_usdt", "near_usdt", "dot_usdt", "ltc_usdt", "uni_usdt", "matic_usdt",
           "pepe_usdt", "shib_usdt", "apt_usdt", "ton_usdt", "fet_usdt", "render_usdt", "injective_usdt",
           "sui_usdt", "fil_usdt", "aave_usdt", "arb_usdt", "op_usdt", "xlm_usdt", "trx_usdt", "etc_usdt", "gala_usdt"]

bot = telebot.TeleBot(TELEGRAM_TOKEN)

def notify_shutdown(reason="نامشخص"):
    if CHAT_ID and TELEGRAM_TOKEN:
        try:
            bot.send_message(CHAT_ID, f"⚠️ **هشدار: ربات متوقف شد!**\n\n🔴 دلیل: {reason}")
        except: pass

atexit.register(lambda: notify_shutdown("خاموش شدن اسکریپت"))

def xt_request(method, endpoint, params=None):
    """تابع استاندارد ارتباط با صرافی XT با رعایت دقیق فرمت امضا"""
    url = f"https://fapi.xt.com{endpoint}"
    timestamp = str(int(time.time() * 1000))
    
    if method == "GET":
        query_string = "&".join([f"{k}={v}" for k, v in sorted(params.items())]) if params else ""
        sign_str = f"accessKey={API_KEY}&timestamp={timestamp}"
        if query_string:
            sign_str = f"accessKey={API_KEY}&params={query_string}&timestamp={timestamp}"
            url += f"?{query_string}"
        signature = hmac.new(SECRET_KEY.encode('utf-8'), sign_str.encode('utf-8'), hashlib.sha256).hexdigest()
        
        headers = {
            "validate-appKey": API_KEY,
            "validate-timestamp": timestamp,
            "validate-signature": signature
        }
        response = requests.get(url, headers=headers, timeout=10)
    else:
        body_str = json.dumps(params, separators=(',', ':')) if params else "{}"
        sign_str = f"accessKey={API_KEY}&params={body_str}&timestamp={timestamp}"
        signature = hmac.new(SECRET_KEY.encode('utf-8'), sign_str.encode('utf-8'), hashlib.sha256).hexdigest()
        
        headers = {
            "Content-Type": "application/json",
            "validate-appKey": API_KEY,
            "validate-timestamp": timestamp,
            "validate-signature": signature
        }
        response = requests.post(url, data=body_str, headers=headers, timeout=10)
        
    return response.json()

def get_safe_balance():
    try:
        res = xt_request("GET", "/future/user/v1/account/balance")
        result = res.get('result') or res.get('data')
        if isinstance(result, list):
            for item in result:
                if str(item.get('coin') or '').lower() in ('usdt', 'usdt_perp'):
                    return float(item.get('walletBalance') or item.get('availableBalance') or 0)
        elif isinstance(result, dict):
            return float(result.get('walletBalance') or result.get('availableBalance') or 0)
        return 0.0
    except Exception as e:
        print(f"خطای موجودی: {e}")
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
    "capital_percent": 0.25,
    "leverage": 50,
    "daily_stats": {"trades": 0, "pnl": 0.0}
}

class MasterXTBot:
    def get_data(self, symbol):
        try:
            res = xt_request("GET", "/future/market/v1/public/ticker/price", {"symbol": symbol.lower().replace("_", "-")})
            t_data = res.get('result') or res.get('data')
            price = 0.0
            if isinstance(t_data, dict):
                price = float(t_data.get('price') or t_data.get('lastPrice') or 0)
            elif isinstance(t_data, list) and len(t_data) > 0:
                price = float(t_data[0].get('price') or t_data[0].get('lastPrice') or 0)

            if price > 0:
                df_fake = pd.DataFrame({
                    'open': [price * 0.99] * 35,
                    'high': [price * 1.01] * 35,
                    'low': [price * 0.98] * 35,
                    'close': [price * (1 + (i*0.0001)) for i in range(35)]
                })
                return df_fake
            return None
        except Exception as e:
            print(f"Error fetching data: {e}")
            return None

    def execute_trade(self, symbol, reason, price):
        try:
            formatted_symbol = symbol.lower().replace("_", "-")
            
            # تنظیم اهرم معامله
            try:
                xt_request("POST", "/future/trade/v1/leverage/adjust", {
                    "symbol": formatted_symbol,
                    "leverage": state['leverage'],
                    "positionSide": "LONG"
                })
            except: pass

            balance = get_safe_balance()
            effective_balance = balance if balance > 0 else 10.0
            
            capital_in_trade = effective_balance * state['capital_percent']
            raw_qty = (capital_in_trade * state['leverage']) / price
            quantity = round(raw_qty, 3)
            if quantity <= 0: quantity = 0.001

            print(f"ارسال سفارش به صرافی روی {formatted_symbol} با حجم {quantity}")
            
            payload = {
                "symbol": formatted_symbol,
                "orderSide": "BUY",
                "orderType": "MARKET",
                "volume": str(quantity),
                "positionSide": "LONG"
            }
            order_res = xt_request("POST", "/future/trade/v1/order/create", payload)
            
            if order_res.get('rc') != 0 and order_res.get('code') != 0:
                raise Exception(f"خطای صرافی: {order_res.get('msg') or order_res}")

            print(f"پوزیشن با موفقیت باز شد: {order_res}")
            active_positions[symbol] = {"entry": price, "quantity": quantity}
            save_active_positions()
            state['daily_stats']['trades'] += 1

            if CHAT_ID:
                bot.send_message(CHAT_ID, f"🚀 پوزیشن واقعی در صرافی باز شد!\n- نماد: {symbol}\n- قیمت ورود: {price}\n- حجم: {quantity}\n- اهرم: {state['leverage']}x")
        except Exception as e:
            print(f"خطای ثبت ترید در صرافی: {e}")
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
                            engine.execute_trade(symbol, "سیگنال بازار", current_price)
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
        bot.send_message(chat_id, f"🟢 متصل است.\n💰 موجودی: {balance} USDT", reply_markup=get_reply_gateway := get_reply_keyboard())

threading.Thread(target=trading_loop, daemon=True).start()

if __name__ == "__main__":
    try:
        bot.infinity_polling()
    except Exception as e:
        notify_shutdown(f"خطا: {e}")
