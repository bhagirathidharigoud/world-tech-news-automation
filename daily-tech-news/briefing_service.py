# ─────────────────────────────────────────────────────────────────
#  briefing_service.py
#
#  PURPOSE:
#  Score articles for importance, select the best stories per
#  category, and format a clean readable daily briefing.
#
#  HOW TO USE IN OTHER FILES:
#      from briefing_service import generate_daily_briefing
#
#  DATA FLOW:
#  MongoDB articles → score → select → format → save → print
# ─────────────────────────────────────────────────────────────────

from datetime import datetime, timezone
from collections import defaultdict    # Groups items by key automatically

from config import BRIEFING_TOP_ARTICLES
from database import (
    get_todays_news,
    save_briefing,
    get_news_collection
)
from models import (
    create_daily_briefing,
    briefing_to_dict,
    VALID_CATEGORIES
)
from news_service import get_category_counts


# ═════════════════════════════════════════════════════════════════
#  SCORING CONFIGURATION
# ═════════════════════════════════════════════════════════════════
# All scoring rules are defined as constants here so they are easy
# to find, read, and adjust without touching the logic.

# Categories and their base importance score.
# Higher = more likely to appear in the briefing.
CATEGORY_SCORES = {
    "Agentic AI":           20,
    "AI":                   20,
    "Quantum Computing":    20,
    "Cybersecurity":        20,
    "Cloud Computing":      10,
    "Programming":          10,
    "Developer Tools":      10,
    "Startups":              5,
    "Technology Companies":  5,
    "Other Technology":      0,
}

# Company names that signal a major, newsworthy article.
MAJOR_COMPANIES = [
    "openai", "google", "microsoft", "apple", "meta", "amazon",
    "nvidia", "anthropic", "deepmind", "tesla", "spacex", "ibm",
    "intel", "amd", "samsung", "huawei", "mistral", "gemini",
    "chatgpt", "claude", "gpt", "copilot"
]

# Words in the title that suggest a significant development.
URGENCY_WORDS = [
    "launches", "releases", "announces", "unveils", "introduces",
    "breaks", "discovers", "warns", "critical", "major", "new",
    "first", "historic", "emergency", "urgent", "attack", "breach",
    "banned", "acquires", "raises", "beats", "record", "billion"
]

# Words in the description that signal impact or importance.
IMPACT_WORDS = [
    "first", "breakthrough", "record", "historic", "billion",
    "major", "significant", "critical", "warning", "largest",
    "unprecedented", "revolutionary", "landmark", "milestone"
]

# Minimum score for an article to be considered for the briefing.
MINIMUM_SCORE_THRESHOLD = 20


# ═════════════════════════════════════════════════════════════════
#  SCORING ENGINE
# ═════════════════════════════════════════════════════════════════

def _score_single_article(article):
    """
    Calculate an importance score for one article.

    Examines the article's category, title, description, and
    publication date, and adds points based on signals that
    suggest the article is important and worth including.

    Args:
        article (dict): An article dictionary from MongoDB.

    Returns:
        int: The total importance score (higher = more important).

    Python concept — Accumulator pattern:
        We start score at 0 and keep adding to it.
        This is the same pattern as summing a list:
            total = 0
            for num in numbers:
                total += num
    """
    score = 0

    # ── SAFE FIELD EXTRACTION ─────────────────────────────────────
    # .get() returns None if the field is missing — no crash.
    # "or ''" converts None to an empty string for .lower() safety.
    title       = (article.get("title")       or "").lower()
    description = (article.get("description") or "").lower()
    category    = article.get("category",   "Other Technology")
    published   = article.get("published_at")

    # ── RULE 1: Category base score ───────────────────────────────
    # Start with the importance score for this category.
    # AI and cybersecurity news is inherently more relevant to
    # a tech briefing than generic "Other Technology" content.
    score += CATEGORY_SCORES.get(category, 0)

    # ── RULE 2: Major company mentioned in title ──────────────────
    # Articles about OpenAI, Google, Microsoft etc. are inherently
    # newsworthy for a global tech audience.
    if any(company in title for company in MAJOR_COMPANIES):
        score += 15

    # ── RULE 3: Urgency words in title ────────────────────────────
    # "Google LAUNCHES new AI model" is more newsworthy than
    # "Google continues work on AI model".
    if any(word in title for word in URGENCY_WORDS):
        score += 10

    # ── RULE 4: Substantial description ──────────────────────────
    # A real article has a meaningful description.
    # Short or missing descriptions suggest low-quality content.
    if len(description) > 100:
        score += 10
    elif len(description) < 20:
        # Very short description — probably a placeholder.
        score -= 5

    # ── RULE 5: Impact words in description ───────────────────────
    # "First ever", "record-breaking", "historic breakthrough" signal
    # that this article is reporting something significant.
    if any(word in description for word in IMPACT_WORDS):
        score += 10

    # ── RULE 6: Recency bonus ─────────────────────────────────────
    # Fresh news is more valuable in a daily briefing.
    if published:
        try:
            now = datetime.now(timezone.utc)

            # Handle both datetime objects and strings.
            if isinstance(published, str):
                pub_date = datetime.fromisoformat(
                    published.replace("Z", "+00:00")
                )
            else:
                pub_date = published

            # Make sure both are timezone-aware for comparison.
            if pub_date.tzinfo is None:
                pub_date = pub_date.replace(tzinfo=timezone.utc)

            hours_old = (now - pub_date).total_seconds() / 3600

            if hours_old <= 24:
                score += 15    # Published today
            elif hours_old <= 168:
                score += 5     # Published this week

        except (ValueError, TypeError):
            # Date parsing failed — skip the recency bonus.
            pass

    # ── RULE 7: Title length quality check ───────────────────────
    # A title between 30 and 120 characters is likely a real headline.
    # Too short = clickbait fragment. Too long = SEO spam.
    title_len = len(article.get("title", ""))
    if 30 <= title_len <= 120:
        score += 5

    # ── RULE 8: Penalty for generic/missing description ───────────
    no_description_phrases = [
        "no description available",
        "unknown",
        ""
    ]
    raw_desc = (article.get("description") or "").strip().lower()
    if raw_desc in no_description_phrases:
        score -= 10

    return max(score, 0)    # Score cannot go below zero


def score_articles(articles):
    """
    Score a list of articles and return them sorted by score.

    Also writes the score back to each article dict AND updates
    the score field in MongoDB for reference.

    Args:
        articles (list): List of article dicts from MongoDB.

    Returns:
        list: Same articles sorted by score descending (best first).

    Python concept — sorted() with key parameter:
        sorted(items, key=lambda x: x["score"], reverse=True)
        key= tells sorted() WHAT to sort by.
        lambda x: x["score"] means: for each item x, use x["score"].
        reverse=True means highest score first.
    """
    if not articles:
        return []

    collection = get_news_collection()

    print(f"  Scoring {len(articles)} articles...")

    for article in articles:
        score = _score_single_article(article)
        article["score"] = score

        # Write the score back to MongoDB so we can inspect it
        # in Compass and use it in future queries.
        if collection is not None and "_id" in article:
            try:
                from bson import ObjectId
                # $set updates ONLY the 'score' field.
                # Without $set, MongoDB would replace the entire document.
                collection.update_one(
                    {"_id": ObjectId(article["_id"])},
                    {"$set": {"score": score}}
                )
            except Exception:
                pass   # Score update failing is not critical

    # Sort articles by score, highest first.
    # Python concept — sorted():
    #   Does not modify the original list — returns a new sorted list.
    scored = sorted(articles, key=lambda x: x.get("score", 0), reverse=True)

    return scored


# ═════════════════════════════════════════════════════════════════
#  ARTICLE SELECTION
# ═════════════════════════════════════════════════════════════════

def select_top_news(scored_articles):
    """
    Select the best article(s) per category for the briefing.

    Strategy:
    1. Group all articles by category.
    2. Within each category, take the top-scoring article.
    3. Add a second article for high-priority categories if available.
    4. Discard any article below the minimum score threshold.

    Args:
        scored_articles (list): Articles sorted by score (best first).

    Returns:
        list: Selected articles for the briefing (one or two per category).

    Python concept — defaultdict:
        defaultdict(list) is like a regular dict, but if you access
        a key that doesn't exist, it automatically creates it with
        an empty list as the value. This avoids having to write:
            if category not in groups:
                groups[category] = []
            groups[category].append(article)
    """

    # Group articles by category.
    # defaultdict(list) means each key starts with an empty list.
    groups = defaultdict(list)

    for article in scored_articles:
        # Only consider articles above the minimum quality threshold.
        if article.get("score", 0) >= MINIMUM_SCORE_THRESHOLD:
            category = article.get("category", "Other Technology")
            groups[category].append(article)

    selected = []

    # High-priority categories get up to 2 articles.
    high_priority = {"Agentic AI", "AI", "Quantum Computing", "Cybersecurity"}

    # Process categories in the order defined in VALID_CATEGORIES
    # so the briefing always appears in the same order.
    for category in VALID_CATEGORIES:
        category_articles = groups.get(category, [])

        if not category_articles:
            continue

        # Articles are already sorted by score (highest first).
        # Take the best one for every category.
        selected.append(category_articles[0])

        # Add a second article for high-priority categories
        # if there is a second article available.
        if category in high_priority and len(category_articles) > 1:
            selected.append(category_articles[1])

    return selected


# ═════════════════════════════════════════════════════════════════
#  BRIEFING FORMATTER
# ═════════════════════════════════════════════════════════════════

def _format_article_section(number, category, article):
    """
    Format one article as a briefing section.

    Args:
        number  (int):  Section number (1, 2, 3...).
        category (str): Category heading.
        article (dict): The article to format.

    Returns:
        str: A formatted multi-line string for this section.
    """
    title       = article.get("title",       "No title")
    description = article.get("description", "No description available.")
    source      = article.get("source",      "Unknown Source")
    url         = article.get("url",         "")
    published   = article.get("published_at", "")

    # Format the publication date into a readable string.
    pub_str = ""
    if published:
        try:
            if isinstance(published, str):
                dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
            else:
                dt = published
            pub_str = dt.strftime("%d %b %Y, %I:%M %p UTC")
        except (ValueError, TypeError):
            pub_str = str(published)[:10]

    # "Why it matters" — a short explanation based on category.
    # This gives students context, not just headlines.
    why_matters = _get_why_it_matters(category, title, description)

    lines = [
        f"{'-' * 60}",
        f"{number}. {category.upper()}",
        f"{'-' * 60}",
        f"  Headline : {title}",
        f"  Summary  : {description}",
        f"  Why it matters: {why_matters}",
        f"  Source   : {source}",
        f"  Published: {pub_str}",
        f"  URL      : {url}",
        ""
    ]

    return "\n".join(lines)


def _get_why_it_matters(category, title, description):
    """
    Generate a short 'Why it matters' sentence for a given category.

    This is rule-based — not AI-generated. It matches the category
    and keywords in the title/description to produce a relevant
    one-sentence explanation.

    Args:
        category    (str): Article category.
        title       (str): Article title.
        description (str): Article description.

    Returns:
        str: A short explanation sentence.
    """
    text = (title + " " + description).lower()

    explanations = {
        "Agentic AI": (
            "Agentic AI systems can make decisions and take actions "
            "autonomously — understanding this shift is essential for "
            "any software developer building modern applications."
        ),
        "AI": (
            "AI is reshaping every industry. Staying current with major "
            "AI developments helps you understand where software, "
            "products, and careers are heading."
        ),
        "Quantum Computing": (
            "Quantum computing will eventually break today's encryption "
            "and solve problems classical computers cannot. "
            "It is the next major platform shift after AI."
        ),
        "Cloud Computing": (
            "Nearly all modern software runs on cloud infrastructure. "
            "Understanding cloud announcements helps you build "
            "scalable, cost-effective systems."
        ),
        "Cybersecurity": (
            "Security incidents affect every developer and every user. "
            "Understanding how attacks happen is the first step to "
            "building systems that are resistant to them."
        ),
        "Programming": (
            "New languages, frameworks and tooling directly affect your "
            "daily work as a developer. "
            "Staying current keeps your skills competitive."
        ),
        "Developer Tools": (
            "Better tools mean faster development and fewer errors. "
            "Knowing what tools exist helps you choose the right one "
            "for your next project."
        ),
        "Startups": (
            "Startup funding reveals which technology problems the market "
            "considers worth solving — a signal for where "
            "future jobs and products will emerge."
        ),
        "Technology Companies": (
            "Decisions by major technology companies shape the platforms, "
            "APIs, and standards that developers build on."
        ),
        "Other Technology": (
            "Broad technology literacy makes you a more effective "
            "developer and communicator with non-technical stakeholders."
        ),
    }

    return explanations.get(category, "Technology shapes the world we build in.")


def _generate_learning_of_the_day(top_news):
    """
    Suggest one practical learning topic based on the day's top stories.

    Looks at the categories present in the briefing and suggests
    a relevant beginner-friendly learning direction.

    Args:
        top_news (list): The selected articles for today's briefing.

    Returns:
        str: A learning suggestion paragraph.
    """
    categories_present = set(a.get("category", "") for a in top_news)

    # Priority order — suggest learning for the most impactful topic.
    if "Agentic AI" in categories_present:
        return (
            "Today's briefing features agentic AI heavily.\n"
            "  Suggested topic: Learn how LangChain or AutoGen works.\n"
            "  Start here    : Build a simple AI agent that searches the web\n"
            "                  and summarises results — 2-3 hours of practice.\n"
            "  Key concept   : Understand the difference between a chatbot\n"
            "                  (responds) and an agent (plans + acts)."
        )
    elif "Quantum Computing" in categories_present:
        return (
            "Quantum computing appeared in today's briefing.\n"
            "  Suggested topic: Understand what a qubit is and how it differs\n"
            "                   from a classical bit.\n"
            "  Start here    : IBM Quantum Learning (free at learning.quantum.ibm.com)\n"
            "  Key concept   : Superposition — a qubit can be 0 AND 1 simultaneously\n"
            "                  until measured."
        )
    elif "Cybersecurity" in categories_present:
        return (
            "Cybersecurity featured prominently today.\n"
            "  Suggested topic: Study the OWASP Top 10 web vulnerabilities.\n"
            "  Start here    : owasp.org — free, beginner-friendly.\n"
            "  Key concept   : SQL injection — the most common attack beginners\n"
            "                  can learn to prevent immediately."
        )
    elif "AI" in categories_present:
        return (
            "AI news dominated today.\n"
            "  Suggested topic: Understand how a transformer model works at a high level.\n"
            "  Start here    : The Illustrated Transformer by Jay Alammar (free blog post)\n"
            "  Key concept   : Attention mechanism — how AI models decide which\n"
            "                  words matter most in a sentence."
        )
    else:
        return (
            "Today's briefing covers broad technology topics.\n"
            "  Suggested topic: Practice reading and writing REST APIs.\n"
            "  Start here    : Build a simple Flask endpoint that returns JSON.\n"
            "  Key concept   : Understand the difference between GET, POST,\n"
            "                  PUT, and DELETE HTTP methods."
        )


def _generate_career_opportunity(top_news):
    """
    Identify career-relevant skills from today's news.

    Args:
        top_news (list): Selected articles.

    Returns:
        str: A career insight paragraph.
    """
    categories_present = set(a.get("category", "") for a in top_news)

    skills = []
    roles = []

    if "Agentic AI" in categories_present or "AI" in categories_present:
        skills.extend(["Python", "LLM APIs (OpenAI / Anthropic)", "Prompt Engineering"])
        roles.extend(["AI Engineer", "ML Engineer", "AI Product Developer"])

    if "Cybersecurity" in categories_present:
        skills.extend(["Network Security", "Python scripting", "OWASP practices"])
        roles.extend(["Security Engineer", "Penetration Tester"])

    if "Cloud Computing" in categories_present:
        skills.extend(["AWS / Azure / GCP basics", "Serverless architecture"])
        roles.extend(["Cloud Engineer", "DevOps Engineer"])

    if "Programming" in categories_present or "Developer Tools" in categories_present:
        skills.extend(["Git / GitHub", "CI/CD pipelines", "Testing practices"])
        roles.extend(["Software Developer", "Full-Stack Engineer"])

    if "Quantum Computing" in categories_present:
        skills.extend(["Linear algebra", "Qiskit (IBM quantum SDK)"])
        roles.extend(["Quantum Software Engineer (emerging role)"])

    if not skills:
        skills = ["Python", "REST APIs", "MongoDB", "Cloud basics"]
        roles  = ["Backend Developer", "Full-Stack Engineer"]

    # Remove duplicates while preserving order using dict.fromkeys().
    unique_skills = list(dict.fromkeys(skills))
    unique_roles  = list(dict.fromkeys(roles))

    skill_list = "\n".join(f"    • {s}" for s in unique_skills[:5])
    role_list  = "\n".join(f"    • {r}" for r in unique_roles[:4])

    return (
        f"  Based on today's technology news, these skills are in demand:\n"
        f"{skill_list}\n\n"
        f"  Roles to explore:\n"
        f"{role_list}"
    )


def format_briefing(date_str, top_news, total_news, category_counts):
    """
    Build the complete formatted briefing text.

    Args:
        date_str        (str):  "YYYY-MM-DD"
        top_news        (list): Selected article dicts.
        total_news      (int):  Total articles collected today.
        category_counts (dict): Articles per category.

    Returns:
        str: The complete formatted briefing as a multi-line string.
    """

    # ── HEADER ────────────────────────────────────────────────────
    lines = [
        "",
        "=" * 60,
        "  DAILY GLOBAL TECH BRIEFING",
        f"  Date    : {date_str}",
        f"  Articles: {total_news} collected  |  {len(top_news)} selected",
        "=" * 60,
        "",
        "  Good morning. Here are today's most important",
        "  technology developments across the world.",
        "",
    ]

    # ── NEWS SECTIONS ─────────────────────────────────────────────
    # Group selected articles by category so we can present them
    # under category headings.
    section_number = 1
    seen_categories = set()

    for article in top_news:
        category = article.get("category", "Other Technology")

        # Add a category heading on first appearance.
        if category not in seen_categories:
            seen_categories.add(category)

        section = _format_article_section(section_number, category, article)
        lines.append(section)
        section_number += 1

    # ── COVERAGE SUMMARY ──────────────────────────────────────────
    lines.append("=" * 60)
    lines.append("  TODAY'S COVERAGE SUMMARY")
    lines.append("=" * 60)
    lines.append("")

    for cat, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
        bar = "#" * min(count, 30)
        lines.append(f"  {cat:<25} {count:>3} articles  {bar}")

    lines.append("")

    # ── LEARNING OF THE DAY ───────────────────────────────────────
    lines.append("=" * 60)
    lines.append("  LEARNING OF THE DAY")
    lines.append("=" * 60)
    lines.append("")
    lines.append("  " + _generate_learning_of_the_day(top_news).replace("\n", "\n  "))
    lines.append("")

    # ── CAREER OPPORTUNITY ────────────────────────────────────────
    lines.append("=" * 60)
    lines.append("  CAREER OPPORTUNITY")
    lines.append("=" * 60)
    lines.append("")
    lines.append(_generate_career_opportunity(top_news))
    lines.append("")

    # ── FOOTER ────────────────────────────────────────────────────
    lines.append("=" * 60)
    lines.append("  End of Daily Global Tech Briefing")
    lines.append(f"  Generated at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("=" * 60)
    lines.append("")

    return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════
#  MAIN PUBLIC FUNCTION
# ═════════════════════════════════════════════════════════════════

def generate_daily_briefing(articles=None):
    """
    Run the full briefing pipeline:
      1. Load today's articles (or use provided list).
      2. Score every article.
      3. Select the best articles per category.
      4. Format the briefing text.
      5. Save to MongoDB.
      6. Print to terminal.

    Args:
        articles (list): Optional. If None, loads today's news
                         from MongoDB automatically.

    Returns:
        dict or None: The saved briefing document, or None on failure.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    print("\n" + "=" * 50)
    print(f"GENERATING DAILY BRIEFING FOR {today}")
    print("=" * 50)

    # ── STEP 1: Load articles ─────────────────────────────────────
    if articles is None:
        print("Loading today's articles from MongoDB...")
        articles = get_todays_news()

    if not articles:
        print("No articles found for today. Run fetch_and_store_news() first.")
        return None

    print(f"Loaded {len(articles)} articles.")

    # ── STEP 2: Score articles ────────────────────────────────────
    scored = score_articles(articles)
    above_threshold = [a for a in scored if a.get("score", 0) >= MINIMUM_SCORE_THRESHOLD]
    print(f"  {len(above_threshold)} articles scored above threshold ({MINIMUM_SCORE_THRESHOLD}).")

    if not above_threshold:
        print("No articles met the minimum quality threshold.")
        return None

    # ── STEP 3: Select top stories ────────────────────────────────
    top_news = select_top_news(scored)
    print(f"  Selected {len(top_news)} articles for the briefing.")

    # ── STEP 4: Gather statistics ─────────────────────────────────
    category_counts = get_category_counts(articles)
    total_news = len(articles)

    # ── STEP 5: Format the briefing ───────────────────────────────
    briefing_text = format_briefing(today, top_news, total_news, category_counts)

    # ── STEP 6: Build and save the briefing document ──────────────
    briefing_doc = create_daily_briefing(
        briefing_date=today,
        top_news=top_news,
        briefing_text=briefing_text,
        category_counts=category_counts,
        total_news=total_news
    )

    briefing_id = save_briefing(briefing_doc)

    if briefing_id:
        print(f"  Briefing saved to MongoDB (id: {briefing_id})")
    else:
        print("  Briefing already exists for today or could not be saved.")

    # ── STEP 7: Print the briefing ────────────────────────────────
    print(briefing_text)

    return briefing_to_dict(briefing_doc)
