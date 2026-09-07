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

# --- تنظیمات اختصاصی و کلیدهای صرافی XT ---
TOKEN = "توکن_ربات_تلگرام_شما"
XT_API_KEY = "c25d4d1a-b496-4c2a-a8ee-599cee26b975"
XT_SECRET_KEY = "4f1f059a2c87a642129e38e7f86b9ab149e4d8a"
ADMIN_ID = 7178006484

bot = telebot.TeleBot(TOKEN)
TRADINGVIEW_CHART_URL = "https://www.xt.com/en/futures/trade/btc_usdt"

def get_xt_signature(secret_key, path, method, timestamp, query_string="", body_string=""):
  payload = f"{method.upper()}\n{path}\n{query_string}\n{body_string}\n{timestamp}"
  signature = hmac.new(
      secret_key.encode("utf-8"),
      payload.encode("utf-8"),
      hashlib.sha256
  ).hexdigest()
  return signature

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

def get_bitcoin_news_sentiment():
  try:
    url = "https://cryptopanic.com/api/v1/posts/?auth_token=free&currencies=BTC&filter=important"
    res = requests.get(url, timeout=10).json()
    results = res.get("results", [])
    if results:
      latest_title = results[0].get("title", "").lower()
      positive_words = ["bull", "surge", "pump", "high", "approval", "etf", "100k", "rally", "adopt"]
      negative_words = ["bear", "crash", "drop", "ban", "hack", "sec", "lawsuit", "fall", "liquidation"]
      
      pos_score = sum(1 for word in positive_words if word in latest_title)
      neg_score = sum(1 for word in negative_words if word in latest_title)
      
      if pos_score > neg_score:
        return "BUY", f"اخبار فاندامنتال مثبت: {results[0].get('title')[:50]}..."
      elif neg_score > pos_score:
        return "SELL", f"اخبار فاندامنتال منفی: {results[0].get('title')[:50]}..."
  except Exception:
    pass
  return None, "اخبار فاندامنتال خنثی"

def analyze_world_class_candles_with_news():
  try:
    news_side, news_reason = get_bitcoin_news_sentiment()
    url = "https://sapi.xt.com/v4/market/public/q/kline?symbol=btc_usdt&interval=15m&limit=5"
    res = requests.get(url, timeout=10).json()
    if res.get("rc") == 0 and len(res.get("result", [])) >= 3:
      candles = res["result"]
      c3 = {"open": float(candles[-1][1]), "close": float(candles[-1][4])}
      tech_side = "BUY" if c3["close"] >= c3["open"] else "SELL"
      
      if news_side and news_side == tech_side:
        return news_side, f"تایید دوگانه (تکنیکال + اخبار): {news_reason}"
      elif news_side:
        return news_side, f"سیگنال اخبار فاندامنتال: {news_reason}"
      
      return tech_side, "سیگنال کندل‌خوانی ۱۵ دقیقه"
  except Exception:
    pass
  return "BUY", "سیگنال روتین بازار"

def send_startup_notification():
  time.sleep(3)
  is_connected, balance = check_real_connection_and_balance()
  if is_connected:
    msg = (
        f"🟢 **ربات با موفقیت به صرافی XT متصل شد!**\n"
        f"👑 تریدر: امیرعلی جمشیدزایی\n\n"
        f"💰 موجودی واقعی فیوچرز: `{balance:.2f} تتر (USDT)`\n"
        f"🚀 ربات ۲۴ ساعته فعال شد."
    )
  else:
    msg = "⚠️ ربات روشن شد اما در اتصال به صرافی XT خطا رخ داد. کلیدها را چک کنید."
  
  try:
    bot.send_message(ADMIN_ID, msg, parse_mode="Markdown")
  except Exception as e:
    print(f"Startup Notification Error: {e}")

def automated_trading_worker():
  while True:
    time.sleep(2880) # بررسی هر ۴۸ دقیقه برای هدف ۳۰ سیگنال در روز
    is_connected, live_bal = check_real_connection_and_balance()
    if not is_connected or live_bal < 1.0:
      continue

    symbol = "btc_usdt"
    try:
      ticker_res = requests.get(f"https://sapi.xt.com/v4/market/public/q/ticker/price?symbol={symbol}", timeout=10).json()
      if ticker_res.get("rc") == 0:
        current_price = float(ticker_res["result"]["price"])
        side, combined_reason = analyze_world_class_candles_with_news()
        
        capital_to_use = live_bal * 0.15
        leverage = 20
        quantity = round((capital_to_use * leverage) / current_price, 4)

        if quantity > 0:
          host = "https://fapi.xt.com"
          path = "/v1/order"
          method = "POST"
          timestamp = str(int(time.time() * 1000))
          
          body = {
              "symbol": symbol,
              "side": side,
              "bizType": "OPEN",
              "orderType": "MARKET",
              "amount": str(quantity),
              "leverage": str(leverage)
          }
          body_str = json.dumps(body)
          signature = get_xt_signature(XT_SECRET_KEY, path, method, timestamp, body_string=body_str)
          
          headers = {
              "xt-access-key": XT_API_KEY,
              "xt-sign": signature,
              "xt-timestamp": timestamp,
              "Content-Type": "application/json"
          }
          
          order_response = requests.post(host + path, data=body_str, headers=headers, timeout=10).json()
          
          if order_response and order_response.get("rc") == 0:
            side_fa = "خرید (Long 🟢)" if side == "BUY" else "فروش (Short 🔴)"
            report_msg = (
                f"🚨🦁 **گزارش معامله خودکار صرافی XT**\n"
                f"👑 تریدر: امیرعلی جمشیدزایی\n\n"
                f"📊 جفت ارز: `BTC/USDT`\n"
                f"⚡️ جهت: {side_fa} | اهرم: {leverage}x\n"
                f"📰 تحلیل: {combined_reason}\n"
                f"🎯 قیمت ورود: {current_price}\n"
                f"💰 مارجین درگیر: {capital_to_use:.2f} تتر"
            )
            bot.send_message(ADMIN_ID, report_msg, parse_mode="Markdown")
    except Exception as e:
      print(f"Worker Error: {e}")

if __name__ == "__main__":
  threading.Thread(target=send_startup_notification, daemon=True).start()
  threading.Thread(target=automated_trading_worker, daemon=True).start()
  bot.infinity_polling()
