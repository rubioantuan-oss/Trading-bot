import ccxt
import pandas as pd
import ta
import numpy as np
import time
import winsound
import websocket
import json
import threading

############################################
# EXCHANGE
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
# REAL TIME PRICE STREAM
############################################

prices = {}

def on_message(ws, message):

    data = json.loads(message)

    symbol = data['s']
    bid = float(data['b'])
    ask = float(data['a'])

    prices[symbol] = (bid, ask)


def start_socket():

    url = "wss://stream.binance.com:9443/ws/!bookTicker"

    ws = websocket.WebSocketApp(
        url,
        on_message=on_message
    )

    ws.run_forever()

############################################
# MARKET DATA
############################################

def get_data(symbol, timeframe):

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

############################################
# LIQUIDITY FILTER
############################################

def liquidity_filter(symbol):

    try:

        ticker = exchange.fetch_ticker(symbol)

        volume = ticker['quoteVolume']

        if volume is None:
            return False

        return volume > 1000000

    except:
        return False

############################################
# ORDERBOOK IMBALANCE
############################################

def liquidity_imbalance(symbol):

    try:

        book = exchange.fetch_order_book(symbol, 10)

        bid_vol = sum([b[1] for b in book['bids']])
        ask_vol = sum([a[1] for a in book['asks']])

        if ask_vol == 0:
            return 0

        return bid_vol / ask_vol

    except:
        return 0

############################################
# SPREAD FILTER
############################################

def spread_filter(symbol):

    key = symbol.replace("/","")

    if key not in prices:
        return False

    bid, ask = prices[key]

    if bid == 0 or ask == 0:
        return False

    spread = (ask - bid) / ask

    return spread < 0.002

############################################
# TREND
############################################

def is_bullish(df):

    last = df.iloc[-1]

    return last['ema9'] > last['ema21'] and last['close'] > last['ema200']

############################################
# LIQUIDITY GRAB
############################################

def liquidity_grab(df):

    last = df.iloc[-1]
    prev = df.iloc[-2]

    grab = (
        last['low'] < prev['support'] and
        last['close'] > prev['support']
    )

    return grab

############################################
# WHALE VOLUME
############################################

def whale_volume(df):

    last = df.iloc[-1]
    avg = df['vol_avg'].iloc[-1]

    if avg == 0 or np.isnan(avg):
        return False

    return last['volume'] > avg * 2.5

############################################
# MOMENTUM
############################################

def momentum(df):

    last3 = df.tail(3)

    price_up = (
        last3['close'].iloc[2] >
        last3['close'].iloc[1] >
        last3['close'].iloc[0]
    )

    vol_up = (
        last3['volume'].iloc[2] >
        last3['volume'].iloc[1]
    )

    return price_up and vol_up

############################################
# PROBABILITY ENGINE
############################################

def probability_score(df5, df15, btc, symbol):

    score = 0

    last = df5.iloc[-1]

    if last['ema9'] > last['ema21']:
        score += 15

    if last['close'] > last['ema200']:
        score += 15

    if 45 <= last['rsi'] <= 65:
        score += 10

    if last['adx'] > 20:
        score += 10

    if whale_volume(df5):
        score += 15

    if liquidity_grab(df5):
        score += 10

    if is_bullish(df15):
        score += 10

    if is_bullish(btc):
        score += 5

    if momentum(df5):
        score += 5

    imbalance = liquidity_imbalance(symbol)

    if imbalance > 1.3:
        score += 5

    return score

############################################
# SIGNAL ENGINE
############################################

def check_symbol(symbol, btc15):

    try:

        if not liquidity_filter(symbol):
            return

        if not spread_filter(symbol):
            return

        df5 = get_data(symbol,'5m')
        df15 = get_data(symbol,'15m')

        last = df5.iloc[-1]

        prob = probability_score(df5, df15, btc15, symbol)

        if prob >= 70:

            if symbol not in active_signals:

                entry_price = last['close']
                atr = last['atr']

                if np.isnan(atr):
                    return

                stop_price = entry_price - (atr * 1.2)
                take_profit = entry_price + (atr * 2)

                risk_amount = capital * risk_percent

                quantity = risk_amount / (entry_price - stop_price)

                potential_loss = quantity * (entry_price - stop_price)
                potential_gain = quantity * (take_profit - entry_price)

                print(f"\n🔥 SETUP PROBABILIDAD ALTA en {symbol}")
                print(f"Probabilidad sistema: {prob}%")

                print(f"\nPrecio entrada: {round(entry_price,4)}")
                print(f"Cantidad: {round(quantity,4)}")

                print("\n🎯 OCO SUGERIDO")
                print(f"TAKE PROFIT: {round(take_profit,4)}")
                print(f"STOP LOSS: {round(stop_price,4)}")

                print(f"\nRiesgo: ${round(potential_loss,2)}")
                print(f"Ganancia estimada: ${round(potential_gain,2)}")

                print("🔔 ALERTA TRADE")

                active_signals[symbol] = True

        else:

            if symbol in active_signals:
                del active_signals[symbol]

    except Exception as e:

        print(f"error en {symbol}: {e}")

############################################
# START SOCKET
############################################

thread = threading.Thread(target=start_socket)
thread.daemon = True
thread.start()

############################################
# LOOP
############################################

while True:

    print("\n🔎 Escaneando mercado institucional...")

    btc15 = get_data('BTC/USDT','15m')

    for symbol in symbols:

        check_symbol(symbol, btc15)

    time.sleep(30)
