from flask import Flask
import trading
import os
import logging
import time
from openai import OpenAI

app = Flask(__name__)

if not os.path.exists('logs'):
    os.makedirs('logs')
from logging.handlers import RotatingFileHandler
handler = RotatingFileHandler('logs/trader.log', maxBytes=10*1024*1024, backupCount=5)
logging.basicConfig(handlers=[handler], level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

DRY_RUN = os.getenv('DRY_RUN', 'true').lower() == 'true'
PAIRS = ['XBTUSD', 'ETHUSD', 'ADAUSD']

def init_openai():
    client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    if not DRY_RUN:
        try:
            # Estimate £100/month (~$130) at $0.01 per 1K tokens, ~13K calls
            response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": "Test"}], max_tokens=100)
            logging.info("Open AI quota check passed")
            if response.usage.total_tokens > 1300000:  # Rough cap
                raise Exception("Open AI quota exceeds £100/month estimate")
        except Exception as e:
            logging.error(f"Open AI quota error: {e}")
            raise
    return client

openai = init_openai()

def review_with_gpt4o(last_trade):
    if not DRY_RUN and last_trade:
        mission_context = "Mission: Achieve 1.5%-3% daily compounding returns on Kraken USDT pairs with 100% allocation, 5 agents at ≥3% conviction, 24/7 operation."
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": mission_context}, {"role": "user", "content": f"Review this trade: {last_trade}. Suggest conviction or strategy adjustments."}],
            max_tokens=200
        )
        return response.choices[0].message.content
    return "Dry run review"

def review_with_gpt5():
    current_time = time.strftime("%H%M")
    if not DRY_RUN and current_time in ["1200", "2300"]:
        mission_context = "Mission: Achieve 1.5%-3% daily compounding returns on Kraken USDT pairs with 100% allocation, 5 agents at ≥3% conviction, 24/7 operation."
        response = openai.chat.completions.create(
            model="gpt-5" if "gpt-5" in openai.models.list() else "gpt-4o",
            messages=[{"role": "system", "content": mission_context}, {"role": "user", "content": f"Strategize for tomorrow's crypto trading on Kraken USDT pairs: {PAIRS}."}],
            max_tokens=300
        )
        return response.choices[0].message.content
    return "Dry run strategy"

@app.route('/')
def health_check():
    return "Kraken Trader Running", 200

if __name__ == "__main__":
    trading.start_trading(PAIRS, review_with_gpt4o, review_with_gpt5)