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
chat_id = os.getenv("CHAT_ID") # یا می‌توانید آیدی عددی چت خود را مستقیماً اینجا وارد کنید
bot = telebot.TeleBot(TELEGRAM_TOKEN) if TELEGRAM_TOKEN else None

class MasterXTBot:
    def __init__(self):
        # کلیدهای اختصاصی صرافی
        self.api_key = "11bfe446-a063-4ee0-8871-d7ecfd612db6"
        self.secret_key = "f4442716939deb0ff2415e88503d26fc663c2738"
        self.history_file = 'trade_history.json'
        
        # راه‌اندازی ارتباط با صرافی XT
        try:
            self.xt_perp = Perp(host="https://fapi.xt.com", access_key=self.api_key, secret_key=self.secret_key)
            self.connection_status, self.connection_msg = self.test_connection()
        except Exception as e:
            self.connection_status = False
            self.connection_msg = f"❌ خطای بحرانی در راه‌اندازی ماژول صرافی: {str(e)}"

        # بارگذاری هوش مصنوعی و وزن‌ها
        self.weights = self.load_intelligence()
        self.active_positions = {} # برای ردیابی پوزیشن‌های باز

    def test_connection(self):
        """تست اتصال به صرافی و بررسی اعتبار حساب"""
        try:
            account_info = self.xt_perp.get_account_capital()
            if account_info:
                return True, "✅ اتصال به صرافی XT با موفقیت برقرار شد و حساب معتبر است."
            return False, "⚠️ اتصال برقرار شد اما صرافی پاسخ خالی داد."
        except Exception as e:
            return False, f"❌ عدم امکان اتصال به صرافی XT. دلیل: {str(e)}"

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
        df['Engulfing'] = ta.cdl_engulfing(df['open'], df['high'], df['low'], df['close'])
        df['Hammer'] = ta.cdl_hammer(df['open'], df['high'], df['low'], df['close'])
        
        rsi_val = df['RSI_14'].iloc[-1]
        current_close = float(df['close'].iloc[-1])
        
        score = (rsi_val * self.weights['RSI']) + \
                (abs(df['Engulfing'].iloc[-1]) * self.weights['Engulfing']) + \
                (abs(df['Hammer'].iloc[-1]) * self.weights['Hammer'])
        
        # تعیین سیگنال خرید یا فروش بر اساس RSI و الگوها
        if rsi_val < 35:
            return {"status": "success", "signal": "BUY", "price": current_close, "score": score, "rationale": "RSI Oversold + Patterns"}
        elif rsi_val > 65:
            return {"status": "success", "signal": "SELL", "price": current_close, "score": score, "rationale": "RSI Overbought + Patterns"}
        
        return {"status": "neutral", "score": score}

    def calculate_position_size(self, balance, risk_percent, stop_loss_dist):
        """۳. مدیریت ریسک (محاسبه خودکار حجم و اهرم)"""
        if stop_loss_dist == 0:
            stop_loss_dist = 1.0
        position_size = (balance * risk_percent) / stop_loss_dist
        leverage = 5 # اهرم پیش‌فرض
        return round(position_size, 4), leverage

    def execute_trade(self, signal, rationale, price):
        """۵. ثبت معامله در صرافی و لاگ‌ها همراه با عیب‌یابی دقیق"""
        if not self.connection_status:
            error_msg = f"❌ معامله انجام نشد زیرا ربات به صرافی متصل نیست: {self.connection_msg}"
            logging.error(error_msg)
            return error_msg

        try:
            # دریافت موجودی حساب برای محاسبه حجم
            account_data = self.xt_perp.get_account_capital()
            available_balance = 10.0 # مقدار پیش‌فرض محافظتی
            if isinstance(account_data, dict):
                res_res = account_data.get("result", account_data)
                available_balance = float(res_res.get("availableBalance") or res_res.get("accountAvailableBalance") or 10.0)

            # محاسبه حجم و اهرم
            amount, leverage = self.calculate_position_size(available_balance, risk_percent=0.02, stop_loss_dist=price * 0.01)
            
            position_side = "LONG" if signal == "BUY" else "SHORT"
            order_side = "BUY" if signal == "BUY" else "SELL"

            # ارسال سفارش به صرافی XT
            order_res = self.xt_perp.send_order(
                symbol="btc_usdt",
                price=price,
                amount=amount,
                order_side=order_side,
                order_type="MARKET",
                position_side=position_side
            )

            # بررسی خطاهای برگشتی از سوی صرافی
            if isinstance(order_res, dict) and order_res.get("rc", 0) != 0:
                error_detail = f"❌ صرافی سفارش را رد کرد. کد خطا: {order_res.get('rc')} | دلیل: {order_res.get('msg', order_res)}"
                logging.error(error_detail)
                return error_detail

            success_msg = f"✅ معامله موفق ({signal}) | حجم: {amount} | قیمت: {price} | دلیل: {rationale}"
            logging.info(success_msg)
            return success_msg

        except Exception as e:
            error_detail = f"❌ خطای غیرمنتظره هنگام باز کردن پوزیشن در صرافی: {str(e)}"
            logging.error(error_detail)
            return error_detail

    def run_bot_loop(self, target_chat_id):
        """حلقه اصلی اجرای ربات و بررسی بازار"""
        if bot and target_chat_id:
            bot.send_message(target_chat_id, f"🤖 وضعیت اتصال اولیه صرافی:\n{self.connection_msg}")

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

                    analysis = self.analyze_market(df)
                    
                    if analysis["status"] == "success":
                        result_msg = self.execute_trade(analysis["signal"], analysis["rationale"], analysis["price"])
                        if bot and target_chat_id:
                            bot.send_message(target_chat_id, result_msg)
                    else:
                        logging.info("بازار خنثی است، سیگنای صادر نشد.")

            except Exception as loop_err:
                err_text = f"⚠️ خطا در حلقه پردازش داده‌های بازار: {str(loop_err)}"
                logging.error(err_text)
                if bot and target_chat_id:
                    bot.send_message(target_chat_id, err_text)

            time.sleep(900) # بررسی هر ۱۵ دقیقه

# راه‌اندازی و اجرا
if __name__ == "__main__":
    bot_core = MasterXTBot()
    print(bot_core.connection_msg)
    
    # اگر خواستید به صورت لوکال یا با تلگرام تست کنید:
    # target_id = "YOUR_CHAT_ID"
    # bot_core.run_bot_loop(target_id)
    
