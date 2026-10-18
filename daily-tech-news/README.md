# Daily Global Tech News Scheduler

A Python application that automatically collects, categorizes, stores, and
generates a daily technology news briefing using MongoDB and public news APIs.

Built as a learning project for BCA students. Every concept is explained
in the code comments.

---

## What It Does

Every morning at 6:00 AM the application:

1. Calls NewsAPI with 9 targeted technology search queries
2. Categorizes each article using keyword matching
3. Removes duplicate articles (within batch and across days)
4. Saves new articles to MongoDB
5. Scores each article for importance (0-100 points)
6. Selects the top story per category
7. Generates a structured 10-minute daily briefing
8. Saves the briefing to MongoDB
9. Prints the briefing to the terminal

A REST API exposes all collected data for querying and searching.

---

## Technology Stack

| Technology     | Version  | Purpose                                      |
|----------------|----------|----------------------------------------------|
| Python         | 3.10+    | Core language                                |
| MongoDB        | 7.x      | Database for articles and briefings          |
| PyMongo        | 4.6.1    | Python driver for MongoDB                    |
| Flask          | 3.0.2    | REST API framework                           |
| Requests       | 2.31.0   | HTTP calls to NewsAPI                        |
| APScheduler    | 3.10.4   | Runs the daily job automatically             |
| python-dotenv  | 1.0.1    | Reads .env file into environment variables   |
| NewsAPI        | free     | Source of technology news articles           |

---

## Project Structure

```
daily-tech-news/
|
|-- main.py              Flask REST API server (entry point)
|-- config.py            Reads all settings from .env
|-- database.py          MongoDB connection and helper functions
|-- models.py            Data structure definitions
|-- news_service.py      Fetches and categorizes news from API
|-- briefing_service.py  Scores, selects, and formats the briefing
|-- scheduler.py         Runs the pipeline automatically at 6 AM
|-- requirements.txt     Python package list
|-- .env                 Your secrets (never commit to GitHub)
|-- .env.example         Template showing required variables
|-- .gitignore           Files Git will never track
`-- README.md            This file
```

### What Each File Is Responsible For

```
config.py
    Reads .env and exposes constants.
    Contains CATEGORY_KEYWORDS dictionary.
    All other files import settings from here.

database.py
    One MongoDB connection shared across the app.
    Functions: connect, save, find, search, health check.
    No other file creates a MongoClient.

models.py
    create_news_article()     -- blueprint for one article
    create_daily_briefing()   -- blueprint for one briefing
    article_to_dict()         -- converts dates for JSON responses
    create_error_response()   -- consistent API error format
    create_success_response() -- consistent API success format

news_service.py
    fetch_news()              -- calls NewsAPI, returns clean article list
    fetch_and_store_news()    -- fetch + save to MongoDB
    _categorize_article()     -- keyword matching logic

briefing_service.py
    score_articles()          -- adds importance score to each article
    select_top_news()         -- picks best article per category
    format_briefing()         -- builds readable briefing text
    generate_daily_briefing() -- runs the full pipeline

scheduler.py
    daily_job()               -- the full pipeline in one function
    start_scheduler()         -- starts APScheduler with cron trigger
    run_once()                -- runs pipeline once and exits

main.py
    Flask app with all REST API endpoints.
    Calls database/service functions.
    Never contains business logic directly.
```

---

## Prerequisites

Install these before starting:

- Python 3.10 or higher — https://python.org
- MongoDB Community Edition — https://www.mongodb.com/try/download/community
- MongoDB Compass (GUI) — https://www.mongodb.com/try/download/compass
- Postman — https://www.postman.com/downloads
- VS Code — https://code.visualstudio.com
- A free NewsAPI key — https://newsapi.org (register, takes 2 minutes)

---

## Installation

### 1. Clone or download the project

```
git clone <your-repo-url>
cd daily-tech-news
```

### 2. Install Python packages

```
pip install -r requirements.txt
```

### 3. Set up environment variables

Copy the example file and fill in your values:

```
copy .env.example .env
```

Open `.env` and replace the placeholder values:

```
NEWS_API_KEY=your_real_key_from_newsapi_org
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=tech_news
NEWS_SCHEDULE_HOUR=6
NEWS_SCHEDULE_MINUTE=0
FLASK_PORT=5000
FLASK_ENV=development
NEWS_FETCH_PAGE_SIZE=50
BRIEFING_TOP_ARTICLES=15
```

### 4. Start MongoDB

Make sure MongoDB is running locally before starting the app.

Windows:

```
mongod
```

Or start it from the Windows Services panel if installed as a service.

### 5. Verify your setup

```
python -c "from config import validate_config; print(validate_config())"
```

Empty list `[]` means all configuration is correct.

---

## Running the Application

### Option A: REST API only (most common during development)

```
python main.py
```

Server starts at http://localhost:5000

Test it: http://localhost:5000/health

### Option B: Run the full pipeline once and exit

```
python scheduler.py once
```

Fetches news, stores in MongoDB, generates briefing, prints to terminal.
Does not start the web server.

### Option C: Start the scheduler (runs at 6 AM every day)

```
python scheduler.py
```

Runs the pipeline immediately, then waits for 6:00 AM every day.
Keep this running in the background on your server or development machine.

### Option D: Start scheduler without immediate run

```
python scheduler.py norun
```

Registers the 6 AM job and waits. Useful when you have already run
the pipeline today and do not want to run it again.

---

## MongoDB Setup

MongoDB creates the database and collections automatically on first use.
You do not need to create them manually.

### Database name: `tech_news`

### Collections

#### `news`

Stores every article collected from the API.

```json
{
    "_id":          "ObjectId (auto-generated)",
    "title":        "OpenAI Releases New AI Agent Framework",
    "description":  "OpenAI has released a new framework...",
    "url":          "https://techcrunch.com/...",
    "source":       "TechCrunch",
    "author":       "Jane Smith",
    "category":     "Agentic AI",
    "published_at": "2026-10-18T06:00:00+00:00",
    "collected_at": "2026-10-18T06:29:00+00:00",
    "score":        85
}
```

#### `daily_briefings`

Stores one briefing document per day.

```json
{
    "_id":           "ObjectId (auto-generated)",
    "briefing_date": "2026-10-18",
    "generated_at":  "2026-10-18T06:30:00+00:00",
    "total_news":    366,
    "categories": {
        "AI":                 51,
        "Agentic AI":         45,
        "Quantum Computing":  8,
        "Cloud Computing":    31,
        "Cybersecurity":      43,
        "Programming":        59,
        "Developer Tools":    61,
        "Startups":           30,
        "Technology Companies": 38
    },
    "top_news":      [ { ...article... }, { ...article... } ],
    "briefing_text": "=== DAILY GLOBAL TECH BRIEFING ..."
}
```

### Indexes

Created automatically on first run:

| Collection       | Field          | Type   | Purpose                        |
|------------------|----------------|--------|--------------------------------|
| news             | url            | Unique | Prevents duplicate articles    |
| news             | published_at   | Normal | Fast date sorting              |
| news             | category       | Normal | Fast category filtering        |
| daily_briefings  | briefing_date  | Unique | One briefing per day only      |

### Inspecting Data in MongoDB Compass

1. Open MongoDB Compass
2. Connect to: `mongodb://localhost:27017`
3. Open database: `tech_news`
4. Click `news` to see all articles
5. Use the filter bar to query:

```json
{ "category": "AI" }
{ "score": { "$gte": 60 } }
{ "source": "TechCrunch" }
{ "published_at": { "$gte": { "$date": "2026-10-18T00:00:00Z" } } }
```

---

## News Categories

Articles are automatically categorized using keyword matching.

| Category             | Example Keywords                              |
|----------------------|-----------------------------------------------|
| Agentic AI           | AI agent, autonomous agent, multi-agent       |
| AI                   | machine learning, LLM, OpenAI, GPT, Anthropic |
| Quantum Computing    | qubit, quantum processor, quantum supremacy   |
| Cloud Computing      | AWS, Azure, Google Cloud, serverless          |
| Cybersecurity        | data breach, ransomware, zero-day, hacking    |
| Programming          | Python, JavaScript, open source, GitHub       |
| Developer Tools      | VS Code, DevOps, CI/CD, Docker                |
| Startups             | funding, Series A, venture capital, unicorn   |
| Technology Companies | Apple, Google, Microsoft, Meta, Nvidia        |
| Other Technology     | Fallback for articles that match nothing else |

Categories are checked in this order. The first match wins.
Agentic AI is checked before AI so agent articles are not
mis-labelled as plain AI.

To add a keyword, open `config.py` and add it to the relevant
list in `CATEGORY_KEYWORDS`.

---

## Article Scoring

Every article receives an importance score (0-100) before briefing selection.

| Signal                                    | Points |
|-------------------------------------------|--------|
| High-priority category (AI, Agentic AI,   |        |
| Quantum Computing, Cybersecurity)         | +20    |
| Medium-priority category (Cloud,          |        |
| Programming, Developer Tools)             | +10    |
| Lower-priority category (Startups,        |        |
| Tech Companies, Other)                    | +5     |
| Major company name in title               | +15    |
| Urgency word in title (launches, breaks)  | +10    |
| Description longer than 100 characters   | +10    |
| Impact word in description (first,        |        |
| record, breakthrough, billion)            | +10    |
| Published today (within 24 hours)        | +15    |
| Published this week                       | +5     |
| Good title length (30-120 characters)    | +5     |

Minimum score to appear in briefing: 20 points.

---

## API Documentation

Base URL: `http://localhost:5000`

All responses follow this format:

Success:
```json
{
    "error":   false,
    "message": "OK",
    "total":   50,
    "data":    [ ... ]
}
```

Error:
```json
{
    "error":   true,
    "message": "Article not found.",
    "code":    404
}
```

---

### GET /health

Check application and database status.

```
GET http://localhost:5000/health
```

Response 200:
```json
{
    "error": false,
    "message": "OK",
    "data": {
        "status": "healthy",
        "database": "tech_news",
        "collections": {
            "news": 379,
            "daily_briefings": 1
        },
        "server_time": "2026-10-18T06:00:00+00:00",
        "api_version": "1.0"
    }
}
```

---

### GET /news

Return the latest articles.

```
GET http://localhost:5000/news
GET http://localhost:5000/news?limit=10
```

Query parameters:

| Parameter | Type | Default | Description         |
|-----------|------|---------|---------------------|
| limit     | int  | 50      | Max articles (1-100) |

Response 200:
```json
{
    "error": false,
    "total": 50,
    "data": [
        {
            "_id":          "6ad4684ce8c68d86b0b18f12",
            "title":        "OpenAI Sued By Eight U.S. States",
            "description":  "A bipartisan group of eight states sued OpenAI...",
            "url":          "https://...",
            "source":       "Naturalnews.com",
            "author":       "Chase Codewell",
            "category":     "AI",
            "published_at": "2026-10-17T06:00:00",
            "collected_at": "2026-10-18T06:33:48.293000",
            "score":        55
        }
    ]
}
```

---

### GET /news/\<id\>

Return a single article by MongoDB ID.

```
GET http://localhost:5000/news/6ad4684ce8c68d86b0b18f12
```

Response 200: single article object
Response 400: invalid ID format
Response 404: article not found

---

### GET /news/category/\<category\>

Return articles filtered by category.

```
GET http://localhost:5000/news/category/AI
GET http://localhost:5000/news/category/Quantum%20Computing
GET http://localhost:5000/news/category/Cybersecurity?limit=10
```

Valid categories:
`AI`, `Agentic AI`, `Quantum Computing`, `Cloud Computing`,
`Cybersecurity`, `Programming`, `Developer Tools`,
`Startups`, `Technology Companies`, `Other Technology`

Response 400 if category is not in the valid list.

---

### GET /news/search

Search articles by keyword across title, description, and category.

```
GET http://localhost:5000/news/search?keyword=python
GET http://localhost:5000/news/search?keyword=openai&limit=5
```

Query parameters:

| Parameter | Type   | Required | Description                |
|-----------|--------|----------|----------------------------|
| keyword   | string | Yes      | Search term (min 2 chars)  |
| limit     | int    | No       | Max results (default 20)   |

Response 400 if keyword is missing or too short.

---

### GET /briefings

Return a summary list of all past daily briefings.

```
GET http://localhost:5000/briefings
GET http://localhost:5000/briefings?limit=7
```

Returns summary only (no full text, no article list).

---

### GET /briefings/\<date\>

Return the full briefing for a specific date.

```
GET http://localhost:5000/briefings/2026-10-18
```

Date format: `YYYY-MM-DD`

Response 400 if date format is wrong.
Response 404 if no briefing exists for that date.

---

### POST /fetch

Manually trigger a news fetch and store cycle.

```
POST http://localhost:5000/fetch
```

No request body required.

Response 200:
```json
{
    "error": false,
    "message": "News fetch complete.",
    "data": {
        "fetched": 366,
        "saved":   13,
        "skipped": 353,
        "errors":  0
    }
}
```

---

### POST /briefing/generate

Manually generate today's daily briefing from stored articles.

```
POST http://localhost:5000/briefing/generate
```

No request body required.
Run `POST /fetch` first if no articles exist for today.

Response 200:
```json
{
    "error": false,
    "message": "Briefing generated.",
    "data": {
        "briefing_date":  "2026-10-18",
        "total_news":     379,
        "top_news_count": 13
    }
}
```

---

## Scheduler Configuration

The schedule is controlled entirely by `.env` variables.

```
NEWS_SCHEDULE_HOUR=6
NEWS_SCHEDULE_MINUTE=0
```

This runs the job at 06:00 UTC every day.

To change to 8:30 AM:
```
NEWS_SCHEDULE_HOUR=8
NEWS_SCHEDULE_MINUTE=30
```

The scheduler reads these values at startup via `config.py`.
No code changes needed to update the schedule.

### Scheduler Modes

```
python scheduler.py          Start + run immediately
python scheduler.py once     Run pipeline once and exit
python scheduler.py norun    Start scheduler, wait for schedule
```

---

## Environment Variables Reference

| Variable              | Required | Default                      | Description                      |
|-----------------------|----------|------------------------------|----------------------------------|
| NEWS_API_KEY          | Yes      | (none)                       | NewsAPI.org API key              |
| NEWS_API_BASE_URL     | No       | https://newsapi.org/v2       | NewsAPI base URL                 |
| MONGO_URI             | Yes      | mongodb://localhost:27017    | MongoDB connection string        |
| MONGO_DB_NAME         | No       | tech_news                    | Database name                    |
| NEWS_SCHEDULE_HOUR    | No       | 6                            | Hour to run daily job (0-23)     |
| NEWS_SCHEDULE_MINUTE  | No       | 0                            | Minute to run daily job (0-59)   |
| FLASK_PORT            | No       | 5000                         | REST API server port             |
| FLASK_ENV             | No       | development                  | development or production        |
| NEWS_FETCH_PAGE_SIZE  | No       | 50                           | Articles per API query (max 100) |
| BRIEFING_TOP_ARTICLES | No       | 15                           | Max articles in daily briefing   |

---

## Security Notes

- Never commit `.env` to GitHub. It is listed in `.gitignore`.
- Never print or log the value of `NEWS_API_KEY`.
- Error responses never expose internal error messages to the client.
- The app validates input (category names, date formats, ID lengths)
  before passing values to MongoDB.
- MongoDB queries use PyMongo's query objects, not string concatenation,
  which prevents injection attacks.

---

## Common Errors

### "NEWS_API_KEY is missing"
Open `.env` and paste your real API key from newsapi.org.

### "Could not connect to MongoDB"
MongoDB is not running. Start it with `mongod` in a separate terminal.

### "API rate limit exceeded"
Free tier allows 100 requests/day. The app makes 9 requests per run.
If you run the pipeline more than 11 times in one day you will hit the limit.

### "Briefing already exists for today"
Normal. The unique index prevents duplicate briefings.
The briefing still generates and prints — it just is not saved again.

### "charmap codec can't encode character"
A news article title contains a special Unicode character that the
Windows terminal cannot display. This is a display issue only —
the data is stored correctly in MongoDB.

---

## Data Flow Diagram

```
newsapi.org (internet)
      |
      | HTTP GET (9 queries)
      | requests library
      v
news_service.py
      | parse JSON
      | _categorize_article()  <--- CATEGORY_KEYWORDS (config.py)
      | _deduplicate_articles()
      v
database.py
      | save_many_articles()
      | unique index blocks duplicates
      v
MongoDB: tech_news.news (one document per article)
      |
      v
briefing_service.py
      | score_articles()
      | select_top_news()
      | format_briefing()
      v
MongoDB: tech_news.daily_briefings (one document per day)
      |
      v
Terminal output
      |
      v
main.py (Flask REST API)
      |
      | HTTP JSON responses
      v
Postman / Browser / Frontend
```

---

## GitHub Setup

### Initialize repository

```
git init
git add .
git commit -m "Initial commit: Daily Global Tech News Scheduler"
```

### Check what is staged (important before first commit)

```
git status
```

Make sure `.env` is NOT in the list. If it appears, your `.gitignore`
is not working. Fix it before committing.

### Verify .gitignore is working

```
git check-ignore -v .env
```

Should print: `.gitignore:4:.env   .env`

### Push to GitHub

```
git remote add origin https://github.com/yourusername/daily-tech-news.git
git push -u origin main
```

---

## Final Demonstration Checklist

Use this checklist to walk someone through the complete project.

### Part 1: Start the application

```
python main.py
```

Show: server starts, all endpoints listed, MongoDB connected.

### Part 2: Test health check in Postman

```
GET http://localhost:5000/health
```

Show: status healthy, database name, article count.

### Part 3: Trigger a news fetch

```
POST http://localhost:5000/fetch
```

Show: articles fetched, saved count, skipped duplicates.

### Part 4: Open MongoDB Compass

- Connect to mongodb://localhost:27017
- Open tech_news database
- Click the news collection
- Show document structure (all 9 fields)
- Apply filter: `{ "category": "AI" }`
- Click Indexes tab — show unique_article_url index

### Part 5: Query the API in Postman

```
GET http://localhost:5000/news?limit=5
GET http://localhost:5000/news/category/AI
GET http://localhost:5000/news/search?keyword=openai
GET http://localhost:5000/news/search?keyword=quantum
```

### Part 6: Generate the briefing

```
POST http://localhost:5000/briefing/generate
```

Then retrieve it:

```
GET http://localhost:5000/briefings/2026-10-18
```

Show the briefing_text field.

### Part 7: Show error handling

```
GET http://localhost:5000/news/category/Space
GET http://localhost:5000/briefings/18-10-2026
GET http://localhost:5000/news/badid
GET http://localhost:5000/nonexistent
```

Each returns a clean JSON error with the correct HTTP status code.

### Part 8: Show the scheduler

In a separate terminal:

```
python scheduler.py once
```

Walk through the output line by line:
- MongoDB connection
- 9 API queries firing
- Article processing and deduplication
- Save results (saved vs skipped)
- Scoring and selection
- Briefing generation and print

### Part 9: Explain the data flow

Without looking at code, explain:

1. How does a news article get from newsapi.org into MongoDB?
2. How does the app decide an article belongs to "Agentic AI" vs "AI"?
3. How does the duplicate prevention work? (Two levels)
4. How does the scoring system decide what goes in the briefing?
5. How does `scheduler.py` know what time to run?
6. What happens if NewsAPI is down?
7. What happens if MongoDB is down?
8. Why does the `.env` file never go to GitHub?

---

## Learning Outcomes

After completing this project you understand:

**Python**
- Variables, data types, lists, dictionaries, sets, tuples
- Functions with parameters and return values
- for loops and conditional statements
- Exception handling with try/except/finally
- Modules and imports
- Working with JSON and HTTP APIs
- Environment variables and the dotenv pattern
- Date and time handling with datetime
- Scheduling with APScheduler
- Building REST APIs with Flask
- The requests library for HTTP calls

**MongoDB**
- Database, collection, document model
- ObjectId and document identity
- insert_one, find, find_one, update_one
- Query operators: $gte, $regex, $or, $set
- Indexes and unique indexes
- Using MongoDB Compass to inspect data

**Software Engineering Practices**
- Separation of concerns (one responsibility per file)
- Environment-based configuration
- Defensive programming and error handling
- Consistent API response structure
- Preventing duplicate data at two levels
- Keeping secrets out of version control

---

## Author

Built step by step as a BCA learning project.
Each step includes: what, why, concepts, data flow, how to test,
common errors, and 5 interview questions.


---

## Frequently Asked Questions

---

### 1. Complete Project Flow

This is the full journey from code startup to reading your briefing.

```
START APPLICATION
      |
      v
main.py starts
  - Reads .env file (API key, MongoDB URI, schedule time)
  - Connects to MongoDB (creates tech_news database if new)
  - Creates indexes on the news collection
  - Registers all Flask REST API routes
  - Starts the Flask web server on port 5000
  - Starts the BackgroundScheduler thread
      |
      v
[Every day at scheduled time OR when triggered manually]
      |
      v
STEP 1 — news_service.py: FETCH
  - Sends 9 HTTP GET requests to NewsAPI
  - Each request uses a different tech keyword query
    (AI, Agentic AI, Quantum, Cloud, Cybersecurity, etc.)
  - Receives JSON responses with article lists
  - Parses each article: title, description, url, source, author, date
      |
      v
STEP 2 — news_service.py: CATEGORIZE
  - For each article, checks title + description against CATEGORY_KEYWORDS
  - Keywords are defined in config.py
  - First matching category wins (Agentic AI checked before AI)
  - Uncategorized articles go to "Other Technology"
      |
      v
STEP 3 — news_service.py: DEDUPLICATE (batch level)
  - Uses a Python set to track URLs seen in this batch
  - If same URL appears in two different queries, keeps only one copy
      |
      v
STEP 4 — database.py: SAVE
  - Calls save_many_articles() for every clean article
  - MongoDB unique index on 'url' field blocks cross-session duplicates
  - Result: saved (new), skipped (duplicate), errors (failed)
      |
      v
STEP 5 — briefing_service.py: SCORE
  - Every stored article receives an importance score (0-100)
  - Score is based on: category priority, company names, urgency words,
    description length, impact words, recency, title quality
  - Score is written back to MongoDB ($set operator)
      |
      v
STEP 6 — briefing_service.py: SELECT
  - Articles sorted by score, highest first
  - Best article(s) per category selected
  - High-priority categories (AI, Agentic AI, Quantum, Cybersecurity)
    get up to 2 articles each
  - Minimum score threshold filters out low-quality articles
      |
      v
STEP 7 — briefing_service.py: FORMAT
  - Selected articles formatted into readable sections
  - Each section: Headline, Summary, Why it matters, Source, URL
  - Learning of the Day added based on dominant category
  - Career Opportunity section added
      |
      v
STEP 8 — database.py: SAVE BRIEFING
  - Complete briefing stored in daily_briefings collection
  - Unique index on briefing_date prevents duplicate briefings
      |
      v
STEP 9 — OUTPUT
  - Briefing printed to terminal
  - Available via REST API: GET /briefings/YYYY-MM-DD
  - Visible in the web dashboard at /ui
```

---

### 2. Why a Scheduler — and How It Triggers Your Python Function

**Why you need a scheduler:**

Without a scheduler, you would have to manually run the Python script every
single day. The whole point of this application is automation — it should
work even while you sleep. A scheduler is the mechanism that makes that
possible.

**Two schedulers in this project:**

`scheduler.py` uses `BlockingScheduler` from APScheduler.
This runs as a standalone process using a cron trigger.

`main.py` uses `BackgroundScheduler` from APScheduler.
This runs inside the Flask process as a background thread.

**How APScheduler triggers your Python function — step by step:**

```python
# 1. You register a job with a trigger
scheduler.add_job(
    func=daily_job,                      # The Python function to call
    trigger=CronTrigger(hour=6, minute=0), # When to call it
    id="daily_news_job"
)

# 2. APScheduler runs an internal loop in the background
# Every second it checks: "Has the trigger time arrived?"

# 3. When the clock reaches 06:00:00 UTC
# APScheduler calls daily_job() automatically

# 4. daily_job() runs the full pipeline:
#    fetch → categorize → save → score → briefing → print
```

**CronTrigger vs IntervalTrigger:**

```
CronTrigger(hour=6, minute=0)
→ Fires once per day at exactly 6:00 AM
→ Like setting a daily alarm clock
→ Used in scheduler.py for the 6 AM job

IntervalTrigger(seconds=300)
→ Fires every 300 seconds (5 minutes)
→ Keeps firing repeatedly until stopped
→ Used in main.py for the UI scheduler feature
```

**The function is never "called" by you.** You register it once.
APScheduler stores the function reference and calls it when the time comes.
This is why we write `func=daily_job` without parentheses —
we are passing the function itself, not its return value.

---

### 3. What Happens If the Server Is Stopped Before the Scheduled Time

**Scenario:** Schedule is set for 7:00 AM. Application stops at 6:00 AM.

**Answer: The job does NOT run. It is silently missed.**

APScheduler is an in-process scheduler. It lives inside your Python process.
When the Python process stops, the scheduler stops with it.
There is no external clock or daemon keeping track.

```
06:00 AM — Application stopped (Ctrl+C or server crash)
           APScheduler thread dies
           No job is running or waiting

07:00 AM — Clock reaches scheduled time
           Nothing happens — no process is alive to fire the job

Next time you start the application:
  - APScheduler starts fresh
  - No record of the missed run
  - Next trigger is 7:00 AM tomorrow (or the next interval tick)
```

**What this means in practice:**

| Situation | Result |
|---|---|
| App running at 7:00 AM | Job fires normally |
| App stopped before 7:00 AM | Job missed, no data fetched |
| App restarted after 7:00 AM | Job runs at next scheduled time (tomorrow) |
| App restarted with `run_now=True` | Job runs immediately on startup |

**How to handle this in real applications:**

For production systems, you have three options:

1. **Use Linux cron** (external to Python) — `0 7 * * * python main.py once`
   The OS triggers Python regardless of whether the app was running.

2. **Use `misfire_grace_time`** — APScheduler's setting that says
   "if a job was missed by less than N seconds, run it anyway on restart".

3. **Always restart with `run_now=True`** — our `scheduler.py once` command
   manually runs the pipeline whenever you need it, regardless of schedule.

In this project, running `python scheduler.py once` is the safest way
to ensure the job runs even after a missed scheduled time.

---

### 4. How Duplicate News Is Prevented in MongoDB

Duplicate prevention works at **two separate levels** in this application.

**Level 1 — Python set (within one batch):**

When we make 9 API calls in one session, the same article can appear
in two different search results. For example, an OpenAI article might
appear in both the "AI" query and the "Technology Companies" query.

```python
# In news_service.py — _deduplicate_articles()

seen_urls = set()      # A Python set — stores only unique values
unique_articles = []

for article in articles:
    url = article.get("url", "")
    if url not in seen_urls:
        seen_urls.add(url)          # Mark this URL as seen
        unique_articles.append(article)  # Keep it
    # If url IS in seen_urls → silently skip it
```

A Python `set` checks membership in O(1) — constant time, extremely fast
even with thousands of articles.

**Level 2 — MongoDB unique index (across all sessions):**

Even after batch deduplication, an article from today might have been
fetched and saved yesterday. The Python set only covers the current batch,
not the entire database history.

MongoDB handles cross-session deduplication through a **unique index**:

```python
# In database.py — _create_indexes()

news_col.create_index(
    [("url", ASCENDING)],
    unique=True,              # This is the key setting
    name="unique_article_url"
)
```

When this index exists, MongoDB enforces a rule at the database level:
**no two documents in the news collection can have the same url value.**

```
INSERT article where url = "https://techcrunch.com/openai-article"
      |
      v
MongoDB checks the unique_article_url index
      |
      v
URL already exists in index?
  YES → Raise DuplicateKeyError → PyMongo catches it → article skipped
  NO  → Insert document → index updated → article saved
```

In Python we catch this error silently:

```python
# In database.py — save_news_article()

try:
    result = collection.insert_one(article)
    return str(result.inserted_id)   # Success
except DuplicateKeyError:
    return None                      # Already exists — not an error
```

**Why two levels instead of one?**

| Level | What it prevents | Why needed |
|---|---|---|
| Python set | Duplicates within the same batch | Faster — avoids unnecessary DB calls |
| MongoDB index | Duplicates across different days/sessions | Persistent — survives app restarts |

If you only had the Python set, re-running the app the next day would
insert all yesterday's articles again because the set is empty on restart.

If you only had the MongoDB index, every API call would try to insert
duplicates and fail — wasting time and database write operations.

Together they make duplicate prevention fast and reliable.

---

### 5. How News Travels: External API → Python → MongoDB → REST API → Postman

This is the complete data journey of one news article, from the internet
to your screen.

```
STAGE 1 — EXTERNAL API (NewsAPI.org)
─────────────────────────────────────
NewsAPI stores millions of news articles from sources worldwide.
It exposes a REST API that accepts keyword queries and returns JSON.

You send:
  GET https://newsapi.org/v2/everything
      ?q=artificial+intelligence
      &language=en
      &sortBy=publishedAt
      &pageSize=50
      &apiKey=YOUR_KEY

NewsAPI responds with:
  {
    "status": "ok",
    "totalResults": 4821,
    "articles": [
      {
        "title": "OpenAI launches new model",
        "description": "OpenAI has released...",
        "url": "https://techcrunch.com/...",
        "publishedAt": "2026-10-18T06:00:00Z",
        "source": { "name": "TechCrunch" },
        "author": "Jane Smith"
      },
      ...
    ]
  }
```

```
STAGE 2 — PYTHON (news_service.py)
────────────────────────────────────
The requests library makes the HTTP call.
Python parses the JSON response into a dictionary.

  response = requests.get(url, params=params, timeout=10)
  data = response.json()
  articles = data.get("articles", [])

For each raw article, _extract_article_fields() cleans it:
  - Removes articles with title "[Removed]"
  - Extracts source name from nested object
  - Calls _categorize_article() to assign a category
  - Calls create_news_article() to build a clean dict

The result is a Python dictionary:
  {
    "title": "OpenAI launches new model",
    "description": "OpenAI has released...",
    "url": "https://techcrunch.com/...",
    "source": "TechCrunch",
    "author": "Jane Smith",
    "category": "AI",
    "published_at": datetime(2026,10,18,6,0,0),
    "collected_at": datetime(2026,10,18,9,30,0),
    "score": 0
  }
```

```
STAGE 3 — MONGODB (database.py)
─────────────────────────────────
PyMongo sends the Python dictionary to MongoDB.
MongoDB stores it as a BSON document with an auto-generated _id.

  result = collection.insert_one(article)
  # result.inserted_id = ObjectId("6ad4684ce8c68d86b0b18f12")

In MongoDB the document looks like:
  {
    "_id": ObjectId("6ad4684ce8c68d86b0b18f12"),
    "title": "OpenAI launches new model",
    "description": "OpenAI has released...",
    "url": "https://techcrunch.com/...",
    "source": "TechCrunch",
    "author": "Jane Smith",
    "category": "AI",
    "published_at": ISODate("2026-10-18T06:00:00Z"),
    "collected_at": ISODate("2026-10-18T09:30:00Z"),
    "score": 55
  }

You can see this document in MongoDB Compass by opening:
  tech_news → news → Browse Documents
```

```
STAGE 4 — REST API (main.py / Flask)
──────────────────────────────────────
When Postman sends a GET request, Flask calls the database function.

Postman sends:
  GET http://localhost:5000/news/category/AI

Flask receives the request and calls the route handler:
  @app.route("/news/category/<string:category>")
  def get_news_by_cat(category):
      articles = get_news_by_category("AI", limit=20)
      return jsonify(create_success_response(articles))

database.get_news_by_category() queries MongoDB:
  collection.find({"category": "AI"}).sort("published_at", -1).limit(20)

MongoDB returns matching documents.
Python converts them to JSON-safe dicts (dates become strings).
Flask wraps them in the response structure.
Flask sends back the HTTP response.
```

```
STAGE 5 — POSTMAN
───────────────────
Postman receives the HTTP response and displays it.

HTTP/1.1 200 OK
Content-Type: application/json

{
  "error": false,
  "message": "Found 8 articles in 'AI'",
  "total": 8,
  "data": [
    {
      "_id": "6ad4684ce8c68d86b0b18f12",
      "title": "OpenAI launches new model",
      "description": "OpenAI has released...",
      "url": "https://techcrunch.com/...",
      "source": "TechCrunch",
      "category": "AI",
      "published_at": "2026-10-18T06:00:00+00:00",
      "score": 55
    },
    ...
  ]
}
```

**The complete journey visualized:**

```
NewsAPI.org
    |  HTTP GET (requests library)
    v
news_service.py
    |  Python dictionary
    v
database.py (PyMongo)
    |  BSON document
    v
MongoDB: tech_news.news
    |  PyMongo query
    v
database.py (find + convert)
    |  Python list of dicts
    v
main.py (Flask jsonify)
    |  HTTP JSON response
    v
Postman / Browser / Dashboard UI
```

Each layer has one job:
- `news_service.py` — fetch and clean
- `database.py` — store and retrieve
- `main.py` — expose via HTTP
- Postman — test and inspect

No layer reaches into another layer's responsibility.
This is the separation of concerns principle in action.

---
