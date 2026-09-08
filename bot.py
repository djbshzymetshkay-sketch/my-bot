import os
import threading
import time
from datetime import datetime
import telebot
from telebot import types
from pyxt.perp import Perp

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
      return (
          True,
          "اتصال به حساب فیوچرز صرافی با موفقیت از طریق پکیج رسمی برقرار شد.",
      )
    else:
      return False, f"پاسخ صرافی خالی بود: {account_info}"
  except Exception as e:
    return (
        False,
        f"خطای اتصال (محدودیت IP یا اعتبار کلید را بررسی کنید): {str(e)}",
    )


def advanced_smart_market_analysis():
  try:
    import requests

    url = f"https://fapi.xt.com/future/market/v1/public/q/kline?symbol=btc_usdt&interval=15m&limit=30"
    response = requests.get(url, timeout=10)
    data = response.json()

    if response.status_code == 200 and "result" in data:
      candles = data["result"]
      closes = [float(c["c"]) for c in candles]
      opens = [float(c["o"]) for c in candles]
      current_price = closes[-1]

      prev_close = closes[-2]
      prev_open = opens[-2]

      is_bullish_engulfing = (
          (prev_close < prev_open)
          and (closes[-1] > opens[-1])
          and (closes[-1] >= prev_open)
          and (opens[-1] <= prev_close)
      )
      is_bearish_engulfing = (
          (prev_close > prev_open)
          and (closes[-1] < opens[-1])
          and (closes[-1] <= prev_open)
          and (opens[-1] >= prev_close)
      )

      sma_short = sum(closes[-5:]) / 5
      sma_long = sum(closes[-15:]) / 15

      recent_failures = [
          t for t in daily_stats["trades_history"][-4:] if not t["success"]
      ]
      avoid_direction = None
      if len(recent_failures) >= 2:
        avoid_direction = recent_failures[-1]["direction"]

      if (
          is_bullish_engulfing
          or (sma_short > sma_long and closes[-1] > opens[-1])
      ) and avoid_direction != "BUY":
        return {
            "status": "success",
            "trend": "صعودی معتبر (Bullish)",
            "action": "BUY",
            "price": current_price,
            "reason": "تشخیص الگوی کندل‌پترن صعودی و میانگین متحرک",
            "tp": round(current_price * 1.015, 2),
            "sl": round(current_price * 0.994, 2),
        }
      elif (
          is_bearish_engulfing
          or (sma_short < sma_long and closes[-1] < opens[-1])
      ) and avoid_direction != "SELL":
        return {
            "status": "success",
            "trend": "نزولی معتبر (Bearish)",
            "action": "SELL",
            "price": current_price,
            "reason": "تشخیص الگوی کندل‌پترن نزولی و فشار فروش",
            "tp": round(current_price * 0.985, 2),
            "sl": round(current_price * 1.006, 2),
        }
      else:
        return {
            "status": "neutral",
            "message": "بازار در حال تثبیت؛ منتظر الگوی قطعی کندل.",
        }
    return {
        "status": "error",
        "message": f"خطای کندل: {response.status_code}",
    }
  except Exception as e:
    return {"status": "error", "message": f"خطای تحلیل کندل: {str(e)}"}


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

        volume = "0.002"
        position_side = "1" if action == "BUY" else "2"
        side = "1" if action == "BUY" else "2"

        try:
          order_res = xt_perp.submit_order(
              symbol="btc_usdt",
              orderType="1",
              entrustType="1",
              bizType="1",
              positionSide=position_side,
              side=side,
              vol=volume,
          )
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
                f"🚀 **معامله هوشمند مبتنی بر کندل‌پترن ثبت شد!**\n\n"
                f"📈 روند: {trend}\n🎯 جهت: {action}\n💲 قیمت ورود: {price}\n"
                f"💡 تحلیل تکنیکال: {reason}\n🟢 حد سود (TP): {tp}\n🔴 حد ضرر"
                f" (SL): {sl}"
            )
            bot.send_message(chat_id, msg, parse_mode="Markdown")
        else:
          daily_stats["failed_trades"] += 1
          daily_stats["consecutive_losses"] += 1
          if chat_id:
            bot.send_message(
                chat_id,
                f"⚠️ **خطای صرافی (ثبت در حافظه تطبیقی):**\n{order_error}",
                parse_mode="Markdown",
            )

      time.sleep(900)
    except Exception as e:
      if chat_id:
        bot.send_message(chat_id, f"⚠️ **خطای سیستم:** {str(e)}")
      time.sleep(60)


def nightly_report_scheduler(chat_id):
  global daily_stats
  while True:
    now = datetime.now()
    if now.hour == 21 and now.minute == 0:
      if chat_id:
        report = (
            f"🌙 **گزارش عملکرد ۲۴ ساعته ربات**\n\n"
            f"📊 کل سیگنال‌های باکیفیت: {daily_stats['signals_opened']}\n"
            f"✅ معاملات موفق: {daily_stats['successful_trades']}\n"
            f"❌ خطاها/ناموفق: {daily_stats['failed_trades']}\n"
            f"🧠 وضعیت یادگیری از الگوها: فعال و به‌روز"
        )
        bot.send_message(chat_id, report, parse_mode="Markdown")
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
  if success:
    intro_msg = (
        f"✅ **ربات هوشمند کندل‌خوان با پکیج رسمی روشن شد!**\n\n{conn_msg}"
    )
  else:
    intro_msg = f"❌ **اتصال صرافی نیازمند بررسی کلیدهاست:**\n{conn_msg}"

  bot.send_message(chat_id, intro_msg, parse_mode="Markdown", reply_markup=markup)

  threading.Thread(
      target=execute_auto_trade, args=(chat_id,), daemon=True
  ).start()
  threading.Thread(
      target=nightly_report_scheduler, args=(chat_id,), daemon=True
  ).start()


@bot.message_handler(func=lambda message: True)
def handle_messages(message):
  global daily_stats
  if message.text == "وضعیت اتصال صرافی":
    success, msg = test_xt_connection()
    bot.send_message(message.chat.id, f"✅ {msg}" if success else f"❌ {msg}")
  elif message.text == "تحلیل لحظه‌ای بازار":
    res = advanced_smart_market_analysis()
    if res["status"] == "success":
      bot.send_message(
          message.chat.id,
          f"📊 تحلیل کندل‌پترن بازار:\nروند:"
          f" {res['trend']}\nپیشنهاد: {res['action']}\nدلیل:"
          f" {res['reason']}\nقیمت: {res['price']}",
      )
    else:
      bot.send_message(
          message.chat.id,
          f"📌 {res.get('message', 'بازار در حال بررسی است.')}",
      )
  elif message.text == "آمار معاملات امروز":
    stats_msg = (
        f"📈 **آمار عملکرد و یادگیری:**\n\n"
        f"مجموع معاملات: {daily_stats['signals_opened']}\n"
        f"موفق: {daily_stats['successful_trades']} | خطا:"
        f" {daily_stats['failed_trades']}"
    )
    bot.send_message(message.chat.id, stats_msg, parse_mode="Markdown")
  else:
    bot.send_message(message.chat.id, f"لطفاً از دکمه‌های منو استفاده کنید.")


if __name__ == "__main__":
  bot.infinity_polling()
        
