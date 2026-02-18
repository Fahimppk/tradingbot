import ccxt
import pandas as pd
import time
import os
import telebot
from threading import Thread
from keep_alive import keep_alive # Imports your web server

# ===== 1. CONFIGURATION (SECURE) =====
# On Render, add TG_TOKEN to the 'Environment' tab
TG_TOKEN = os.environ.get('TG_TOKEN', '7729719892:AAFWa6QFX3pxSHe5wXpwt2_2mr3MZs42NhY')
TG_CHAT_ID = "7729719892" 
SYMBOL = 'ETH/USD:USD' 
TIMEFRAME = '15m'

# Strategy Params
EMA_FAST_LEN = 15
EMA_SLOW_LEN = 33
RSI_LEN = 14
BODY_PCT_REQ = 60.0

# ===== 2. INITIALIZATION =====
bot = telebot.TeleBot(TG_TOKEN)
exchange = ccxt.delta({
    'urls': {'api': {'public': 'https://api.india.delta.exchange'}}
})

latest_data = {"price": 0.0, "rsi": 0.0, "high": 0.0, "low": 0.0, "ema15": 0.0}

# ===== 3. COMMAND HANDLERS =====
@bot.message_handler(commands=['price', 'status'])
def send_price(message):
    global latest_data
    if latest_data["price"] == 0.0:
        bot.reply_to(message, "⏳ Syncing data... Try again in 10 seconds.")
    else:
        text = (f"📊 *ETH/USDT Perpetual*\n"
                f"Price: {latest_data['price']}\n"
                f"RSI: {latest_data['rsi']:.2f}\n"
                f"EMA 15: {latest_data['ema15']:.2f}")
        bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(commands=['top'])
def send_top(message):
    global latest_data
    text = (f"🏔️ *Candle Extremes (15m):*\n"
            f"High: {latest_data['high']}\n"
            f"Low: {latest_data['low']}\n"
            f"Target EMA: {latest_data['ema15']:.2f}")
    bot.reply_to(message, text, parse_mode="Markdown")

# ===== 4. STRATEGY LOOP =====
def run_strategy():
    global latest_data
    print(f"🚀 Monitoring {SYMBOL}...")
    last_signal_time = None

    while True:
        try:
            bars = exchange.fetch_ohlcv(SYMBOL, timeframe=TIMEFRAME, limit=100)
            df = pd.DataFrame(bars, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
            df['close'] = df['close'].astype(float)
            
            # EMA Calculations
            df['ema_f'] = df['close'].ewm(span=EMA_FAST_LEN, adjust=False).mean()
            df['ema_s'] = df['close'].ewm(span=EMA_SLOW_LEN, adjust=False).mean()
            
            # RSI Calculation
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=RSI_LEN).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=RSI_LEN).mean()
            df['rsi'] = 100 - (100 / (1 + (gain / loss)))

            curr = df.iloc[-1]
            latest_data.update({"price": curr['close'], "rsi": curr['rsi'], "high": curr['high'], "low": curr['low'], "ema15": curr['ema_f']})

            # Signal Logic (EMA Touch + Strong Body + RSI)
            c_range = curr['high'] - curr['low']
            body_pct = (abs(curr['close'] - curr['open']) / c_range * 100) if c_range > 0 else 0
            
            buy_sig = (curr['ema_f'] > curr['ema_s']) and (curr['low'] <= curr['ema_f'] <= curr['high']) and (curr['close'] > curr['open']) and body_pct >= BODY_PCT_REQ and curr['rsi'] > 60
            sell_sig = (curr['ema_f'] < curr['ema_s']) and (curr['low'] <= curr['ema_f'] <= curr['high']) and (curr['close'] < curr['open']) and body_pct >= BODY_PCT_REQ and curr['rsi'] < 40

            if (buy_sig or sell_sig) and curr['ts'] != last_signal_time:
                side = "🟢 BUY" if buy_sig else "🔴 SELL"
                bot.send_message(TG_CHAT_ID, f"*{side} SIGNAL*\nPrice: {curr['close']}\nRSI: {curr['rsi']:.2f}", parse_mode="Markdown")
                last_signal_time = curr['ts']

            time.sleep(30)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(20)

# ===== 5. EXECUTION =====
if __name__ == "__main__":
    keep_alive() # Starts web server to prevent Render from sleeping
    Thread(target=run_strategy, daemon=True).start()
    bot.infinity_polling()