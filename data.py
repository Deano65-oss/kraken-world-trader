import requests
import json
import websocket
import time
import logging
from threading import Thread

BASE_URL = 'https://api.kraken.com'
PUBLIC_PATH = '/0/public/'
COINGECKO_URL = 'https://api.coingecko.com/api/v3'
CRYPTOCOMPARE_URL = 'https://min-api.cryptocompare.com/data'

def public_query(endpoint, params):
    url = BASE_URL + PUBLIC_PATH + endpoint + '?' + '&'.join([f"{k}={v}" for k, v in params.items()])
    try:
        response = requests.get(url, timeout=10)
        result = response.json()
        if result['error']:
            logging.error(f"API Error: {result['error']}")
            raise Exception(f"API Error: {result['error']}")
        return result['result']
    except requests.RequestException as e:
        logging.error(f"Network Error: {e}")
        time.sleep(5)
        return public_query(endpoint, params)

def pre_load_ohlc(pair, days=30):
    since = int(time.time()) - days * 24 * 3600
    return public_query('OHLC', {'pair': pair, 'interval': 60, 'since': since})[pair]

def get_market_data(pair):
    ticker = public_query('Ticker', {'pair': pair})
    price = float(ticker[list(ticker.keys())[0]]['c'][0])
    depth = public_query('Depth', {'pair': pair})
    volume = float(depth[pair]['b'][0][1]) + float(depth[pair]['a'][0][1])
    ohlc = public_query('OHLC', {'pair': pair, 'interval': 5, 'since': int(time.time()) - 300})[pair][-5:]
    highs = [float(c[2]) for c in ohlc]
    lows = [float(c[3]) for c in ohlc]
    closes = [float(c[4]) for c in ohlc]
    atr = sum(max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])) for i in range(1, len(ohlc))) / (len(ohlc) - 1) if len(ohlc) > 1 else 0.01
    return price, volume, atr

def get_external_data(pairs):
    external_data = {}
    for pair in pairs:
        asset = pair.split('USD')[0].lower()
        try:
            # CoinGecko
            cg_response = requests.get(f"{COINGECKO_URL}/coins/markets", params={'vs_currency': 'usd', 'ids': asset})
            cg_data = cg_response.json()[0] if cg_response.status_code == 200 and cg_data else {}
            volume_24h = cg_data.get('total_volume', 0)

            # CryptoCompare
            cc_response = requests.get(f"{CRYPTOCOMPARE_URL}/pricemultifull", params={'fsyms': asset, 'tsyms': 'USD'})
            cc_data = cc_response.json().get(asset, {}).get('USD', {})
            market_cap = cc_data.get('MKTCAP', 0)

            external_data[pair] = {'volume_24h': volume_24h, 'market_cap': market_cap}
        except Exception as e:
            logging.warning(f"External data error for {pair}: {e}")
            external_data[pair] = {'volume_24h': 0, 'market_cap': 0}
    return external_data

def start_websocket(pairs, callback):
    def on_message(ws, message):
        data = json.loads(message)
        pair = data.get('pair', pairs[0])
        if pair in pairs:
            callback(pair, float(data.get('price', 0)))
    def on_error(ws, error):
        logging.error(f"WebSocket Error: {error}")
    def on_close(ws):
        logging.warning("WebSocket closed, attempting reconnect")
        start_websocket(pairs, callback)
    ws = websocket.WebSocketApp("wss://ws.kraken.com", on_message=on_message, on_error=on_error, on_close=on_close)
    Thread(target=ws.run_forever, kwargs={'reconnect': 5}).start()