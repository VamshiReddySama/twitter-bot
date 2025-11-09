import os
import json
import time
import random
import traceback
from pathlib import Path

import tweepy

# ================== Settings (edit safely) ==================
BOT_REPLY = os.getenv("BOT_REPLY", "Thanks for the mention! 🙌")
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "15"))   # check interval
MAX_ACTIONS_PER_RUN = int(os.getenv("MAX_ACTIONS_PER_RUN", "1"))
STATE_FILE = os.getenv("STATE_FILE", "state.json")    # remembers last handled mention
LIKE_DELAY_RANGE = (2, 3)      # seconds
REPLY_DELAY_RANGE = (2, 3)     # seconds
# ===========================================================


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
    """Create Tweepy v2 client. Loads .env if present (local), otherwise uses env (Render)."""
    # local convenience: load .env if present
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
        wait_on_rate_limit=False
    )


def build_user_map(includes):
    """Map author_id -> username from response.includes"""
    if not includes or "users" not in includes:
        return {}
    return {u.id: u.username for u in includes["users"]}


def handle_mentions(client, me_id: int, first_run: bool = False):
    """Like + reply to new mentions for the given user id (me_id)."""
    state = load_state()
    since_id = state.get("last_mention_id")

    base_kwargs = {
        "expansions": ["author_id"],
        "user_fields": ["username"],
        "tweet_fields": ["created_at"],
    }
    # fetch modestly on first run to avoid spamming old mentions
    if since_id:
        kwargs = {**base_kwargs, "since_id": since_id, "max_results": 100}
    else:
        kwargs = {**base_kwargs, "max_results": 10}

    try:
        resp = client.get_users_mentions(id=me_id, **kwargs)
    except tweepy.errors.TooManyRequests:
        print("[bot] rate limited when fetching mentions — sleeping 60s")
        time.sleep(60)
        return
    except Exception as e:
        print("[bot] fetch mentions error:", e)
        traceback.print_exc()
        return

    if not resp or not resp.data:
        print("[bot] no new mentions")
        return

    users = build_user_map(getattr(resp, "includes", {}))
    tweets = list(resp.data)
    newest_id = tweets[0].id  # most recent

    # on very first run, just set the pointer and skip replying to old backlog
    if first_run and not since_id:
        state["last_mention_id"] = newest_id
        save_state(state)
        print("[bot] first run: pointer set, skipping old mentions")
        return

    actions = 0
    # process oldest -> newest (natural order)
    for tw in reversed(tweets):
        if actions >= MAX_ACTIONS_PER_RUN:
            print(f"[bot] reached MAX_ACTIONS_PER_RUN={MAX_ACTIONS_PER_RUN}")
            break

        # skip our own tweets just in case
        if str(tw.author_id) == str(me_id):
            continue

        # like
        try:
            client.like(tw.id)
            print(f"[bot] liked {tw.id}")
        except tweepy.errors.TooManyRequests:
            print("[bot] rate limited on like — sleeping 60s")
            time.sleep(60)
            break
        except Exception as e:
            print(f"[bot] like failed {tw.id}: {e}")

        time.sleep(random.uniform(*LIKE_DELAY_RANGE))

        # reply
        uname = users.get(tw.author_id, "")
        reply_text = f"@{uname} {BOT_REPLY}" if uname else BOT_REPLY
        try:
            client.create_tweet(text=reply_text, in_reply_to_tweet_id=tw.id)
            print(f"[bot] replied to {tw.id}")
            actions += 1
        except tweepy.errors.TooManyRequests:
            print("[bot] rate limited on reply — sleeping 60s")
            time.sleep(60)
            break
        except Exception as e:
            print(f"[bot] reply failed {tw.id}: {e}")

        time.sleep(random.uniform(*REPLY_DELAY_RANGE))

    # advance pointer
    state["last_mention_id"] = newest_id
    save_state(state)


def main():
    """Main loop: uses USER_ID env, never calls get_me()."""
    client = get_client()

    me_id_str = os.getenv("USER_ID")
    if not me_id_str:
        raise RuntimeError(
            "Missing USER_ID env var. Set your numeric user id, e.g. 1910972858286960640"
        )
    me_id = int(me_id_str)
    print(f"[bot] Using USER_ID={me_id}")

    first_loop = False
    while True:
        try:
            print("[bot] tick")
            handle_mentions(client, me_id, first_run=first_loop)
            first_loop = False
            time.sleep(POLL_SECONDS)
        except tweepy.errors.TooManyRequests:
            print("[bot] global rate limit — sleeping 60s")
            time.sleep(60)
        except Exception as e:
            print("[bot] loop error:", e)
            traceback.print_exc()
            time.sleep(30)


if __name__ == "__main__":
    main()
