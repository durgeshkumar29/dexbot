# dex_bot.py
from dotenv import load_dotenv
load_dotenv()
from flask import Flask, render_template
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, MessageFilter
import os
import threading

app = Flask(__name__)

# Mobile-friendly Web UI Routes
@app.route('/')
def dashboard():
    return render_template('mobile_dashboard.html')

@app.route('/analytics')
def analytics():
    return render_template('analytics.html')

class DexBotUI:
    def __init__(self, updater):
        self.updater = updater
        self.setup_handlers()

    def setup_handlers(self):
        self.updater.dispatcher.add_handler(CommandHandler('start', self.start))
        self.updater.dispatcher.add_handler(CallbackQueryHandler(self.button_handler))
        self.updater.dispatcher.add_handler(MessageHandler(Filters.text, self.message_handler))

    def start(self, update: Update, context):
        keyboard = [
            [InlineKeyboardButton("📊 Live Analytics", callback_data='analytics'),
             InlineKeyboardButton("⚡ Quick Trade", callback_data='trade')],
            [InlineKeyboardButton("🔔 Alerts", callback_data='alerts'),
             InlineKeyboardButton("⚙ Settings", callback_data='settings')]
        ]
        update.message.reply_text(
            '🚀 DexBot Mobile Control Panel:',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    def button_handler(self, update: Update, context):
        query = update.callback_query
        query.answer()
        
        if query.data == 'analytics':
            context.bot.send_message(
                chat_id=query.message.chat_id,
                text="Open analytics dashboard:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Open Dashboard", url=f"http://localhost:5000/analytics")]])
            )
        
        # Add other button handlers

    def message_handler(self, update: Update, context):
        # Handle mobile text inputs
        pass

if __name__ == "__main__":
    # Start Flask web UI in separate thread
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=5000, debug=False)).start()
    
    # Start Telegram bot
    updater = Updater(token=os.getenv('TG_TOKEN'), use_context=True)
    DexBotUI(updater)
    updater.start_polling()
    updater.idle()
