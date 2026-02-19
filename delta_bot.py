import ccxt
import pandas as pd
import time
import os
import telebot
from threading import Thread
from datetime import datetime
from keep_alive import keep_alive

# ===== 1. CONFIGURATION (SECURE) =====
TG_TOKEN = os.environ.get('TG_TOKEN')
TG_CHAT_ID = "7729719892" 
SYMBOL = 'ETH/USD:USD' 

# Trade Settings
TRADE_AMOUNT = 0.01  
LEVERAGE = 25        
SL_POINTS = 10.0     
TP_POINTS = 20.0     

# Global State & Stats
is_trading_active = False # Default to OFF for safety
daily_stats = {"wins": 0, "losses": 0, "total_points": 0.0, "start_time": time.time()}
latest_data = {"price": 0.0, "rsi": 0.0}

# ===== 2. INITIALIZATION =====
bot = telebot.TeleBot(TG_TOKEN)
exchange = ccxt.delta({
    'apiKey': os.environ.get('DELTA_API_KEY'),
    'secret': os.environ.get('DELTA_API_SECRET'),
    'urls': {'api': {'public': 'https://api.india.delta.exchange', 'private': 'https://api.india.delta.exchange'}}
})

try:
    exchange.set_leverage(LEVERAGE, SYMBOL)
except:
    pass

# ===== 3. TELEGRAM COMMAND HANDLERS =====

@bot.message_handler(commands=['start'])
def start_bot(message):
    global is_trading_active
    is_trading_active = True
    welcome_text = (
        "👋 **Welcome to your Delta Trading Bot!**\n\n"
        "🟢 **Auto-Trading: STARTED**\n"
        "The bot is now scanning ETH/USDT for signals.\n\n"
        "**Available Commands:**\n"
        "📊 /price - Get current ETH price & RSI\n"
        "📈 /report - See session profit/loss\n"
        "🛑 /stop - Stop auto-trading"
    )
    bot.reply_to(message, welcome_text, parse_mode="Markdown")

@bot.message_handler(commands=['stop'])
def stop_bot(message):
    global is_trading_active
    is_trading_active = False
    bot.reply_to(message, "🛑 **Auto-Trading: STOPPED**\nThe bot will still track price but will NOT place new trades.", parse_mode="Markdown")

@bot.message_handler(commands=['price', 'status'])
def send_price(message):
    global latest_data
    if latest_data["price"] == 0.0:
        bot.reply_to(message, "⏳ Still syncing market data... Wait 30s.")
    else:
        text = (f"📊 *ETH/USDT Status*\nPrice: {latest_data['price']}\nRSI: {latest_data['rsi']:.2f}\n"
                f"Trading Mode: {'🟢 ACTIVE' if is_trading_active else '🔴 STOPPED'}")
        bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(commands=['report'])
def manual_report(message):
    global daily_stats
    report = (f"📊 **CURRENT SESSION STATS**\n"
              f"Wins: {daily_stats['wins']}\n"
              f"Losses: {daily_stats['losses']}\n"
              f"Net Points: {daily_stats['total_points']:.2f}")
    bot.reply_to(message, report, parse_mode="Markdown")

# ===== 4. BACKGROUND LOGIC & TRADING =====

def send_daily_report():
    global daily_stats
    while True:
        time.sleep(86400) # 24 Hours
        report = (f"📅 **DAILY TRADING REPORT**\n"
                  f"Trades: {daily_stats['wins'] + daily_stats['losses']}\n"
                  f"✅ Wins: {daily_stats['wins']} | ❌ Losses: {daily_stats['losses']}\n"
                  f"📈 Net P/L: {daily_stats['total_points']:.2f} Points")
        bot.send_message(TG_CHAT_ID, report, parse_mode="Markdown")
        daily_stats = {"wins": 0, "losses": 0, "total_points": 0.0, "start_time": time.time()}

def monitor_trade_result(order_id, side, sl_price, tp_price):
    global daily_stats
    while True:
        try:
            open_orders = exchange.fetch_open_orders(SYMBOL)
            if not any(o['id'] == order_id for o in open_orders):
                closed_trades = exchange.fetch_my_trades(SYMBOL, limit=5)
                exit_p = float(closed_trades[-1]['price'])
                is_win = (side == 'buy' and exit_p >= tp_price) or (side == 'sell' and exit_p <= tp_price)
                
                if is_win:
                    daily_stats["wins"] += 1
                    daily_stats["total_points"] += TP_POINTS
                    msg = "💰 **TAKE PROFIT HIT!**"
                else:
                    daily_stats["losses"] += 1
                    daily_stats["total_points"] -= SL_POINTS
                    msg = "📉 **STOP LOSS HIT**"
                
                bot.send_message(TG_CHAT_ID, f"{msg}\nExit: {exit_p}\nSession P/L: {daily_stats['total_points']:.2f}", parse_mode="Markdown")
                break 
            time.sleep(60) 
        except:
            time.sleep(30)

def execute_trade(side, entry_price):
    try:
        exchange.create_market_order(SYMBOL, side, TRADE_AMOUNT)
        sl_p = entry_price - SL_POINTS if side == 'buy' else entry_price + SL_POINTS
        tp_p = entry_price + TP_POINTS if side == 'buy' else entry_price - SL_POINTS
        
        exit_order = exchange.create_order(SYMBOL, 'market', 'sell' if side == 'buy' else 'buy', TRADE_AMOUNT, params={
            'stopLossPrice': sl_p, 'takeProfitPrice': tp_p
        })
        
        bot.send_message(TG_CHAT_ID, f"🚀 **AUTO-{side.upper()} OPENED**\nPrice: {entry_price}")
        Thread(target=monitor_trade_result, args=(exit_order['id'], side, sl_p, tp_p), daemon=True).start()
    except Exception as e:
        bot.send_message(TG_CHAT_ID, f"❌ **ORDER ERROR:** {e}")

def run_strategy():
    global latest_data, is_trading_active
    last_signal_time = None
    while True:
        try:
            bars = exchange.fetch_ohlcv(SYMBOL, timeframe='15m', limit=100)
            df = pd.DataFrame(bars, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
            df['close'] = df['close'].astype(float)
            
            # EMA & RSI Fix
            df['ema_f'] = df['close'].ewm(span=15, adjust=False).mean()
            df['ema_s'] = df['close'].ewm(span=33, adjust=False).mean()
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
            loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
            df['rsi'] = 100 - (100 / (1 + (gain / loss)))

            curr = df.iloc[-1]
            latest_data.update({"price": curr['close'], "rsi": curr['rsi']})

            # Signal Logic
            c_range = curr['high'] - curr['low']
            body_pct = (abs(curr['close'] - curr['open']) / c_range * 100) if c_range > 0 else 0
            buy_sig = (curr['ema_f'] > curr['ema_s']) and (curr['low'] <= curr['ema_f'] <= curr['high']) and (curr['close'] > curr['open']) and body_pct >= 60 and curr['rsi'] > 60
            sell_sig = (curr['ema_f'] < curr['ema_s']) and (curr['low'] <= curr['ema_f'] <= curr['high']) and (curr['close'] < curr['open']) and body_pct >= 60 and curr['rsi'] < 40

            if (buy_sig or sell_sig) and curr['ts'] != last_signal_time:
                if is_trading_active:
                    execute_trade('buy' if buy_sig else 'sell', curr['close'])
                    last_signal_time = curr['ts']

            time.sleep(30)
        except:
            time.sleep(20)

# ===== 5. MAIN START =====

if __name__ == "__main__":
    keep_alive() 
    Thread(target=run_strategy, daemon=True).start()
    Thread(target=send_daily_report, daemon=True).start()
    print("🤖 Bot is starting infinity polling...")
    bot.infinity_polling(timeout=60, long_polling_timeout=5)