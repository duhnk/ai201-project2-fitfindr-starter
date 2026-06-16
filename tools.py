"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Search helpers ──────────────────────────────────────────────────────────

# Weight a keyword hit by which field it landed in: a match in the title or
# style tags signals relevance far more strongly than one buried in prose.
_FIELD_WEIGHTS = {
    "style_tags": 3,
    "title": 3,
    "category": 2,
    "colors": 2,
    "brand": 2,
    "description": 1,
}

# Common words that shouldn't earn a listing any relevance score.
_STOPWORDS = {"a", "an", "the", "with", "for", "in", "of", "and", "to", "my"}


def _tokenize(text: str) -> set[str]:
    """Lowercase a string and split it into a set of word tokens."""
    return set(re.findall(r"[a-z0-9']+", text.lower()))


def _score(query_terms: set[str], item: dict) -> int:
    """Score one listing by weighted keyword overlap with the query terms."""
    score = 0
    for field, weight in _FIELD_WEIGHTS.items():
        value = item.get(field)
        if value is None:
            continue
        text = " ".join(value) if isinstance(value, list) else str(value)
        score += weight * len(query_terms & _tokenize(text))
    return score


def _size_matches(query_size: str, item_size: str) -> bool:
    """
    Case-insensitive size match. Splits compound sizes so "M" matches "S/M",
    and falls back to a substring check so "30" matches "W30 L30".
    """
    q = query_size.strip().lower()
    if not q:
        return True
    item_lower = item_size.lower()
    tokens = re.split(r"[\s/]+", item_lower)
    return q in tokens or q in item_lower


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# Default chat model; override with GROQ_MODEL in .env if desired.
_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")


def _chat(prompt: str, *, temperature: float = 0.7, system: str | None = None) -> str:
    """
    Send a single-turn prompt to the Groq chat model and return the reply text.

    Shared by the LLM-backed tools (suggest_outfit, create_fit_card) so the
    client setup and response parsing live in exactly one place.
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    client = _get_groq_client()
    response = client.chat.completions.create(
        model=_MODEL,
        messages=messages,
        temperature=temperature,
    )
    return response.choices[0].message.content.strip()


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
    limit: int = 10,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.
        limit:       Maximum number of results to return (top-N by relevance).
                     Pass None to return all matches.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    query_terms = _tokenize(description) - _STOPWORDS

    scored: list[tuple[int, dict]] = []
    for item in load_listings():
        # Hard filters: skip anything over budget or the wrong size.
        if max_price is not None and item["price"] > max_price:
            continue
        if size is not None and not _size_matches(size, item["size"]):
            continue

        # Relevance score; drop listings with no keyword overlap.
        score = _score(query_terms, item)
        if score > 0:
            scored.append((score, item))

    # Sort by score (highest first); ties broken by lowest price for stability.
    scored.sort(key=lambda pair: (-pair[0], pair[1]["price"]))
    results = [item for _, item in scored]
    return results if limit is None else results[:limit]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    system = (
        "You are FitFindr, a friendly thrift-styling assistant. "
        "Give practical, specific outfit ideas. Keep it concise (under ~120 words)."
    )

    # Describe the new item once; both branches reference it.
    item_desc = (
        f"{new_item['title']} "
        f"(category: {new_item['category']}; "
        f"colors: {', '.join(new_item['colors'])}; "
        f"style: {', '.join(new_item['style_tags'])})"
    )

    items = wardrobe.get("items", [])

    if not items:
        # Empty wardrobe → general styling advice, no specific pieces to name.
        prompt = (
            f"A user is considering buying this thrifted item:\n{item_desc}\n\n"
            "They haven't entered any wardrobe yet. Suggest what kinds of pieces "
            "pair well with it and what vibe/occasions it suits. Offer one or two "
            "general outfit directions they could build."
        )
    else:
        # Populated wardrobe → format pieces so the LLM can name real items.
        wardrobe_lines = "\n".join(
            f"- {it['name']} ({it['category']}; "
            f"{', '.join(it.get('colors', []))}; "
            f"{', '.join(it.get('style_tags', []))})"
            for it in items
        )
        prompt = (
            f"A user is considering buying this thrifted item:\n{item_desc}\n\n"
            f"Here is their existing wardrobe:\n{wardrobe_lines}\n\n"
            "Suggest 1-2 complete outfits built around the new item, naming "
            "specific pieces from their wardrobe by name. Make sure each outfit "
            "is wearable head-to-toe."
        )

    return _chat(prompt, temperature=0.7, system=system)


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    # 1. Guard against an empty / whitespace-only outfit — return an error
    #    string rather than raising or calling the LLM with nothing to work from.
    if not outfit or not outfit.strip():
        return "Error: no outfit was provided, so there is no fit card to create."

    system = (
        "You are FitFindr, writing playful, authentic OOTD captions for social "
        "media. Sound like a real person posting a thrift find — not a product "
        "listing. Emojis and hashtags are welcome but keep it natural."
    )

    price = new_item.get("price")
    price_str = f"${price:.0f}" if price is not None else "a steal"

    # 2. Give the LLM the item details + the outfit, and the style rules.
    prompt = (
        f"Write a short, shareable Instagram/TikTok caption (2-4 sentences) for "
        f"a thrifted outfit.\n\n"
        f"Item: {new_item.get('title', 'this piece')}\n"
        f"Price: {price_str}\n"
        f"Platform: {new_item.get('platform', 'a thrift app')}\n"
        f"Outfit: {outfit}\n\n"
        "Mention the item name, price, and platform naturally — each exactly "
        "once. Capture the outfit's vibe in specific terms. Keep it casual and "
        "authentic, like a real OOTD post."
    )

    # 3. Higher temperature so captions feel fresh and vary between runs.
    return _chat(prompt, temperature=0.9, system=system)
