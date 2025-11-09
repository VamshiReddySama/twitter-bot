# app.py — Flask healthcheck + Twitter bot loop in one file (Render-friendly)

import os, json, time, random, traceback
from pathlib import Path
from threading import Thread
from flask import Flask
import tweepy

# ---------- Settings you can tweak ----------
BOT_REPLY = os.getenv("BOT_REPLY", "Thanks for the mention! 🙌")
POLL_SECONDS = 15                # check interval
MAX_ACTIONS_PER_RUN = 1          # like+reply per loop
STATE_FILE = "state.json"        # remember last handled mention
LIKE_DELAY_RANGE = (2, 3)
REPLY_DELAY_RANGE = (2, 3)
# --------------------------------------------

app = Flask(__name__)

def load_state():
    p = Path(STATE_FILE)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}

def save_state(st):
    Path(STATE_FILE).write_text(json.dumps(st))

def get_client():
    # Local dev: optionally load .env if present; on Render, env vars already set
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).with_name(".env")
        if env_path.exists():
            load_dotenv(env_path)
    except Exception:
        pass

    api_key = os.getenv("API_KEY")
    api_key_secret = os.getenv("API_KEY_SECRET")
    access_token = os.getenv("ACCESS_TOKEN")
    access_token_secret = os.getenv("ACCESS_TOKEN_SECRET")
    bearer = os.getenv("BEARER_TOKEN")

    missing = [k for k, v in {
        "API_KEY": api_key,
        "API_KEY_SECRET": api_key_secret,
        "ACCESS_TOKEN": access_token,
        "ACCESS_TOKEN_SECRET": access_token_secret,
        "BEARER_TOKEN": bearer
    }.items() if not v]
    if missing:
        raise RuntimeError("Missing env vars -> " + ", ".join(missing))

    print("[bot] get_client(): credentials loaded")
    return tweepy.Client(
        consumer_key=api_key,
        consumer_secret=api_key_secret,
        access_token=access_token,
        access_token_secret=access_token_secret,
        bearer_token=bearer,
        wait_on_rate_limit=False,
        timeout=20
    )

def build_user_map(includes):
    if not includes or "users" not in includes:
        return {}
    return {u.id: u.username for u in includes["users"]}

def sleep_rand(lo_hi):
    time.sleep(random.uniform(*lo_hi))

def handle_mentions(client, first_run=False):
    me = client.get_me().data
    st = load_state()
    since_id = st.get("last_mention_id")

    base = {
        "expansions": ["author_id"],
        "user_fields": ["username"],
        "tweet_fields": ["created_at"]
    }
    kwargs = {**base, "max_results": 100}
    if since_id:
        kwargs["since_id"] = since_id
    else:
        # first time: only peek a few so we don't spam old mentions
        kwargs["max_results"] = 10

    try:
        resp = client.get_users_mentions(id=me.id, **kwargs)
    except tweepy.errors.TooManyRequests:
        print("[bot] rate limited fetching mentions — sleep 60s")
        time.sleep(60); return
    except Exception as e:
        print("[bot] fetch mentions error:", e); return

    if not resp or not resp.data:
        print("[bot] no new mentions")
        return

    users = build_user_map(getattr(resp, "includes", {}))
    tweets = list(resp.data)
    newest_id = tweets[0].id

    # Optional: on very first run, just set pointer and skip old
    if first_run and not since_id:
        st["last_mention_id"] = newest_id
        save_state(st)
        print("[bot] first run: pointer set, skipping old mentions")
        return

    actions = 0
    for tw in reversed(tweets):
        if actions >= MAX_ACTIONS_PER_RUN:
            break
        if str(tw.author_id) == str(me.id):
            continue

        # like
        try:
            client.like(tw.id)
            print(f"[bot] liked {tw.id}")
        except tweepy.errors.TooManyRequests:
            print("[bot] rate limited on like — sleep 60s")
            time.sleep(60); break
        except Exception as e:
            print(f"[bot] like failed {tw.id}: {e}")

        sleep_rand(LIKE_DELAY_RANGE)

        # reply
        uname = users.get(tw.author_id, "")
        reply_text = f"@{uname} {BOT_REPLY}" if uname else BOT_REPLY
        try:
            client.create_tweet(text=reply_text, in_reply_to_tweet_id=tw.id)
            print(f"[bot] replied to {tw.id}")
            actions += 1
        except tweepy.errors.TooManyRequests:
            print("[bot] rate limited on reply — sleep 60s")
            time.sleep(60); break
        except Exception as e:
            print(f"[bot] reply failed {tw.id}: {e}")

        sleep_rand(REPLY_DELAY_RANGE)

    st["last_mention_id"] = newest_id
    save_state(st)

def bot_loop():
    try:
        print("[app] starting bot loop…")
        client = get_client()
        print("[bot] calling get_me()…")
        me = client.get_me().data
        print(f"[bot] Running as @{me.username} (id={me.id})")
    except Exception as e:
        print("[bot] startup error:", e)
        traceback.print_exc()
        time.sleep(30)
        return

    first = True
    while True:
        try:
            print("[bot] tick")
            handle_mentions(client, first_run=first)
            first = False
            time.sleep(POLL_SECONDS)
        except tweepy.errors.TooManyRequests:
            print("[bot] global rate limit — sleep 60s")
            time.sleep(60)
        except Exception as e:
            print("[bot] loop error:", e)
            traceback.print_exc()
            time.sleep(30)

# start background thread immediately
Thread(target=bot_loop, daemon=True).start()

@app.get("/")
def health():
    return "bot alive ✅"

if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    print(f"[app] running Flask server on port {port}")
    app.run(host="0.0.0.0", port=port)
