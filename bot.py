import os
import threading
import time
import hmac
import hashlib
import json
import requests
from datetime import datetime
import telebot
from telebot import types

TELEGRAM_TOKEN = os.getenv("TOKEN")
XT_API_KEY = "c25d4d1a-b496-4c2a-a8ee-599cee26b975"
XT_SECRET_KEY = "e8b8bc8b8d3ee498ac71194becd6498ecc2f67bd"
XT_BASE_URL = "https://fapi.xt.com"

bot = telebot.TeleBot(TELEGRAM_TOKEN)

daily_stats = {
    "signals_opened": 0,
    "successful_trades": 0,
    "failed_trades": 0,
    "consecutive_losses": 0,
    "trades_history": [],
}

def get_xt_signature(secret_key, message):
    return hmac.new(
        secret_key.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

def send_xt_request(method, endpoint, params=None):
    try:
        timestamp = str(int(time.time() * 1000))
        
        # تعیین دقیق مسیر (Path) بر اساس مستندات فیوچرز XT
        if any(x in endpoint for x in ["account", "position", "order"]):
            path = f"/future/user/v1{endpoint}"
        else:
            path = f"/future/market/v1{endpoint}"

        query_string = ""
        body_string = ""
        
        if params and method.upper() == "GET":
            query_string = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
            full_path = f"{path}?{query_string}" if query_string else path
        else:
            full_path = path
            if params and method.upper() == "POST":
                body_string = json.dumps(params, separators=(',', ':'))

        # ساخت پاداش امضا طبق استاندارد مستندات صرافی XT
        sign_payload = f"{method.upper()}\n{full_path}\n{timestamp}"
        if body_string and method.upper() == "POST":
            sign_payload += f"\n{body_string}"

        signature = get_xt_signature(XT_SECRET_KEY, sign_payload)

        headers = {
            "xt-validate-appkey": XT_API_KEY,
            "xt-validate-timestamp": timestamp,
            "xt-validate-signature": signature,
            "xt-validate-algorithms": "HmacSHA256",
            "Content-Type": "application/json"
        }

        url = f"{XT_BASE_URL}{full_path}"
        if method.upper() == "GET":
            response = requests.get(url, headers=headers, timeout=10)
        else:
            response = requests.post(url, headers=headers, data=body_string if body_string else None, timeout=10)

        return response.json()
    except Exception as e:
        return {"returnCode": 999, "msgInfo": str(e)}

def test_xt_connection():
    res = send_xt_request("GET", "/account/balance")
    if isinstance(res, dict) and (res.get("returnCode") == 0 or res.get("code") == 0 or "result" in res):
        if res.get("returnCode") == 0 or res.get("code") == 0 or res.get("result") is not None:
            return True, "اتصال به حساب فیوچرز صرافی با موفقیت برقرار شد."
    return False, f"خطای اتصال صرافی: {res}"

def get_account_balance_details():
    res = send_xt_request("GET", "/account/balance")
    if isinstance(res, dict):
        result_data = res.get("result", res)
        balance = result_data.get("balance") or result_data.get("accountWalletBalance") or result_data.get("totalWalletBalance") or "0.0"
        available = result_data.get("availableBalance") or result_data.get("accountAvailableBalance") or "0.0"
        return f"📊 وضعیت کیف پول فیوچرز صرافی XT:\n\nموجودی کل: {balance} USDT\nموجودی قابل استفاده: {available} USDT"
    return f"خطا در دریافت موجودی از صرافی:\n{res}"

def advanced_candlestick_and_market_analysis():
    try:
        url = f"{XT_BASE_URL}/future/market/v1/public/q/kline?symbol=btc_usdt&interval=15m&limit=30"
        response = requests.get(url, timeout=10)
        data = response.json()

        if response.status_code == 200 and "result" in data:
            candles = data["result"]
            closes = [float(c["c"]) for c in candles]
            opens = [float(c["o"]) for c in candles]
            highs = [float(c["h"]) for c in candles]
            lows = [float(c["l"]) for c in candles]
            volumes = [float(c.get("v", 0)) for c in candles]
            current_price = closes[-1]

            curr_open = opens[-1]
            curr_close = closes[-1]
            curr_high = highs[-1]
            curr_low = lows[-1]

            prev_close = closes[-2]
            prev_open = opens[-2]

            body = abs(curr_close - curr_open)
            upper_shadow = curr_high - max(curr_close, curr_open)
            lower_shadow = min(curr_close, curr_open) - curr_low

            is_bullish_engulfing = (prev_close < prev_open) and (curr_close > curr_open) and (curr_close >= prev_open) and (curr_open <= prev_close)
            is_bearish_engulfing = (prev_close > prev_open) and (curr_close < curr_open) and (curr_close <= prev_open) and (curr_close >= prev_close)

            is_hammer = (lower_shadow >= 2 * body) and (upper_shadow <= 0.2 * body)
            is_shooting_star = (upper_shadow >= 2 * body) and (lower_shadow <= 0.2 * body)

            sma_short = sum(closes[-5:]) / 5
            sma_long = sum(closes[-15:]) / 15

            avg_volume = sum(volumes[-6:-1]) / 5 if len(volumes) >= 6 else volumes[-1]
            is_volume_confirmed = volumes[-1] > (avg_volume * 1.1)

            recent_failures = [t for t in daily_stats["trades_history"][-4:] if not t["success"]]
            avoid_direction = None
            if len(recent_failures) >= 2:
                avoid_direction = recent_failures[-1]["direction"]

            if sma_short > sma_long and (is_bullish_engulfing or is_hammer) and is_volume_confirmed and avoid_direction != "BUY":
                pattern_name = "اینگالفینگ صعودی (Bullish Engulfing)" if is_bullish_engulfing else "الگوی چکش صعودی (Hammer)"
                return {
                    "status": "success",
                    "trend": "صعودی قوی",
                    "action": "BUY",
                    "price": current_price,
                    "pattern": pattern_name,
                    "tp": round(current_price * 1.018, 2),
                    "sl": round(current_price * 0.992, 2)
                }
            elif sma_short < sma_long and (is_bearish_engulfing or is_shooting_star) and is_volume_confirmed and avoid_direction != "SELL":
                pattern_name = "اینگالفینگ نزولی (Bearish Engulfing)" if is_bearish_engulfing else "الگوی ستاره دنباله‌دار (Shooting Star)"
                return {
                    "status": "success",
                    "trend": "نزولی قوی",
                    "action": "SELL",
                    "price": current_price,
                    "pattern": pattern_name,
                    "tp": round(current_price * 0.982, 2),
                    "sl": round(current_price * 1.008, 2)
                }
            else:
                return {"status": "neutral", "message": "بازار فاقد شرایط صددرصدی مطمئن؛ ربات منتظر می‌ماند."}
        return {"status": "error", "message": "خطای دریافت کندل"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def execute_auto_trade(chat_id):
    global daily_stats
    while True:
        try:
            analysis = advanced_candlestick_and_market_analysis()
            if analysis.get("status") == "success":
                action = analysis["action"]
                price = analysis["price"]
                trend = analysis["trend"]
                pattern = analysis["pattern"]
                tp = analysis["tp"]
                sl = analysis["sl"]

                position_side = "1" if action == "BUY" else "2"
                side = "1" if action == "BUY" else "2"
                applied_leverage = 50

                success_order = False
                order_error = ""

                try:
                    send_xt_request("POST", "/position/leverage", {
                        "symbol": "btc_usdt",
                        "leverage": applied_leverage,
                        "positionSide": position_side
                    })
                    
                    bal_res = send_xt_request("GET", "/account/balance")
                    available_balance = 1.0
                    if isinstance(bal_res, dict):
                        res_data = bal_res.get("result", bal_res)
                        available_balance = float(res_data.get("availableBalance") or res_data.get("accountAvailableBalance") or 1.0)

                    total_power = max(available_balance, 1.0) * applied_leverage
                    calculated_volume = round(total_power / price, 4)
                    volume = str(max(calculated_volume, 0.0001))

                    res_order = send_xt_request("POST", "/order/create", {
                        "symbol": "btc_usdt",
                        "orderType": "1",
                        "entrustType": "1",
                        "bizType": "1",
                        "positionSide": position_side,
                        "side": side,
                        "vol": volume
                    })

                    if isinstance(res_order, dict) and (res_order.get("returnCode") == 0 or res_order.get("code") == 0):
                        success_order = True
                    else:
                        success_order = False
                        order_error = str(res_order)
                except Exception as ex:
                    success_order = False
                    order_error = str(ex)

                daily_stats["trades_history"].append({"direction": action, "price": price, "success": success_order})

                if success_order:
                    daily_stats["signals_opened"] += 1
                    daily_stats["successful_trades"] += 1
                    if chat_id:
                        bot.send_message(chat_id, f"🚨 معامله اتوماتیک اجرا شد!\n\nکندل: {pattern}\nروند: {trend}\nجهت: {action}\nاهرم: {applied_leverage}x\nقیمت: {price}\nحد سود: {tp}\nحد ضرر: {sl}")
                else:
                    daily_stats["failed_trades"] += 1
                    if chat_id:
                        bot.send_message(chat_id, f"خطای صرافی در ثبت پوزیشن:\n{order_error}")

            time.sleep(900)
        except Exception as e:
            time.sleep(60)

def nightly_report_scheduler(chat_id):
    global daily_stats
    while True:
        now = datetime.now()
        if now.hour == 21 and now.minute == 0:
            if chat_id:
                bot.send_message(chat_id, f"گزارش عملکرد ۲۴ ساعته ربات:\n\nکل معاملات: {daily_stats['signals_opened']}\nموفق: {daily_stats['successful_trades']}\nخطا: {daily_stats['failed_trades']}")
            time.sleep(3600)
        else:
            time.sleep(30)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("وضعیت اتصال صرافی"),
        types.KeyboardButton("موجودی حساب"),
        types.KeyboardButton("تحلیل لحظه‌ای بازار"),
        types.KeyboardButton("آمار معاملات امروز")
    )
    success, conn_msg = test_xt_connection()
    bot.send_message(chat_id, f"ربات هوشمند روشن شد!\n\n{conn_msg}", reply_markup=markup)
    threading.Thread(target=execute_auto_trade, args=(chat_id,), daemon=True).start()
    threading.Thread(target=nightly_report_scheduler, args=(chat_id,), daemon=True).start()

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    global daily_stats
    if message.text == "وضعیت اتصال صرافی":
        _, msg = test_xt_connection()
        bot.send_message(message.chat.id, msg)
    elif message.text == "موجودی حساب":
        bot.send_message(message.chat.id, get_account_balance_details())
    elif message.text == "تحلیل لحظه‌ای بازار":
        res = advanced_candlestick_and_market_analysis()
        if res.get("status") == "success":
            bot.send_message(message.chat.id, f"وضعیت بازار:\nکندل: {res['pattern']}\nروند: {res['trend']}\nپیشنهاد: {res['action']}\nقیمت: {res['price']}")
        else:
            bot.send_message(message.chat.id, res.get("message", "در حال بررسی بازار..."))
    elif message.text == "آمار معاملات امروز":
        bot.send_message(message.chat.id, f"آمار عملکرد:\n\nمجموع: {daily_stats['signals_opened']}\nموفق: {daily_stats['successful_trades']} | خطا: {daily_stats['failed_trades']}")
    else:
        bot.send_message(message.chat.id, "لطفاً از دکمه‌های منو استفاده کنید.")

if __name__ == "__main__":
    bot.infinity_polling()
            
