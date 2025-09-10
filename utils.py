import os
import logging
import smtplib
from email.mime.text import MIMEText
import time

def log_error(error):
    logging.error(f"Error: {error}")
    send_alert(f"Trading Error: {error}")

def send_alert(message):
    if not os.getenv('DRY_RUN', 'true').lower() == 'true':
        try:
            msg = MIMEText(message)
            msg['Subject'] = 'Kraken Trader Alert'
            msg['From'] = os.getenv('EMAIL_FROM')
            msg['To'] = os.getenv('EMAIL_TO')
            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(os.getenv('EMAIL_USER'), os.getenv('EMAIL_PASS'))
                server.send_message(msg)
        except Exception as e:
            logging.error(f"Alert failed: {e}")

def heartbeat():
    while True:
        with open('heartbeat.txt', 'w') as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S BST"))
        time.sleep(3600)