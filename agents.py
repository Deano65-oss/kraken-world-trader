from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

def review_with_gpt4o(pair, price):
    prompt = f"Review {pair} at {price}. Should we buy or sell for 2% daily growth? Just say 'buy', 'sell', or 'hold'."
    response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}], max_tokens=10)
    return response.choices[0].message.content.strip().lower() == 'buy'

def review_with_gpt5(pair, price):
    prompt = f"Advanced review for {pair} at {price}. Consider market trends for 2% - 3% daily growth. Buy, sell, or hold?"
    response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], max_tokens=10)
    return response.choices[0].message.content.strip().lower() == 'buy'

def add_agent(suggestion):
    global review_with_gpt5
    if "new agent" in suggestion.lower():
        review_with_gpt5 = lambda pair, price: client.chat.completions.create(
            model="gpt-4o", messages=[{"role": "user", "content": f"New agent review for {pair} at {price} for 2% growth. Buy, sell, or hold?"}], max_tokens=10
        ).choices[0].message.content.strip().lower() == 'buy'
        logging.info("New agent added for 2% growth target.")
