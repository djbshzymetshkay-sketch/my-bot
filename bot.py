import threading
import time
import json
import datetime
import os
import sys
import atexit
import hmac
import hashlib
import time as ttime
import requests
import pandas as pd
import pandas_ta as ta
import telebot
from telebot import types

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
BASE_URL = "https://fapi.xt.com"

def get_signature(path, query_string="", body_string=""):
    timestamp = str(int(ttime.time() * 1000))
    raw = f"{timestamp}{path}{query_string}{body_string}"
    signature = hmac.new(SECRET_KEY.encode('utf-8'), raw.encode('utf-8'), hashlib.sha256).hexdigest()
    return timestamp, signature

def get_xt_headers(path, query_string="", body_string=""):
    timestamp, signature = get_signature(path, query_string, body_string)
    return {
        "access-key": API_KEY,
        "timestamp": timestamp,
        "signature": signature,
        "Content-Type": "application/json"
    }

def get_safe_balance():
    try:
        path = "/future/user/v1/balance"
        url = f"{BASE_URL}{path}"
        headers = get_xt_headers(path)
        res = requests.get(url, headers=headers, timeout=10)
        
        print(f"🔥 [HTTP Status]: {res.status_code}")
        print(f"🔥 [Raw Text Response]: {res.text}")
        
        data = res.json()
        result_data = data.get('result') or data.get('data') or data
        
        if isinstance(result_data, list):
            for item in result_data:
                coin = str(item.get('coin') or item.get('currency') or item.get('asset') or '').lower()
                bal = float(item.get('walletBalance') or item.get('availableBalance') or item.get('balance') or item.get('equity') or 0)
                if coin == 'usdt' or 'usdt' in coin:
                    if bal > 0: return bal
            for item in result_data:
                bal = float(item.get('walletBalance') or item.get('availableBalance') or item.get('balance') or 0)
                if bal > 0: return bal
        elif isinstance(result_data, dict):
            for k, v in result_data.items():
                if isinstance(v, dict):
                    bal = float(v.get('walletBalance') or v.get('balance') or v.get('equity') or 0)
                    if bal > 0: return bal
            bal = float(result_data.get('walletBalance') or result_data.get('balance') or 0)
            if bal > 0: return bal
            
        return 0.0
    except Exception as e:
        print(f"🔥 [Exception in balance]: {e}")
        return 0.0

def send_xt_order(symbol, side, quantity):
    try:
        path = "/future/trade/v1/order/create"
        body = {
            "symbol": symbol,
            "orderSide": side.upper(),
            "orderType": "MARKET",
            "quantity": str(quantity),
            "positionSide": "LONG"
        }
        body_str = json.dumps(body)
        headers = get_xt_headers(path, body_string=body_str)
        res = requests.post(f"{BASE_URL}{path}", headers=headers, data=body_str, timeout=10)
        print(f"Order response for {symbol}: {res.text}")
        res.raise_for_status()
        return res.json()
    except Exception as e:
        print(f"Order error {symbol}: {e}")
        raise e

def set_xt_leverage(symbol, leverage):
    try:
        path = "/future/trade/v1/position/leverage"
        body = {"symbol": symbol, "leverage": int(leverage)}
        body_str = json.dumps(body)
        headers = get_xt_headers(path, body_string=body_str)
        requests.post(f"{BASE_URL}{path}", headers=headers, data=body_str, timeout=10)
    except Exception as e:
        print(f"Leverage error {symbol}: {e}")

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

POSITIONS_FILE = "active_positions.json"
def load_active_positions():
    if os.path.exists(POSITIONS_FILE):
        try:
            with open(POSITIONS_FILE, 'r') as f: return json.load(f)
        except Exception: return {}
    return {}

def save_active_positions():
    try:
        with open(POSITIONS_FILE, 'w') as f: json.dump(active_positions, f)
    except Exception: pass

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
            data = res.get('result') or res.get('data') or res
            if not isinstance(data, list) or not data: return None
            df = pd.DataFrame(data)
            if df.empty: return None
            if 'c' in df.columns: df['close'] = df['c'].astype(float)
            elif 'close' in df.columns: df['close'] = df['close'].astype(float)
            elif len(df.columns) >= 5: df['close'] = df.iloc[:, 4].astype(float)
            else: return None
            return df
        except Exception: return None

    def analyze(self, df):
        if df is None or len(df) < 25 or 'close' not in df.columns: return None, ""
        close = df['close']
        ema9 = close.ewm(span=9, adjust=False).mean()
        ema21 = close.ewm(span=21, adjust=False).mean()
        if (ema9.iloc[-2] <= ema21.iloc[-2]) and (ema9.iloc[-1] > ema21.iloc[-1]):
            return "BUY", "EMA9/21 CrossUp"
        return None, ""

    def execute_trade(self, symbol, reason, price):
        try:
            set_xt_leverage(symbol, state['leverage'])
            balance = get_safe_balance()
            capital_in_trade = (balance if balance > 0 else 10.0) * state['capital_percent']
            quantity = (capital_in_trade * state['leverage']) / price if price > 0 else 0
            
            send_xt_order(symbol, "BUY", quantity)

            tp1 = price * 1.01
            tp2 = price * 1.02
            tp3 = price * 1.03
            sl = price * 0.98
            
            active_positions[symbol] = {"entry": price, "tp1": tp1, "tp2": tp2, "tp3": tp3, "sl": sl, "quantity": quantity}
            save_active_positions()
            state['daily_stats']['trades'] += 1
            
            if CHAT_ID:
                bot.send_message(CHAT_ID, f"🚀 پوزیشن جدید: {symbol}\n💰 ورود: {price}\n⚡️ اهرم: {state['leverage']}x")
        except Exception as e:
            if CHAT_ID:
                bot.send_message(CHAT_ID, f"❌ خطای ترید {symbol}: {e}")

def manage_positions():
    engine = MasterXTBot()
    while True:
        try:
            if active_positions:
                for symbol, pos in list(active_positions.items()):
                    df = engine.get_data(symbol)
                    if df is not None and not df.empty:
                        current_price = float(df.iloc[-1]['close'])
                        entry, sl, tp1, quantity = pos['entry'], pos['sl'], pos['tp1'], pos['quantity']
                        if current_price <= sl or current_price >= tp1:
                            side = "SELL"
                            send_xt_order(symbol, side, quantity)
                            del active_positions[symbol]
                            save_active_positions()
            time.sleep(5)
        except Exception: time.sleep(10)

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
                            if price_val > 0: engine.execute_trade(symbol, reason, price_val)
                    time.sleep(0.5)
            time.sleep(2)
        except Exception: time.sleep(5)

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
    bot.send_message(message.chat.id, "🤖 MasterXTBot فعال شد:", reply_markup=get_reply_keyboard())

@bot.message_handler(func=lambda msg: True)
def handle_text_buttons(message):
    text, chat_id = message.text, message.chat.id
    if text == "🛑 توقف اضطراری":
        state['running'] = False
        bot.send_message(chat_id, "🔴 ربات متوقف شد.", reply_markup=get_reply_keyboard())
    elif text == "🔍 موجودی" or text == "🟢 وضعیت اتصال صرافی":
        balance = get_safe_balance()
        bot.send_message(chat_id, f"💰 موجودی کیف پول: {balance} USDT", reply_markup=get_reply_keyboard())
    elif text == "🔄 ریست اتصال (رفع Conflict)":
        try:
            bot.remove_webhook()
        except Exception: pass
        bot.send_message(chat_id, "🔄 ریست انجام شد.", reply_markup=get_reply_keyboard())
    else:
        bot.send_message(chat_id, "دستور دریافت شد.", reply_markup=get_reply_keyboard())

threading.Thread(target=trading_loop, daemon=True).start()
threading.Thread(target=manage_positions, daemon=True).start()

if __name__ == "__main__":
    while True:
        try:
            try:
                bot.remove_webhook()
            except Exception: pass
            time.sleep(1)
            bot.infinity_polling(timeout=60, long_polling_timeout=30, skip_pending=True)
        except Exception as e:
            print(f"Polling warning/crash handled: {e}")
            time.sleep(5)
