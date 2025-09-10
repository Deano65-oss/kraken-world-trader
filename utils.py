import os
import time
import logging
import sqlite3
import numpy as np
from openai import OpenAI
from email.mime.text import MIMEText
import smtplib

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
logging.basicConfig(level=logging.INFO)

def send_alert(message):
    try:
        if all(os.getenv(var) for var in ['EMAIL_FROM', 'EMAIL_TO', 'EMAIL_USER', 'EMAIL_PASS']):
            msg = MIMEText(message)
            msg['Subject'] = 'Kraken Trader Alert'
            msg['From'] = os.getenv('EMAIL_FROM')
            msg['To'] = os.getenv('EMAIL_TO')
            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(os.getenv('EMAIL_USER'), os.getenv('EMAIL_PASS'))
                server.send_message(msg)
            logging.info(f"Alert sent: {message}")
        else:
            logging.warning(f"Alert not sent: Missing email env vars. Message: {message}")
    except Exception as e:
        logging.error(f"Failed to send alert: {e}. Check EMAIL_USER and EMAIL_PASS. Message logged instead.")

def log_error(message):
    logging.error(message)
    send_alert(message)  # Non-blocking attempt

def review_with_gpt4o(pair, price):
    try:
        prompt = f"Review {pair} at {price} for 2% daily growth. Buy, sell, or hold?"
        response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}], max_tokens=10)
        return response.choices[0].message.content.strip().lower() == 'buy'
    except Exception as e:
        log_error(f"GPT-4o review failed: {e}")
        return False

def review_with_gpt5(pair, price):
    try:
        prompt = f"Advanced review for {pair} at {price} for 2% daily growth. Buy, sell, or hold?"
        response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], max_tokens=10)
        return response.choices[0].message.content.strip().lower() == 'buy'
    except Exception as e:
        log_error(f"GPT-5 review failed: {e}")
        return False

def optimize_performance(conn_sqlite):
    try:
        cursor = conn_sqlite.execute("SELECT pair, SUM(pnl) as total_pnl FROM daily_pnl GROUP BY pair")
        performance = {row[0]: row[1] for row in cursor.fetchall()}
        prompt = f"Optimize trading for 2% daily growth: {performance}. Suggest top 3 pairs."
        response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}], max_tokens=200)
        return response.choices[0].message.content.split()[:3]
    except Exception as e:
        log_error(f"Optimization failed: {e}")
        return ['XBTUSD', 'ETHUSD', 'ADAUSD']  # Fallback to default pairs

def predict_compounding(initial_capital=10000, daily_growth=0.02, days=365):
    try:
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
    except Exception as e:
        log_error(f"Prediction failed: {e}")
        return 0, "Fallback: Check API key"
