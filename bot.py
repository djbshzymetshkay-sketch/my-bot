import os
import time
import hmac
import hashlib
import threading
import requests
import telebot
from telebot import types
from datetime import datetime

# --- خواندن توکن از ریلی‌وی و کلیدهای صرافی از داخل کد ---
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
        
        try:
            data = response.json()
        except:
            return False, f"پاسخ خام غیرقابل پردازش از صرافی: {response.text}"
        
        # بررسی وضعیت و نمایش دلیل دقیق در صورت بروز خطا
        if response.status_code == 200 and data.get("returnCode") == 0:
            return True, "اتصال با موفقیت برقرار شد و حساب آماده است."
        else:
            err_code = data.get("returnCode", response.status_code)
            err_msg = data.get("retMsg") or data.get("msg") or str(data)
            return False, f"کد خطا: {err_code} | دلیل صرافی: {err_msg}"
            
    except Exception as e:
        return False, f"خطای ارتباط شبکه: {str(e)}"

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
            return {"returnCode": 0, "msg": "معامله با موفقیت ثبت شد."}
        else:
            err_msg = res_data.get("retMsg") or res_data.get("msg") or "خطای ناشناخته"
            return {"returnCode": -1, "msg": err_msg}
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
                return {"status": "success", "trend": "صعودی", "action": "BUY", "price": current_price, "tp": round(current_price * 1.01, 2), "sl": round(current_price * 0.995, 2)}
            else:
                return {"status": "success", "trend": "نزولی", "action": "SELL", "price": current_price, "tp": round(current_price * 0.99, 2), "sl": round(current_price * 1.005, 2)}
        return {"status": "error"}
    except:
        return {"status": "error"}

def execute_auto_trade(chat_id):
    global daily_stats
    while True:
        try:
            analysis = analyze_market_optimized()
            if analysis["status"] == "success":
                action = analysis["action"]
                price = analysis["price"]
                order_res = place_real_xt_order("btc_usdt", action, price)
                daily_stats["signals_opened"] += 1
                
                if chat_id:
                    msg = f"🚀 معامله خودکار ثبت شد!\nجهت: {action}\nقیمت: {price}\nنتیجه: {order_res['msg']}"
                    bot.send_message(chat_id, msg)
            time.sleep(900)
        except:
            time.sleep(60)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    success, conn_msg = test_xt_connection()
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("وضعیت اتصال صرافی"), types.KeyboardButton("تحلیل لحظه‌ای بازار"), types.KeyboardButton("آمار معاملات امروز"))
    
    bot.send_message(message.chat.id, f"سلام! ربات روشن شد.\n\nوضعیت: {conn_msg}", reply_markup=markup)
    threading.Thread(target=execute_auto_trade, args=(message.chat.id,), daemon=True).start()

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    global daily_stats
    if message.text == "وضعیت اتصال صرافی":
        success, msg = test_xt_connection()
        bot.send_message(message.chat.id, f"✅ {msg}" if success else f"❌ {msg}")
    elif message.text == "تحلیل لحظه‌ای بازار":
        res = analyze_market_optimized()
        if res["status"] == "success":
            bot.send_message(message.chat.id, f"📊 روند: {res['trend']} | سیگنال: {res['action']} | قیمت: {res['price']}")
        else:
            bot.send_message(message.chat.id, "خطا در دریافت تحلیل بازار.")
    elif message.text == "آمار معاملات امروز":
        bot.send_message(message.chat.id, f"📈 آمار امروز: {daily_stats['signals_opened']} معامله")
    else:
        bot.send_message(message.chat.id, "لطفاً از دکمه‌ها استفاده کنید.")

if __name__ == "__main__":
    bot.infinity_polling()
        
