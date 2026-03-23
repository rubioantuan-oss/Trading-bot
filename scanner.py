import ccxt
import pandas as pd
import ta
import numpy as np
import time
import websocket
import json
import threading
import os

# 🔵 FLASK SERVER (CORREGIDO PARA REPLIT)
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Bot activo 24/7 🚀"

def run():
    port = int(os.environ.get("PORT", 8080))  # 🔥 IMPORTANTE
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()

############################################
# EXCHANGE (KUCOIN)
############################################

exchange = ccxt.kucoin({
    'enableRateLimit': True
})

markets = exchange.load_markets()

symbols = [
    s for s in markets
    if "/USDT" in s and markets[s]['spot']
]

capital = 100
risk_percent = 0.02

active_signals = {}

############################################
# DATA
############################################

def get_data(symbol, timeframe):

    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=200)

        df = pd.DataFrame(
            ohlcv,
            columns=['time','open','high','low','close','volume']
        )

        df['ema9'] = ta.trend.ema_indicator(df['close'], 9)
        df['ema21'] = ta.trend.ema_indicator(df['close'], 21)
        df['ema200'] = ta.trend.ema_indicator(df['close'], 200)

        df['rsi'] = ta.momentum.rsi(df['close'], 14)

        df['atr'] = ta.volatility.average_true_range(
            df['high'], df['low'], df['close'], window=14
        )

        df['adx'] = ta.trend.adx(
            df['high'], df['low'], df['close'], 14
        )

        df['vol_avg'] = df['volume'].rolling(20).mean()

        df['resistance'] = df['high'].rolling(20).max()
        df['support'] = df['low'].rolling(20).min()

        return df

    except Exception as e:
        print(f"Error data {symbol}: {e}")
        return None

############################################
# FILTROS
############################################

def liquidity_filter(symbol):
    try:
        ticker = exchange.fetch_ticker(symbol)
        volume = ticker['quoteVolume']
        return volume and volume > 1000000
    except:
        return False

def liquidity_imbalance(symbol):
    try:
        book = exchange.fetch_order_book(symbol, 10)
        bid_vol = sum([b[1] for b in book['bids']])
        ask_vol = sum([a[1] for a in book['asks']])
        return bid_vol / ask_vol if ask_vol != 0 else 0
    except:
        return 0

############################################
# ESTRATEGIA
############################################

def is_bullish(df):
    last = df.iloc[-1]
    return last['ema9'] > last['ema21'] and last['close'] > last['ema200']

def liquidity_grab(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    return last['low'] < prev['support'] and last['close'] > prev['support']

def whale_volume(df):
    last = df.iloc[-1]
    avg = df['vol_avg'].iloc[-1]
    return avg and not np.isnan(avg) and last['volume'] > avg * 2.5

def momentum(df):
    last3 = df.tail(3)
    return (
        last3['close'].iloc[2] >
        last3['close'].iloc[1] >
        last3['close'].iloc[0]
    )

############################################
# PROBABILIDAD
############################################

def probability_score(df5, df15, btc, symbol):

    score = 0
    last = df5.iloc[-1]

    if last['ema9'] > last['ema21']: score += 15
    if last['close'] > last['ema200']: score += 15
    if 45 <= last['rsi'] <= 65: score += 10
    if last['adx'] > 20: score += 10
    if whale_volume(df5): score += 15
    if liquidity_grab(df5): score += 10
    if is_bullish(df15): score += 10
    if is_bullish(btc): score += 5
    if momentum(df5): score += 5
    if liquidity_imbalance(symbol) > 1.3: score += 5

    return score

############################################
# SIGNAL ENGINE
############################################

def check_symbol(symbol, btc15):

    try:

        if not liquidity_filter(symbol):
            return

        df5 = get_data(symbol,'5m')
        df15 = get_data(symbol,'15m')

        if df5 is None or df15 is None:
            return

        last = df5.iloc[-1]
        prob = probability_score(df5, df15, btc15, symbol)

        if prob >= 70 and symbol not in active_signals:

            entry = last['close']
            atr = last['atr']

            if np.isnan(atr):
                return

            sl = entry - (atr * 1.2)
            tp = entry + (atr * 2)

            print(f"\n🔥 {symbol}")
            print(f"Probabilidad: {prob}%")
            print(f"Entrada: {entry}")
            print(f"TP: {tp}")
            print(f"SL: {sl}")
            print("🚀 TRADE LISTO")

            active_signals[symbol] = True

        elif prob < 70 and symbol in active_signals:
            del active_signals[symbol]

    except Exception as e:
        print(f"Error {symbol}: {e}")

############################################
# START
############################################

keep_alive()

print("🚀 BOT INICIADO 24/7")

while True:

    try:
        print("\n🔎 Escaneando mercado...")

        btc15 = get_data('BTC/USDT','15m')

        if btc15 is None:
            continue

        for symbol in symbols:
            check_symbol(symbol, btc15)

        time.sleep(30)

    except Exception as e:
        print("ERROR LOOP:", e)
        time.sleep(10)
