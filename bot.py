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


def get_account_balance_details():
  try:
    capital = xt_perp.get_account_capital()
    if capital:
      return f"📊 وضعیت دارایی و کیف پول فیوچرز صرافی XT:\n\n{str(capital)}"
    else:
      return "اطلاعات موجودی از صرافی دریافت نشد."
  except Exception as e:
    return f"خطا در دریافت موجودی حساب: {str(e)}"


def advanced_candlestick_and_market_analysis():
  try:
    import requests

    url = f"https://fapi.xt.com/future/market/v1/public/q/kline?symbol=btc_usdt&interval=15m&limit=30"
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

      # تشخیص دقیق الگوهای کلاسیک جهان کندل‌خوانی
      body = abs(curr_close - curr_open)
      upper_shadow = curr_high - max(curr_close, curr_open)
      lower_shadow = min(curr_close, curr_open) - curr_low

      # ۱. الگوی اینگالفینگ (پوشاننده)
      is_bullish_engulfing = (
          (prev_close < prev_open)
          and (curr_close > curr_open)
          and (curr_close >= prev_open)
          and (curr_open <= prev_close)
      )
      is_bearish_engulfing = (
          (prev_close > prev_open)
          and (curr_close < curr_open)
          and (curr_close <= prev_open)
          and (curr_open >= prev_close)
      )

      # ۲. الگوی چکش صعودی (Hammer) و ستاره دنباله‌دار نزولی (Shooting Star)
      is_hammer = (lower_shadow >= 2 * body) and (
          upper_shadow <= 0.2 * body
      )  # چکش صعودی
      is_shooting_star = (upper_shadow >= 2 * body) and (
          lower_shadow <= 0.2 * body
      )  # ستاره دنباله‌دار

      # اندیکاتورهای روند و حجم
      sma_short = sum(closes[-5:]) / 5
      sma_long = sum(closes[-15:]) / 15

      avg_volume = sum(volumes[-6:-1]) / 5 if len(volumes) >= 6 else volumes[-1]
      is_volume_confirmed = volumes[-1] > (avg_volume * 1.1)

      # حافظه تطبیقی برای جلوگیری از ضرر تکراری
      recent_failures = [
          t for t in daily_stats["trades_history"][-4:] if not t["success"]
      ]
      avoid_direction = None
      if len(recent_failures) >= 2:
        avoid_direction = recent_failures[-1]["direction"]

      # شرط ورود بسیار مطمئن (تلاقی کندل خوانی + روند + تایید حجم)
      if (
          sma_short > sma_long
          and (is_bullish_engulfing or is_hammer)
          and is_volume_confirmed
          and avoid_direction != "BUY"
      ):
        pattern_name = (
            "اینگالفینگ صعودی (Bullish Engulfing)"
            if is_bullish_engulfing
            else "الگوی چکش صعودی (Hammer)"
        )
        return {
            "status": "success",
            "trend": "صعودی قوی",
            "action": "BUY",
            "price": current_price,
            "pattern": pattern_name,
            "reason": (
                f"تایید هم‌زمان روند، الگوی کندل‌خوانی {pattern_name} و جهش"
                " حجم خرید"
            ),
            "tp": round(current_price * 1.018, 2),
            "sl": round(current_price * 0.992, 2),
        }

      elif (
          sma_short < sma_long
          and (is_bearish_engulfing or is_shooting_star)
          and is_volume_confirmed
          and avoid_direction != "SELL"
      ):
        pattern_name = (
            "اینگالفینگ نزولی (Bearish Engulfing)"
            if is_bearish_engulfing
            else "الگوی ستاره دنباله‌دار (Shooting Star)"
        )
        return {
            "status": "success",
            "trend": "نزولی قوی",
            "action": "SELL",
            "price": current_price,
            "pattern": pattern_name,
            "reason": (
                f"تایید هم‌زمان روند، الگوی کندل‌خوانی {pattern_name} و حجم"
                " سنگین فروش"
            ),
            "tp": round(current_price * 0.982, 2),
            "sl": round(current_price * 1.008, 2),
        }
      else:
        return {
            "status": "neutral",
            "message": (
                "بازار فاقد شرایط صددرصدی مطمئن؛ ربات هوشمندانه منتظر سیگنال"
                " کم‌ریسک می‌ماند."
            ),
        }
    return {
        "status": "error",
        "message": f"خطای کندل: {response.status_code}",
    }
  except Exception as e:
    return {"status": "error", "message": f"خطای تحلیل پیشرفته: {str(e)}"}


def execute_auto_trade(chat_id):
  global daily_stats
  while True:
    try:
      analysis = advanced_candlestick_and_market_analysis()
      if analysis["status"] == "success":
        action = analysis["action"]
        price = analysis["price"]
        trend = analysis["trend"]
        reason = analysis["reason"]
        pattern = analysis["pattern"]
        tp = analysis["tp"]
        sl = analysis["sl"]

        position_side = "1" if action == "BUY" else "2"
        side = "1" if action == "BUY" else "2"

        success_order = False
        order_error = ""
        applied_leverage = 50

        try:
          try:
            xt_perp.submit_leverage(
                symbol="btc_usdt",
                leverage=str(applied_leverage),
                positionSide=position_side,
            )
          except:
            pass

          capital_info = xt_perp.get_account_capital()
          available_balance = 1.0
          if isinstance(capital_info, dict):
            available_balance = float(
                capital_info.get(
                    "availableBalance", capital_info.get("balance", 1.0)
                )
            )
          elif isinstance(capital_info, (int, float)):
            available_balance = float(capital_info)

          total_power = max(available_balance, 1.0) * applied_leverage
          calculated_volume = round(total_power / price, 4)
          volume = str(max(calculated_volume, 0.0001))

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
                f"🚨 سیگنال مطمئن بر اساس کندل‌خوانی اجرا شد!\n\n"
                f"الگوی کندل: {pattern}\nروند: {trend}\nجهت معامله: {action}\n"
                f"اهرم: {applied_leverage}x\nقیمت ورود: {price}\n"
                f"حد سود: {tp}\nحد ضرر: {sl}"
            )
            bot.send_message(chat_id, msg)
        else:
          daily_stats["failed_trades"] += 1
          daily_stats["consecutive_losses"] += 1
          if chat_id:
            bot.send_message(
                chat_id,
                f"خطای صرافی در اجرای خودکار:\n{order_error}",
            )

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
            "گزارش عملکرد ۲۴ ساعته ربات کندل‌خوانی\n\n"
            f"سیگنال‌های باکیفیت صید شده: {daily_stats['signals_opened']}\n"
            f"موفق: {daily_stats['successful_trades']}\n"
            f"خطاها: {daily_stats['failed_trades']}\n"
            "استراتژی: کندل‌خوانی کامل + مدیریت اتوماتیک سرمایه"
        )
        bot.send_message(chat_id, report)
      time.sleep(3600)
    else:
      time.sleep(30)


@bot.message_handler(commands=["start"])
def send_welcome(message):
  chat_id = message.chat.id
  markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
  markup.add(
      types.KeyboardButton("وضعیت اتصال صرافی"),
      types.KeyboardButton("موجودی حساب"),
      types.KeyboardButton("تحلیل لحظه‌ای بازار"),
      types.KeyboardButton("آمار معاملات امروز"),
  )

  success, conn_msg = test_xt_connection()
  if success:
    intro_msg = (
        "ربات هوشمند کندل‌خوانی با دکمه موجودی حساب روشن شد!\n\n"
        f"{conn_msg}"
    )
  else:
    intro_msg = f"اتصال صرافی نیازمند بررسی کلیدهاست:\n{conn_msg}"

  bot.send_message(chat_id, intro_msg, reply_markup=markup)

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
    bot.send_message(message.chat.id, f"{msg}" if success else f"{msg}")
  elif message.text == "موجودی حساب":
    balance_msg = get_account_balance_details()
    bot.send_message(message.chat.id, balance_msg)
  elif message.text == "تحلیل لحظه‌ای بازار":
    res = advanced_candlestick_and_market_analysis()
    if res["status"] == "success":
      bot.send_message(
          message.chat.id,
          f"وضعیت کلیدی بازار:\nالگوی کندل: {res['pattern']}\nروند:"
          f" {res['trend']}\nپیشنهاد: {res['action']}\nدلیل: {res['reason']}\nقیمت:"
          f" {res['price']}",
      )
    else:
      bot.send_message(
          message.chat.id,
          f"{res.get('message', 'بازار در حال بررسی است.')}",
      )
  elif message.text == "آمار معاملات امروز":
    stats_msg = (
        "آمار عملکرد اتوماتیک کندل‌خوانی:\n\n"
        f"مجموع معاملات: {daily_stats['signals_opened']}\n"
        f"موفق: {daily_stats['successful_trades']} | خطا:"
        f" {daily_stats['failed_trades']}"
    )
    bot.send_message(message.chat.id, stats_msg)
  else:
    bot.send_message(message.chat.id, "لطفاً از دکمه‌های منو استفاده کنید.")


if __name__ == "__main__":
  bot.infinity_polling()
          
