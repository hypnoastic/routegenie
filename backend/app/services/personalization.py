from collections import Counter

from app.models import SearchSession, Trip, UserPreference


INTEREST_KEYWORDS = {
    "cafe": ["cafe", "coffee", "espresso", "starbucks"],
    "food": ["food", "restaurant", "breakfast", "lunch", "dinner", "snack"],
    "fuel": ["fuel", "gas", "petrol", "diesel"],
    "ev_charging": ["ev", "charging", "charger"],
    "scenic": ["scenic", "sunset", "viewpoint", "lake", "hill"],
    "shopping": ["mall", "shopping", "market"],
    "restroom": ["restroom", "washroom", "toilet"],
    "temples": ["temple", "mandir"],
    "work_commute": ["office", "commute", "work"],
    "safety": ["safe", "safer", "crowded", "main roads"],
    "budget": ["cheap", "budget", "cheaper", "save money"],
}


def extract_interest_scores(texts: list[str]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    haystack = " ".join(texts).lower()
    for interest, keywords in INTEREST_KEYWORDS.items():
        counter[interest] = sum(haystack.count(keyword) for keyword in keywords)
    return {key: value for key, value in counter.items() if value > 0}


def update_preferences_from_history(preferences: UserPreference, trips: list[Trip], searches: list[SearchSession]) -> None:
    texts = [
        trip.title for trip in trips
    ] + [
        trip.origin_text for trip in trips
    ] + [
        trip.destination_text for trip in trips
    ] + [
        search.query_text for search in searches
    ]
    preferences.interests_json = extract_interest_scores(texts)


def build_personalization_context(preferences: UserPreference | None, trips: list[Trip], searches: list[SearchSession]) -> dict:
    recent_trip_titles = [trip.title for trip in trips[:5]]
    recent_queries = [search.query_text for search in searches[:5]]
    return {
        "enabled": preferences.personalization_enabled if preferences else False,
        "preferred_travel_mode": preferences.preferred_travel_mode if preferences else "DRIVE",
        "avoid_tolls": preferences.avoid_tolls if preferences else False,
        "avoid_highways": preferences.avoid_highways if preferences else False,
        "safety_mode": preferences.safety_mode if preferences else False,
        "interests": preferences.interests_json if preferences else {},
        "recent_trips": recent_trip_titles,
        "recent_queries": recent_queries,
    }
