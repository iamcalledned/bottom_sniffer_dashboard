# twitter_feed.py
import tweepy
from flask import Blueprint, jsonify
import os

twitter_feed = Blueprint('twitter_feed', __name__)

# Load from env
BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")

client = tweepy.Client(bearer_token=BEARER_TOKEN)

@twitter_feed.route("/api/tweets")
def get_recent_tweets():
    try:
        response = client.get_users_tweets(id='your_user_id', max_results=5)  # Replace with your user ID
        tweets = [{"text": t.text} for t in response.data] if response.data else []
        return jsonify(tweets=tweets)
    except Exception as e:
        return jsonify(error=str(e)), 500
