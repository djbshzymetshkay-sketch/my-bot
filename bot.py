import telebot

TOKEN = "8768214414:AAEfjCLbeg4K1UwxsQJsSaToqx_SlcX2ISY"
bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "سلام! ربات امیر تریدر آنلاین و آماده به کار است.")

@bot.message_handler(func=lambda message: True)
def echo_all(message):
    bot.reply_to(message, message.text)

bot.infinity_polling()
