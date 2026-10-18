# ─────────────────────────────────────────────────────────────────
#  main.py
#
#  PURPOSE:
#  Start the Flask REST API server.
#  This is the entry point of the entire application.
#
#  HOW TO RUN:
#      python main.py
#
#  The server starts at:
#      http://localhost:5000
#
#  ENDPOINTS:
#      GET  /health
#      GET  /news
#      GET  /news/<id>
#      GET  /news/category/<category>
#      GET  /news/search?keyword=python
#      GET  /briefings
#      GET  /briefings/<date>
#      POST /fetch
#      POST /briefing/generate
# ─────────────────────────────────────────────────────────────────

from flask import Flask, jsonify, request, send_from_directory   # Core Flask
import os
import threading
from datetime import datetime, timezone

# APScheduler — BackgroundScheduler runs in a thread alongside Flask.
# BlockingScheduler (used in scheduler.py) blocks the process.
# BackgroundScheduler does NOT block — perfect for embedding in Flask.
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import FLASK_PORT, FLASK_ENV, validate_config
from database import (
    connect_to_mongodb,
    check_database_health,
    get_latest_news,
    get_article_by_id,
    get_news_by_category,
    search_news,
    get_briefing_by_date,
    get_all_briefings,
    get_todays_news
)
from models import (
    article_to_dict,
    briefing_to_dict,
    create_error_response,
    create_success_response,
    VALID_CATEGORIES
)
from news_service import fetch_and_store_news
from briefing_service import generate_daily_briefing


# ── CREATE THE FLASK APPLICATION ──────────────────────────────────
# Flask(__name__) creates the application.
# __name__ tells Flask where to find resources (templates, static files).
# Compute the absolute path to the project root once at startup.
# We use inspect to get the real path of this file regardless
# of how Python was launched or what the working directory is.
import inspect as _inspect
_ROOT = os.path.dirname(os.path.abspath(_inspect.getfile(_inspect.currentframe())))

# Read the dashboard HTML once at startup into memory.
# This avoids all file-path issues with Flask's debug reloader.
_UI_HTML = ""
try:
    _ui_path = os.path.join(_ROOT, "templates", "index.html")
    with open(_ui_path, "r", encoding="utf-8") as _f:
        _UI_HTML = _f.read()
    print(f"Dashboard UI loaded ({len(_UI_HTML)} bytes) from {_ui_path}")
except Exception as _e:
    print(f"WARNING: Could not load dashboard UI: {_e}")

app = Flask(__name__, template_folder=os.path.join(_ROOT, "templates"))


# ═════════════════════════════════════════════════════════════════
#  RUNTIME SCHEDULER STATE
#  A single BackgroundScheduler instance lives alongside Flask.
#  The UI can start / stop / inspect it via REST endpoints.
# ═════════════════════════════════════════════════════════════════

# Valid intervals the user can choose from the UI.
INTERVALS = {
    "1min":  {"seconds": 60,      "label": "Every 1 Minute"},
    "5min":  {"seconds": 300,     "label": "Every 5 Minutes"},
    "1hour": {"seconds": 3600,    "label": "Every 1 Hour"},
    "1day":  {"seconds": 86400,   "label": "Every 1 Day"},
}

# Module-level scheduler — one instance shared across all requests.
_bg_scheduler = BackgroundScheduler(timezone="UTC")
_bg_scheduler.start()   # Start the scheduler thread immediately (no jobs yet).

# State dictionary — thread-safe reads via a lock.
_sched_lock = threading.Lock()
_sched_state = {
    "running":        False,          # Is a job currently scheduled?
    "interval_key":   None,           # "1min" / "5min" / "1hour" / "1day"
    "interval_label": None,
    "interval_secs":  None,
    "started_at":     None,           # ISO timestamp when started
    "last_run_at":    None,           # ISO timestamp of last successful run
    "next_run_at":    None,           # ISO timestamp of next scheduled run
    "run_count":      0,              # How many times the job has fired
    "last_result":    None,           # Summary from last run
}

JOB_ID = "ui_news_refresh"


def _scheduler_job():
    """
    The function APScheduler calls on every tick.
    Runs the full pipeline: fetch → store → generate briefing.
    Updates _sched_state so the UI can show live progress.
    """
    with _sched_lock:
        _sched_state["last_run_at"] = datetime.now(timezone.utc).isoformat()

    print(f"\n[SCHEDULER] Job fired at {_sched_state['last_run_at']}")

    try:
        connect_to_mongodb()

        from news_service import fetch_and_store_news
        from briefing_service import generate_daily_briefing

        result = fetch_and_store_news()

        briefing = generate_daily_briefing()

        with _sched_lock:
            _sched_state["run_count"] += 1
            _sched_state["last_result"] = {
                "fetched":  result.get("fetched", 0),
                "saved":    result.get("saved", 0),
                "skipped":  result.get("skipped", 0),
                "briefing": briefing.get("briefing_date") if briefing else None,
            }
            # Update next_run_at from the live job object
            job = _bg_scheduler.get_job(JOB_ID)
            if job and job.next_run_time:
                _sched_state["next_run_at"] = job.next_run_time.isoformat()

        print(f"[SCHEDULER] Done. Saved {result.get('saved',0)} new articles.")

    except Exception as e:
        print(f"[SCHEDULER] ERROR: {e}")
        with _sched_lock:
            _sched_state["last_result"] = {"error": str(e)}
#  HELPER FUNCTIONS
# ═════════════════════════════════════════════════════════════════

def success(data, message="OK", status_code=200):
    """
    Return a successful JSON response.

    Args:
        data        : The data to return (list or dict).
        message     : Human-readable success message.
        status_code : HTTP status code (default 200).

    Returns:
        Flask Response object with JSON body.

    Flask concept — jsonify():
        Converts a Python dict to a JSON HTTP response.
        Sets Content-Type header to application/json automatically.

    Flask concept — tuple return:
        Returning (response, status_code) from a route function
        tells Flask to use that specific HTTP status code.
    """
    return jsonify(create_success_response(data, message)), status_code


def error(message, status_code=400, details=None):
    """
    Return an error JSON response.

    Args:
        message     : Human-readable error message.
        status_code : HTTP status code (400, 404, 500, etc.).
        details     : Optional extra detail (never expose secrets).

    Returns:
        Flask Response object with JSON body.
    """
    return jsonify(create_error_response(message, status_code, details)), status_code


def convert_articles(articles):
    """
    Convert a list of MongoDB article documents to JSON-safe dicts.
    Dates become strings, ObjectIds stay as strings.
    """
    return [article_to_dict(a) for a in articles if a]


# ═════════════════════════════════════════════════════════════════
#  STARTUP
# ═════════════════════════════════════════════════════════════════

@app.before_request
def ensure_db_connected():
    connect_to_mongodb()


# ═════════════════════════════════════════════════════════════════
#  UI ROUTE — serves the web dashboard
# ═════════════════════════════════════════════════════════════════

@app.route("/ui")
@app.route("/ui/")
def serve_ui():
    """Serve the web dashboard at http://localhost:5000/ui"""
    if not _UI_HTML:
        return "Dashboard not available. Check templates/index.html exists.", 500
    from flask import make_response
    resp = make_response(_UI_HTML)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    return resp


# ═════════════════════════════════════════════════════════════════
#  SCHEDULER API ENDPOINTS
# ═════════════════════════════════════════════════════════════════

@app.route("/scheduler/status", methods=["GET"])
def scheduler_status():
    """
    GET /scheduler/status

    Return the current state of the background scheduler.

    Response:
    {
        "running": true,
        "interval_key": "5min",
        "interval_label": "Every 5 Minutes",
        "interval_secs": 300,
        "started_at": "2026-10-18T06:00:00+00:00",
        "last_run_at": "2026-10-18T06:05:00+00:00",
        "next_run_at": "2026-10-18T06:10:00+00:00",
        "run_count": 3,
        "last_result": { "fetched": 366, "saved": 5, "skipped": 361 }
    }
    """
    with _sched_lock:
        state = dict(_sched_state)

    # Refresh next_run_at from the live job object
    job = _bg_scheduler.get_job(JOB_ID)
    if job and job.next_run_time:
        state["next_run_at"] = job.next_run_time.isoformat()

    state["available_intervals"] = {
        k: v["label"] for k, v in INTERVALS.items()
    }

    return success(state)


@app.route("/scheduler/start", methods=["POST"])
def scheduler_start():
    """
    POST /scheduler/start
    Body: { "interval": "5min" }

    Start the background scheduler with the chosen interval.
    Valid intervals: 1min, 5min, 1hour, 1day

    Response 200:
    { "message": "Scheduler started. Running every 5 Minutes." }

    Response 400: invalid interval key
    """
    body = request.get_json(silent=True) or {}
    interval_key = body.get("interval", "").strip()

    if interval_key not in INTERVALS:
        keys = ", ".join(INTERVALS.keys())
        return error(f"Invalid interval '{interval_key}'. Choose from: {keys}", 400)

    cfg = INTERVALS[interval_key]

    # Remove any existing job before adding new one.
    if _bg_scheduler.get_job(JOB_ID):
        _bg_scheduler.remove_job(JOB_ID)

    # Add the job with an IntervalTrigger.
    # IntervalTrigger fires repeatedly every N seconds.
    _bg_scheduler.add_job(
        func=_scheduler_job,
        trigger=IntervalTrigger(seconds=cfg["seconds"]),
        id=JOB_ID,
        name=f"UI News Refresh ({cfg['label']})",
        replace_existing=True,
        misfire_grace_time=60     # Allow up to 60s late before skipping
    )

    now = datetime.now(timezone.utc).isoformat()
    job = _bg_scheduler.get_job(JOB_ID)
    next_run = job.next_run_time.isoformat() if job and job.next_run_time else None

    with _sched_lock:
        _sched_state["running"]        = True
        _sched_state["interval_key"]   = interval_key
        _sched_state["interval_label"] = cfg["label"]
        _sched_state["interval_secs"]  = cfg["seconds"]
        _sched_state["started_at"]     = now
        _sched_state["next_run_at"]    = next_run
        _sched_state["run_count"]      = 0
        _sched_state["last_result"]    = None

    print(f"[SCHEDULER] Started — {cfg['label']} (every {cfg['seconds']}s)")

    return success({
        "interval_key":   interval_key,
        "interval_label": cfg["label"],
        "interval_secs":  cfg["seconds"],
        "next_run_at":    next_run,
    }, message=f"Scheduler started. Running {cfg['label']}.")


@app.route("/scheduler/stop", methods=["POST"])
def scheduler_stop():
    """
    POST /scheduler/stop

    Stop the background scheduler job.
    The scheduler thread keeps running but no jobs fire.

    Response 200: { "message": "Scheduler stopped." }
    """
    if _bg_scheduler.get_job(JOB_ID):
        _bg_scheduler.remove_job(JOB_ID)

    with _sched_lock:
        _sched_state["running"]        = False
        _sched_state["interval_key"]   = None
        _sched_state["interval_label"] = None
        _sched_state["interval_secs"]  = None
        _sched_state["next_run_at"]    = None

    print("[SCHEDULER] Stopped.")
    return success({}, message="Scheduler stopped.")


@app.route("/scheduler/run-now", methods=["POST"])
def scheduler_run_now():
    """
    POST /scheduler/run-now

    Immediately run the news fetch job once,
    regardless of the current schedule.

    Response 200: fetch summary
    """
    try:
        print("[SCHEDULER] Manual run triggered from UI.")
        connect_to_mongodb()

        from news_service import fetch_and_store_news
        from briefing_service import generate_daily_briefing

        result = fetch_and_store_news()
        briefing = generate_daily_briefing()

        with _sched_lock:
            _sched_state["last_run_at"] = datetime.now(timezone.utc).isoformat()
            _sched_state["run_count"]  += 1
            _sched_state["last_result"] = {
                "fetched":  result.get("fetched", 0),
                "saved":    result.get("saved", 0),
                "skipped":  result.get("skipped", 0),
                "briefing": briefing.get("briefing_date") if briefing else None,
            }

        return success({
            "fetched":  result.get("fetched", 0),
            "saved":    result.get("saved", 0),
            "skipped":  result.get("skipped", 0),
        }, message="Run complete.")

    except Exception as e:
        return error(f"Run failed: {str(e)}", 500)


# ═════════════════════════════════════════════════════════════════
#  HEALTH CHECK
# ═════════════════════════════════════════════════════════════════

@app.route("/health", methods=["GET"])
def health_check():
    """
    GET /health

    Check whether the application and database are running.

    Response 200:
    {
        "error": false,
        "message": "OK",
        "data": {
            "status": "healthy",
            "database": "tech_news",
            "collections": { "news": 379, "daily_briefings": 1 },
            "server_time": "2026-10-18T06:00:00+00:00",
            "api_version": "1.0"
        }
    }

    Use this endpoint in Postman first — if it returns healthy,
    everything is working correctly.
    """
    db_health = check_database_health()

    response_data = {
        **db_health,                    # Spread all DB health fields in
        "server_time": datetime.now(timezone.utc).isoformat(),
        "api_version": "1.0"
    }

    # HTTP 200 if healthy, 503 (Service Unavailable) if not.
    status_code = 200 if db_health.get("status") == "healthy" else 503
    return jsonify(create_success_response(response_data, "OK")), status_code


# ═════════════════════════════════════════════════════════════════
#  NEWS ENDPOINTS
# ═════════════════════════════════════════════════════════════════

@app.route("/news", methods=["GET"])
def get_news():
    """
    GET /news
    GET /news?limit=20

    Return the latest news articles.

    Query parameters:
        limit (int): Max articles to return. Default 50, max 100.

    Response 200:
    {
        "error": false,
        "message": "OK",
        "total": 50,
        "data": [ { article }, { article }, ... ]
    }

    Flask concept — request.args:
        URL query parameters (the ?key=value part) are available
        in request.args as a dictionary.
        request.args.get("limit", 50) reads "limit" from the URL,
        defaulting to 50 if not provided.
    """
    try:
        # Read the 'limit' query parameter.
        # .get() returns the default if the param is missing.
        limit = request.args.get("limit", 50, type=int)

        # Clamp to a safe range — never return more than 100.
        limit = max(1, min(limit, 100))

        articles = get_latest_news(limit=limit)
        return success(convert_articles(articles))

    except Exception as e:
        return error("Could not retrieve news.", 500)


@app.route("/news/search", methods=["GET"])
def search_news_endpoint():
    """
    GET /news/search?keyword=python
    GET /news/search?keyword=openai&limit=10

    Search news articles by keyword.
    Searches title, description, and category fields.

    Query parameters:
        keyword (str): Required. The search term.
        limit   (int): Optional. Max results. Default 20.

    Response 200:
    {
        "error": false,
        "message": "Found 5 articles matching 'python'",
        "total": 5,
        "data": [ { article }, ... ]
    }

    Response 400:
    {
        "error": true,
        "message": "keyword parameter is required.",
        "code": 400
    }

    IMPORTANT: This route must be defined BEFORE /news/<id>
    because Flask matches routes top to bottom.
    If /news/<id> came first, "search" would be treated as an id.
    """
    keyword = request.args.get("keyword", "").strip()

    if not keyword:
        return error("keyword parameter is required. Use: /news/search?keyword=python", 400)

    if len(keyword) < 2:
        return error("keyword must be at least 2 characters.", 400)

    try:
        limit = request.args.get("limit", 20, type=int)
        limit = max(1, min(limit, 100))

        articles = search_news(keyword, limit=limit)
        return success(
            convert_articles(articles),
            message=f"Found {len(articles)} articles matching '{keyword}'"
        )

    except Exception as e:
        return error("Search failed.", 500)


@app.route("/news/category/<string:category>", methods=["GET"])
def get_news_by_cat(category):
    """
    GET /news/category/AI
    GET /news/category/Quantum%20Computing
    GET /news/category/Cybersecurity?limit=10

    Return articles filtered by category.

    URL parameter:
        category (str): Category name. Must be one of VALID_CATEGORIES.

    Query parameters:
        limit (int): Max articles. Default 20.

    Response 400 (invalid category):
    {
        "error": true,
        "message": "Invalid category. Valid categories: ...",
        "code": 400
    }

    Flask concept — URL parameters:
        <string:category> in the route captures whatever appears
        at that position in the URL as a Python string variable
        named 'category'. It's passed to the function automatically.
    """
    # Validate category — only accept known categories.
    # We compare case-insensitively to handle URL encoding differences.
    matched_category = None
    for valid in VALID_CATEGORIES:
        if valid.lower() == category.lower():
            matched_category = valid
            break

    if not matched_category:
        valid_list = ", ".join(VALID_CATEGORIES)
        return error(
            f"Invalid category '{category}'. "
            f"Valid categories: {valid_list}",
            400
        )

    try:
        limit = request.args.get("limit", 20, type=int)
        limit = max(1, min(limit, 100))

        articles = get_news_by_category(matched_category, limit=limit)
        return success(
            convert_articles(articles),
            message=f"Found {len(articles)} articles in '{matched_category}'"
        )

    except Exception as e:
        return error("Could not retrieve news by category.", 500)


@app.route("/news/<string:article_id>", methods=["GET"])
def get_single_article(article_id):
    """
    GET /news/507f1f77bcf86cd799439011

    Return a single article by its MongoDB _id.

    URL parameter:
        article_id (str): The MongoDB ObjectId as a string.

    Response 200:
    {
        "error": false,
        "message": "OK",
        "data": { article }
    }

    Response 404:
    {
        "error": true,
        "message": "Article not found.",
        "code": 404
    }

    HTTP concept — 404 Not Found:
        Used when a specific resource the client asked for
        does not exist. Different from 400 (bad request format)
        and 500 (server broke).
    """
    if not article_id or len(article_id) != 24:
        return error(
            "Invalid article ID format. MongoDB IDs are 24-character hex strings.",
            400
        )

    try:
        article = get_article_by_id(article_id)

        if not article:
            return error(f"Article with id '{article_id}' not found.", 404)

        return success(article_to_dict(article))

    except Exception as e:
        return error("Could not retrieve article.", 500)


# ═════════════════════════════════════════════════════════════════
#  BRIEFING ENDPOINTS
# ═════════════════════════════════════════════════════════════════

@app.route("/briefings", methods=["GET"])
def get_briefings():
    """
    GET /briefings
    GET /briefings?limit=10

    Return previous daily briefings (summary view, no full text).

    Query parameters:
        limit (int): Max briefings to return. Default 30.

    Response 200:
    {
        "error": false,
        "total": 5,
        "data": [
            {
                "briefing_date": "2026-10-18",
                "total_news": 379,
                "categories": { "AI": 52, ... }
            },
            ...
        ]
    }
    """
    try:
        limit = request.args.get("limit", 30, type=int)
        limit = max(1, min(limit, 90))

        briefings = get_all_briefings(limit=limit)

        # Return a summary view — exclude the large briefing_text
        # and top_news array to keep the response compact.
        summary_list = []
        for b in briefings:
            b_dict = briefing_to_dict(b)
            if b_dict:
                summary = {
                    "_id":           b_dict.get("_id"),
                    "briefing_date": b_dict.get("briefing_date"),
                    "generated_at":  b_dict.get("generated_at"),
                    "total_news":    b_dict.get("total_news"),
                    "categories":    b_dict.get("categories"),
                    "top_news_count": len(b_dict.get("top_news", []))
                }
                summary_list.append(summary)

        return success(summary_list)

    except Exception as e:
        return error("Could not retrieve briefings.", 500)


@app.route("/briefings/<string:date_str>", methods=["GET"])
def get_briefing(date_str):
    """
    GET /briefings/2026-10-18

    Return the full daily briefing for a specific date.

    URL parameter:
        date_str (str): Date in YYYY-MM-DD format.

    Response 200:
    {
        "error": false,
        "data": {
            "briefing_date": "2026-10-18",
            "briefing_text": "...",
            "top_news": [ ... ],
            "total_news": 379,
            "categories": { ... }
        }
    }

    Response 400 (invalid date format):
    {
        "error": true,
        "message": "Invalid date format. Use YYYY-MM-DD."
    }

    Response 404 (no briefing for that date):
    {
        "error": true,
        "message": "No briefing found for 2026-10-19."
    }
    """
    # Validate date format before querying MongoDB.
    # This prevents garbage queries and gives a helpful error message.
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return error(
            f"Invalid date format '{date_str}'. Use YYYY-MM-DD (e.g. 2026-10-18).",
            400
        )

    try:
        briefing = get_briefing_by_date(date_str)

        if not briefing:
            return error(f"No briefing found for {date_str}.", 404)

        return success(briefing_to_dict(briefing))

    except Exception as e:
        return error("Could not retrieve briefing.", 500)


# ═════════════════════════════════════════════════════════════════
#  ACTION ENDPOINTS (POST)
# ═════════════════════════════════════════════════════════════════

@app.route("/fetch", methods=["POST"])
def trigger_fetch():
    """
    POST /fetch

    Manually trigger a news fetch and store cycle.
    Useful for testing without waiting for the scheduler.

    No request body required.

    Response 200:
    {
        "error": false,
        "message": "News fetch complete.",
        "data": {
            "fetched": 366,
            "saved": 13,
            "skipped": 353,
            "errors": 0
        }
    }

    HTTP concept — POST vs GET:
        GET  → retrieve data, no side effects, can be called repeatedly.
        POST → trigger an action that changes state (fetches + saves data).
        Fetching and storing news changes the database, so POST is correct.
    """
    try:
        print("\nManual fetch triggered via API...")
        result = fetch_and_store_news()

        # Don't return the full articles list — too large.
        summary = {
            "fetched": result["fetched"],
            "saved":   result["saved"],
            "skipped": result["skipped"],
            "errors":  result["errors"]
        }

        return success(summary, message="News fetch complete.")

    except Exception as e:
        return error("News fetch failed.", 500)


@app.route("/briefing/generate", methods=["POST"])
def trigger_briefing():
    """
    POST /briefing/generate

    Manually generate today's daily briefing from stored articles.

    No request body required.

    Response 200:
    {
        "error": false,
        "message": "Briefing generated.",
        "data": {
            "briefing_date": "2026-10-18",
            "total_news": 379,
            "top_news_count": 13
        }
    }

    Response 404 (no articles to build from):
    {
        "error": true,
        "message": "No articles found for today. Run POST /fetch first."
    }
    """
    try:
        print("\nManual briefing generation triggered via API...")
        briefing = generate_daily_briefing()

        if not briefing:
            return error(
                "No articles found for today. Run POST /fetch first.",
                404
            )

        summary = {
            "briefing_date":  briefing.get("briefing_date"),
            "total_news":     briefing.get("total_news"),
            "top_news_count": len(briefing.get("top_news", []))
        }

        return success(summary, message="Briefing generated.")

    except Exception as e:
        return error("Briefing generation failed.", 500)


# ═════════════════════════════════════════════════════════════════
#  ERROR HANDLERS
# ═════════════════════════════════════════════════════════════════

@app.errorhandler(404)
def not_found(e):
    """
    Handle requests to routes that don't exist.

    Flask concept — @app.errorhandler:
        Registers a function to handle a specific HTTP error.
        Without this, Flask returns an HTML error page.
        We return JSON instead so the API is consistent.

    Example: GET /nonexistent → 404 JSON response
    """
    return jsonify(create_error_response(
        f"The endpoint '{request.path}' does not exist.",
        404
    )), 404


@app.errorhandler(405)
def method_not_allowed(e):
    """
    Handle wrong HTTP methods — e.g. POST to a GET-only endpoint.

    Example: POST /news → 405 Method Not Allowed
    """
    return jsonify(create_error_response(
        f"Method '{request.method}' is not allowed on '{request.path}'. "
        f"Check the API documentation.",
        405
    )), 405


@app.errorhandler(500)
def internal_error(e):
    """
    Handle unexpected server errors.
    Never expose internal details in the response.
    """
    return jsonify(create_error_response(
        "An internal server error occurred.",
        500
    )), 500


# ═════════════════════════════════════════════════════════════════
#  STARTUP VALIDATION & ENTRY POINT
# ═════════════════════════════════════════════════════════════════

def print_routes():
    """
    Print all registered API routes on startup.
    Helpful for developers to see what's available.
    """
    print("\nRegistered API endpoints:")
    print("-" * 45)

    # Flask stores all routes in app.url_map.
    rules = sorted(app.url_map.iter_rules(), key=lambda r: r.rule)
    for rule in rules:
        if rule.endpoint == "static":
            continue
        methods = ", ".join(sorted(rule.methods - {"HEAD", "OPTIONS"}))
        print(f"  {methods:<8} {rule.rule}")

    print("-" * 45)
    print(f"  Server: http://localhost:{FLASK_PORT}")
    print(f"  Health: http://localhost:{FLASK_PORT}/health")
    print("-" * 45 + "\n")


if __name__ == "__main__":
    print("=" * 50)
    print("  DAILY GLOBAL TECH NEWS — API SERVER")
    print("=" * 50)

    # ── VALIDATE CONFIGURATION ────────────────────────────────────
    config_errors = validate_config()
    if config_errors:
        print("\nConfiguration warnings:")
        for e in config_errors:
            print(f"  [WARNING] {e}")

    # ── CONNECT TO MONGODB ────────────────────────────────────────
    print("\nConnecting to MongoDB...")
    connected = connect_to_mongodb()
    if not connected:
        print("WARNING: Could not connect to MongoDB.")
        print("The server will start but database endpoints will return errors.")
        print("Make sure MongoDB is running: mongod")

    # ── PRINT AVAILABLE ROUTES ────────────────────────────────────
    print_routes()

    # ── START FLASK ───────────────────────────────────────────────
    # debug=True  → auto-reloads on code changes (development only)
    # debug=False → stable, no auto-reload (production)
    #
    # use_reloader=False prevents Flask from starting twice
    # when debug=True, which would cause duplicate connections.
    is_debug = FLASK_ENV == "development"

    print(f"Starting Flask server on port {FLASK_PORT}...")
    print("Press Ctrl+C to stop.\n")

    app.run(
        host="0.0.0.0",          # Accept connections from any network interface
        port=FLASK_PORT,
        debug=is_debug,
        use_reloader=False        # Prevent double startup in debug mode
    )
