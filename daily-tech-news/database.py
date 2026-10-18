# ─────────────────────────────────────────────────────────────────
#  database.py
#
#  PURPOSE:
#  Connect to MongoDB and provide simple helper functions
#  for saving and retrieving news articles and briefings.
#
#  HOW TO USE IN OTHER FILES:
#      from database import save_news_article, get_news_collection
#
#  RULE:
#  All MongoDB logic lives here. No other file should create
#  a MongoClient directly.
# ─────────────────────────────────────────────────────────────────

from pymongo import MongoClient, ASCENDING   # PyMongo — MongoDB driver
from pymongo.errors import (
    ConnectionFailure,       # Raised when MongoDB server is unreachable
    DuplicateKeyError,       # Raised when a unique index is violated
    ServerSelectionTimeoutError  # Raised when connection times out
)
from datetime import datetime, timezone      # For timestamps

from config import (
    MONGO_URI,
    MONGO_DB_NAME,
    COLLECTION_NEWS,
    COLLECTION_BRIEFINGS
)


# ── MODULE-LEVEL VARIABLE ─────────────────────────────────────────
# We store the MongoClient in a module-level variable so that we
# create only ONE connection and reuse it across all function calls.
#
# This pattern is called a "singleton" — one shared instance.
# Creating a new connection for every database call is wasteful.

_client = None   # Will hold the MongoClient once connected
_db = None       # Will hold the database object once connected


# ═════════════════════════════════════════════════════════════════
#  CONNECTION FUNCTIONS
# ═════════════════════════════════════════════════════════════════

def connect_to_mongodb():
    """
    Create a connection to MongoDB and store it in module variables.

    Returns:
        bool: True if connection succeeded, False if it failed.

    MongoDB concept:
        MongoClient is the object that manages your connection.
        It does NOT immediately connect when created — it connects
        lazily when you first use it. We call 'ping' to force an
        immediate connection test.
    """
    # 'global' tells Python we want to modify the module-level
    # variables _client and _db, not create new local ones.
    global _client, _db

    try:
        print(f"Connecting to MongoDB at {MONGO_URI} ...")

        # Create the MongoClient.
        # serverSelectionTimeoutMS=5000 means:
        # if MongoDB does not respond within 5 seconds, raise an error.
        # Without this, Python would wait forever.
        _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)

        # Ping the server to confirm the connection is actually alive.
        # 'admin' is a built-in MongoDB database used for server commands.
        _client.admin.command("ping")

        # Get (or create) the tech_news database.
        # MongoDB creates the database automatically on first use —
        # you do not need to create it manually.
        _db = _client[MONGO_DB_NAME]

        print(f"Connected to MongoDB. Database: '{MONGO_DB_NAME}'")

        # Create indexes after confirming connection.
        _create_indexes()

        return True

    except ServerSelectionTimeoutError:
        # MongoDB is installed but not running, or the URI is wrong.
        print("ERROR: Could not connect to MongoDB.")
        print("  → Is MongoDB running? Try: mongod")
        print(f"  → Is the URI correct? Current: {MONGO_URI}")
        return False

    except ConnectionFailure as e:
        print(f"ERROR: MongoDB connection failed — {e}")
        return False

    except Exception as e:
        # Catch anything else unexpected.
        print(f"ERROR: Unexpected error connecting to MongoDB — {e}")
        return False


def _create_indexes():
    """
    Create indexes on the collections to improve query speed
    and enforce uniqueness rules.

    This function is 'private' — the underscore prefix is a Python
    convention meaning 'intended for internal use only'.

    MongoDB concept — Index:
        An index makes queries faster, like the index at the back
        of a textbook. Without it, MongoDB reads every document
        to find a match (slow). With an index, it jumps directly.

    MongoDB concept — Unique Index:
        A unique index is an index that also ENFORCES uniqueness.
        If you try to insert a document where the indexed field
        already exists, MongoDB raises DuplicateKeyError.
        We use this on the 'url' field to prevent duplicate articles.
    """
    try:
        news_col = _db[COLLECTION_NEWS]
        briefings_col = _db[COLLECTION_BRIEFINGS]

        # Unique index on 'url' in the news collection.
        # Effect: if you try to save an article with a URL that
        # already exists, MongoDB rejects it automatically.
        news_col.create_index(
            [("url", ASCENDING)],
            unique=True,
            name="unique_article_url"
        )

        # Index on 'published_at' so we can quickly sort and
        # filter news by date.
        news_col.create_index(
            [("published_at", ASCENDING)],
            name="news_published_date"
        )

        # Index on 'category' so filtering by category is fast.
        news_col.create_index(
            [("category", ASCENDING)],
            name="news_category"
        )

        # Unique index on 'briefing_date' in the briefings collection.
        # Effect: only one briefing per date can exist.
        briefings_col.create_index(
            [("briefing_date", ASCENDING)],
            unique=True,
            name="unique_briefing_date"
        )

        print("MongoDB indexes created (or already exist).")

    except Exception as e:
        # Index creation failing is not fatal — the app still works,
        # just slightly slower and without duplicate protection.
        print(f"WARNING: Could not create indexes — {e}")


def get_database():
    """
    Return the database object.
    Connects automatically if not already connected.

    Returns:
        Database object or None if connection failed.
    """
    global _db
    if _db is None:
        success = connect_to_mongodb()
        if not success:
            return None
    return _db


def disconnect_from_mongodb():
    """
    Close the MongoDB connection cleanly.
    Call this when the application is shutting down.
    """
    global _client, _db
    if _client:
        _client.close()
        _client = None
        _db = None
        print("MongoDB connection closed.")


# ═════════════════════════════════════════════════════════════════
#  COLLECTION HELPERS
# ═════════════════════════════════════════════════════════════════

def get_news_collection():
    """
    Return the 'news' collection object.

    MongoDB concept — Collection:
        A collection is a group of documents, similar to a table
        in a relational database, except documents in the same
        collection do not need to have the same fields.

    Returns:
        Collection object or None if database unavailable.
    """
    db = get_database()
    if db is None:
        return None
    return db[COLLECTION_NEWS]


def get_briefings_collection():
    """
    Return the 'daily_briefings' collection object.

    Returns:
        Collection object or None if database unavailable.
    """
    db = get_database()
    if db is None:
        return None
    return db[COLLECTION_BRIEFINGS]


# ═════════════════════════════════════════════════════════════════
#  NEWS ARTICLE FUNCTIONS
# ═════════════════════════════════════════════════════════════════

def article_exists(url):
    """
    Check whether an article with the given URL is already stored.

    This is our duplicate detection function. Before saving any
    article, we check if its URL already exists in the database.

    Args:
        url (str): The article URL to check.

    Returns:
        bool: True if the article exists, False if it is new.

    MongoDB concept — find_one():
        find_one() returns the FIRST document that matches the query,
        or None if no match is found.
        {"url": url} is the query — find a document where the
        'url' field equals the value of our url variable.
    """
    collection = get_news_collection()
    if collection is None:
        return False

    try:
        result = collection.find_one({"url": url})
        # If result is not None, the article exists.
        return result is not None

    except Exception as e:
        print(f"WARNING: Could not check for duplicate — {e}")
        # If the check fails, return False so we attempt to save.
        # The unique index will still block actual duplicates.
        return False


def save_news_article(article):
    """
    Save a single news article to the 'news' collection.

    Args:
        article (dict): A news article dictionary (see models.py).

    Returns:
        str or None: The inserted document's _id as a string,
                     or None if saving failed.

    MongoDB concept — insert_one():
        insert_one() adds a single document to a collection.
        MongoDB automatically creates and assigns the '_id' field
        (an ObjectId) unless you provide one yourself.
        The result object has an 'inserted_id' attribute.

    MongoDB concept — DuplicateKeyError:
        If we try to insert an article whose URL already exists
        (because of our unique index), PyMongo raises
        DuplicateKeyError. We catch it silently — it just means
        we already have this article.
    """
    collection = get_news_collection()
    if collection is None:
        return None

    try:
        result = collection.insert_one(article)
        # result.inserted_id is a BSON ObjectId object.
        # str() converts it to a readable string like:
        # "507f1f77bcf86cd799439011"
        return str(result.inserted_id)

    except DuplicateKeyError:
        # Article already exists — this is expected and not an error.
        return None

    except Exception as e:
        print(f"ERROR: Could not save article — {e}")
        return None


def save_many_articles(articles):
    """
    Save multiple news articles at once.

    Loops through the list and saves each article individually.
    Counts how many were new (saved) vs duplicates (skipped).

    Args:
        articles (list): A list of article dictionaries.

    Returns:
        dict: {"saved": int, "skipped": int, "errors": int}
    """
    results = {"saved": 0, "skipped": 0, "errors": 0}

    for article in articles:
        # Validate that the article has a URL before trying to save.
        if not article.get("url"):
            results["errors"] += 1
            continue

        inserted_id = save_news_article(article)

        if inserted_id:
            results["saved"] += 1
        else:
            # None means either duplicate or error.
            # article_exists() tells us which.
            if article_exists(article["url"]):
                results["skipped"] += 1
            else:
                results["errors"] += 1

    return results


# ═════════════════════════════════════════════════════════════════
#  RETRIEVAL FUNCTIONS
# ═════════════════════════════════════════════════════════════════

def get_latest_news(limit=50):
    """
    Retrieve the most recent news articles.

    Args:
        limit (int): Maximum number of articles to return.

    Returns:
        list: A list of article dictionaries, newest first.

    MongoDB concept — find():
        find() with no arguments returns ALL documents.
        find({"category": "AI"}) filters by category.

    MongoDB concept — sort():
        sort("published_at", -1) sorts by published_at descending
        (-1 = descending = newest first).
        sort("published_at", 1) would be oldest first.

    MongoDB concept — limit():
        limit(50) stops after returning 50 documents.
        Without this, find() would return the entire collection.
    """
    collection = get_news_collection()
    if collection is None:
        return []

    try:
        # Method chaining: find() → sort() → limit()
        # Each method returns the cursor so we can chain the next.
        cursor = collection.find().sort("published_at", -1).limit(limit)

        # Convert the cursor to a Python list.
        # Also convert ObjectId to string so it can be JSON serialized.
        articles = []
        for doc in cursor:
            doc["_id"] = str(doc["_id"])
            articles.append(doc)

        return articles

    except Exception as e:
        print(f"ERROR: Could not retrieve news — {e}")
        return []


def get_news_by_category(category, limit=20):
    """
    Retrieve articles filtered by category.

    Args:
        category (str): Category name e.g. "AI", "Cybersecurity".
        limit (int): Maximum number of articles to return.

    Returns:
        list: Matching articles, newest first.

    MongoDB concept — Query filter:
        {"category": category} is the filter document.
        MongoDB returns only documents where 'category' field
        equals the value we pass in.
    """
    collection = get_news_collection()
    if collection is None:
        return []

    try:
        # Case-insensitive query using a regex.
        # This lets "AI" match "ai" or "Ai" in the stored data.
        import re
        query = {"category": {"$regex": f"^{re.escape(category)}$", "$options": "i"}}

        cursor = collection.find(query).sort("published_at", -1).limit(limit)

        articles = []
        for doc in cursor:
            doc["_id"] = str(doc["_id"])
            articles.append(doc)

        return articles

    except Exception as e:
        print(f"ERROR: Could not retrieve news by category — {e}")
        return []


def get_article_by_id(article_id):
    """
    Retrieve a single article by its MongoDB ObjectId.

    Args:
        article_id (str): The _id string from MongoDB.

    Returns:
        dict or None: The article, or None if not found.

    MongoDB concept — ObjectId:
        MongoDB stores IDs as BSON ObjectId objects, not plain strings.
        We must convert the string back to ObjectId before querying.
    """
    from bson import ObjectId           # BSON types from PyMongo
    from bson.errors import InvalidId   # Raised if the string is not a valid ObjectId

    collection = get_news_collection()
    if collection is None:
        return None

    try:
        # Convert the string ID back to a MongoDB ObjectId.
        object_id = ObjectId(article_id)
        doc = collection.find_one({"_id": object_id})

        if doc:
            doc["_id"] = str(doc["_id"])
            return doc
        return None

    except InvalidId:
        # The provided string is not a valid ObjectId format.
        print(f"ERROR: '{article_id}' is not a valid article ID.")
        return None

    except Exception as e:
        print(f"ERROR: Could not retrieve article — {e}")
        return None


def search_news(keyword, limit=20):
    """
    Search news articles by keyword in title, description, or category.

    Args:
        keyword (str): The search term.
        limit (int): Maximum results to return.

    Returns:
        list: Matching articles.

    MongoDB concept — $regex operator:
        $regex allows pattern matching inside a query.
        "i" option makes it case-insensitive.

    MongoDB concept — $or operator:
        $or takes a list of conditions and returns documents
        where AT LEAST ONE condition is true.
    """
    collection = get_news_collection()
    if collection is None:
        return []

    try:
        import re
        # Build a regex pattern from the keyword.
        pattern = re.escape(keyword)

        # $or means: match if title contains keyword
        #         OR description contains keyword
        #         OR category contains keyword
        query = {
            "$or": [
                {"title":       {"$regex": pattern, "$options": "i"}},
                {"description": {"$regex": pattern, "$options": "i"}},
                {"category":    {"$regex": pattern, "$options": "i"}}
            ]
        }

        cursor = collection.find(query).sort("published_at", -1).limit(limit)

        articles = []
        for doc in cursor:
            doc["_id"] = str(doc["_id"])
            articles.append(doc)

        return articles

    except Exception as e:
        print(f"ERROR: Search failed — {e}")
        return []


def get_todays_news():
    """
    Retrieve all articles collected today (since midnight).

    Returns:
        list: Today's articles, newest first.

    Python concept — datetime:
        datetime.now() gives current date and time.
        We use replace() to set the time to midnight (00:00:00)
        to get the start of today.
    """
    collection = get_news_collection()
    if collection is None:
        return []

    try:
        # Get today's date at midnight (start of day).
        now = datetime.now(timezone.utc)
        start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # $gte means "greater than or equal to".
        # So: find articles where collected_at >= start of today.
        query = {"collected_at": {"$gte": start_of_today}}

        cursor = collection.find(query).sort("published_at", -1)

        articles = []
        for doc in cursor:
            doc["_id"] = str(doc["_id"])
            articles.append(doc)

        return articles

    except Exception as e:
        print(f"ERROR: Could not retrieve today's news — {e}")
        return []


# ═════════════════════════════════════════════════════════════════
#  BRIEFING FUNCTIONS
# ═════════════════════════════════════════════════════════════════

def save_briefing(briefing):
    """
    Save a daily briefing to the 'daily_briefings' collection.

    Args:
        briefing (dict): A briefing dictionary (see models.py).

    Returns:
        str or None: Inserted _id as string, or None on failure.
    """
    collection = get_briefings_collection()
    if collection is None:
        return None

    try:
        result = collection.insert_one(briefing)
        return str(result.inserted_id)

    except DuplicateKeyError:
        # A briefing for this date already exists.
        print(f"WARNING: Briefing for {briefing.get('briefing_date')} already exists.")
        return None

    except Exception as e:
        print(f"ERROR: Could not save briefing — {e}")
        return None


def get_briefing_by_date(date_str):
    """
    Retrieve a briefing by its date string.

    Args:
        date_str (str): Date in "YYYY-MM-DD" format.

    Returns:
        dict or None: The briefing document, or None if not found.
    """
    collection = get_briefings_collection()
    if collection is None:
        return None

    try:
        doc = collection.find_one({"briefing_date": date_str})
        if doc:
            doc["_id"] = str(doc["_id"])
            return doc
        return None

    except Exception as e:
        print(f"ERROR: Could not retrieve briefing — {e}")
        return None


def get_all_briefings(limit=30):
    """
    Retrieve the most recent daily briefings.

    Args:
        limit (int): Maximum number of briefings to return.

    Returns:
        list: Briefing documents, newest first.
    """
    collection = get_briefings_collection()
    if collection is None:
        return []

    try:
        cursor = collection.find().sort("briefing_date", -1).limit(limit)

        briefings = []
        for doc in cursor:
            doc["_id"] = str(doc["_id"])
            briefings.append(doc)

        return briefings

    except Exception as e:
        print(f"ERROR: Could not retrieve briefings — {e}")
        return []


# ═════════════════════════════════════════════════════════════════
#  HEALTH CHECK
# ═════════════════════════════════════════════════════════════════

def check_database_health():
    """
    Verify MongoDB is reachable and return status information.

    Returns:
        dict: Status information about the database connection.

    Used by the GET /health API endpoint.
    """
    try:
        db = get_database()
        if db is None:
            return {
                "status": "unhealthy",
                "message": "Could not connect to MongoDB",
                "database": MONGO_DB_NAME
            }

        # Count documents in each collection as a quick health signal.
        news_count = db[COLLECTION_NEWS].count_documents({})
        briefings_count = db[COLLECTION_BRIEFINGS].count_documents({})

        return {
            "status": "healthy",
            "message": "MongoDB is connected",
            "database": MONGO_DB_NAME,
            "collections": {
                "news": news_count,
                "daily_briefings": briefings_count
            }
        }

    except Exception as e:
        return {
            "status": "unhealthy",
            "message": f"Database error: {str(e)}",
            "database": MONGO_DB_NAME
        }
