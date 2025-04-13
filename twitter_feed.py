# twitter_feed.py
import os
import tweepy
from flask import Blueprint, jsonify
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Load and clean Twitter credentials
BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")
USERNAMES = [u.strip() for u in os.getenv("TWITTER_USERNAMES", "").split(",") if u.strip()]

# Init Tweepy client
client = tweepy.Client(bearer_token=BEARER_TOKEN)
twitter_feed = Blueprint('twitter_feed', __name__)

@twitter_feed.route("/api/tweets")
def get_recent_tweets():
    try:
        all_tweets = []

        for username in USERNAMES:
            user = client.get_user(username=username)
            if not user or not user.data:
                continue

            user_id = user.data.id
            response = client.get_users_tweets(id=user_id, max_results=5, exclude=["retweets", "replies"])
            tweets = [{"text": t.text, "user": username} for t in response.data] if response.data else []
            all_tweets.extend(tweets)

        return jsonify(tweets=all_tweets)
    except Exception as e:
        return jsonify(error=str(e)), 500
