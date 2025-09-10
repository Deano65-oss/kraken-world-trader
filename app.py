from flask import Flask, request, jsonify
from openai import OpenAI
import os, logging, time, sqlite3, psycopg2, shutil
from trading import start_trading, PAIRS
from utils import send_alert, log_error, review_with_gpt4o, review_with_gpt5

app = Flask(__name__)
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY', ''))
logging.basicConfig(level=logging.INFO)

def auto_configure_env():
    required = ['KRAKEN_API_KEY', 'KRAKEN_API_SECRET', 'OPENAI_API_KEY', 'EMAIL_FROM', 'EMAIL_TO', 'EMAIL_USER', 'EMAIL_PASS', 'PG_DB', 'PG_USER', 'PG_PASS', 'PG_HOST', 'PG_PORT']
    missing = [var for var in required if not os.getenv(var)]
    if missing:
        prompt = f"Guide user to configure missing env vars: {missing}. Provide step-by-step instructions."
        response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}], max_tokens=300)
        send_alert(f"Setup Guidance: {response.choices[0].message.content}")
        logging.warning(f"Missing vars: {missing}. Guidance: {response.choices[0].message.content}")
        return False
    return True

def check_system_health():
    try:
        conn_sqlite = sqlite3.connect('trader.db', check_same_thread=False)
        conn_postgres = psycopg2.connect(dbname=os.getenv('PG_DB'), user=os.getenv('PG_USER'), password=os.getenv('PG_PASS'), host=os.getenv('PG_HOST'), port=int(os.getenv('PG_PORT')))
        kraken = API()
        kraken.load_key((os.getenv('KRAKEN_API_KEY'), os.getenv('KRAKEN_API_SECRET')))
        kraken.query_public('Time')
        client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": "Test"}], max_tokens=10)
        return "Healthy"
    except Exception as e:
        return f"Error: {e}"

@app.route('/jarvis', methods=['GET', 'POST'])
def jarvis():
    if request.method == 'POST':
        query = request.json.get('query', '')
        prompt = f"Act as Jarvis, the AI assistant. User query: {query}. Provide guidance or action for the Kraken trading system. Current status: {check_system_health()}. Suggest next steps."
        response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}], max_tokens=500)
        return jsonify({"response": response.choices[0].message.content})
    return jsonify({"status": check_system_health(), "message": "Ask Jarvis anything (POST with 'query')"})

@app.route('/')
def health_check():
    write_heartbeat()
    backup_database()
    return "Kraken Trader Running", 200

def write_heartbeat():
    with open('heartbeat.txt', 'a') as f:
        f.write(f"Alive at {time.strftime('%Y-%m-%d %H:%M:%S BST')}\n")

def backup_database():
    if os.path.exists('trader.db'):
        shutil.copy('trader.db', f'trader_backup_{time.strftime("%Y%m%d_%H%M%S")}.db')
    with open('backup_postgres.sql', 'w') as f:
        conn_postgres = psycopg2.connect(dbname=os.getenv('PG_DB'), user=os.getenv('PG_USER'), password=os.getenv('PG_PASS'), host=os.getenv('PG_HOST'), port=int(os.getenv('PG_PORT')))
        cursor = conn_postgres.cursor()
        cursor.execute("SELECT pg_dump('trader')")
        f.write(cursor.fetchone()[0])

if __name__ == "__main__":
    if not auto_configure_env():
        logging.error("Setup incomplete. Check alerts or Render env vars.")
        exit(1)
    check_api_connections()
    start_trading(PAIRS, review_with_gpt4o, review_with_gpt5)
