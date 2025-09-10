import os, time, sqlite3, psycopg2, logging, numpy as np
from krakenex import API
from data import get_market_data
from utils import send_alert, log_error, review_with_gpt4o, review_with_gpt5, optimize_performance, predict_compounding
from openai import OpenAI

PAIRS = ['XBTUSD', 'ETHUSD', 'ADAUSD']
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', 60))

def init_database(conn_sqlite, conn_postgres):
    conn_sqlite.execute('''CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, pair TEXT, action TEXT, amount REAL, price REAL)''')
    conn_sqlite.execute('''CREATE TABLE IF NOT EXISTS daily_pnl (date TEXT, pair TEXT, pnl REAL, trades INTEGER, PRIMARY KEY (date, pair))''')
    conn_postgres.execute('''CREATE TABLE IF NOT EXISTS trades (id SERIAL PRIMARY KEY, timestamp TEXT, pair TEXT, action TEXT, amount REAL, price REAL)''')
    conn_postgres.execute('''CREATE TABLE IF NOT EXISTS daily_pnl (date TEXT, pair TEXT, pnl REAL, trades INTEGER, PRIMARY KEY (date, pair))''')
    conn_sqlite.commit()
    conn_postgres.commit()

def adjust_strategy(pairs, historical_data):
    volatility = {pair: np.std([data['price'] for data in historical_data.get(pair, [])[-100:]]) for pair in pairs}
    high_vol = [pair for pair, vol in volatility.items() if vol > np.mean(list(volatility.values())) * 1.5]  # 50% above average
    return high_vol if high_vol else pairs, min(0.1, 0.02 * len(high_vol or pairs))  # Adjust for 2% target

def phase_implementation(phase):
    if phase == 1:
        return "Phase 1: API Connections Tested"
    elif phase == 2:
        return "Phase 2: Dry Run Trading Simulated (2% target)"
    elif phase == 3:
        return "Phase 3: Live Trading Started (2% target)"
    return "Phase Complete"

def execute_trade(pair, data, amount, gpt4o_review, gpt5_review, conn_sqlite, conn_postgres):
    price = data['price']
    action = 'buy' if gpt4o_review(pair, price) and gpt5_review(pair, price) else 'sell'
    if os.getenv('DRY_RUN', 'true').lower() == 'true':
        log_error(f"[DRY RUN] Would {action} {amount} {pair} at {price}")
    else:
        kraken = API()
        kraken.load_key((os.getenv('KRAKEN_API_KEY'), os.getenv('KRAKEN_API_SECRET')))
        response = kraken.query_private(f'AddOrder', {'pair': pair, 'type': action, 'ordertype': 'limit', 'price': price, 'volume': amount})
        if response['error']:
            log_error(f"Trade failed: {response['error']}")
        else:
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
            conn_sqlite.execute("INSERT INTO trades (timestamp, pair, action, amount, price) VALUES (?, ?, ?, ?, ?)", (timestamp, pair, action, amount, price))
            conn_postgres.execute("INSERT INTO trades (timestamp, pair, action, amount, price) VALUES (%s, %s, %s, %s, %s)", (timestamp, pair, action, amount, price))
            conn_sqlite.commit()
            conn_postgres.commit()
            logging.info(f"Executed {action} {amount} {pair} at {price}")

def start_trading(pairs, gpt4o_review, gpt5_review):
    conn_sqlite = sqlite3.connect('trader.db', check_same_thread=False)
    conn_postgres = psycopg2.connect(dbname=os.getenv('PG_DB'), user=os.getenv('PG_USER'), password=os.getenv('PG_PASS'), host=os.getenv('PG_HOST'), port=int(os.getenv('PG_PORT')))
    init_database(conn_sqlite, conn_postgres)
    historical_data = {}
    phase = 1

    while True:
        try:
            if phase == 1 and check_api_connections():
                send_alert(phase_implementation(phase))
                phase = 2
            elif phase == 2 and os.getenv('DRY_RUN', 'true').lower() == 'true':
                pairs, amount_per_trade = adjust_strategy(pairs, historical_data)
                for pair in pairs:
                    data = get_market_data(pair)
                    historical_data.setdefault(pair, []).append({'price': data['price']})
                    if len(historical_data[pair]) > 100:
                        historical_data[pair].pop(0)
                    execute_trade(pair, data, amount_per_trade, gpt4o_review, gpt5_review, conn_sqlite, conn_postgres)
                send_alert(phase_implementation(phase))
                phase = 3
            elif phase == 3 and os.getenv('DRY_RUN', 'false').lower() == 'false':
                pairs, amount_per_trade = adjust_strategy(pairs, historical_data)
                for pair in pairs:
                    data = get_market_data(pair)
                    historical_data.setdefault(pair, []).append({'price': data['price']})
                    if len(historical_data[pair]) > 100:
                        historical_data[pair].pop(0)
                    execute_trade(pair, data, amount_per_trade, gpt4o_review, gpt5_review, conn_sqlite, conn_postgres)
                if time.time() % 86400 < 60:  # Daily
                    global PAIRS
                    PAIRS = optimize_performance(conn_sqlite) or PAIRS
                    predict_compounding(10000, 0.02, 365)  # Recalculate with 2% target
                send_alert(phase_implementation(phase))
            time.sleep(CHECK_INTERVAL)
        except Exception as e:
            log_error(f"Trading error: {e}")
            send_alert(f"Paused due to: {e}. Restarting in 60s.")
            time.sleep(60)
