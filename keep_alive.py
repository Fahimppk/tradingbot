from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Bot is awake and tracking ETH/USDT!"

def run():
    # Render uses port 8080 by default
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()