import json
import os
import time
import random
from pathlib import Path

import tweepy
from dotenv import load_dotenv

# ===== Editable settings =====
BOT_REPLY = "Thanks for the mention! 🙌"
POLL_SECONDS = 20              # check every N seconds
MAX_ACTIONS_PER_RUN = 1        # limit to 1 like+reply per loop
FIRST_RUN_SKIP_OLD = True      # skip old mentions
STATE_FILE = "state.json"      # file to save last mention ID
LIKE_DELAY_RANGE = (2, 3)
REPLY_DELAY_RANGE = (2, 3)
# =============================


def load_state():
    p = Path(STATE_FILE)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}


def save_state(state):
    Path(STATE_FILE).write_text(json.dumps(state))

def get_client():
    # Try loading .env if present (local dev). On Render, env vars already exist.
    try:
        from pathlib import Path
        env_path = Path(__file__).with_name(".env")
        if env_path.exists():
            from dotenv import load_dotenv
            load_dotenv(dotenv_path=env_path)
    except Exception:
        pass  # safe to ignore

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
        wait_on_rate_limit=False
    )


    return tweepy.Client(
        consumer_key=api_key,
        consumer_secret=api_key_secret,
        access_token=access_token,
        access_token_secret=access_token_secret,
        bearer_token=bearer,
        wait_on_rate_limit=False  # we'll handle rate limits ourselves
    )


def build_user_map(includes):
    if not includes or "users" not in includes:
        return {}
    return {u.id: u.username for u in includes["users"]}


def _sleep_with_jitter(lo_hi):
    time.sleep(random.uniform(*lo_hi))


def _handle_rate_limit(e):
    # Tweepy TooManyRequests has response headers with reset time
    reset_ts = None
    try:
        reset_hdr = e.response.headers.get("x-rate-limit-reset")
        if reset_hdr:
            reset_ts = int(reset_hdr)
    except Exception:
        pass

    now = int(time.time())
    wait_for = (reset_ts - now + 3) if reset_ts and reset_ts > now else 60
    wait_for = max(10, min(wait_for, 900))  # clamp between 10s and 15m
    print(f"Rate limit hit. Sleeping for ~{wait_for} seconds.")
    time.sleep(wait_for)


def handle_mentions(client, first_run=False):
    me = client.get_me().data
    state = load_state()
    since_id = state.get("last_mention_id")

    base_kwargs = {
        "expansions": ["author_id"],
        "user_fields": ["username"],
        "tweet_fields": ["created_at"]
    }

    if since_id:
        kwargs = {**base_kwargs, "since_id": since_id, "max_results": 100}
    else:
        kwargs = {**base_kwargs, "max_results": 10}

    try:
        resp = client.get_users_mentions(id=me.id, **kwargs)
    except tweepy.errors.TooManyRequests as e:
        _handle_rate_limit(e)
        return
    except Exception as e:
        print(f"Fetch mentions failed: {e}")
        return

    if not resp or not resp.data:
        print("No new mentions.")
        return

    user_map = build_user_map(getattr(resp, "includes", {}))
    tweets = list(resp.data)
    newest_id = tweets[0].id  # most recent id

    # If first run, optionally just set pointer and skip old replies
    if first_run and FIRST_RUN_SKIP_OLD and not since_id:
        state["last_mention_id"] = newest_id
        save_state(state)
        print("First run: skipping old mentions; pointer updated.")
        return

    actions = 0

    # Process oldest -> newest to keep order
    for tw in reversed(tweets):
        if actions >= MAX_ACTIONS_PER_RUN:
            print(f"Reached MAX_ACTIONS_PER_RUN={MAX_ACTIONS_PER_RUN}.")
            break

        if str(tw.author_id) == str(me.id):
            continue  # skip our own posts

        # 1) Like
        try:
            client.like(tw.id)
            print(f"Liked {tw.id}")
        except tweepy.errors.TooManyRequests as e:
            _handle_rate_limit(e)
            break
        except Exception as e:
            print(f"Like failed for {tw.id}: {e}")

        _sleep_with_jitter(LIKE_DELAY_RANGE)

        # 2) Reply
        username = user_map.get(tw.author_id, "")
        reply_text = f"@{username} {BOT_REPLY}" if username else BOT_REPLY
        try:
            client.create_tweet(text=reply_text, in_reply_to_tweet_id=tw.id)
            print(f"Replied to {tw.id}")
            actions += 1
        except tweepy.errors.TooManyRequests as e:
            _handle_rate_limit(e)
            break
        except Exception as e:
            print(f"Reply failed for {tw.id}: {e}")

        _sleep_with_jitter(REPLY_DELAY_RANGE)

    # advance pointer even if we broke from rate limit (we processed some)
    state["last_mention_id"] = newest_id
    save_state(state)


def main():
    client = get_client()
    me = client.get_me().data
    print(f"[bot] Running as @{me.username} (id={me.id})")

    first_loop = True
    while True:
        print("[bot] tick")
        handle_mentions(client, first_run=first_loop)
        first_loop = False
        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main()
