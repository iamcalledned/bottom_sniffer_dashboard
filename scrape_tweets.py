from playwright.sync_api import sync_playwright

def get_recent_tweets(username, count=10):
    tweets = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"https://twitter.com/{username}")

        # Wait for tweets to load
        page.wait_for_selector('article')

        articles = page.query_selector_all("article")[:count]
        for article in articles:
            try:
                content = article.inner_text()
                tweets.append(content)
            except Exception as e:
                print("Tweet parse error:", e)

        browser.close()

    return tweets
