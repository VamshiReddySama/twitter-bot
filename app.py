# app.py — Flask healthcheck + background bot thread (Render-friendly)

import os
import time
import traceback
from threading import Thread

from flask import Flask
import main  # our bot module

app = Flask(__name__)

def run_bot():
    """Run the bot loop forever; auto-restart on crash."""
    while True:
        try:
            print("[app] starting bot loop…")
            main.main()
        except Exception as e:
            print("[app] bot crashed:", e)
            traceback.print_exc()
            print("[app] restarting bot in 30 seconds…")
            time.sleep(30)

# start the bot in the background as soon as the app imports
Thread(target=run_bot, daemon=True).start()

@app.get("/")
def health():
    return "bot alive ✅"

if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    print(f"[app] running Flask server on port {port}")
    app.run(host="0.0.0.0", port=port)
