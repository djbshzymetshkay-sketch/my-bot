import threading
import time
import json
import datetime
import os
import sys
import atexit
import pandas as pd
import pandas_ta as ta  # برای محاسبات دقیق اندیکاتورها
import telebot
from telebot import types
from pyxt.perp import Perp

# --- ۱. پیکربندی و تنظیمات اولیه ---
API_KEY = os.environ.get("XT_API_KEY", "your_api_key_here")
SECRET_KEY = os.environ.get("XT_SECRET_KEY", "your_secret_key_here")
TELEGRAM_TOKEN = os.environ.get("TOKEN", "your_bot_token_here")
CHAT_ID = os.environ.get("CHAT_ID", "your_chat_id_here")

SYMBOLS = ["btc_usdt", "eth_usdt", "sol_usdt", "xrp_usdt", "bnb_usdt", "doge_usdt", "ada_usdt",
           "avax_usdt", "link_usdt", "near_usdt", "dot_usdt", "ltc_usdt", "uni_usdt", "matic_usdt",
           "pepe_usdt", "shib_usdt", "apt_usdt", "ton_usdt", "fet_usdt", "render_usdt", "injective_usdt",
           "sui_usdt", "fil_usdt", "aave_usdt", "arb_usdt", "op_usdt", "xlm_usdt", "trx_usdt", "etc_usdt", "gala_usdt"]

bot = telebot.TeleBot(TELEGRAM_TOKEN)
xt = Perp(host="https://fapi.xt.com", access_key=API_KEY, secret_key=SECRET_KEY)

POSITIONS_FILE = "active_positions.json"

# سیستم خروج امن برای جلوگیری از کرش در Railway
def notify_shutdown(reason="نامشخص"):
    if CHAT_ID:
        try:
            bot.send_message(CHAT_ID, f"⚠️ **هشدار: ربات متوقف شد!**\n\n🔴 دلیل: {reason}")
        except: pass

atexit.register(lambda: notify_shutdown("بسته شدن سیستم"))

# --- ۲. مدیریت حافظه و وضعیت ---
def load_active_positions():
    if os.path.exists(POSITIONS_FILE):
        try:
            with open(POSITIONS_FILE, 'r') as f: return json.load(f)
        except: return {}
    return {}

def save_active_positions(positions):
    with open(POSITIONS_FILE, 'w') as f: json.dump(positions, f)

active_positions = load_active_positions()

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
        with open(self.file, 'w') as f: json.dump(self.data, f)
    def learn(self, success):
        self.data['total_trades'] += 1
        factor = 1 if success else 0
        self.data['win_rate'] = (self.data['win_rate'] * (self.data['total_trades']-1) + factor) / self.data['total_trades']
        self.save()

brain = Brain()

state = {
    "running": True,
    "capital_percent": 0.5, 
    "leverage": 50,
    "daily_stats": {"trades": 0, "pnl": 0.0}
}

def get_safe_balance():
    try:
        acc = xt.get_account_capital()
        data = acc[1] if isinstance(acc, tuple) else acc
        if isinstance(data, dict):
            res = data.get('result') or data.get('data') or data
            if isinstance(res, list) and len(res) > 0:
                for item in res:
                    if item.get('coin', '').lower() in ['usdt', 'usdt_perp']:
                        return float(item.get('walletBalance', 0))
            elif isinstance(res, dict):
                for k, v in res.items():
                    if isinstance(v, dict) and v.get('coin', '').lower() in ['usdt', 'usdt_perp']:
                        return float(v.get('walletBalance', 0))
                return float(res.get('walletBalance', 0))
        return 0.0
    except Exception as e:
        print(f"❌ [Error] Balance Error: {e}")
        return 0.0

# --- ۳. کلاس اصلی ربات و استراتژی ---
class MasterXTBot:
    def __init__(self):
        self.is_trading = True

    def get_data(self, symbol):
        try:
            res = xt.get_kline(symbol, interval='5m', limit=300)
            if not res: return None
            df_raw = res[1] if isinstance(res, tuple) else res
            if isinstance(df_raw, dict): df_raw = df_raw.get('result') or df_raw.get('data') or df_raw
            if not df_raw: return None
            
            df = pd.DataFrame(df_raw)
            df['close'] = df['close'].astype(float)
            df['high'] = df['high'].astype(float)
            df['low'] = df['low'].astype(float)
            df['open'] = df['open'].astype(float)
            
            df['ema9'] = ta.ema(df['close'], length=9)
            df['ema21'] = ta.ema(df['close'], length=21)
            df['ema200'] = ta.ema(df['close'], length=200)
            df['rsi'] = ta.rsi(df['close'], length=14)
            return df
        except Exception as e:
            print(f"❌ [Data Error] {symbol}: {e}")
            return None

    def analyze_signals(self, symbol):
        df = self.get_data(symbol)
        if df is None or len(df) < 200: return None

        last = df.iloc[-1]
        prev = df.iloc[-2]
        curr_price = last['close']
        
        # استراتژی ترکیبی: CrossUp + Trend Filter (EMA200) + Momentum Filter (RSI)
        long_condition = (
            prev['ema9'] <= prev['ema21'] and 
            last['ema9'] > last['ema21'] and 
            curr_price > last['ema200'] and 
            40 < last['rsi'] < 70
        )

        exit_condition = (curr_price < last['ema21'] or last['rsi'] > 80)

        if long_condition: return "LONG"
        if exit_condition: return "EXIT"
        return None

    def trading_loop(self):
        print("🚀 [System] Trading Loop Started...")
        while state["running"]:
            try:
                for symbol in SYMBOLS:
                    if not state["running"]: break
                    
                    signal = self.analyze_signals(symbol)
                    if signal == "LONG" and symbol not in active_positions:
                        self.execute_trade(symbol, "LONG")
                    elif signal == "EXIT" and symbol in active_positions:
                        self.close_position(symbol)
                time.sleep(60) 
            except Exception as e:
                print(f"❌ [Loop Error] {e}")
                time.sleep(30)

    def execute_trade(self, symbol, side):
        try:
            balance = get_safe_balance()
            if balance <= 0: return
            df = self.get_data(symbol)
            price = df.iloc[-1]['close']
            amount_usdt = balance * state["capital_percent"]
            qty = amount_usdt / price

            # ارسال سفارش واقعی به صرافی XT (اطمینان از ساختار استاندارد متد send_order)
            xt.send_order(symbol=symbol, orderSide="BUY", orderType="MARKET", quantity=str(round(qty, 4)), positionSide="LONG")
            
            active_positions[symbol] = {
                "side": side, "entry_price": price, "qty": qty,
                "leverage": state["leverage"], "time": str(datetime.datetime.now())
            }
            save_active_positions(active_positions)
            bot.send_message(CHAT_ID, f"✅ **پوزیشن جدید باز شد!**\n\n💎 Symbol: `{symbol}`\n📈 Side: {side}\n💰 Entry: {price}\n⚙️ Leverage: {state['leverage']}x", parse_mode="Markdown")
            print(f"🚀 [TRADE] {symbol} {side} executed.")
        except Exception as e:
            print(f"❌ [Trade Error] {symbol}: {e}")

    def close_position(self, symbol):
        try:
            pos = active_positions[symbol]
            # بستن پوزیشن در صرافی XT
            xt.send_order(symbol=symbol, orderSide="SELL", orderType="MARKET", quantity=str(round(pos['qty'], 4)), positionSide="LONG")
            
            del active_positions[symbol]
            save_active_positions(active_positions)
            bot.send_message(CHAT_ID, f"🏁 **پوزیشن بسته شد!**\n\n💎 Symbol: `{symbol}`\n💰 Exit logic triggered.", parse_mode="Markdown")
            print(f"🛑 [EXIT] {symbol} position closed.")
        except Exception as e:
            print(f"❌ [Close Error] {symbol}: {e}")

# --- ۴. کنترل تلگرام و دستورات ---
@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("📊 وضعیت ربات", "💰 موجودی")
    markup.add("⚙️ تنظیمات", "🛑 توقف")
    bot.reply_to(message, "سلام امیر! MasterXT آماده است. 🚀", reply_markup=markup)

@bot.message_handler(func=lambda m: True)
def handle_msg(message):
    if message.text == "📊 وضعیت ربات":
        msg = f"🤖 **وضعیت سیستم:**\n\n🔄 Running: {'✅' if state['running'] else '❌'}\n💵 Capital: {state['capital_percent']*100}%\n🚀 Leverage: {state['leverage']}x"
        bot.send_message(message.chat.id, msg, parse_mode="Markdown")
    elif message.text == "💰 موجودی":
        bal = get_safe_balance()
        bot.send_message(message.chat.id, f"💵 موجودی: `{bal:.2f} USDT`", parse_mode="Markdown")
    elif message.text == "⚙️ تنظیمات":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("تغییر اهرم", callback_data="set_lev"),
                   types.InlineKeyboardButton("تغییر درگیری سرمایه", callback_data="set_cap"))
        bot.send_message(message.chat.id, "تنظیمات مدیریت ریسک:", reply_markup=markup)
    elif message.text == "🛑 توقف":
        state["running"] = False
        bot.send_message(message.chat.id, "⚠️ در حال توقف ربات...")

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.data == "set_lev":
        msg = bot.send_message(call.message.chat.id, "اهرم جدید (1-125):")
        bot.register_next_step_handler(msg, update_leverage)
    elif call.data == "set_cap":
        msg = bot.send_message(call.message.chat.id, "درگیری سرمایه (0.1 برای 10٪):")
        bot.register_next_step_handler(msg, update_capital)

def update_leverage(m):
    try:
        v = int(m.text)
        if 1 <= v <= 125: 
            state["leverage"] = v
            bot.send_message(m.chat.id, f"✅ اهرم: {v}x")
        else: bot.send_message(m.chat.id, "❌ خطا")
    except: bot.send_message(m.chat.id, "❌ خطا")

def update_capital(m):
    try:
        v = float(m.text)
        if 0.01 <= v <= 1.0:
            state["capital_percent"] = v
            bot.send_message(m.chat.id, f"✅ سرمایه: {v*100}%")
        else: bot.send_message(m.chat.id, "❌ خطا")
    except: bot.send_message(m.chat.id, "❌ خطا")

# --- ۵. نقطه شروع اجرای برنامه ---
def run_bot():
    master = MasterXTBot()
    threading.Thread(target=master.trading_loop, daemon=True).start()
    print("🤖 [System] Telegram Bot is polling...")
    bot.infinity_polling()

if __name__ == "__main__":
    print(f"🚀 MasterXTBot V2.6 Starting... | {datetime.datetime.now()}")
    try:
        run_bot()
    except Exception as e:
        print(f"🔥 [FATAL] {e}")
        notify_shutdown(str(e))
        sys.exit(1)
