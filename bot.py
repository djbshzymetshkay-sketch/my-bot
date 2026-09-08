import os
import time
import hmac
import hashlib
import threading
import requests
import telebot
from telebot import types
from datetime import datetime

# --- توکن تلگرام و کلیدهای صرافی ---
TELEGRAM_TOKEN = os.getenv("TOKEN")
XT_API_KEY = "c25d4d1a-b496-4c2a-a8ee-599cee26b975"
XT_SECRET_KEY = "e8b8bc8b8d3ee498ac71194becd6498ecc2f67bd"

bot = telebot.TeleBot(TELEGRAM_TOKEN)
XT_BASE_URL = "https://fapi.xt.com"

daily_stats = {
    "signals_opened": 0,
    "total_profit": 0.0,
    "total_loss": 0.0,
    "trades": []
}

def get_xt_signature(secret_key, message):
    return hmac.new(secret_key.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).hexdigest()

def test_xt_connection():
    try:
        path = "/future/user/balance"
        url = XT_BASE_URL + path
        timestamp = str(int(time.time() * 1000))
        
        # مرتب‌سازی پارامترها برای ساخت امضای دقیق فیوچرز XT
        params_str = f"timestamp={timestamp}"
        signature = get_xt_signature(XT_SECRET_KEY, params_str)
        
        headers = {
            "xt-app-id": XT_API_KEY,
            "xt-access-key": XT_API_KEY,
            "xt-sig": signature,
            "xt-timestamp": timestamp,
            "Content-Type": "application/json"
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        
        if response.status_code == 200 and data.get("returnCode") == 0:
            return True, "ارتباط با صرافی XT برقرار است و حساب آماده معامله است."
        else:
            return False, f"خطا از صرافی XT: {data.get('retMsg', data.get('msg', 'پاسخ نامعتبر'))}"
    except Exception as e:
        return False, f"خطای شبکه: {str(e)}"

def place_real_xt_order(symbol, direction, price):
    try:
        path = "/future/trade/order/create"
        url = XT_BASE_URL + path
        timestamp = str(int(time.time() * 1000))
        
        payload = {
            "symbol": symbol,
            "orderType": "1",
            "entrustType": "1",
            "bizType": "1",
            "positionSide": "1" if direction == "BUY" else "2",
            "side": "1" if direction == "BUY" else "2",
            "vol": "0.002"
        }
        
        body_str = f"bizType=1&entrustType=1&orderType=1&positionSide={payload['positionSide']}&side={payload['side']}&symbol={symbol}&timestamp={timestamp}&vol=0.002"
        signature = get_xt_signature(XT_SECRET_KEY, body_str)
        
        headers = {
            "xt-app-id": XT_API_KEY,
            "xt-access-key": XT_API_KEY,
            "xt-sig": signature,
            "xt-timestamp": timestamp,
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        response = requests.post(url, headers=headers, data=payload, timeout=10)
        res_data = response.json()
        
        if response.status_code == 200 and res_data.get("returnCode") == 0:
            return {"returnCode": 0, "msg": "معامله واقعی با موفقیت در صرافی ثبت شد."}
        else:
            return {"returnCode": -1, "msg": res_data.get("retMsg", "خطای صرافی")}
    except Exception as e:
        return {"returnCode": -1, "msg": str(e)}

def analyze_market_optimized():
    try:
        url = f"{XT_BASE_URL}/future/market/kline?symbol=btc_usdt&interval=15m&limit=5"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if response.status_code == 200 and "result" in data:
            candles = data["result"]
            last_candle = candles[-1]
            open_price = float(last_candle[1])
            close_price = float(last_candle[4])
            current_price = close_price
            
            if close_price >= open_price:
                trend = "صعودی (Bullish)"
                action = "BUY"
                reason = "تایید مومنتوم صعودی در کندل ۱۵ دقیقه‌ای."
                tp = round(current_price * 1.01, 2)
                sl = round(current_price * 0.995, 2)
            else:
                trend = "نزولی (Bearish)"
                action = "SELL"
                reason = "فشار فروش در کندل ۱۵ دقیقه‌ای."
                tp = round(current_price * 0.99, 2)
                sl = round(current_price * 1.005, 2)
                
            return {
                "status": "success", "trend": trend, "action": action,
                "price": current_price, "reason": reason, "tp": tp, "sl": sl
            }
        return {"status": "error", "message": "داده‌ای دریافت نشد."}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def execute_auto_trade(chat_id):
    global daily_stats
    while True:
        try:
            analysis = analyze_market_optimized()
            if analysis["status"] == "success":
                action = analysis["action"]
                price = analysis["price"]
                trend = analysis["trend"]
                reason = analysis["reason"]
                tp = analysis["tp"]
                sl = analysis["sl"]
                
                order_res = place_real_xt_order("btc_usdt", action, price)
                daily_stats["signals_opened"] += 1
                
                if chat_id:
                    msg = (
                        f"🚀 **معامله خودکار جدید باز شد!**\n\n"
                        f"📈 روند: {trend}\n🎯 جهت: {action}\n💲 ورود: {price}\n"
                        f"🟢 حد سود: {tp}\n🔴 حد ضرر: {sl}\n📡 صرافی: {order_res['msg']}"
                    )
                    bot.send_message(chat_id, msg)
            time.sleep(900)
        except Exception as e:
            print(f"Error: {str(e)}")
            time.sleep(60)

def nightly_report_scheduler(chat_id):
    global daily_stats
    while True:
        now = datetime.now()
        if now.hour == 21 and now.minute == 0:
            if chat_id:
                report = f"🌙 **گزارش شبانه (ساعت ۲۱:۰۰)**\n\nتعداد کل معاملات امروز: {daily_stats['signals_opened']}"
                bot.send_message(chat_id, report)
            time.sleep(3600)
        else:
            time.sleep(30)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    success, conn_msg = test_xt_connection()
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("وضعیت اتصال صرافی"), types.KeyboardButton("تحلیل لحظه‌ای بازار"), types.KeyboardButton("آمار معاملات امروز"))
    
    bot.send_message(message.chat.id, f"سلام! ربات متصل شد.\n\nوضعیت صرافی: {conn_msg}", reply_markup=markup)
    threading.Thread(target=execute_auto_trade, args=(message.chat.id,), daemon=True).start()
    threading.Thread(target=nightly_report_scheduler, args=(message.chat.id,), daemon=True).start()

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    global daily_stats
    if message.text == "وضعیت اتصال صرافی":
        success, msg = test_xt_connection()
        bot.send_message(message.chat.id, f"✅ {msg}" if success else f"❌ {msg}")
    elif message.text == "تحلیل لحظه‌ای بازار":
        res = analyze_market_optimized()
        if res["status"] == "success":
            bot.send_message(message.chat.id, f"📊 تحلیل (15m):\nروند: {res['trend']}\nسیگنال: {res['action']}\nقیمت: {res['price']}")
        else:
            bot.send_message(message.chat.id, "خطا در دریافت تحلیل.")
    elif message.text == "آمار معاملات امروز":
        bot.send_message(message.chat.id, f"📈 آمار امروز: {daily_stats['signals_opened']} معامله")
    else:
        bot.send_message(message.chat.id, "لطفاً از دکمه‌ها استفاده کنید.")

if __name__ == "__main__":
    print("Bot is running...")
    bot.infinity_polling()
        
