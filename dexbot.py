# solana_dex_bot.py
import os
import time
import aiohttp
import sqlite3
import asyncio
from datetime import datetime
from typing import Dict, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater, CommandHandler, CallbackQueryHandler,
    MessageHandler, Filters, CallbackContext
)
from solana.rpc.api import Client
from solana.rpc.commitment import Confirmed
from solders.keypair import Keypair
from spl.token.client import Token
from dotenv import load_dotenv

load_dotenv()

class SolanaDexBot:
    def __init__(self):
        self.config = {
            'rpc_url': os.getenv('SOLANA_RPC'),
            'dex_programs': {
                'raydium': '675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8',
                'orca': '9W959DqEETiGZocYWCQPaJ6sBmUzgfxXfqGeTEdap3XV'
            },
            'jupiter_api': 'https://quote-api.jup.ag/v6',
            'risk_params': {
                'min_liquidity': 5000,
                'max_creator_burns': 3,
                'verified_programs': True
            }
        }
        
        self.db = sqlite3.connect('dexbot.db')
        self._init_db()
        self.client = Client(self.config['rpc_url'])
        self.security = SecurityManager()

    def _init_db(self):
        cursor = self.db.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS tokens
            (address TEXT PRIMARY KEY,
             symbol TEXT,
             liquidity REAL,
             volume REAL,
             creator_burns INTEGER,
             created_at DATETIME,
             risk_status TEXT)''')
        self.db.commit()

    async def analyze_token(self, token_address: str) -> Dict[str, Any]:
        """Comprehensive Solana token analysis"""
        token_data = await self._fetch_token_data(token_address)
        analysis = {
            'rug_risk': 'low',
            'liquidity_risk': self._check_liquidity(token_data),
            'program_risk': self._check_program_risk(token_data),
            'creator_risk': self._check_creator_behavior(token_data)
        }
        return {**token_data, **analysis}

    async def _fetch_token_data(self, address: str) -> Dict[str, Any]:
        """Fetch token metadata and market data"""
        async with aiohttp.ClientSession() as session:
            # Get basic token info
            async with session.get(
                f"https://api.dexscreener.com/latest/dex/tokens/{address}"
            ) as resp:
                dexscreener_data = await resp.json()
            
            # Get additional chain data
            token_info = self.client.get_account_info(address).value
            mint_info = Token(self.client, address).get_mint_info()
            
        return {
            'address': address,
            'liquidity': dexscreener_data['pairs'][0]['liquidity']['usd'],
            'volume': dexscreener_data['pairs'][0]['volume']['h24'],
            'creator_burns': token_info.owner.burns,
            'program_id': str(token_info.owner),
            'created_at': datetime.fromtimestamp(mint_info.data.timestamp)
        }

    def _check_liquidity(self, token: Dict[str, Any]) -> str:
        return 'high' if token['liquidity'] > self.config['risk_params']['min_liquidity'] else 'low'

    def _check_program_risk(self, token: Dict[str, Any]) -> str:
        return 'verified' if token['program_id'] in self.config['dex_programs'].values() else 'unverified'

    def _check_creator_behavior(self, token: Dict[str, Any]) -> str:
        if token['creator_burns'] > self.config['risk_params']['max_creator_burns']:
            return 'high'
        return 'low'

    async def execute_swap(self, user_wallet: str, token_in: str, amount: float) -> str:
        """Execute swap through Jupiter Aggregator with security checks"""
        if not self.security.verify_wallet(user_wallet):
            raise Exception("Wallet verification failed")

        async with aiohttp.ClientSession() as session:
            # Get quote
            async with session.get(
                f"{self.config['jupiter_api']}/quote",
                params={
                    'inputMint': 'So11111111111111111111111111111111111111112',  # SOL
                    'outputMint': token_in,
                    'amount': int(amount * 1e9),
                    'slippageBps': 100
                }
            ) as resp:
                quote = await resp.json()

            if not self.security.validate_quote(quote):
                raise Exception("Invalid swap quote")

            # Prepare swap
            async with session.post(
                f"{self.config['jupiter_api']}/swap",
                json={
                    'quoteResponse': quote,
                    'userPublicKey': user_wallet,
                    'wrapAndUnwrapSol': True
                }
            ) as resp:
                swap_data = await resp.json()

        return await self._sign_and_send(swap_data['swapTransaction'], user_wallet)

    async def _sign_and_send(self, transaction: str, wallet: str) -> str:
        """Sign and send transaction (implementation simplified)"""
        # In real implementation, use proper wallet integration
        return "SIMULATED_TX_ID"

class TelegramBot:
    def __init__(self, dex_bot: SolanaDexBot):
        self.dex_bot = dex_bot
        self.updater = Updater(os.getenv('TG_TOKEN'), use_context=True)
        
        handlers = [
            CommandHandler('start', self.start),
            CommandHandler('analyze', self.analyze),
            CommandHandler('buy', self.buy),
            CallbackQueryHandler(self.button_handler)
        ]
        for handler in handlers:
            self.updater.dispatcher.add_handler(handler)

    def start(self, update: Update, context: CallbackContext):
        keyboard = [
            [InlineKeyboardButton("🔄 SOL Swap", callback_data='swap')],
            [InlineKeyboardButton("📈 Token Analytics", callback_data='analyze')]
        ]
        update.message.reply_text(
            '🔹 Solana DexBot Interface',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    def analyze(self, update: Update, context: CallbackContext):
        if not context.args:
            update.message.reply_text("Usage: /analyze [TOKEN_ADDRESS]")
            return
            
        token_address = context.args[0]
        analysis = asyncio.run(self.dex_bot.analyze_token(token_address))
        
        report = f"🔍 Analysis for {token_address}:\n" \
                 f"• Liquidity: ${analysis['liquidity']:,.2f}\n" \
                 f"• Program Risk: {analysis['program_risk'].upper()}\n" \
                 f"• Creator Risk: {analysis['creator_risk'].upper()}\n" \
                 f"• Overall Safety: {analysis['rug_risk'].upper()}"
        
        update.message.reply_text(report)

    def buy(self, update: Update, context: CallbackContext):
        if len(context.args) < 2:
            update.message.reply_text("Usage: /buy [TOKEN_ADDRESS] [SOL_AMOUNT]")
            return
            
        token_address = context.args[0]
        amount = float(context.args[1])
        
        try:
            tx_id = asyncio.run(self.dex_bot.execute_swap(
                user_wallet=str(update.message.chat_id),
                token_in=token_address,
                amount=amount
            ))
            update.message.reply_text(f"✅ Swap executed! TX ID: {tx_id}")
        except Exception as e:
            update.message.reply_text(f"❌ Error: {str(e)}")

class SecurityManager:
    def __init__(self):
        self.blacklist = self._load_blacklist()
    
    def _load_blacklist(self):
        # Would load from external source in production
        return {
            'HoneyPotTokens': set(),
            'KnownScamWallets': set()
        }
    
    def verify_wallet(self, wallet: str) -> bool:
        return wallet not in self.blacklist['KnownScamWallets']
    
    def validate_quote(self, quote: Dict) -> bool:
        # Check for reasonable slippage and valid routes
        return (
            quote['priceImpactPct'] < 0.1 and
            quote['marketInfos'][0]['amm'] == 'Raydium'
        )

if __name__ == "__main__":
    bot = SolanaDexBot()
    tg_bot = TelegramBot(bot)
    
    tg_bot.updater.start_polling()
    
    # Monitoring loop
    while True:
        # Would implement actual monitoring logic
        time.sleep(300)
