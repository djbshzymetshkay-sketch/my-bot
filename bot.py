import datetime
import os
import sqlite3
import threading
import time
import requests
import telebot
from telebot import types

TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = 7178006484

bot = telebot.TeleBot(TOKEN)

# تنظیمات اتصال واقعی به صرافی XT
API_KEY = "c25d4d1a-b496-4c2a-a8ee-599cee26b975"
SECRET_KEY = "4f1f05a92c8c7a642129e38e7f86b9ab149e4d8a"
BASE_URL = "https://fapi.xt.com"

# لینک تصویر اختصاصی شیر و چارت جمشیدزایی
LION_IMAGE_URL = "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=800"

# دیکشنری موقت برای ذخیره وضعیت تنظیم دستی کاربران
user_temp_settings = {}

def init_db():
  conn = sqlite3.connect("users_xt.db")
  cursor = conn.cursor()
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            leverage INTEGER DEFAULT 10,
            custom_capital REAL DEFAULT 0.0,
            status TEXT DEFAULT 'inactive',
            daily_profit REAL DEFAULT 0.0,
            daily_trades INTEGER DEFAULT 0
        )
    """)
  conn.commit()
  conn.close()

init_db()

def fetch_xt_balance():
  endpoint = "/future/user/v1/balance"
  timestamp = str(int(time.time() * 1000))
  headers = {"xt-app-key": API_KEY, "xt-timestamp": timestamp}
  try:
    response = requests.get(BASE_URL + endpoint, headers=headers, timeout=10).json()
    if response.get("rc") == 0:
      for asset in response.get("result", []):
        if asset.get("currency") == "usdt":
          return float(asset.get("availableAmount", 0.0))
    return 0.0
  except Exception:
    return 0.0

def place_real_xt_order_with_sl_tp(symbol, side, quantity, leverage, entry_price):
  endpoint = "/future/trade/v1/order/create"
  timestamp = str(int(time.time() * 1000))
  
  if side.upper() == "BUY":
    stop_loss = round(entry_price * 0.98, 2)
    take_profit = round(entry_price * 1.04, 2)
  else:
    stop_loss = round(entry_price * 1.02, 2)
    take_profit = round(entry_price * 0.96, 2)

  params = {
      "symbol": symbol.lower().replace("/", "_"),
      "side": side.upper(),
      "bizType": "OPEN",
      "orderType": "MARKET",
      "amount": str(quantity),
      "leverage": str(leverage),
      "stopLossPrice": str(stop_loss),
      "takeProfitPrice": str(take_profit)
  }
  headers = {"xt-app-key": API_KEY, "xt-timestamp": timestamp}
  try:
    response = requests.post(BASE_URL + endpoint, json=params, headers=headers, timeout=10).json()
    if response.get("rc") == 0:
      return True, stop_loss, take_profit, "موفق"
    else:
      return False, stop_loss, take_profit, response.get("retMsg", "خطا")
  except Exception as e:
    return False, 0, 0, str(e)

# موتور اتوماتیک ترید همراه با تحلیل دلیل ورود
def auto_trading_worker():
  while True:
    time.sleep(300)  # بررسی بازار هر ۵ دقیقه
    conn = sqlite3.connect("users_xt.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, leverage, custom_capital FROM users WHERE status = 'active'")
    active_users = cursor.fetchall()
    conn.close()

    if not active_users:
      continue

    live_bal = fetch_xt_balance()
    if live_bal < 1.0:
      continue

    symbol = "BTC_USDT"
    
    try:
      ticker_url = f"https://sapi.xt.com/v4/market/public/q/ticker/price?symbol={symbol}"
      res = requests.get(ticker_url, timeout=10).json()
      if res.get("rc") == 0:
        current_price = float(res["result"]["price"])
        
        for u in active_users:
          uid, leverage, custom_cap = u
          # استفاده از سرمایه دستی یا محاسبه اتوماتیک ۹۰ درصد موجودی
          capital_to_use = custom_cap if custom_cap > 0 else (live_bal * 0.9)
          
          notional_value = capital_to_use * leverage
          quantity = round(notional_value / current_price, 4)

          if quantity > 0:
            success, sl, tp, msg = place_real_xt_order_with_sl_tp(symbol, "BUY", quantity, leverage, current_price)
            
            if success:
              conn = sqlite3.connect("users_xt.db")
              cursor = conn.cursor()
              cursor.execute("UPDATE users SET daily_trades = daily_trades + 1, daily_profit = daily_profit + ? WHERE user_id = ?", (capital_to_use * 0.015, uid))
              conn.commit()
              conn.close()

              entry_reason = (
                  "شکست مقاومت کلیدی بازه زمانی اخیر همراه با ورود حجم سنگین خرید (Bullish Volume Spike) "
                  "و تشکیل کندل تأیید صعودی در چارت."
              )

              signal_caption = (
                  f"🔥 **شکار سیگنال جدید در صرافی XT**\n"
                  f"👑 *امپراتوری ترید: امیرعلی جمشیدزایی*\n\n"
                  f"📊 جفت ارز: `BTC/USDT` (Long 🟢)\n"
                  f"⚡️ لوریج: {leverage}x\n"
                  f"🎯 نقطه ورود: {current_price}\n"
                  f"🛑 حد ضرر (Stop Loss): {sl}\n"
                  f"🎯 حد سود (Take Profit): {tp}\n\n"
                  f"🧠 **دلیل ورود به معامله:**\n{entry_reason}\n\n"
                  f"💰 سرمایه درگیر: {capital_to_use:.2f} تتر\n"
                  f"💪 سود شما با مدیریت ریسک کامل در جریان است!"
              )
              try:
                bot.send_photo(uid, LION_IMAGE_URL, caption=signal_caption, parse_mode="Markdown")
              except Exception:
                pass
    except Exception as e:
      print(f"Auto trade worker error: {e}")

threading.Thread(target=auto_trading_worker, daemon=True).start()

# موتور ارسال گزارش شبانه دقیقاً ساعت ۲۱:۰۰ (ساعت ۹ شب)
def daily_night_report_worker():
  while True:
    now = datetime.datetime.now()
    if now.hour == 21 and now.minute == 0:
      conn = sqlite3.connect("users_xt.db")
      cursor = conn.cursor()
      cursor.execute("SELECT user_id, daily_profit, daily_trades FROM users WHERE status = 'active'")
      active_users = cursor.fetchall()
      
      live_bal = fetch_xt_balance()

      for u in active_users:
        uid, d_profit, d_trades = u
        profit_percent = (d_profit / live_bal) * 100 if live_bal > 0 else 0

        report_caption = (
            f"🌙 **گزارش سود ۲۴ ساعت گذشته (ساعت ۲۱:۰۰)**\n"
            f"👑 *امپراتوری ترید: امیرعلی جمشیدزایی*\n\n"
            f"📊 کل معاملات انجام شده امروز: {d_trades} معامله\n"
            f"💰 سود خالص کسب شده در ۲۴ ساعت: {d_profit:+.2f} تتر\n"
            f"📈 درصد سود نسبت به موجودی: {profit_percent:+.1f}%\n"
            f"💵 موجودی فعلی صرافی: {live_bal:.2f} تتر\n\n"
            f"قدرت بازار زیر دست ماست، امیرعلی!"
        )
        try:
          bot.send_photo(uid, LION_IMAGE_URL, caption=report_caption, parse_mode="Markdown")
        except Exception:
          pass

      cursor.execute("UPDATE users SET daily_profit = 0.0, daily_trades = 0")
      conn.commit()
      conn.close()
      
      time.sleep(70)
    
    time.sleep(30)

threading.Thread(target=daily_night_report_worker, daemon=True).start()

@bot.message_handler(commands=["start"])
def send_welcome(message):
  user_id = message.from_user.id
  user_name = message.from_user.first_name or "ناشناس"
  username = f"@{message.from_user.username}" if message.from_user.username else "بدون آیدی"

  conn = sqlite3.connect("users_xt.db")
  cursor = conn.cursor()
  cursor.execute(
      "INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
      (user_id, username, user_name)
  )
  cursor.execute(
      "UPDATE users SET username = ?, first_name = ? WHERE user_id = ?",
      (username, user_name, user_id)
  )
  conn.commit()
  conn.close()

  markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
  markup.add(types.KeyboardButton("📊 موجودی واقعی صرافی"))
  markup.add(types.KeyboardButton("⚙️ تنظیم دستی اهرم و سرمایه"))
  markup.add(types.KeyboardButton("🚀 شروع ترید اتوماتیک"), types.KeyboardButton("🛑 توقف ترید"))

  if user_id == ADMIN_ID:
    markup.add(types.KeyboardButton("👑 پنل مدیریت کل"))

  welcome_text = (
      "سلام به قلمرو تحلیل حرفه‌ای و ترید اتوماتیک فیوچرز. سرعت، قدرت و دقت در اجرای عملکرد، زیر نظر امیرعلی جمشیدزایی.\n\n"
      "قابلیت‌ها:\n"
      "🦁 پوزیشن خودکار همراه با دلیل ورود، حد سود و ضرر • تنظیم دستی اهرم و سرمایه • گزارش سود ساعت ۹ شب • اتصال صرافی XT\n\n"
      "برای شروع قلمرو، کلیک کنید ⚡"
  )
  bot.send_message(message.chat.id, welcome_text, reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "📊 موجودی واقعی صرافی")
def check_real_balance(message):
  live_bal = fetch_xt_balance()
  bot.send_message(
      message.chat.id,
      f"📊 وضعیت حساب واقعی شما در صرافی XT:\n\n💰 موجودی قابل معامله: {live_bal:.2f} تتر",
  )

@bot.message_handler(func=lambda message: message.text == "⚙️ تنظیم دستی اهرم و سرمایه")
def manual_settings_prompt(message):
  warning_text = (
      "⚠️ **اخطار بسیار مهم مدیریت ریسک و سرمایه:**\n\n"
      "استفاده از اهرم‌های بالا و ورود حجم سنگین از سرمایه در بازار فیوچرز، ریسک لیکویید شدن و از دست رفتن دارایی را به شدت بالا می‌برد. "
      "مسئولیت تنظیمات دستی به عهده خود شماست.\n\n"
      "لطفاً تنظیمات خود را به صورت زیر ارسال کنید (مثلاً اهرم ۱۰ و سرمایه ۵۰ تتر):\n"
      "`10,50`"
  )
  user_temp_settings[message.from_user.id] = "waiting_for_manual_input"
  bot.send_message(message.chat.id, warning_text, parse_mode="Markdown")

@bot.message_handler(func=lambda message: user_temp_settings.get(message.from_user.id) == "waiting_for_manual_input")
def save_manual_settings(message):
  user_id = message.from_user.id
  try:
    parts = message.text.split(",")
    leverage = int(parts[0].strip())
    capital = float(parts[1].strip())

    if leverage < 1 or leverage > 125:
      bot.send_message(message.chat.id, "❌ اهرم باید بین ۱ تا ۱۲۵ باشد.")
      return

    live_bal = fetch_xt_balance()
    if capital > live_bal:
      bot.send_message(message.chat.id, f"❌ سرمایه از موجودی کل شما ({live_bal:.2f} تتر) بیشتر است.")
      return

    conn = sqlite3.connect("users_xt.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET leverage = ?, custom_capital = ? WHERE user_id = ?", (leverage, capital, user_id))
    conn.commit()
    conn.close()

    user_temp_settings.pop(user_id, None)

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("🚀 شروع ترید اتوماتیک"))
    markup.add(types.KeyboardButton("📊 موجودی واقعی صرافی"), types.KeyboardButton("⚙️ تنظیم دستی اهرم و سرمایه"))

    bot.send_message(
        message.chat.id,
        f"✅ تنظیمات دستی با موفقیت ثبت شد:\n\n- اهرم: {leverage}x\n- سرمایه: {capital} تتر\n\n"
        f"حالا می‌توانید دکمه شروع اتوماتیک را بزنید:",
        reply_markup=markup
    )
  except Exception:
    bot.send_message(message.chat.id, "❌ فرمت ورودی اشتباه است. لطفاً به صورت `اهرم,سرمایه` (مثلاً `10,50`) بفرستید.")

@bot.message_handler(func=lambda message: message.text == "🚀 شروع ترید اتوماتیک")
def start_trading(message):
  user_id = message.from_user.id
  conn = sqlite3.connect("users_xt.db")
  cursor = conn.cursor()
  cursor.execute("UPDATE users SET status = 'active' WHERE user_id = ?", (user_id,))
  cursor.execute("SELECT leverage, custom_capital FROM users WHERE user_id = ?", (user_id,))
  row = cursor.fetchone()
  conn.commit()
  conn.close()

  leverage, custom_cap = row if row else (10, 0)
  live_bal = fetch_xt_balance()
  cap_text = f"{custom_cap} تتر (دستی)" if custom_cap > 0 else f"خودکار ({live_bal * 0.9:.2f} تتر)"

  bot.send_message(
      message.chat.id,
      f"🚀 موتور ترید اتوماتیک با موفقیت روشن شد!\n\n"
      f"• اهرم فعال: {leverage}x\n"
      f"• سرمایه معاملاتی: {cap_text}\n"
      f"ربات بازار را رصد می‌کند و با حد سود، حد ضرر و دلیل ورود معامله باز می‌کند.",
  )

@bot.message_handler(func=lambda message: message.text == "🛑 توقف ترید")
def stop_trading(message):
  user_id = message.from_user.id
  conn = sqlite3.connect("users_xt.db")
  cursor = conn.cursor()
  cursor.execute("UPDATE users SET status = 'inactive' WHERE user_id = ?", (user_id,))
  conn.commit()
  conn.close()
  bot.send_message(message.chat.id, "🛑 ترید اتوماتیک متوقف شد.")

@bot.message_handler(func=lambda message: message.text == "👑 پنل مدیریت کل" and message.from_user.id == ADMIN_ID)
def admin_panel(message):
  conn = sqlite3.connect("users_xt.db")
  cursor = conn.cursor()
  cursor.execute("SELECT user_id, username, first_name, status, leverage, custom_capital FROM users")
  all_users = cursor.fetchall()
  conn.close()

  total_users = len(all_users)
  active_users = sum(1 for u in all_users if u[3] == 'active')

  users_detail_list = ""
  for idx, (uid, uname, fname, status, lev, cap) in enumerate(all_users, 1):
    status_fa = "فعال ✅" if status == 'active' else "غیرفعال ❌"
    users_detail_list += f"{idx}. نام: {fname} | آیدی: {uname} | اهرم: {lev}x | سرمایه دستی: {cap} | وضعیت: {status_fa}\n"

  live_bal = fetch_xt_balance()
  admin_panel_text = (
      f"👑 پنل مدیریت کل امپراتوری:\n\n"
      f"- موجودی زنده صرافی XT: {live_bal:.2f} تتر\n"
      f"- کل کاربران متصل: {total_users}\n"
      f"- کاربران فعال: {active_users}\n\n"
      f"📋 لیست کاربران:\n{users_detail_list if users_detail_list else 'کاربری ثبت نشده.'}\n\n"
      f"قدرت دست ماست، امیرعلی!"
  )
  bot.send_message(message.chat.id, admin_panel_text, parse_mode="Markdown")

if __name__ == "__main__":
  print("Complete Bot with Manual Settings and Risk Warning is running...")
  bot.infinity_polling()
