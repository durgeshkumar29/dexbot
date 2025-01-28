# dex_bot.py
import os
import requests
import sqlite3
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    Updater, CommandHandler, CallbackQueryHandler,
    MessageHandler, Filters, CallbackContext
)
from web3 import Web3
from walletconnect import WCClient
from dotenv import load_dotenv

load_dotenv()

class DexBot:
    def __init__(self):
        self.config = {
            'filters': {
                'min_liquidity': 25000,
                'max_holders': 1500,
                'volume_threshold': 100000
            },
            'blacklist': {
                'coins': ['0x123...abc', 'SCAM', 'RUG*'],
                'devs': ['0x456...def']
            },
            'apis': {
                'dexscreener': 'https://api.dexscreener.com/latest/dex',
                'pocket_universe': 'https://api.pocketuniverse.ai/v1',
                'rugcheck': 'https://rugcheck.xyz/api/v1'
            },
            'security': {
                'session_timeout': 15,
                'max_trade': 0.1
            }
        }
        
        self.db = sqlite3.connect('dexbot.db')
        self._init_db()
        self.w3 = Web3(Web3.HTTPProvider(os.getenv('INFURA_URL')))
        self.wc_client = WCClient()

    def _init_db(self):
        cursor = self.db.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS tokens
            (address TEXT PRIMARY KEY,
             symbol TEXT,
             chain TEXT,
             liquidity REAL,
             volume REAL,
             holders INTEGER,
             created_at DATETIME,
             fake_volume_score REAL,
             rugcheck_status TEXT)''')
        self.db.commit()

    # Core Analysis Features
    def analyze_token(self, token_data):
        analysis = {
            'rug_risk': self._check_rug_risk(token_data),
            'fake_volume': self._detect_fake_volume(token_data),
            'blacklisted': self._check_blacklist(token_data)
        }
        return analysis

    def _check_rug_risk(self, token):
        response = requests.get(
            f"{self.config['apis']['rugcheck']}/contracts/verify",
            params={'address': token['address'], 'chain': token['chain']},
            headers={'x-api-key': os.getenv('RUGCHECK_KEY')}
        )
        return response.json().get('risk_status', 'unknown')

    def _detect_fake_volume(self, token):
        internal_score = self._internal_volume_check(token)
        external_score = self._pocket_universe_check(token)
        return max(internal_score, external_score)

    # Security & Trading Components
    def execute_trade(self, chat_id, action, symbol, amount):
        if not self._validate_trade(chat_id, amount):
            return False
            
        tx_data = self._prepare_transaction(action, symbol, amount)
        return self.wc_client.send_transaction(tx_data)

class TelegramBot:
    def __init__(self, dex_bot):
        self.dex_bot = dex_bot
        self.updater = Updater(os.getenv('TG_TOKEN'), use_context=True)
        
        # Command Handlers
        self.updater.dispatcher.add_handler(CommandHandler('start', self.start))
        self.updater.dispatcher.add_handler(CommandHandler('analyze', self.analyze))
        self.updater.dispatcher.add_handler(CommandHandler('buy', self.buy))
        self.updater.dispatcher.add_handler(CallbackQueryHandler(self.button_handler))

    # Mobile-Optimized UI
    def start(self, update: Update, context: CallbackContext):
        keyboard = [
            [InlineKeyboardButton("📊 Live Charts", callback_data='charts'),
             InlineKeyboardButton("⚡ Trade", callback_data='trade')],
            [InlineKeyboardButton("🔒 Security Center", callback_data='security')]
        ]
        update.message.reply_text(
            '📱 DexBot Mobile Interface',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    def analyze(self, update: Update, context: CallbackContext):
        report = self.dex_bot.generate_report()
        update.message.reply_text(f"🔍 Analysis Report:\n{report}")

    def buy(self, update: Update, context: CallbackContext):
        if not context.args:
            update.message.reply_text("Usage: /buy [SYMBOL] [AMOUNT]")
            return
            
        symbol = context.args[0]
        amount = float(context.args[1])
        self.dex_bot.execute_trade(update.message.chat_id, 'buy', symbol, amount)
        update.message.reply_text(f"✅ Buy order for {amount} {symbol} submitted")

    def button_handler(self, update: Update, context: CallbackContext):
        query = update.callback_query
        query.answer()
        
        if query.data == 'security':
            self.show_security_options(update)

class SecurityManager:
    def __init__(self):
        self.sessions = {}
        self.pin_codes = {}

    def authenticate(self, update: Update):
        chat_id = update.message.chat_id
        if self._check_session(chat_id):
            return True
            
        update.message.reply_text("🔒 Session expired. Please /login")
        return False

    def _check_session(self, chat_id):
        session = self.sessions.get(chat_id)
        return session and datetime.now() < session['expiry']

if __name__ == "__main__":
    # Initialize components
    dex_bot = DexBot()
    tg_bot = TelegramBot(dex_bot)
    
    # Start bot
    tg_bot.updater.start_polling()
    
    # Main analysis loop
    while True:
        tokens = dex_bot.fetch_market_data()
        for token in tokens:
            analysis = dex_bot.analyze_token(token)
            if analysis['blacklisted']:
                continue
                
            dex_bot.save_token(token)
        
        time.sleep(300)
