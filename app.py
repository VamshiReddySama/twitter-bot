# app.py — tiny web + background bot for Render

from threading import Thread
from flask import Flask
import main  # your bot file (main.py)

app = Flask(__name__)

def run_bot():
    # call the main loop from main.py
    main.main()

# start bot in a background thread
Thread(target=run_bot, daemon=True).start()

@app.get("/")
def health():
    return "bot alive ✅"

if __name__ == "__main__":
    # Render will set PORT; locally we default to 10000
    import os
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
