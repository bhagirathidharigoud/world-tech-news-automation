# ─────────────────────────────────────────────────────────────────
#  models.py
#
#  PURPOSE:
#  Define the exact structure (shape) of every piece of data
#  this application stores in MongoDB.
#
#  These are NOT classes — just functions that return dictionaries.
#  Keeping it simple is intentional for learning purposes.
#
#  HOW TO USE IN OTHER FILES:
#      from models import create_news_article, create_daily_briefing
# ─────────────────────────────────────────────────────────────────

from datetime import datetime, timezone   # For timestamps


# ═════════════════════════════════════════════════════════════════
#  HELPER FUNCTIONS
# ═════════════════════════════════════════════════════════════════

def _now():
    """
    Return the current UTC time.

    We always store timestamps in UTC (Coordinated Universal Time)
    so that the app works correctly regardless of which timezone
    the server is in.

    UTC is the global standard for storing time in databases.
    When displaying to users, you convert UTC to their local time.
    """
    return datetime.now(timezone.utc)


def _clean_string(value, default=""):
    """
    Clean a string value coming from an external API.

    External APIs sometimes send:
    - None  (missing field)
    - Extra whitespace around the text
    - The string "None" instead of actual None

    This function handles all of those cases.

    Args:
        value: The raw value from the API response.
        default (str): What to return if the value is empty/None.

    Returns:
        str: A clean, stripped string or the default value.

    Python concept — str methods:
        .strip()  removes leading and trailing whitespace
        .lower()  converts to lowercase (used when comparing)
    """
    if value is None:
        return default

    # Convert to string in case a number was passed in by mistake.
    cleaned = str(value).strip()

    # Treat the literal string "None" as empty.
    if cleaned.lower() == "none" or cleaned == "":
        return default

    return cleaned


def _parse_date(date_value):
    """
    Convert a date string from an API into a Python datetime object.

    NewsAPI returns dates as ISO 8601 strings like:
        "2026-10-18T06:30:00Z"

    MongoDB stores Python datetime objects natively.
    We need to convert the string → datetime before storing.

    Args:
        date_value: A date string, datetime object, or None.

    Returns:
        datetime: A timezone-aware datetime, or current UTC time
                  if parsing fails.

    Python concept — datetime.strptime():
        Parses a string into a datetime object using a format pattern.
        %Y = 4-digit year, %m = month, %d = day
        %H = hour, %M = minute, %S = second
    """
    if date_value is None:
        return _now()

    # If it's already a datetime, just return it.
    if isinstance(date_value, datetime):
        return date_value

    # Try parsing ISO 8601 format: "2026-10-18T06:30:00Z"
    try:
        # Replace "Z" with "+00:00" — Python's preferred UTC format.
        date_str = str(date_value).replace("Z", "+00:00")
        return datetime.fromisoformat(date_str)
    except (ValueError, AttributeError):
        pass

    # Try a simpler format: "2026-10-18"
    try:
        dt = datetime.strptime(str(date_value)[:10], "%Y-%m-%d")
        # Make it timezone-aware by attaching UTC.
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    # If all parsing fails, use the current time.
    print(f"  WARNING: Could not parse date '{date_value}'. Using current time.")
    return _now()


# ═════════════════════════════════════════════════════════════════
#  NEWS ARTICLE MODEL
# ═════════════════════════════════════════════════════════════════

# These are all the valid category names in our system.
# Defined once here so that models.py and other files can
# import and reuse this list without hardcoding strings.
VALID_CATEGORIES = [
    "Agentic AI",
    "AI",
    "Quantum Computing",
    "Cloud Computing",
    "Cybersecurity",
    "Programming",
    "Developer Tools",
    "Startups",
    "Technology Companies",
    "Other Technology"
]


def create_news_article(
    title,
    url,
    description=None,
    source=None,
    author=None,
    published_at=None,
    category="Other Technology"
):
    """
    Create a clean news article dictionary ready to store in MongoDB.

    This function is the blueprint for a news article.
    Every article stored in the 'news' collection will
    have exactly these fields — no more, no less.

    Args:
        title       (str):  Headline of the article. Required.
        url         (str):  Article URL. Required. Used as unique ID.
        description (str):  Short summary. Optional.
        source      (str):  Publisher name e.g. "TechCrunch". Optional.
        author      (str):  Writer's name. Optional.
        published_at:       When the article was published. Optional.
        category    (str):  One of VALID_CATEGORIES. Default: "Other Technology".

    Returns:
        dict: A clean article dictionary, or None if title/url missing.

    Python concept — Dictionary:
        A dictionary is a collection of key-value pairs.
        { "key": value, "key2": value2 }
        Values can be strings, numbers, dates, lists, or other dicts.

    MongoDB concept — Document:
        This dictionary becomes one document in the 'news' collection.
        MongoDB stores it as BSON (Binary JSON) internally.
    """

    # ── VALIDATION ────────────────────────────────────────────────
    # title and url are REQUIRED. Without them, we cannot store
    # a meaningful article or check for duplicates.

    clean_title = _clean_string(title)
    clean_url = _clean_string(url)

    if not clean_title:
        print("  WARNING: Article rejected — missing title.")
        return None

    if not clean_url:
        print("  WARNING: Article rejected — missing URL.")
        return None

    # ── CATEGORY VALIDATION ───────────────────────────────────────
    # Make sure the category is one we recognise.
    # If an unknown category is passed, fall back to "Other Technology".

    clean_category = _clean_string(category, default="Other Technology")
    if clean_category not in VALID_CATEGORIES:
        print(f"  WARNING: Unknown category '{clean_category}'. Using 'Other Technology'.")
        clean_category = "Other Technology"

    # ── BUILD THE DOCUMENT ────────────────────────────────────────
    # This is the dictionary that gets stored as a MongoDB document.
    #
    # Notice:
    # - We do NOT include '_id' — MongoDB generates it automatically.
    # - All string values are cleaned before storing.
    # - 'score' starts at 0 — briefing_service.py will calculate it.
    # - 'collected_at' is always NOW — when our app fetched this article.
    # - 'published_at' is when the original article was published.

    article = {
        # ── Core content ──────────────────────────────────────────
        "title":        clean_title,
        "description":  _clean_string(description, default="No description available."),
        "url":          clean_url,

        # ── Source information ────────────────────────────────────
        "source":       _clean_string(source, default="Unknown Source"),
        "author":       _clean_string(author, default="Unknown Author"),

        # ── Classification ────────────────────────────────────────
        "category":     clean_category,

        # ── Timestamps ────────────────────────────────────────────
        # published_at: when the journalist published the article
        "published_at": _parse_date(published_at),
        # collected_at: when OUR app fetched and stored it
        "collected_at": _now(),

        # ── Scoring ───────────────────────────────────────────────
        # Starts at 0. briefing_service.py assigns a score
        # based on importance (Step 7).
        "score": 0
    }

    return article


def article_to_dict(article):
    """
    Convert a MongoDB article document to a clean dictionary
    safe for returning in a JSON API response.

    When Flask returns data to Postman, datetime objects must be
    converted to strings — JSON has no datetime type.

    Args:
        article (dict): A raw MongoDB document.

    Returns:
        dict: A clean dictionary with dates as ISO strings.
    """
    if not article:
        return None

    # Make a copy so we don't modify the original.
    result = dict(article)

    # Convert datetime objects to ISO strings for JSON.
    for field in ["published_at", "collected_at"]:
        if field in result and isinstance(result[field], datetime):
            result[field] = result[field].isoformat()

    return result


# ═════════════════════════════════════════════════════════════════
#  DAILY BRIEFING MODEL
# ═════════════════════════════════════════════════════════════════

def create_daily_briefing(
    briefing_date,
    top_news,
    briefing_text,
    category_counts,
    total_news
):
    """
    Create a daily briefing dictionary ready to store in MongoDB.

    This is the processed output — the result of running the
    daily news collection, scoring, and formatting pipeline.

    Args:
        briefing_date   (str):  Date string "YYYY-MM-DD".
        top_news        (list): List of selected article dicts.
        briefing_text   (str):  The fully formatted briefing text.
        category_counts (dict): How many articles per category.
                                e.g. {"AI": 5, "Cybersecurity": 3}
        total_news      (int):  Total articles collected today.

    Returns:
        dict: A briefing dictionary ready for MongoDB.

    Python concept — Nested dictionary:
        The 'categories' field is a dictionary inside a dictionary.
        MongoDB handles nested structures natively — no special setup.
    """

    # ── VALIDATE DATE FORMAT ──────────────────────────────────────
    # We store dates as "YYYY-MM-DD" strings (not datetime objects)
    # because this is the unique identifier for a briefing.
    # String comparison works correctly for this format:
    # "2026-10-18" > "2026-10-17" → True

    clean_date = _clean_string(briefing_date)
    if not clean_date:
        clean_date = _now().strftime("%Y-%m-%d")

    # ── BUILD THE DOCUMENT ────────────────────────────────────────
    briefing = {
        # ── Identity ──────────────────────────────────────────────
        # briefing_date is UNIQUE — one briefing per day.
        # The unique index in MongoDB enforces this.
        "briefing_date":  clean_date,

        # ── Timestamps ────────────────────────────────────────────
        "generated_at":   _now(),
        "created_at":     _now(),

        # ── Statistics ────────────────────────────────────────────
        # total_news: how many articles were collected and stored today
        "total_news":     total_news if isinstance(total_news, int) else 0,

        # categories: count of articles per category
        # Example: {"AI": 8, "Cybersecurity": 4, "Cloud Computing": 3}
        "categories":     category_counts if isinstance(category_counts, dict) else {},

        # ── Content ───────────────────────────────────────────────
        # top_news: the selected articles included in this briefing
        # Stored as an array of embedded documents inside the briefing.
        # MongoDB concept — Embedded document:
        #   Instead of a separate collection with a reference/foreign key,
        #   we embed the article data directly in the briefing document.
        #   This makes reading a briefing fast — one query, all data.
        "top_news":       top_news if isinstance(top_news, list) else [],

        # briefing_text: the final formatted text ready to print/display
        "briefing_text":  _clean_string(briefing_text, default="No briefing generated.")
    }

    return briefing


def briefing_to_dict(briefing):
    """
    Convert a MongoDB briefing document to a clean dictionary
    safe for returning in a JSON API response.

    Args:
        briefing (dict): A raw MongoDB briefing document.

    Returns:
        dict: A clean dictionary with dates as ISO strings.
    """
    if not briefing:
        return None

    result = dict(briefing)

    # Convert datetime fields to strings.
    for field in ["generated_at", "created_at"]:
        if field in result and isinstance(result[field], datetime):
            result[field] = result[field].isoformat()

    # Convert datetimes inside each article in top_news.
    if "top_news" in result and isinstance(result["top_news"], list):
        result["top_news"] = [article_to_dict(a) for a in result["top_news"]]

    return result


# ═════════════════════════════════════════════════════════════════
#  ERROR RESPONSE MODEL
# ═════════════════════════════════════════════════════════════════

def create_error_response(message, status_code=400, details=None):
    """
    Create a consistent error response dictionary for the REST API.

    Every error returned by our API will have the same structure.
    Consistency helps developers using our API understand errors quickly.

    Args:
        message     (str): Human-readable error description.
        status_code (int): HTTP status code (400, 404, 500, etc.).
        details     (str): Optional extra information. Never expose secrets.

    Returns:
        dict: An error response dictionary.

    HTTP Status Codes used in this project:
        200 — OK (success)
        400 — Bad Request (client sent invalid input)
        404 — Not Found (article or briefing does not exist)
        500 — Internal Server Error (something broke on our side)
    """
    response = {
        "error":   True,
        "message": _clean_string(message, default="An error occurred."),
        "code":    status_code
    }

    # Only include details if provided.
    # We never put passwords, stack traces, or API keys in details.
    if details:
        response["details"] = _clean_string(details)

    return response


def create_success_response(data, message="Success", total=None):
    """
    Create a consistent success response dictionary for the REST API.

    Args:
        data    (list or dict): The actual data to return.
        message (str):          Human-readable success message.
        total   (int):          Optional total count (useful for lists).

    Returns:
        dict: A success response dictionary.
    """
    response = {
        "error":   False,
        "message": message,
        "data":    data
    }

    # Include count only when returning a list.
    if total is not None:
        response["total"] = total
    elif isinstance(data, list):
        response["total"] = len(data)

    return response
