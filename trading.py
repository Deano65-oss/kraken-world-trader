import time
import logging
import sqlite3
import psycopg2
from agents import AgentSystem
from data import get_market_data, pre_load_ohlc, start_websocket, get_external_data
from utils import log_error, send_alert
import os

def start_trading(pairs, gpt4o_review, gpt5_review):
    api_key = os.getenv('KRAKEN_API_KEY')
    api_secret = os.getenv('KRAKEN_API_SECRET')
    if not api_key or not api_secret:
        raise Exception("Set KRAKEN_API_KEY and KRAKEN_API_SECRET")

    logging.info(f"Starting Kraken 24/7 Trading Bot at 10:15 AM BST, September 10, 2025...")
    logging.info(f"Dry Run: {os.getenv('DRY_RUN', 'true')}")
    agent_system = AgentSystem(pairs)
    conn_sqlite = sqlite3.connect('trader.db', check_same_thread=False)
    conn_sqlite.execute('''CREATE TABLE IF NOT EXISTS trades
                           (id INTEGER PRIMARY KEY, timestamp TEXT, pair TEXT, action TEXT, amount REAL, price REAL)''')
    conn_sqlite.execute('''CREATE TABLE IF NOT EXISTS daily_pnl
                           (date TEXT PRIMARY KEY, pair TEXT, pnl REAL, trades INTEGER)''')

    # PostgreSQL setup
    conn_postgres = psycopg2.connect(
        dbname=os.getenv('PG_DB'),
        user=os.getenv('PG_USER'),
        password=os.getenv('PG_PASS'),
        host=os.getenv('PG_HOST'),
        port=os.getenv('PG_PORT')
    )
    conn_postgres.execute('''CREATE TABLE IF NOT EXISTS trades (
        id SERIAL PRIMARY KEY, timestamp TEXT, pair TEXT, action TEXT, amount REAL, price REAL)''')
    conn_postgres.execute('''CREATE TABLE IF NOT EXISTS daily_pnl (
        date TEXT, pair TEXT, pnl REAL, trades INTEGER, PRIMARY KEY (date, pair))''')

    ohlc_data = {pair: pre_load_ohlc(pair, days=30) for pair in pairs}  # 30 days pre-load
    external_data = get_external_data(pairs)
    start_websocket(pairs, lambda p, pr: ohlc_data.update({p: pre_load_ohlc(p, days=1)}))

    # Initial state load
    in_position = {}
    entry_prices = {}
    cursor = conn_sqlite.execute("SELECT pair, price FROM trades ORDER BY id DESC LIMIT ?", (len(pairs),))
    for row in cursor:
        in_position[row[0]] = True
        entry_prices[row[0]] = row[1]

    daily_target = 0.015
    current_date = time.strftime("%Y-%m-%d")
    trades_today = {pair: 0 for pair in pairs}
    daily_pnl = {pair: 0.0 for pair in pairs}

    while True:
        try:
            current_time = time.strftime("%Y-%m-%d %H:%M:%S BST")
            for pair in pairs:
                if not pair.endswith('USD'):
                    continue
                price, volume, atr = get_market_data(pair)
                usd_balance = sum(get_usd_balance(api_key, api_secret, pair) for pair in pairs) / len(pairs)
                btc_balance = get_btc_balance(api_key, api_secret, pair)
                dynamic_stop_loss = min(0.02, atr * 2 / price)
                logging.info(f"{pair} - Time: {current_time} | Price: ${price:.2f} | USD: ${usd_balance:.2f} | BTC: {btc_balance:.6f} | ATR: {atr:.4f}")

                signals = agent_system.get_signals(price, ohlc_data[pair], volume, atr, external_data[pair])
                convictions = {k: v[0] for k, v in signals.items()}
                directions = {k: v[1] for k, v in signals.items()}
                logging.info(f"{pair} Agent Signals: %s", {k: f"{v[0]*100:.1f}% -> {v[1]}" for k, v in signals.items()})

                if time.strftime("%Y-%m-%d") != current_date:
                    for p in pairs:
                        conn_sqlite.execute("INSERT OR REPLACE INTO daily_pnl (date, pair, pnl, trades) VALUES (?, ?, ?, ?)",
                                           (current_date, p, daily_pnl[p], trades_today[p]))
                        conn_postgres.execute("INSERT INTO daily_pnl (date, pair, pnl, trades) VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                                             (current_date, p, daily_pnl[p], trades_today[p]))
                    conn_sqlite.commit()
                    conn_postgres.commit()
                    current_date = time.strftime("%Y-%m-%d")
                    for p in pairs:
                        trades_today[p] = 0
                        daily_pnl[p] = 0.0
                    logging.info(f"New day started. Daily PNL: {[f'{p}: {v*100:.2f}%' for p, v in daily_pnl.items()]}")

                if pair not in in_position:
                    in_position[pair] = False
                    entry_prices[pair] = 0.0
                if not in_position[pair] and usd_balance > 1:
                    conviction_met = all(conv >= 0.03 for conv in convictions.values())
                    direction_aligned = all(d == directions['momentum'] for d in directions.values())
                    if conviction_met and direction_aligned:
                        txid = buy_btc(usd_balance / len(pairs), api_key, api_secret, pair)
                        entry_prices[pair] = price
                        in_position[pair] = True
                        trades_today[pair] += 1
                        conn_sqlite.execute("INSERT INTO trades (timestamp, pair, action, amount, price) VALUES (?, ?, ?, ?, ?)",
                                           (current_time, pair, 'buy', usd_balance / len(pairs), price))
                        conn_postgres.execute("INSERT INTO trades (timestamp, pair, action, amount, price) VALUES (%s, %s, %s, %s, %s)",
                                             (current_time, pair, 'buy', usd_balance / len(pairs), price))
                        conn_sqlite.commit()
                        conn_postgres.commit()
                        logging.info(f"{pair} Entered {directions['momentum']} at ~${price:.2f} TXID: {txid}")
                    elif trades_today[pair] == 0 and time.strftime("%H%M") > "2300" and all(conv >= 0.025 for conv in convictions.values()) and direction_aligned:
                        txid = buy_btc(usd_balance / len(pairs), api_key, api_secret, pair)
                        entry_prices[pair] = price
                        in_position[pair] = True
                        trades_today[pair] += 1
                        conn_sqlite.execute("INSERT INTO trades (timestamp, pair, action, amount, price) VALUES (?, ?, ?, ?, ?)",
                                           (current_time, pair, 'buy', usd_balance / len(pairs), price))
                        conn_postgres.execute("INSERT INTO trades (timestamp, pair, action, amount, price) VALUES (%s, %s, %s, %s, %s)",
                                             (current_time, pair, 'buy', usd_balance / len(pairs), price))
                        conn_sqlite.commit()
                        conn_postgres.commit()
                        logging.info(f"{pair} Fallback entered {directions['momentum']} at ~${price:.2f} TXID: {txid}")

                elif in_position[pair] and btc_balance > 0:
                    pnl_pct = (price - entry_prices[pair]) / entry_prices[pair]
                    target_profit = max(0.015, atr * 2 / price)
                    if pnl_pct >= target_profit:
                        txid = sell_btc(api_key, api_secret, pair)
                        daily_pnl[pair] += pnl_pct - 0.004
                        conn_sqlite.execute("INSERT INTO trades (timestamp, pair, action, amount, price) VALUES (?, ?, ?, ?, ?)",
                                           (current_time, pair, 'sell', btc_balance, price))
                        conn_postgres.execute("INSERT INTO trades (timestamp, pair, action, amount, price) VALUES (%s, %s, %s, %s, %s)",
                                             (current_time, pair, 'sell', btc_balance, price))
                        conn_sqlite.commit()
                        conn_postgres.commit()
                        logging.info(f"{pair} Take Profit hit: {pnl_pct*100:.2f}%. Daily PNL: {daily_pnl[pair]*100:.2f}% TXID: {txid}")
                        in_position[pair] = False
                        ohlc_data[pair] = pre_load_ohlc(pair, days=30)
                    elif pnl_pct <= -dynamic_stop_loss:
                        txid = sell_btc(api_key, api_secret, pair)
                        daily_pnl[pair] += pnl_pct
                        conn_sqlite.execute("INSERT INTO trades (timestamp, pair, action, amount, price) VALUES (?, ?, ?, ?, ?)",
                                           (current_time, pair, 'sell', btc_balance, price))
                        conn_postgres.execute("INSERT INTO trades (timestamp, pair, action, amount, price) VALUES (%s, %s, %s, %s, %s)",
                                             (current_time, pair, 'sell', btc_balance, price))
                        conn_sqlite.commit()
                        conn_postgres.commit()
                        logging.info(f"{pair} Stop Loss hit: {pnl_pct*100:.2f}%. Daily PNL: {daily_pnl[pair]*100:.2f}% TXID: {txid}")
                        in_position[pair] = False
                        ohlc_data[pair] = pre_load_ohlc(pair, days=30)

                if daily_pnl[pair] < daily_target and trades_today[pair] > 0 and time.strftime("%H%M") < "2300":
                    logging.warning(f"{pair} Daily target {daily_target*100:.2f}% not met. Current PNL: {daily_pnl[pair]*100:.2f}%")
                    if all(conv >= 0.025 for conv in convictions.values()) and direction_aligned:
                        txid = buy_btc(usd_balance / len(pairs), api_key, api_secret, pair)
                        entry_prices[pair] = price
                        in_position[pair] = True
                        trades_today[pair] += 1
                        conn_sqlite.execute("INSERT INTO trades (timestamp, pair, action, amount, price) VALUES (?, ?, ?, ?, ?)",
                                           (current_time, pair, 'buy', usd_balance / len(pairs), price))
                        conn_postgres.execute("INSERT INTO trades (timestamp, pair, action, amount, price) VALUES (%s, %s, %s, %s, %s)",
                                             (current_time, pair, 'buy', usd_balance / len(pairs), price))
                        conn_sqlite.commit()
                        conn_postgres.commit()
                        logging.info(f"{pair} Risk-on entered {directions['momentum']} at ~${price:.2f} TXID: {txid}")

            if time.strftime("%H%M") in ["1200", "2300"]:
                strategy = gpt5_review()
                logging.info(f"GPT-5 Strategy at {time.strftime('%H:%M')}: {strategy}")
            last_trade = conn_sqlite.execute("SELECT * FROM trades ORDER BY id DESC LIMIT 1").fetchone()
            if last_trade and time.strftime("%M") == "00":
                adjustment = gpt4o_review(dict(last_trade))
                logging.info(f"GPT-4o Adjustment at {time.strftime('%H:%M')}: {adjustment}")
                agent_system.adjust_convictions(adjustment)

            time.sleep(CHECK_INTERVAL)
        except Exception as e:
            log_error(e)
            send_alert(f"Trading Error: {e}")
            time.sleep(60)
        finally:
            conn_sqlite.close()
            conn_postgres.close()

def buy_btc(amount_usd, api_key, api_secret, pair):
    from krakenex import API
    kraken = API()
    kraken.load_key((api_key, api_secret))
    if DRY_RUN:
        logging.info(f"[DRY RUN] Would buy ~${amount_usd} worth of {pair}")
        return "simulated_txid"
    response = kraken.query_private('AddOrder', {
        'pair': pair,
        'type': 'buy',
        'ordertype': 'market',
        'volume': str(amount_usd)
    })
    if response['error']:
        raise Exception(f"Kraken Error: {response['error']}")
    txid = response['result']['txid'][0]
    logging.info(f"Bought {pair} with ${amount_usd}. TXID: {txid}")
    return txid

def sell_btc(api_key, api_secret, pair):
    from krakenex import API
    kraken = API()
    kraken.load_key((api_key, api_secret))
    if DRY_RUN:
        logging.info(f"[DRY RUN] Would sell all {pair}")
        return "simulated_txid"
    response = kraken.query_private('AddOrder', {
        'pair': pair,
        'type': 'sell',
        'ordertype': 'market',
        'volume': 'all'
    })
    if response['error']:
        raise Exception(f"Kraken Error: {response['error']}")
    txid = response['result']['txid'][0]
    logging.info(f"Sold all {pair}. TXID: {txid}")
    return txid

def get_usd_balance(api_key, api_secret, pair):
    from krakenex import API
    kraken = API()
    kraken.load_key((api_key, api_secret))
    balance = kraken.query_private('Balance')['result']
    return float(balance.get('ZUSD', 0))

def get_btc_balance(api_key, api_secret, pair):
    from krakenex import API
    kraken = API()
    kraken.load_key((api_key, api_secret))
    balance = kraken.query_private('Balance')['result']
    asset = pair.split('USD')[0] + 'X' if pair.startswith('X') else pair.split('USD')[0]
    return float(balance.get(asset, 0))