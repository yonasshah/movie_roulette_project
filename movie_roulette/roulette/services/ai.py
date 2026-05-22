import json
import re
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from google import genai


GENRE_NAME_TO_ID = {
    "Action": 28,
    "Adventure": 12,
    "Animation": 16,
    "Comedy": 35,
    "Crime": 80,
    "Documentary": 99,
    "Drama": 18,
    "Family": 10751,
    "Fantasy": 14,
    "History": 36,
    "Horror": 27,
    "Music": 10402,
    "Mystery": 9648,
    "Romance": 10749,
    "Science Fiction": 878,
    "Sci-Fi": 878,
    "Thriller": 53,
    "War": 10752,
    "Western": 37,
}


@dataclass
class MoodFilters:
    content_type: str
    genre_names: list[str]
    genre_ids: list[int]
    min_rating: float
    year_after: int
    explanation: str


def _extract_json(text: str) -> dict[str, Any]:
    """
    Gemini should return JSON, but sometimes models wrap JSON in ```json blocks.
    This function handles both cases.
    """
    text = text.strip()

    match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if match:
        text = match.group(1).strip()

    return json.loads(text)


def generate_mood_filters(mood_prompt: str) -> MoodFilters:
    """
    Converts a natural-language mood into structured roulette filters.
    Example:
    "something funny and fast-paced" -> Comedy/Action, min_rating 6.5, year_after 2000
    """
    if not settings.AI_FEATURES_ENABLED:
        raise RuntimeError("AI features are disabled.")

    if not settings.GEMINI_API_KEY:
        raise RuntimeError("Missing GEMINI_API_KEY.")

    mood_prompt = mood_prompt.strip()

    if not mood_prompt:
        raise ValueError("Mood prompt is required.")

    if len(mood_prompt) > 500:
        raise ValueError("Mood prompt is too long.")

    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    prompt = f"""
You are helping power a movie and TV roulette app.

Convert the user's mood into simple roulette filters.

User mood:
{mood_prompt}

Rules:
- Return JSON only. Do not include markdown.
- content_type must be either "movie" or "tv".
- genre_names should be 1 to 3 genre names from this list:
  Action, Adventure, Animation, Comedy, Crime, Documentary, Drama, Family,
  Fantasy, History, Horror, Music, Mystery, Romance, Science Fiction,
  Thriller, War, Western
- min_rating must be between 0 and 10.
- year_after must be between 1950 and 2025.
- If the user asks for older/classic content, use a lower year_after.
- If unsure, use broad filters.
- explanation must be one short sentence.

Return this exact JSON shape:
{{
  "content_type": "movie",
  "genre_names": ["Comedy"],
  "min_rating": 6.5,
  "year_after": 2000,
  "explanation": "I focused on comedies because you asked for something light."
}}
"""

    response = client.models.generate_content(
        model="gemini-3.1-flash-lite",
        contents=prompt,
    )

    data = _extract_json(response.text)

    content_type = data.get("content_type", "movie")
    if content_type not in ["movie", "tv"]:
        content_type = "movie"

    genre_names = data.get("genre_names", [])
    if not isinstance(genre_names, list):
        genre_names = []

    clean_genre_names = []
    genre_ids = []

    for name in genre_names[:3]:
        if not isinstance(name, str):
            continue

        name = name.strip()
        genre_id = GENRE_NAME_TO_ID.get(name)

        if genre_id:
            clean_genre_names.append(name)
            genre_ids.append(genre_id)

    try:
        min_rating = float(data.get("min_rating", 0))
    except (TypeError, ValueError):
        min_rating = 0

    min_rating = max(0, min(min_rating, 10))

    try:
        year_after = int(data.get("year_after", 1990))
    except (TypeError, ValueError):
        year_after = 1990

    year_after = max(1950, min(year_after, 2025))

    explanation = data.get("explanation", "")
    if not isinstance(explanation, str):
        explanation = ""

    return MoodFilters(
        content_type=content_type,
        genre_names=clean_genre_names,
        genre_ids=genre_ids,
        min_rating=min_rating,
        year_after=year_after,
        explanation=explanation[:240],
    )

def generate_recommendation_explanation(
    mood_prompt: str,
    filters: dict[str, Any],
    content: dict[str, Any],
) -> str:
    """
    Explains why a roulette result fits the user's mood and selected filters.
    """
    if not settings.AI_FEATURES_ENABLED:
        raise RuntimeError("AI features are disabled.")

    if not settings.GEMINI_API_KEY:
        raise RuntimeError("Missing GEMINI_API_KEY.")

    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    mood_prompt = (mood_prompt or "").strip()
    filters = filters or {}
    content = content or {}

    title = content.get("title") or content.get("name") or "this pick"
    overview = content.get("overview") or ""
    rating = content.get("vote_average") or ""
    release_date = content.get("release_date") or content.get("first_air_date") or ""
    content_type = content.get("content_type") or content.get("type") or ""

    prompt = f"""
You are explaining a recommendation in a movie and TV roulette app.

User mood:
{mood_prompt}

Selected filters:
{json.dumps(filters)}

Recommended content:
Title: {title}
Type: {content_type}
Release date: {release_date}
Rating: {rating}
Overview: {overview}

Write 2 short sentences explaining why this recommendation fits.
Do not overclaim.
Do not say the user will definitely like it.
Keep it natural and casual.
Return plain text only.
"""

    response = client.models.generate_content(
        model="gemini-3.1-flash-lite",
        contents=prompt,
    )

    return response.text.strip()[:600]