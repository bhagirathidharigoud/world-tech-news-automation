# ─────────────────────────────────────────────────────────────────
#  news_service.py
#
#  PURPOSE:
#  Fetch technology news from NewsAPI, categorize each article
#  using keyword matching, and return clean article dictionaries
#  ready to be stored in MongoDB.
#
#  HOW TO USE IN OTHER FILES:
#      from news_service import fetch_and_store_news, fetch_news
#
#  DATA FLOW:
#  NewsAPI → HTTP response → JSON → categorized dicts → MongoDB
# ─────────────────────────────────────────────────────────────────

import requests                           # Makes HTTP requests
from requests.exceptions import (
    ConnectionError as RequestsConnectionError,  # No internet / DNS failure
    Timeout,                              # Request took too long
    RequestException                      # Any other requests error
)
from datetime import datetime, timezone

from config import (
    NEWS_API_KEY,
    NEWS_API_BASE_URL,
    NEWS_FETCH_PAGE_SIZE,
    CATEGORY_KEYWORDS
)
from models import create_news_article
from database import save_many_articles


# ── HOW LONG TO WAIT FOR THE API (seconds) ────────────────────────
# If NewsAPI does not respond within 10 seconds, we give up.
# Without a timeout, Python would wait forever on a slow network.
REQUEST_TIMEOUT = 10


# ── SEARCH QUERIES SENT TO NEWSAPI ────────────────────────────────
# NewsAPI's /everything endpoint accepts a keyword query (q=).
# We send multiple targeted queries to cover all our categories.
#
# Why multiple queries instead of one?
# One broad query like q="technology" returns generic articles.
# Specific queries return more relevant, focused results.
#
# Each entry is a dict with:
#   "query"    → the keyword string sent to the API
#   "category" → the category to assign if keyword matching fails
#                (acts as a hint, but keyword matching runs first)

SEARCH_QUERIES = [
    {
        "query": "artificial intelligence OR machine learning OR large language model OR OpenAI OR Anthropic",
        "hint_category": "AI"
    },
    {
        "query": "agentic AI OR AI agent OR autonomous agent OR agent framework OR multi-agent",
        "hint_category": "Agentic AI"
    },
    {
        "query": "quantum computing OR qubit OR quantum processor OR quantum supremacy",
        "hint_category": "Quantum Computing"
    },
    {
        "query": "cloud computing OR AWS OR Azure OR Google Cloud OR serverless OR kubernetes",
        "hint_category": "Cloud Computing"
    },
    {
        "query": "cybersecurity OR data breach OR ransomware OR hacking OR vulnerability OR cyber attack",
        "hint_category": "Cybersecurity"
    },
    {
        "query": "programming language OR software development OR Python OR JavaScript OR Rust OR open source",
        "hint_category": "Programming"
    },
    {
        "query": "developer tools OR VS Code OR DevOps OR CI/CD OR GitHub OR deployment",
        "hint_category": "Developer Tools"
    },
    {
        "query": "tech startup OR startup funding OR venture capital OR Series A OR unicorn",
        "hint_category": "Startups"
    },
    {
        "query": "Apple OR Google OR Microsoft OR Meta OR Nvidia OR Amazon technology",
        "hint_category": "Technology Companies"
    }
]


# ═════════════════════════════════════════════════════════════════
#  CATEGORIZATION
# ═════════════════════════════════════════════════════════════════

def _categorize_article(title, description):
    """
    Determine the category of a news article using keyword matching.

    Checks the article title and description for keywords defined
    in CATEGORY_KEYWORDS (from config.py).

    The categories are checked IN ORDER. The first match wins.
    This is important — "Agentic AI" is checked before "AI" so
    an article about "AI agents" is correctly classified.

    Args:
        title       (str): Article headline.
        description (str): Article short summary.

    Returns:
        str: A category name from VALID_CATEGORIES.

    Python concept — any():
        any(condition for item in list) returns True if the
        condition is True for at least one item in the list.
        It stops checking the moment it finds the first True —
        more efficient than a full loop.

    Python concept — str.lower():
        We lowercase both the article text and the keyword before
        comparing so "OpenAI" matches "openai" in our keyword list.
    """

    # Combine title and description into one string for searching.
    # Use a safe default if either field is None.
    title_text = (title or "").lower()
    description_text = (description or "").lower()
    combined_text = title_text + " " + description_text

    # Check each category in order.
    for category, keywords in CATEGORY_KEYWORDS.items():

        # Skip "Other Technology" — it's the fallback, checked last.
        if category == "Other Technology":
            continue

        # any() returns True if at least one keyword appears in the text.
        # This is equivalent to writing:
        #   for keyword in keywords:
        #       if keyword in combined_text:
        #           return category
        # but more concise.
        if any(keyword.lower() in combined_text for keyword in keywords):
            return category

    # No specific category matched — use the fallback.
    return "Other Technology"


def get_category_counts(articles):
    """
    Count how many articles belong to each category.

    Args:
        articles (list): List of article dictionaries.

    Returns:
        dict: { "AI": 5, "Cybersecurity": 3, ... }

    Python concept — dict.get(key, default):
        If the key exists, return its value.
        If the key does not exist, return the default (0 here).
        Then we add 1 to the count.
    """
    counts = {}
    for article in articles:
        category = article.get("category", "Other Technology")
        counts[category] = counts.get(category, 0) + 1
    return counts


# ═════════════════════════════════════════════════════════════════
#  API RESPONSE PARSING
# ═════════════════════════════════════════════════════════════════

def _extract_article_fields(raw_article, hint_category=None):
    """
    Extract and clean fields from a raw NewsAPI article dict.

    NewsAPI returns articles in this shape:
    {
        "title":       "...",
        "description": "...",
        "url":         "...",
        "urlToImage":  "...",
        "publishedAt": "2026-10-18T06:00:00Z",
        "source":      { "id": "techcrunch", "name": "TechCrunch" },
        "author":      "Jane Smith",
        "content":     "..."
    }

    We pick the fields we need and reshape them to match our model.

    Args:
        raw_article   (dict): One article from the API response.
        hint_category (str):  Suggested category from the search query.
                              Used ONLY if keyword matching fails
                              completely (returns "Other Technology").

    Returns:
        dict or None: A clean article dict, or None if unusable.

    Python concept — dict.get():
        raw_article.get("title") returns None if "title" is missing,
        instead of raising a KeyError and crashing.
    """

    # ── SKIP REMOVED ARTICLES ─────────────────────────────────────
    # NewsAPI sometimes returns placeholder articles with
    # title "[Removed]" when an article was taken down.
    title = raw_article.get("title", "")
    if not title or title == "[Removed]":
        return None

    url = raw_article.get("url", "")
    if not url or url == "https://removed.com":
        return None

    description = raw_article.get("description") or ""

    # ── EXTRACT SOURCE NAME ───────────────────────────────────────
    # NewsAPI nests the source: { "id": "...", "name": "TechCrunch" }
    # We only need the name.
    source_obj = raw_article.get("source", {})
    if isinstance(source_obj, dict):
        source = source_obj.get("name", "Unknown Source")
    else:
        source = str(source_obj)

    author = raw_article.get("author")
    published_at = raw_article.get("publishedAt")      # Note: camelCase from API

    # ── CATEGORIZE ────────────────────────────────────────────────
    # Run keyword matching on title + description.
    category = _categorize_article(title, description)

    # If keyword matching returned "Other Technology" AND we have a
    # hint from the search query, use the hint instead.
    # The hint is more accurate than "Other Technology" because
    # we used a targeted search query to find this article.
    if category == "Other Technology" and hint_category:
        category = hint_category

    # ── BUILD CLEAN ARTICLE ───────────────────────────────────────
    # Pass all fields through models.create_news_article() for
    # validation and consistent structure.
    article = create_news_article(
        title=title,
        url=url,
        description=description,
        source=source,
        author=author,
        published_at=published_at,
        category=category
    )

    return article


# ═════════════════════════════════════════════════════════════════
#  API CALL FUNCTIONS
# ═════════════════════════════════════════════════════════════════

def _fetch_from_newsapi(query, page_size=None):
    """
    Make one HTTP GET request to the NewsAPI /everything endpoint.

    Args:
        query     (str): The search query string.
        page_size (int): Number of articles to request (max 100).

    Returns:
        list: A list of raw article dicts from the API.
              Returns an empty list on any failure.

    NewsAPI /everything endpoint:
        GET https://newsapi.org/v2/everything
        Parameters:
          q        → search query
          language → "en" for English only
          sortBy   → "publishedAt" = newest first
          pageSize → number of results
          apiKey   → your key

    Python concept — requests.get():
        Sends an HTTP GET request.
        'params' is a dictionary of URL query parameters.
        requests builds the full URL automatically:
        https://newsapi.org/v2/everything?q=...&language=en&...

    Python concept — response.raise_for_status():
        If the HTTP status code is 4xx or 5xx (error),
        this raises an HTTPError exception.
        If the status is 2xx (success), it does nothing.
    """
    if not NEWS_API_KEY:
        print("  ERROR: NEWS_API_KEY is not set. Check your .env file.")
        return []

    size = page_size or NEWS_FETCH_PAGE_SIZE

    # Build the request parameters as a dictionary.
    # requests will encode them as URL query parameters automatically.
    params = {
        "q":        query,
        "language": "en",           # English articles only
        "sortBy":   "publishedAt",  # Newest first
        "pageSize": size,
        "apiKey":   NEWS_API_KEY    # Read from environment — never hardcoded
    }

    try:
        print(f"  Fetching: {query[:60]}...")

        # Make the HTTP GET request.
        # timeout=REQUEST_TIMEOUT means give up after 10 seconds.
        response = requests.get(
            f"{NEWS_API_BASE_URL}/everything",
            params=params,
            timeout=REQUEST_TIMEOUT
        )

        # Raise an exception if the server returned an error status.
        # e.g. 401 Unauthorized (bad API key), 429 Too Many Requests
        response.raise_for_status()

        # Parse the JSON response body into a Python dictionary.
        data = response.json()

        # ── HANDLE API-LEVEL ERRORS ───────────────────────────────
        # NewsAPI returns { "status": "error", "message": "..." }
        # even for some errors that come with a 200 HTTP status.
        if data.get("status") != "ok":
            error_message = data.get("message", "Unknown API error")
            print(f"  ERROR from NewsAPI: {error_message}")
            return []

        # Extract the articles list.
        # data.get("articles", []) returns [] if "articles" is missing
        # instead of raising a KeyError.
        articles = data.get("articles", [])
        print(f"  Received {len(articles)} articles.")
        return articles

    except Timeout:
        # The request took longer than REQUEST_TIMEOUT seconds.
        print(f"  ERROR: Request timed out after {REQUEST_TIMEOUT}s. NewsAPI may be slow.")
        return []

    except RequestsConnectionError:
        # No internet connection or DNS resolution failed.
        print("  ERROR: No internet connection. Check your network.")
        return []

    except requests.exceptions.HTTPError as e:
        # HTTP 4xx or 5xx error.
        status_code = e.response.status_code if e.response else "unknown"
        if status_code == 401:
            print("  ERROR: Invalid API key. Check NEWS_API_KEY in your .env file.")
        elif status_code == 429:
            print("  ERROR: API rate limit exceeded. Free tier allows 100 requests/day.")
        elif status_code == 426:
            print("  ERROR: This endpoint requires a paid NewsAPI plan.")
        else:
            print(f"  ERROR: HTTP {status_code} from NewsAPI.")
        return []

    except ValueError:
        # response.json() failed — the response was not valid JSON.
        print("  ERROR: NewsAPI returned invalid JSON.")
        return []

    except RequestException as e:
        # Catch-all for any other requests-related error.
        print(f"  ERROR: Request failed — {e}")
        return []


# ═════════════════════════════════════════════════════════════════
#  DEDUPLICATION
# ═════════════════════════════════════════════════════════════════

def _deduplicate_articles(articles):
    """
    Remove articles with duplicate URLs from a list.

    This handles duplicates WITHIN the current batch — before
    they reach the database. The database unique index handles
    duplicates across different fetch sessions.

    Why two levels of deduplication?
    - Within the batch: same article might appear in two different
      search queries (e.g., an OpenAI article matches both the
      "AI" query and the "Technology Companies" query).
    - Across sessions: an article fetched today might have also
      been fetched yesterday.

    Args:
        articles (list): List of article dicts (may have duplicates).

    Returns:
        list: List with duplicate URLs removed.

    Python concept — Set:
        A set stores only UNIQUE values and checks membership in O(1).
        seen_urls is a set we use to track which URLs we've already added.
        If a URL is already in the set, we skip that article.
    """
    seen_urls = set()     # An empty set — fast membership checking
    unique_articles = []  # The result list — only unique articles

    for article in articles:
        url = article.get("url", "")

        if not url:
            continue  # Skip articles with no URL

        if url not in seen_urls:
            # First time we've seen this URL — keep it.
            seen_urls.add(url)
            unique_articles.append(article)
        # If url IS in seen_urls, we skip this article (it's a duplicate).

    removed_count = len(articles) - len(unique_articles)
    if removed_count > 0:
        print(f"  Removed {removed_count} in-batch duplicates.")

    return unique_articles


# ═════════════════════════════════════════════════════════════════
#  MAIN PUBLIC FUNCTIONS
# ═════════════════════════════════════════════════════════════════

def fetch_news():
    """
    Fetch technology news from all configured search queries.

    Runs all SEARCH_QUERIES, combines the results, removes
    in-batch duplicates, and returns a list of clean article dicts.

    This function does NOT save to MongoDB — it only fetches and
    returns. Keeping fetch and save separate makes each function
    easier to test individually.

    Returns:
        list: Clean, deduplicated article dicts ready for MongoDB.
    """
    print("\n" + "=" * 50)
    print("FETCHING NEWS FROM NEWSAPI")
    print("=" * 50)

    all_raw_articles = []   # Collect raw responses from every query

    # Loop through every search query.
    for search in SEARCH_QUERIES:
        raw_articles = _fetch_from_newsapi(
            query=search["query"],
            page_size=NEWS_FETCH_PAGE_SIZE
        )
        all_raw_articles.append((raw_articles, search["hint_category"]))

    # Process all raw articles into clean dicts.
    print("\nProcessing articles...")
    clean_articles = []

    for raw_list, hint_category in all_raw_articles:
        for raw_article in raw_list:
            article = _extract_article_fields(raw_article, hint_category)
            if article:                      # None means the article was rejected
                clean_articles.append(article)

    print(f"Processed {len(clean_articles)} articles before deduplication.")

    # Remove duplicates within this batch.
    unique_articles = _deduplicate_articles(clean_articles)

    print(f"Final count after deduplication: {len(unique_articles)} articles.")
    return unique_articles


def fetch_and_store_news():
    """
    Fetch news AND save it to MongoDB in one step.

    This is the function the scheduler calls every morning.
    It combines fetch_news() + save_many_articles() and
    reports the final result.

    Returns:
        dict: A summary of what happened.
              {
                "fetched":  total articles from API,
                "saved":    new articles saved to MongoDB,
                "skipped":  duplicates already in database,
                "errors":   articles that failed to save,
                "articles": the list of fetched articles
              }
    """
    print("\nStarting daily news fetch...")

    # Step 1: Fetch from API.
    articles = fetch_news()

    if not articles:
        print("No articles fetched. Check your API key and internet connection.")
        return {
            "fetched": 0,
            "saved": 0,
            "skipped": 0,
            "errors": 0,
            "articles": []
        }

    # Step 2: Save to MongoDB.
    print(f"\nSaving {len(articles)} articles to MongoDB...")
    save_results = save_many_articles(articles)

    # Step 3: Print a summary.
    print("\n" + "=" * 50)
    print("FETCH SUMMARY")
    print("=" * 50)
    print(f"  Total fetched from API : {len(articles)}")
    print(f"  New articles saved     : {save_results['saved']}")
    print(f"  Duplicates skipped     : {save_results['skipped']}")
    print(f"  Errors                 : {save_results['errors']}")

    # Show category breakdown.
    counts = get_category_counts(articles)
    print("\nArticles by category:")
    for category, count in sorted(counts.items(), key=lambda x: x[1], reverse=True):
        bar = "#" * count
        print(f"  {category:<25} {count:>3}  {bar}")

    return {
        "fetched":  len(articles),
        "saved":    save_results["saved"],
        "skipped":  save_results["skipped"],
        "errors":   save_results["errors"],
        "articles": articles
    }


def fetch_news_by_category(category, limit=20):
    """
    Retrieve stored news articles filtered by category.

    This queries MongoDB (not the API) — it returns articles
    already collected and stored.

    Args:
        category (str): Category name to filter by.
        limit    (int): Maximum number of articles to return.

    Returns:
        list: Matching articles from MongoDB.
    """
    from database import get_news_by_category
    from models import VALID_CATEGORIES

    # Validate the category before querying.
    if category not in VALID_CATEGORIES:
        print(f"  WARNING: '{category}' is not a valid category.")
        return []

    return get_news_by_category(category, limit)
