import requests
import logging
import os
from websocket import create_connection

BASE_URL = 'https://api.kraken.com'
PUBLIC_PATH = '/0/public/'

def public_query(endpoint, params, retries=3):
    for attempt in range(retries):
        try:
            url = BASE_URL + PUBLIC_PATH + endpoint + '?' + '&'.join([f"{k}={v}" for k, v in params.items()])
            response = requests.get(url, timeout=10)
            result = response.json()
            if result['error']:
                raise Exception(f"API Error: {result['error']}")
            return result['result']
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            logging.error(f"API failed after {retries} attempts: {e}")
            raise

def get_market_data(pair):
    sources = [
        lambda: public_query('Ticker', {'pair': pair}),
        lambda: requests.get(f'https://api.coingecko.com/api/v3/simple/price?ids={pair.lower()}&vs_currencies=usd').json()
    ]
    for source in sources:
        try:
            data = source()
            if 'error' not in data:
                price = float(data.get(pair, data.get(f"{pair.lower()}", {'usd': 0})['usd']) if isinstance(data, dict) else float(data[list(data.keys())[0]]['c'][0])
                depth = public_query('Depth', {'pair': pair}) if source == sources[0] else {'b': [['0', '0']], 'a': [['0', '0']]}
                volume = float(depth[pair]['b'][0][1]) + float(depth[pair]['a'][0][1]) if source == sources[0] else 0.0
                return {'price': price, 'volume': volume}
        except Exception as e:
            logging.warning(f"Source failed: {e}, trying next.")
    raise Exception("All data sources failed.")
