import os, time, logging, sqlite3, numpy as np
from openai import OpenAI
from email.mime.text import MIMEText
import smtplib

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
logging.basicConfig(level=logging.INFO)

def send_alert(message):
    msg = MIMEText(message)
    msg['Subject'] = 'Kraken Trader Alert'
    msg['From'] = os.getenv('EMAIL_FROM')
    msg['To'] = os.getenv('EMAIL_TO')
    with smtplib.SMTP('smtp.gmail.com', 587) as server:
        server.starttls()
        server.login(os.getenv('EMAIL_USER'), os.getenv('EMAIL_PASS'))
        server.send_message(msg)

def log_error(message):
    logging.error(message)
    send_alert(f"Error: {message}")

def review_with_gpt4o(pair, price):
    prompt = f"Review {pair} at {price} for 2% daily growth. Buy, sell, or hold?"
    response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}], max_tokens=10)
    return response.choices[0].message.content.strip().lower() == 'buy'

def review_with_gpt5(pair, price):
    prompt = f"Advanced review for {pair} at {price} for 2% daily growth. Buy, sell, or hold?"
    response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], max_tokens=10)
    return response.choices[0].message.content.strip().lower() == 'buy'

def optimize_performance(conn_sqlite):
    cursor = conn_sqlite.execute("SELECT pair, SUM(pnl) as total_pnl FROM daily_pnl GROUP BY pair")
    performance = {row[0]: row[1] for row in cursor.fetchall()}
    prompt = f"Optimize trading for 2% daily growth: {performance}. Suggest top 3 pairs."
    response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}], max_tokens=200)
    return response.choices[0].message.content.split()[:3]

def predict_compounding(initial_capital=10000, daily_growth=0.02, days=365):
    cursor = sqlite3.connect('trader.db').execute("SELECT SUM(pnl) FROM daily_pnl")
    total_pnl = cursor.fetchone()[0] or 0
    avg_daily = total_pnl / max(1, days) if days else daily_growth
    prompt = f"Predict compounding from £{initial_capital} with {daily_growth:.2%} daily growth over {days} days. Suggest strategy for 2% target."
    response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}], max_tokens=150)
    suggestion = response.choices[0].message.content
    final_amount = initial_capital * (1 + avg_daily) ** days
    logging.info(f"Predicted: £{final_amount:.2f} for 2% target. Suggestion: {suggestion}")
    send_alert(f"Compounding Prediction: £{final_amount:.2f} for 2% target. {suggestion}")
    return final_amount, suggestion
