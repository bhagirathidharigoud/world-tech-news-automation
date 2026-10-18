# ─────────────────────────────────────────────────────────────────
#  config.py
#
#  PURPOSE:
#  Read all settings from the .env file and make them available
#  to every other file in the project.
#
#  HOW TO USE IN OTHER FILES:
#      from config import NEWS_API_KEY, MONGO_URI
#
#  RULE:
#  Never hardcode secrets here. Always read from environment.
# ─────────────────────────────────────────────────────────────────

import os                        # os module — reads environment variables
from dotenv import load_dotenv   # python-dotenv — loads .env file into os.environ

# ── LOAD THE .env FILE ────────────────────────────────────────────
# load_dotenv() finds the .env file in the current folder and
# loads every KEY=VALUE pair into the operating system's
# environment variables so that os.getenv() can read them.
#
# Must be called BEFORE any os.getenv() calls below.
load_dotenv()


# ── NEWS API SETTINGS ─────────────────────────────────────────────
# os.getenv("KEY") reads the value of KEY from the environment.
# If KEY is missing, it returns None (or the default we provide).

NEWS_API_KEY = os.getenv("NEWS_API_KEY")
NEWS_API_BASE_URL = os.getenv("NEWS_API_BASE_URL", "https://newsapi.org/v2")


# ── MONGODB SETTINGS ──────────────────────────────────────────────
# MONGO_URI is the address of your MongoDB server.
# Default: localhost on port 27017 (standard local MongoDB).

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "tech_news")


# ── SCHEDULER SETTINGS ────────────────────────────────────────────
# int() converts the string from .env into a proper integer.
# os.getenv always returns a string — "6" not 6.
# APScheduler needs an integer for hour and minute.

NEWS_SCHEDULE_HOUR = int(os.getenv("NEWS_SCHEDULE_HOUR", "6"))
NEWS_SCHEDULE_MINUTE = int(os.getenv("NEWS_SCHEDULE_MINUTE", "0"))


# ── FLASK SERVER SETTINGS ─────────────────────────────────────────
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
FLASK_ENV = os.getenv("FLASK_ENV", "development")


# ── APPLICATION SETTINGS ──────────────────────────────────────────
# How many articles to request from the API in one call.
NEWS_FETCH_PAGE_SIZE = int(os.getenv("NEWS_FETCH_PAGE_SIZE", "50"))

# How many top articles to include in each daily briefing.
BRIEFING_TOP_ARTICLES = int(os.getenv("BRIEFING_TOP_ARTICLES", "15"))


# ── MONGODB COLLECTION NAMES ──────────────────────────────────────
# Defined as constants so if we ever rename a collection,
# we change it in one place only.

COLLECTION_NEWS = "news"
COLLECTION_BRIEFINGS = "daily_briefings"


# ── CATEGORY KEYWORDS ─────────────────────────────────────────────
# This dictionary drives automatic categorization in news_service.py.
#
# Structure:
#   "Category Name" : [list of keywords to look for]
#
# How it works:
#   If any keyword from the list is found in an article's
#   title or description, that article is assigned the category.
#
# Categories are checked in ORDER — the first match wins.
# "Other Technology" is the fallback (checked last, always matches).
#
# To add a new keyword: just add it to the list.
# To add a new category: add a new key-value pair.

CATEGORY_KEYWORDS = {
    "Agentic AI": [
        "agentic ai", "ai agent", "autonomous agent", "ai agents",
        "multi-agent", "multiagent", "llm agent", "agent framework",
        "openai agents", "langchain agent", "autogen", "crewai",
        "agentic", "agent workflow", "agent orchestration"
    ],
    "AI": [
        "artificial intelligence", "machine learning", "deep learning",
        "neural network", "large language model", "llm", "gpt", "gemini",
        "claude", "openai", "anthropic", "mistral", "generative ai",
        "gen ai", "ai model", "foundation model", "transformer",
        "natural language processing", "nlp", "computer vision",
        "chatgpt", "copilot", "diffusion model", "stable diffusion"
    ],
    "Quantum Computing": [
        "quantum computing", "quantum computer", "qubit", "qubits",
        "quantum supremacy", "quantum advantage", "quantum processor",
        "quantum algorithm", "quantum hardware", "ibm quantum",
        "google quantum", "quantum error correction", "quantum network"
    ],
    "Cloud Computing": [
        "cloud computing", "aws", "amazon web services", "azure",
        "google cloud", "gcp", "cloud storage", "cloud platform",
        "serverless", "kubernetes", "cloud infrastructure",
        "cloud migration", "cloud native", "iaas", "paas", "saas",
        "multicloud", "hybrid cloud", "cloud security", "edge computing"
    ],
    "Cybersecurity": [
        "cybersecurity", "cyber attack", "data breach", "ransomware",
        "malware", "phishing", "hacking", "vulnerability", "zero-day",
        "exploit", "security patch", "cyber threat", "firewall",
        "encryption", "authentication", "identity theft", "ddos",
        "cyber crime", "infosec", "penetration testing", "cve"
    ],
    "Programming": [
        "python", "javascript", "typescript", "rust", "golang", "java",
        "c++", "programming language", "software development",
        "open source", "github", "git", "code", "coding",
        "developer", "software engineer", "api", "framework",
        "library", "package manager", "npm", "pip", "compiler"
    ],
    "Developer Tools": [
        "vs code", "visual studio", "ide", "developer tools",
        "devops", "ci/cd", "docker", "kubernetes", "terraform",
        "github actions", "gitlab", "jenkins", "testing framework",
        "debugging", "code review", "deployment", "monitoring",
        "observability", "postman", "linux", "terminal", "cli"
    ],
    "Startups": [
        "startup", "start-up", "funding", "seed round", "series a",
        "series b", "series c", "venture capital", "vc funding",
        "unicorn", "valuation", "ipo", "acquisition", "merger",
        "techcrunch", "product launch", "founder", "investor"
    ],
    "Technology Companies": [
        "apple", "google", "microsoft", "meta", "amazon", "tesla",
        "nvidia", "intel", "amd", "samsung", "ibm", "oracle",
        "salesforce", "adobe", "netflix", "uber", "airbnb", "spacex",
        "alphabet", "twitter", "x.com", "tiktok", "bytedance",
        "huawei", "xiaomi", "qualcomm", "broadcom"
    ],
    "Other Technology": [
        # This is the FALLBACK category.
        # Any article that does not match the categories above
        # will be placed here.
        # We use an empty list — the categorization logic
        # assigns this category last, after all others fail.
        "technology", "tech", "innovation", "digital", "software",
        "hardware", "internet", "semiconductor", "robotics",
        "blockchain", "web3", "ar", "vr", "metaverse", "5g", "iot"
    ]
}


# ── VALIDATION ────────────────────────────────────────────────────
# Check that the critical setting (API key) is actually set.
# If it's missing, we warn the developer immediately at startup
# instead of getting a confusing error later during a news fetch.

def validate_config():
    """
    Check that all required environment variables are set.
    Call this once at application startup.

    Returns:
        list: A list of error messages. Empty list means all is fine.
    """
    errors = []

    if not NEWS_API_KEY or NEWS_API_KEY == "your_newsapi_key_here":
        errors.append(
            "NEWS_API_KEY is missing or not set. "
            "Get a free key at https://newsapi.org and add it to your .env file."
        )

    if not MONGO_URI:
        errors.append("MONGO_URI is missing in .env file.")

    if not MONGO_DB_NAME:
        errors.append("MONGO_DB_NAME is missing in .env file.")

    return errors
