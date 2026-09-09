import os
import threading
import time
from datetime import datetime
import telebot
from telebot import types
from pyxt.perp import Perp
import requests

TELEGRAM_TOKEN = os.getenv("TOKEN")
XT_API_KEY = "c25d4d1a-b496-4c2a-a8ee-599cee26b975"
XT_SECRET_KEY = "e8b8bc8b8d3ee498ac71194becd6498ecc2f67bd"

bot = telebot.TeleBot(TELEGRAM_TOKEN)
xt_perp = Perp(
    host="https://fapi.xt.com", access_key=XT_API_KEY, secret_key=XT_SECRET_KEY
)

daily_stats = {
    "signals_opened": 0,
    "successful_trades": 0,
    "failed_trades": 0,
    "consecutive_losses": 0,
    "trades_history": [],
}

def test_xt_connection():
  try:
    account_info = xt_perp.get_account_capital()
    if account_info:
      return True, "اتصال به حساب فیوچرز صرافی با موفقیت از طریق پکیج رسمی برقرار شد."
    else:
      return False, f"پاسخ صرافی خالی بود: {account_info}"
  except Exception as e:
    return False, f"خطای اتصال: {str(e)}"

def advanced_smart_market_analysis():
  try:
    url = f"https://fapi.xt.com/future/market/v1/public/q/kline?symbol=btc_usdt&interval=15m&limit=30"
    response = requests.get(url, timeout=10)
    data = response.json()

    if response.status_code == 200 and "result" in data:
      candles = data["result"]
      closes = [float(c["c"]) for c in candles]
      opens = [float(c["o"]) for c in candles]
      volumes = [float(c.get("v", 0)) for c in candles]
      current_price = closes[-1]

      prev_close = closes[-2]
      prev_open = opens[-2]

      is_bullish_engulfing = (prev_close < prev_open) and (closes[-1] > opens[-1]) and (closes[-1] >= prev_open) and (opens[-1] <= prev_close)
      is_bearish_engulfing = (prev_close > prev_open) and (closes[-1] < opens[-1]) and (closes[-1] <= prev_open) and (opens[-1] >= prev_close)

      sma_short = sum(closes[-5:]) / 5
      sma_long = sum(closes[-15:]) / 15
      avg_volume = sum(volumes[-6:-1]) / 5 if len(volumes) >= 6 else volumes[-1]
      is_volume_confirmed = volumes[-1] > (avg_volume * 1.1)

      recent_failures = [t for t in daily_stats["trades_history"][-4:] if not t["success"]]
      avoid_direction = None
      if len(recent_failures) >= 2:
        avoid_direction = recent_failures[-1]["direction"]

      if sma_short > sma_long and is_bullish_engulfing and is_volume_confirmed and avoid_direction != "BUY":
        return {
            "status": "success",
            "trend": "صعودی فوق‌العاده قوی",
            "action": "BUY",
            "price": current_price,
            "reason": "تلاقی میانگین متحرک، اینگالفینگ و حجم",
            "tp": round(current_price * 1.018, 2),
            "sl": round(current_price * 0.992, 2),
        }
      elif sma_short < sma_long and is_bearish_engulfing and is_volume_confirmed and avoid_direction != "SELL":
        return {
            "status": "success",
            "trend": "نزولی فوق‌العاده قوی",
            "action": "SELL",
            "price": current_price,
            "reason": "تلاقی میانگین متحرک، اینگالفینگ و حجم",
            "tp": round(current_price * 0.982, 2),
            "sl": round(current_price * 1.008, 2),
        }
      else:
        return {"status": "neutral", "message": "بازار فاقد شرایط مناسب."}
    return {"status": "error", "message": f"خطای کندل: {response.status_code}"}
  except Exception as e:
    return {"status": "error", "message": str(e)}

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

        position_side = "LONG" if action == "BUY" else "SHORT"
        order_side = "BUY" if action == "BUY" else "SELL"
        applied_leverage = 50

        try:
          account_data = xt_perp.get_account_capital()
          available_balance = 10.0
          if isinstance(account_data, dict):
            res_res = account_data.get("result", account_data)
            available_balance = float(res_res.get("availableBalance") or res_res.get("accountAvailableBalance") or 10.0)

          total_power = available_balance * applied_leverage
          volume = round(total_power / price, 4)

          order_res = xt_perp.send_order(
              symbol="btc_usdt",
              price=price,
              amount=volume,
              order_side=order_side,
              order_type="MARKET",
              position_side=position_side
          )
          
          print("Response from exchange:", order_res)
          
          if isinstance(order_res, dict) and order_res.get("rc", 0) != 0:
              raise Exception(f"Exchange Error: {order_res.get('msg', order_res)}")

          success_order = True
          order_error = ""
        except Exception as ex:
          success_order = False
          order_error = str(ex)

        trade_record = {
            "direction": action,
            "price": price,
            "success": success_order,
            "time": datetime.now().strftime("%H:%M"),
        }
        daily_stats["trades_history"].append(trade_record)

        if success_order:
          daily_stats["signals_opened"] += 1
          daily_stats["successful_trades"] += 1
          daily_stats["consecutive_losses"] = 0

          if chat_id:
            msg = (
                "🚨 معامله اتوماتیک با اهرم هوشمند اجرا شد!\n\n"
                f"📈 روند: {trend}\n"
                f"🎯 جهت: {action}\n"
                f"⚡️ اهرم: {applied_leverage}x\n"
                f"📦 حجم: {volume}\n"
                f"💵 قیمت ورود: {price}\n"
                f"🧠 دلیل: {reason}\n"
                f"🎯 حد سود: {tp}\n"
                f"🛡 حد ضرر: {sl}"
            )
            bot.send_message(chat_id, msg)
        else:
          daily_stats["failed_trades"] += 1
          daily_stats["consecutive_losses"] += 1
          if chat_id:
            bot.send_message(chat_id, f"خطای صرافی در ثبت پوزیشن خودکار:\n{order_error}")

      time.sleep(900)
    except Exception as e:
      if chat_id:
        bot.send_message(chat_id, f"خطای سیستم: {str(e)}")
      time.sleep(60)

def nightly_report_scheduler(chat_id):
  global daily_stats
  while True:
    now = datetime.now()
    if now.hour == 21 and now.minute == 0:
      if chat_id:
        report = (
            "📅 گزارش عملکرد ۲۴ ساعته ربات:\n\n"
            f"🔹 کل سیگنال‌ها: {daily_stats['signals_opened']}\n"
            f"✅ موفق: {daily_stats['successful_trades']}\n"
            f"❌ خطاها: {daily_stats['failed_trades']}"
        )
        bot.send_message(chat_id, report)
      time.sleep(3600)
    else:
      time.sleep(30)

@bot.message_handler(commands=["start"])
def send_welcome(message):
  chat_id = message.chat.id
  markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
  markup.add(
      types.KeyboardButton("وضعیت اتصال صرافی"),
      types.KeyboardButton("تحلیل لحظه‌ای بازار"),
      types.KeyboardButton("آمار معاملات امروز"),
  )
  success, conn_msg = test_xt_connection()
  bot.send_message(chat_id, f"ربات روشن شد!\n\n{conn_msg}", reply_markup=markup)

  threading.Thread(target=execute_auto_trade, args=(chat_id,), daemon=True).start()
  threading.Thread(target=nightly_report_scheduler, args=(chat_id,), daemon=True).start()

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
  global daily_stats
  if message.text == "وضعیت اتصال صرافی":
    _, msg = test_xt_connection()
    bot.send_message(message.chat.id, msg)
  elif message.text == "تحلیل لحظه‌ای بازار":
    res = advanced_smart_market_analysis()
    if res["status"] == "success":
      bot.send_message(message.chat.id, f"روند: {res['trend']}\nپیشنهاد: {res['action']}\nدلیل: {res['reason']}")
    else:
      bot.send_message(message.chat.id, res.get('message', 'در حال بررسی...'))
  elif message.text == "آمار معاملات امروز":
    bot.send_message(message.chat.id, f"مجموع: {daily_stats['signals_opened']}\nموفق: {daily_stats['successful_trades']} | خطا: {daily_stats['failed_trades']}")
  else:
    bot.send_message(message.chat.id, "لطفاً از دکمه‌های منو استفاده کنید.")

if __name__ == "__main__":
  bot.infinity_polling()
    
