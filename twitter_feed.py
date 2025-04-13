# twitter_feed.py
import os
import tweepy
from flask import Blueprint, jsonify
from dotenv import load_dotenv

# Load .env
load_dotenv()

# Load credentials
BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")
USERNAMES = [u.strip() for u in os.getenv("TWITTER_USERNAMES", "").split(",") if u.strip()]

twitter_feed = Blueprint("twitter_feed", __name__)

# Init tweepy
client = tweepy.Client(bearer_token=BEARER_TOKEN)


@twitter_feed.route("/api/tweets")
def get_recent_tweets():
    try:
        print("🐦 Loading tweets for:", USERNAMES)
        print("📡 Using bearer token:", "✔️" if BEARER_TOKEN else "❌ MISSING")

        all_tweets = []

        for username in USERNAMES:
            print(f"🔍 Fetching user: {username}")
            user = client.get_user(username=username)
            if not user or not user.data:
                print(f"⚠️ No user found for {username}")
                continue

            user_id = user.data.id
            print(f"✅ Found user ID {user_id} for {username}")

            response = client.get_users_tweets(id=user_id, max_results=5, exclude=["retweets", "replies"])
            if response.data:
                for tweet in response.data:
                    print(f"📝 {username}: {tweet.text}")
                tweets = [{"text": t.text, "user": username} for t in response.data]
                all_tweets.extend(tweets)
            else:
                print(f"⚠️ No tweets found for {username}")

        return jsonify(tweets=all_tweets)

    except Exception as e:
        print("🔥 ERROR fetching tweets:", e)
        return jsonify(error=str(e)), 500
