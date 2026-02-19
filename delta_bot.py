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
SYMBOL = 'ETHUSD' 

# Trade Settings
TRADE_AMOUNT = 0.01  
LEVERAGE = 25        
SL_POINTS = 10.0     
TP_POINTS = 20.0     

# Global Stats Tracker
daily_stats = {"wins": 0, "losses": 0, "total_points": 0.0, "start_time": time.time()}

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

# ===== 3. DAILY REPORT LOGIC =====
def send_daily_report():
    global daily_stats
    while True:
        # Wait 24 hours (86400 seconds)
        time.sleep(86400)
        
        report = (f"📅 **DAILY TRADING REPORT**\n"
                  f"Trades: {daily_stats['wins'] + daily_stats['losses']}\n"
                  f"✅ Wins: {daily_stats['wins']}\n"
                  f"❌ Losses: {daily_stats['losses']}\n"
                  f"📈 Total P/L: {daily_stats['total_points']:.2f} Points")
        
        bot.send_message(TG_CHAT_ID, report, parse_mode="Markdown")
        
        # Reset stats for the next day
        daily_stats = {"wins": 0, "losses": 0, "total_points": 0.0, "start_time": time.time()}

@bot.message_handler(commands=['report'])
def manual_report(message):
    report = (f"📊 **CURRENT SESSION STATS**\n"
              f"Wins: {daily_stats['wins']}\n"
              f"Losses: {daily_stats['losses']}\n"
              f"Net Points: {daily_stats['total_points']:.2f}")
    bot.reply_to(message, report, parse_mode="Markdown")

# ===== 4. UPDATED MONITOR (TRACKS STATS) =====
def monitor_trade_result(order_id, side, sl_price, tp_price):
    global daily_stats
    while True:
        try:
            open_orders = exchange.fetch_open_orders(SYMBOL)
            if not any(o['id'] == order_id for o in open_orders):
                closed_trades = exchange.fetch_my_trades(SYMBOL, limit=5)
                exit_p = float(closed_trades[-1]['price'])
                
                is_win = (side == 'buy' and exit_p >= tp_p) or (side == 'sell' and exit_p <= tp_p)
                
                # Update Stats
                if is_win:
                    daily_stats["wins"] += 1
                    daily_stats["total_points"] += TP_POINTS
                    msg = "💰 **TAKE PROFIT HIT!**"
                else:
                    daily_stats["losses"] += 1
                    daily_stats["total_points"] -= SL_POINTS
                    msg = "📉 **STOP LOSS HIT**"
                
                bot.send_message(TG_CHAT_ID, f"{msg}\nExit: {exit_p}\nPoints: {daily_stats['total_points']:.2f}", parse_mode="Markdown")
                break 
            time.sleep(60) 
        except:
            time.sleep(30)

# ===== 5. EXECUTION & LOOP =====
def execute_trade(side, entry_price):
    try:
        exchange.create_market_order(SYMBOL, side, TRADE_AMOUNT)
        sl_p = entry_price - SL_POINTS if side == 'buy' else entry_price + SL_POINTS
        tp_p = entry_price + TP_POINTS if side == 'buy' else entry_price - SL_POINTS
        
        exit_order = exchange.create_order(SYMBOL, 'market', 'sell' if side == 'buy' else 'buy', TRADE_AMOUNT, params={
            'stopLossPrice': sl_p, 'takeProfitPrice': tp_p
        })
        
        bot.send_message(TG_CHAT_ID, f"🚀 **AUTO-{side.upper()} OPENED**\nEntry: {entry_price}")
        Thread(target=monitor_trade_result, args=(exit_order['id'], side, sl_p, tp_p), daemon=True).start()
    except Exception as e:
        bot.send_message(TG_CHAT_ID, f"❌ **ERROR:** {e}")

# ... (EMA/RSI strategy loop remains the same) ...

if __name__ == "__main__":
    keep_alive()
    Thread(target=run_strategy, daemon=True).start()
    Thread(target=send_daily_report, daemon=True).start() # Start the daily timer
    bot.infinity_polling()