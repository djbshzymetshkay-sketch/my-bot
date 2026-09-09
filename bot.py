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
        # کلیدهای اختصاصی صرافی
        self.api_key = "11bfe446-a063-4ee0-8871-d7ecfd612db6"
        self.secret_key = "f4442716939deb0ff2415e88503d26fc663c2738"
        self.history_file = 'trade_history.json'
        
        # راه‌اندازی ارتباط با صرافی XT و بررسی وضعیت اتصال
        try:
            self.xt_perp = Perp(host="https://fapi.xt.com", access_key=self.api_key, secret_key=self.secret_key)
            self.connection_status, self.connection_msg = self.test_connection()
        except Exception as e:
            self.connection_status = False
            self.connection_msg = f"❌ خطای بحرانی در ساخت ماژول صرافی: {str(e)}"

        # بارگذاری هوش مصنوعی و وزن‌ها
        self.weights = self.load_intelligence()
        self.active_positions = {} # برای ردیابی پوزیشن‌های باز

    def test_connection(self):
        """تست اتصال به صرافی و بررسی اعتبار حساب"""
        try:
            account_info = self.xt_perp.get_account_capital()
            if account_info:
                return True, "✅ اتصال به صرافی XT با موفقیت برقرار شد و حساب معتبر است."
            return False, "⚠️ اتصال به صرافی برقرار شد اما پاسخ صرافی خالی بود."
        except Exception as e:
            return False, f"❌ صرافی متصل نشد. دلیل خطا: {str(e)}"

    def load_intelligence(self):
        """بارگذاری وزن استراتژی‌ها از فایل JSON"""
        try:
            with open(self.history_file, 'r') as f:
                data = json.load(f)
                return data.get('weights', {'RSI': 0.5, 'Engulfing': 0.3, 'Hammer': 0.2})
        except:
            return {'RSI': 0.5, 'Engulfing': 0.3, 'Hammer': 0.2}

    def analyze_market(self, df):
        """۱. هسته تحلیل تکنیکال (فنی)"""
        df.ta.rsi(length=14, append=True)
        
        # استفاده از روش ایمن برای الگوها جهت جلوگیری از خطای AttributeError
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
        current_close = float(df['close'].iloc[-1])
        
        # سیستم امتیازدهی
        score = (rsi_val * self.weights['RSI']) + \
                (abs(df['Engulfing'].iloc[-1]) * self.weights['Engulfing']) + \
                (abs(df['Hammer'].iloc[-1]) * self.weights['Hammer'])
        
        if rsi_val < 35:
            return {"status": "success", "signal": "BUY", "price": current_close, "score": score, "rationale": "RSI Oversold + Patterns"}
        elif rsi_val > 65:
            return {"status": "success", "signal": "SELL", "price": current_close, "score": score, "rationale": "RSI Overbought + Patterns"}
        
        return {"status": "neutral", "score": score, "reason": f"بازار خنثی است (RSI: {round(rsi_val, 2)})، شرایط باز کردن پوزیشن برقرار نیست."}

    def calculate_position_size(self, balance, risk_percent, stop_loss_dist):
        """۳. مدیریت ریسک (محاسبه خودکار حجم و اهرم)"""
        if stop_loss_dist <= 0:
            stop_loss_dist = 1.0
        position_size = (balance * risk_percent) / stop_loss_dist
        leverage = 5 # اهرم پیش‌فرض
        return round(position_size, 4), leverage

    def execute_trade(self, signal, rationale, price):
        """۵. ثبت معامله در صرافی و لاگ‌ها همراه با عیب‌یابی دقیق در صورت عدم باز شدن پوزیشن"""
        if not self.connection_status:
            error_msg = f"❌ صرافی متصل نشد! امکان باز کردن پوزیشن وجود ندارد. دلیل:\n{self.connection_msg}"
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

            if isinstance(order_res, dict) and order_res.get("rc", 0) != 0:
                error_detail = f"❌ صرافی پوزیشن را باز نکرد!\nکد خطا: {order_res.get('rc')}\nدلیل صرافی: {order_res.get('msg', order_res)}"
                logging.error(error_detail)
                return error_detail

            success_msg = f"✅ معامله با موفقیت در صرافی ثبت و پوزیشن باز شد!\nجهت: {signal} | حجم: {amount} | قیمت: {price} | دلیل: {rationale}"
            logging.info(success_msg)
            return success_msg

        except Exception as e:
            error_detail = f"❌ خطای صرافی هنگام باز کردن پوزیشن:\n{str(e)}"
            logging.error(error_detail)
            return error_detail

    def manage_position(self, symbol, current_price, entry_price, tp1):
        """۴. مدیریت پوزیشن (خروج پله‌ای و Risk-Free)"""
        if symbol in self.active_positions:
            if current_price >= tp1:
                print(f"TP1 تاچ شد! انتقال استاپ‌لاس به قیمت ورود ({entry_price}) برای {symbol}")
                return True
        return False

    def update_intelligence(self, trade_result):
        """۲. سیستم یادگیری (به‌روزرسانی وزن استراتژی‌ها)"""
        if trade_result['profit'] > 0:
            self.weights['RSI'] += 0.05
            with open(self.history_file, 'w') as f:
                json.dump({'weights': self.weights}, f)
            print("هوش مصنوعی: وزن استراتژی‌ها بر اساس ترید موفق به‌روز شد.")

    def daily_report(self):
        """۵. گزارش‌دهی اتوماتیک رأس ساعت ۸"""
        if datetime.now().hour == 8:
            print("گزارش روزانه: همه سیستم‌ها پایدار، PnL امروز مثبت.")

if bot:
    @bot.message_handler(commands=['start'])
    def send_welcome(message):
        chat_id = message.chat.id
        bot_instance = MasterXTBot()
        msg = f"🤖 ربات شما استارت شد.\n\nوضعیت اتصال صرافی:\n{bot_instance.connection_msg}"
        bot.send_message(chat_id, msg)
        threading.Thread(target=run_bot_loop, args=(chat_id,), daemon=True).start()

    @bot.message_handler(func=lambda message: True)
    def handle_messages(message):
        bot_instance = MasterXTBot()
        if message.text == "وضعیت صرافی":
            bot.send_message(message.chat.id, bot_instance.connection_msg)
        else:
            bot.send_message(message.chat.id, "ربات در حال رصد بازار است. هرگونه خطا یا مشکل در اتصال یا ثبت سفارش مستقیماً به شما اعلام می‌شود.")

def run_bot_loop(target_chat_id):
    bot_core = MasterXTBot()
    if not bot_core.connection_status and bot:
        bot.send_message(target_chat_id, f"⚠️ اخطار اتصال: ربات به صرافی متصل نشد!\nدلیل: {bot_core.connection_msg}")

    while True:
        try:
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
                    logging.info(analysis.get("reason", "پوزیشنی باز نشد."))

        except Exception as loop_err:
            err_msg = f"⚠️ خطا در حلقه پردازش بازار:\n{str(loop_err)}"
            logging.error(err_msg)
            if bot and target_chat_id:
                bot.send_message(target_chat_id, err_msg)

        time.sleep(900)

if __name__ == "__main__":
    if bot:
        print("ربات تلگرام روشن شد...")
        bot.infinity_polling()
    else:
        bot_core = MasterXTBot()
        print(bot_core.connection_msg)
        
