import os
import threading
import time
import json
import logging
from datetime import datetime
import pandas as pd
import pandas_ta as ta
import requests
import telebot
from pyxt.perp import Perp

# تنظیمات لاگ‌نویسی
logging.basicConfig(filename='bot_logs.log', level=logging.INFO, format='%(asctime)s - %(message)s')

TELEGRAM_TOKEN = os.getenv("TOKEN")
bot = telebot.TeleBot(TELEGRAM_TOKEN) if TELEGRAM_TOKEN else None

class MasterXTBot:
    def __init__(self):
        self.api_key = "11bfe446-a063-4ee0-8871-d7ecfd612db6"
        self.secret_key = "f4442716939deb0ff2415e88503d26fc663c2738"
        self.history_file = 'trade_history.json'
        
        try:
            self.xt_perp = Perp(host="https://fapi.xt.com", access_key=self.api_key, secret_key=self.secret_key)
            self.connection_status, self.connection_msg = self.test_connection()
        except Exception as e:
            self.connection_status = False
            self.connection_msg = f"❌ خطای بحرانی در ساخت ماژول صرافی: {str(e)}"

        self.weights = self.load_intelligence()
        self.active_positions = {}

    def test_connection(self):
        try:
            account_info = self.xt_perp.get_account_capital()
            if account_info:
                return True, "✅ اتصال به صرافی XT با موفقیت برقرار شد و حساب معتبر است."
            return False, "⚠️ اتصال به صرافی برقرار شد اما پاسخ صرافی خالی بود."
        except Exception as e:
            return False, f"❌ صرافی متصل نشد. دلیل خطا: {str(e)}"

    def load_intelligence(self):
        try:
            with open(self.history_file, 'r') as f:
                data = json.load(f)
                return data.get('weights', {'RSI': 0.5, 'Engulfing': 0.3, 'Hammer': 0.2})
        except:
            return {'RSI': 0.5, 'Engulfing': 0.3, 'Hammer': 0.2}

    def analyze_market(self, df):
        df.ta.rsi(length=14, append=True)
        
        try:
            engulfing_res = ta.cdl_pattern(df['open'], df['high'], df['low'], df['close'], name='engulfing')
            df['Engulfing'] = engulfing_res.iloc[:, 0] if engulfing_res is not None else 0
        except:
            df['Engulfing'] = 0

        try:
            hammer_res = ta.cdl_pattern(df['open'], df['high'], df['low'], df['close'], name='hammer')
            df['Hammer'] = hammer_res.iloc[:, 0] if hammer_res is not None else 0
        except:
            df['Hammer'] = 0
        
        rsi_val = df['RSI_14'].iloc[-1]
        engulfing_val = df['Engulfing'].iloc[-1]
        hammer_val = df['Hammer'].iloc[-1]
        current_close = float(df['close'].iloc[-1])
        
        score = (rsi_val * self.weights['RSI']) + \
                (abs(engulfing_val) * self.weights['Engulfing']) + \
                (abs(hammer_val) * self.weights['Hammer'])
        
        # اصلاح شرط‌ها برای اطمینان از اینکه الگوها به‌درستی ارزیابی می‌شوند
        # (توجه: الگوهای کندل‌استیک در pandas_ta مقادیری غیر از صفر برمی‌گردانند وقتی تشکیل شوند)
        if rsi_val < 40 and engulfing_val != 0:
            return {"status": "success", "signal": "BUY", "price": current_close, "score": score, "rationale": "RSI Oversold + Engulfing Pattern"}
        elif rsi_val > 60 and engulfing_val != 0:
            return {"status": "success", "signal": "SELL", "price": current_close, "score": score, "rationale": "RSI Overbought + Engulfing Pattern"}
        elif rsi_val < 40 and hammer_val != 0:
            return {"status": "success", "signal": "BUY", "price": current_close, "score": score, "rationale": "RSI Oversold + Hammer Pattern"}
        elif rsi_val > 60 and hammer_val != 0:
            return {"status": "success", "signal": "SELL", "price": current_close, "score": score, "rationale": "RSI Overbought + Hammer Pattern"}
        
        return {"status": "neutral", "score": score, "reason": f"بازار فاقد الگوی تاییدیه است (RSI: {round(rsi_val, 2)}, Engulfing: {engulfing_val}, Hammer: {hammer_val})"}

    def calculate_position_size(self, balance, risk_percent, stop_loss_dist):
        if stop_loss_dist <= 0:
            stop_loss_dist = 1.0
        position_size = (balance * risk_percent) / stop_loss_dist
        leverage = 5
        return round(position_size, 4), leverage

    def execute_trade(self, signal, rationale, price):
        if not self.connection_status:
            error_msg = f"❌ صرافی متصل نشد! امکان باز کردن پوزیشن وجود ندارد."
            logging.error(error_msg)
            return error_msg

        try:
            account_data = self.xt_perp.get_account_capital()
            available_balance = 10.0
            if isinstance(account_data, dict):
                res_res = account_data.get("result", account_data)
                available_balance = float(res_res.get("availableBalance") or res_res.get("accountAvailableBalance") or 10.0)

            amount, leverage = self.calculate_position_size(available_balance, risk_percent=0.02, stop_loss_dist=price * 0.01)
            
            position_side = "LONG" if signal == "BUY" else "SHORT"
            order_side = "BUY" if signal == "BUY" else "SELL"

            order_res = self.xt_perp.send_order(
                symbol="btc_usdt",
                price=price,
                amount=amount,
                order_side=order_side,
                order_type="MARKET",
                position_side=position_side
            )

            if isinstance(order_res, dict):
                rc_code = order_res.get("rc", order_res.get("code", 0))
                if rc_code != 0 and rc_code != "0" and rc_code != "SUCCESS":
                    return f"❌ صرافی پوزیشن را رد کرد:\n{order_res.get('msg', order_res)}"
            elif not order_res:
                return "❌ صرافی پاسخی برای ثبت سفارش برنگرداند."

            return f"✅ معامله ثبت و پوزیشن باز شد!\nجهت: {signal} | حجم: {amount} | قیمت: {price} | دلیل: {rationale}"

        except Exception as e:
            return f"❌ خطای صرافی هنگام باز کردن پوزیشن:\n{str(e)}"

if bot:
    @bot.message_handler(commands=['start'])
    def send_welcome(message):
        chat_id = message.chat.id
        bot_instance = MasterXTBot()
        msg = f"🤖 ربات شما استارت شد و فعال است.\n\nوضعیت اتصال صرافی:\n{bot_instance.connection_msg}"
        bot.send_message(chat_id, msg)
        threading.Thread(target=run_bot_loop, args=(chat_id,), daemon=True).start()

def run_bot_loop(target_chat_id):
    bot_core = MasterXTBot()
    offline_start_time = None
    loop_counter = 0

    while True:
        try:
            # اگر قبلا قطع بوده و الان وصل شده، مدت قطعی را حساب کن و بفرست
            if offline_start_time is not None:
                downtime_duration = (datetime.now() - offline_start_time).total_seconds() / 3600
                hours = int(downtime_duration)
                minutes = int((downtime_duration - hours) * 60)
                if bot and target_chat_id:
                    bot.send_message(target_chat_id, f"⚠️ اینترنت یا سرور مجدداً وصل شد!\nمدت زمان قطعی/خاموش بودن ربات: حدود {hours} ساعت و {minutes} دقیقه.")
                offline_start_time = None

            url = "https://fapi.xt.com/future/market/v1/public/q/kline?symbol=btc_usdt&interval=15m&limit=30"
            response = requests.get(url, timeout=10)
            data = response.json()

            if response.status_code == 200 and "result" in data:
                candles = data["result"]
                df = pd.DataFrame([{
                    "open": float(c["o"]),
                    "high": float(c["h"]),
                    "low": float(c["l"]),
                    "close": float(c["c"]),
                    "volume": float(c.get("v", 0))
                } for c in candles])

                analysis = bot_core.analyze_market(df)
                
                if analysis["status"] == "success":
                    result_msg = bot_core.execute_trade(analysis["signal"], analysis["rationale"], analysis["price"])
                    if bot and target_chat_id:
                        bot.send_message(target_chat_id, result_msg)
                else:
                    # گزارش دوره‌ای هر ۱۰ دقیقه یک‌بار (هر حلقه ۶۰۰ ثانیه یعنی ۱۰ دقیقه)
                    loop_counter += 1
                    if loop_counter >= 1 and bot and target_chat_id:
                        bot.send_message(target_chat_id, f"🔍 بررسی بازار (هر ۱۰ دقیقه):\n{analysis.get('reason')}\nوضعیت: ربات روشن و در حال رصد است.")
                        loop_counter = 0

        except Exception as loop_err:
            # اگر اینترنت قطع شود یا خطایی رخ دهد، زمان شروع قطعی ثبت می‌شود
            if offline_start_time is None:
                offline_start_time = datetime.now()
            logging.error(f"خطای ارتباطی: {str(loop_err)}")

        # زمان استراحت بین هر بررسی (۶۰۰ ثانیه = ۱۰ دقیقه)
        time.sleep(600)

if __name__ == "__main__":
    if bot:
        print("ربات تلگرام روشن شد...")
        bot.infinity_polling()
    else:
        bot_core = MasterXTBot()
        print(bot_core.connection_msg)
        
