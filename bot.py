import os
import time
import hmac
import hashlib
import threading
import requests
import telebot
from telebot import types
from datetime import datetime

TELEGRAM_TOKEN = os.getenv("TOKEN")
XT_API_KEY = "c25d4d1a-b496-4c2a-a8ee-599cee26b975"
XT_SECRET_KEY = "e8b8bc8b8d3ee498ac71194becd6498ecc2f67bd"

bot = telebot.TeleBot(TELEGRAM_TOKEN)
XT_BASE_URL = "https://fapi.xt.com"

daily_stats = {
    "signals_opened": 0,
    "successful_trades": 0,
    "failed_trades": 0,
    "consecutive_losses": 0,
    "trades_history": []
}

def get_xt_signature(secret_key, message):
    return hmac.new(secret_key.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).hexdigest()

def test_xt_connection():
    try:
        path = "/future/user/v1/balance/list"
        url = XT_BASE_URL + path
        timestamp = str(int(time.time() * 1000))
        
        query_string = f"timestamp={timestamp}"
        signature_payload = f"Y=#{path}#{query_string}"
        signature = get_xt_signature(XT_SECRET_KEY, signature_payload)
        
        headers = {
            "validate-appkey": XT_API_KEY,
            "validate-timestamp": timestamp,
            "validate-singature": signature,
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        
        try:
            data = response.json()
        except Exception:
            return False, f"پاسخ نامعتبر از سرور (متن خام): {response.text}"
        
        if response.status_code == 200 and data.get("returnCode") == 0:
            return True, "اتصال به صرافی با موفقیت برقرار شد و حساب فعال است."
        else:
            err_code = data.get("returnCode", response.status_code)
            err_msg = data.get("retMsg") or data.get("msg") or str(data)
            return False, f"خطای صرافی -> کد: {err_code} | دلیل: {err_msg}"
            
    except Exception as e:
        return False, f"خطای شبکه یا ارتباط با اینترنت: {str(e)}"

def place_real_xt_order(symbol, direction, price):
    try:
        path = "/future/trade/v1/order/create"
        url = XT_BASE_URL + path
        timestamp = str(int(time.time() * 1000))
        
        volume = "0.002"
        if daily_stats["consecutive_losses"] >= 2:
            volume = "0.001"
            
        payload = {
            "symbol": symbol,
            "orderType": "1",
            "entrustType": "1",
            "bizType": "1",
            "positionSide": "1" if direction == "BUY" else "2",
            "side": "1" if direction == "BUY" else "2",
            "vol": volume
        }
        
        body_str = f"bizType=1&entrustType=1&orderType=1&positionSide={payload['positionSide']}&side={payload['side']}&symbol={symbol}&timestamp={timestamp}&vol={volume}"
        signature_payload = f"Y=#{path}#{body_str}"
        signature = get_xt_signature(XT_SECRET_KEY, signature_payload)
        
        headers = {
            "validate-appkey": XT_API_KEY,
            "validate-timestamp": timestamp,
            "validate-singature": signature,
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        response = requests.post(url, headers=headers, data=payload, timeout=10)
        res_data = response.json()
        
        if response.status_code == 200 and res_data.get("returnCode") == 0:
            return {"returnCode": 0, "msg": f"سفارش موفق با حجم {volume} ثبت شد."}
        else:
            err_code = res_data.get("returnCode", response.status_code)
            err_msg = res_data.get("retMsg") or res_data.get("msg") or str(res_data)
            return {"returnCode": -1, "msg": f"کد خطا: {err_code} | دلیل صرافی: {err_msg}"}
    except Exception as e:
        return {"returnCode": -1, "msg": f"خطای سیستمی ثبت سفارش: {str(e)}"}

def advanced_smart_market_analysis():
    try:
        url = f"{XT_BASE_URL}/future/market/v1/public/contract/kline?symbol=btc_usdt&interval=15m&limit=15"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if response.status_code == 200 and "result" in data:
            candles = data["result"]
            closes = [float(c[4]) for c in candles]
            opens = [float(c[1]) for c in candles]
            current_price = closes[-1]
            prev_close = closes[-2]
            prev_open = opens[-2]
            
            is_bullish_engulfing = (prev_close < prev_open) and (current_price > opens[-1]) and (closes[-1] > prev_open)
            is_bearish_engulfing = (prev_close > prev_open) and (current_price < opens[-1]) and (closes[-1] < prev_open)
            
            sma_short = sum(closes[-5:]) / 5
            sma_long = sum(closes[-15:]) / 15
            
            if is_bullish_engulfing or (sma_short > sma_long and current_price >= closes[-2]):
                return {
                    "status": "success", "trend": "صعودی (Bullish)", "action": "BUY",
                    "price": current_price, "reason": "تشخیص الگوی برگشتی / تایید روند صعودی",
                    "tp": round(current_price * 1.012, 2), "sl": round(current_price * 0.994, 2)
                }
            elif is_bearish_engulfing or (sma_short < sma_long and current_price <= closes[-2]):
                return {
                    "status": "success", "trend": "نزولی (Bearish)", "action": "SELL",
                    "price": current_price, "reason": "تشخیص فشار فروش / تایید روند نزولی",
                    "tp": round(current_price * 0.988, 2), "sl": round(current_price * 1.006, 2)
                }
            else:
                return {"status": "neutral", "message": "بازار در حالت خنثی یا تثبیت است."}
        return {"status": "error", "message": f"خطای دریافت اطلاعات کندل از صرافی (کد وضعیت: {response.status_code})"}
    except Exception as e:
        return {"status": "error", "message": f"خطای استثنا در تحلیل بازار: {str(e)}"}

def execute_auto_trade(chat_id):
    global daily_stats
    while True:
        try:
            analysis = advanced_smart_market_analysis()
            if analysis["status"] == "success":
                action = analysis["action"]
                price = analysis["price"]
                trend = analysis["trend"]
                reason = analysis["reason"]
                tp = analysis["tp"]
                sl = analysis["sl"]
                
                order_res = place_real_xt_order("btc_usdt", action, price)
                
                if order_res["returnCode"] == 0:
                    daily_stats["signals_opened"] += 1
                    daily_stats["successful_trades"] += 1
                    daily_stats["consecutive_losses"] = 0
                    
                    if chat_id:
                        msg = (
                            f"🚀 **معامله خودکار موفق ثبت شد!**\n\n"
                            f"📈 روند: {trend}\n🎯 جهت: {action}\n💲 قیمت: {price}\n"
                            f"💡 استراتژی: {reason}\n🟢 حد سود: {tp}\n🔴 حد ضرر: {sl}"
                        )
                        bot.send_message(chat_id, msg, parse_mode="Markdown")
                else:
                    daily_stats["failed_trades"] += 1
                    daily_stats["consecutive_losses"] += 1
                    if chat_id:
                        bot.send_message(chat_id, f"⚠️ **خطا در اجرای معامله خودکار:**\n{order_res['msg']}", parse_mode="Markdown")
            elif analysis["status"] == "error" and chat_id:
                bot.send_message(chat_id, f"⚠️ **خطای تحلیل بازار:** {analysis['message']}")
                
            time.sleep(900)
        except Exception as e:
            if chat_id:
                bot.send_message(chat_id, f"⚠️ **خطای بحرانی در بخش اتوماتیک:** {str(e)}")
            time.sleep(60)

def nightly_report_scheduler(chat_id):
    global daily_stats
    while True:
        now = datetime.now()
        if now.hour == 21 and now.minute == 0:
            if chat_id:
                report = (
                    f"🌙 **گزارش عملکرد ۲۴ ساعته ربات**\n\n"
                    f"📊 کل سیگنال‌ها: {daily_stats['signals_opened']}\n"
                    f"✅ معاملات موفق: {daily_stats['successful_trades']}\n"
                    f"❌ خطاها/ناموفق: {daily_stats['failed_trades']}\n"
                    f"⚖️ سطح ریسک: {'محافظه‌کارانه' if daily_stats['consecutive_losses'] >= 2 else 'عادی'}"
                )
                bot.send_message(chat_id, report, parse_mode="Markdown")
            time.sleep(3600)
        else:
            time.sleep(30)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    success, conn_msg = test_xt_connection()
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("وضعیت اتصال صرافی"), types.KeyboardButton("تحلیل لحظه‌ای بازار"), types.KeyboardButton("آمار معاملات امروز"))
    
    status_icon = "✅" if success else "❌"
    bot.send_message(message.chat.id, f"سلام! ربات روشن شد.\n\n{status_icon} {conn_msg}", reply_markup=markup)
    
    threading.Thread(target=execute_auto_trade, args=(message.chat.id,), daemon=True).start()
    threading.Thread(target=nightly_report_scheduler, args=(message.chat.id,), daemon=True).start()

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    global daily_stats
    if message.text == "وضعیت اتصال صرافی":
        success, msg = test_xt_connection()
        bot.send_message(message.chat.id, f"✅ {msg}" if success else f"❌ {msg}")
    elif message.text == "تحلیل لحظه‌ای بازار":
        res = advanced_smart_market_analysis()
        if res["status"] == "success":
            bot.send_message(message.chat.id, f"📊 تحلیل بازار:\nروند: {res['trend']}\nپیشنهاد: {res['action']}\nدلیل: {res['reason']}\nقیمت: {res['price']}")
        else:
            bot.send_message(message.chat.id, f"📌 {res.get('message', 'بازار در حال انتظار است.')}")
    elif message.text == "آمار معاملات امروز":
        stats_msg = (
            f"📈 **آمار عملکرد:**\n\n"
            f"تعداد کل سیگنال‌ها: {daily_stats['signals_opened']}\n"
            f"موفق: {daily_stats['successful_trades']} | خطا: {daily_stats['failed_trades']}"
        )
        bot.send_message(message.chat.id, stats_msg, parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, f"لطفاً از دکمه‌های منو استفاده کنید.")

if __name__ == "__main__":
    bot.infinity_polling()
                                                                       
