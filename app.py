from threading import Thread
from flask import Flask
import traceback
import time
import main  # your bot module

app = Flask(__name__)

def run_bot():
    while True:
        try:
            print("[app] starting bot thread…")
            main.main()
        except Exception as e:
            print("[app] bot crashed:", e)
            traceback.print_exc()
            print("[app] restarting bot in 30 seconds…")
            time.sleep(30)

# start background bot thread at import time
Thread(target=run_bot, daemon=True).start()

@app.get("/")
def health():
    return "bot alive ✅"

if __name__ == "__main__":
    import os
    port = int(os.getenv("PORT", "10000"))
    print(f"[app] running Flask server on port {port}")
    app.run(host="0.0.0.0", port=port)
