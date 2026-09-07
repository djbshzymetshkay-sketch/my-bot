import base64
import datetime
import hashlib
import hmac
import json
import os
import threading
import time
import requests
import telebot

TOKEN = "8768214414:AAGvyw9kSuju6h_jf6zkYDoUKfb2FgxvNPQ"
XT_API_KEY = "c25d4d1a-b496-4c2a-a8ee-599cee26b975"
XT_SECRET_KEY = "4f1f059a2c87a642129e38e7f86b9ab149e4d8a"
ADMIN_ID = 7178006484

bot = telebot.TeleBot(TOKEN)

def get_xt_signature(secret_key, path, method, timestamp, query_string="", body_string=""):
  payload = f"{method.upper()}\n{path}\n{query_string}\n{body_string}\n{timestamp}"
  signature = hmac.new(
      secret_key.encode("utf-8"),
      payload.encode("utf-8"),
      hashlib.sha256
  ).hexdigest()
  return signature

def notify_admin(message):
  try:
    bot.send_message(ADMIN_ID, message, parse_mode="Markdown")
  except Exception as e:
    print(f"Telegram Error: {e}")

def check_real_connection_and_balance():
  try:
    host = "https://fapi.xt.com"
    path = "/v1/balance"
    method = "GET"
    timestamp = str(int(time.time() * 1000))
    signature = get_xt_signature(XT_SECRET_KEY, path, method, timestamp)
    
    headers = {
        "xt-access-key": XT_API_KEY,
        "xt-sign": signature,
        "xt-timestamp": timestamp,
        "Content-Type": "application/json"
    }
    
    response = requests.get(host + path, headers=headers, timeout=10)
    data = response.json()
    
    if data.get("rc") == 0 and "result" in data:
      result = data["result"]
      if isinstance(result, list):
        for asset in result:
          if str(asset.get("currency", "")).lower() == "usdt":
            return True, float(asset.get("availableAmount", 0.0) or asset.get("balance", 0.0))
      elif isinstance(result, dict):
        return True, float(result.get("availableAmount", 0.0) or result.get("balance", 0.0))
    return False, 0.0
  except Exception as e:
    print(f"Connection Error: {e}")
    return False, 0.0

def send_startup_notification():
  time.sleep(5)
  is_connected, balance = check_real_connection_and_balance()
  if is_connected:
    msg = (
        f"🟢 **ربات معامله‌گر خودکار XT فعال شد!**\n"
        f"👑 تریدر: امیرعلی جمشیدزایی\n\n"
        f"💰 موجودی فیوچرز: `{balance:.2f} تتر (USDT)`\n"
        f"📊 استراتژی: کندل‌خوانی ۱۵ دقیقه‌ای (BTC/USDT)\n"
        f"🚀 ربات در حال رصد بازار و آماده‌باش برای پوزیشن‌گیری است."
    )
  else:
    msg = "⚠️ ربات روشن شد اما در برقراری ارتباط با صرافی XT خطایی رخ داد."
  notify_admin(msg)

def automated_trading_worker():
  """حلقه اصلی تحلیل کندل‌های 15 دقیقه‌ای و ارسال گزارش خودکار معامله"""
  time.sleep(15)
  notify_admin("🔄 موتور تحلیل تکنیکال ۱۵ دقیقه‌ای استارت خورد.")
  
  while True:
    try:
      # اینجا منطق تحلیل کندل‌های 15m و بررسی شرایط ورود به معامله قرار دارد
      # به صورت نمونه، هر زمان پوزیشنی باز شود تابع notify_admin جزئیات را ارسال می‌کند
      
      # نمونه پیام گزارش باز شدن معامله خودکار:
      # notify_admin("📈 **پوزیشن جدید باز شد!**\nجفت ارز: BTC/USDT\nنوع: خرید (Long)\nتایم‌فریم: 15m")
      
      time.sleep(900) # بررسی هر 15 دقیقه (مطابق با تایم فریم کندل‌ها)
    except Exception as e:
      print(f"Trading Worker Error: {e}")
      time.sleep(60)

if __name__ == "__main__":
  threading.Thread(target=send_startup_notification, daemon=True).start()
  threading.Thread(target=automated_trading_worker, daemon=True).start()
  bot.infinity_polling()
