#!/usr/bin/env python3
"""Gather next week's planning inputs. Run every Friday.

Fetches three things and writes one JSON file each: what we cooked around this
same week in previous years, the recipes in a saved collection, and the app's
For You suggestions filtered to what fits an evening. Then writes the prompt
that turns them into next week's menu.
"""
import argparse, os, re, json, html, asyncio, aiohttp
from datetime import datetime, timedelta

from dotenv import load_dotenv

from cookidoo_api import Cookidoo
from cookidoo_api.helpers import get_localization_options
from cookidoo_api.types import CookidooConfig

load_dotenv()

COOKIE_FILE = ".cookies"
HISTORY_FILE = "history.json"
COLLECTIONS_FILE = "collections.json"
FANTASY_FILE = "fantasy.json"
PROMPT_FILE = "prompt.md"

YEARS_BACK = 3        # how many previous years to look at
WINDOW_WEEKS = 3      # +/- weeks around the same week last year
MAX_MINUTES = 90      # fantasy picks have to fit in an evening, total time

# The collection to draw from. Set the name here.
# COLLECTION = "Cocina fácil y saludable"
COLLECTION = None

# The For You page renders its suggestions server-side into these chunks; the
# chunks parameter is required or the endpoint 502s
CHUNKS = "hero:0,bento-grid:1,stripe-wide:2,stripe:3,stripe-wide:4,stripe:5,stripe-wide:6"
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
}

# Lunch and dinner every day, except no supper on Friday
MEALS = {
    "Monday": ["lunch", "dinner"],
    "Tuesday": ["lunch", "dinner"],
    "Wednesday": ["lunch", "dinner"],
    "Thursday": ["lunch", "dinner"],
    "Friday": ["lunch"],
    "Saturday": ["lunch", "dinner"],
    "Sunday": ["lunch", "dinner"],
}


def minutes(total_time):
    """Normalise the API's seconds (str or int) into whole minutes."""
    return round(float(total_time) / 60) if total_time else None


def parse_duration(text):
    """Turn a rendered duration ("45 min", "1 h 40 min") into minutes."""
    if not text:
        return None
    hours = re.search(r"(\d+)\s*h", text)
    mins = re.search(r"(\d+)\s*min", text)
    return (int(hours.group(1)) * 60 if hours else 0) + (int(mins.group(1)) if mins else 0) or None


def next_monday(today):
    """The Monday that starts the week we are planning."""
    return today + timedelta(days=7 - today.weekday())


async def fetch_history(cookidoo, target_monday):
    """Days cooked around this same week in previous years."""
    days = []
    for y in range(1, YEARS_BACK + 1):
        # 52 whole weeks keeps the weekday alignment intact
        anchor = target_monday - timedelta(weeks=52 * y)
        for offset in range(-WINDOW_WEEKS, WINDOW_WEEKS + 1):
            week = anchor + timedelta(weeks=offset)
            # Returns only the days of that week which have entries; days we
            # simply never recorded are absent, not evidence of not cooking
            for calday in await cookidoo.get_recipes_in_calendar_week(week):
                day = datetime.strptime(calday.id, "%Y-%m-%d").date()
                days.append(
                    {
                        "date": calday.id,
                        "weekday": day.strftime("%A"),
                        "years_back": y,
                        "weeks_from_target": offset,
                        "recipes": [
                            {
                                "id": r.id,
                                "name": r.name,
                                "minutes": minutes(r.total_time),
                            }
                            for r in calday.recipes
                        ],
                        "custom_recipe_ids": calday.customer_recipe_ids,
                    }
                )
    days.sort(key=lambda d: d["date"])
    return days


def parse_chunk(name, markup):
    """Pull the recipes out of one rendered For You chunk."""
    header = re.search(
        r'class="(?:core-stripe__header|wf-bento-grid__header)"[^>]*>\s*([^<]+)', markup
    )
    section = html.unescape(header.group(1)).strip() if header else name.split(":")[0]

    recipes = []
    for block in re.split(r"(?=<article |<wf-image-tile |<core-tile )", markup):
        recipe_id = re.search(r"/recipes/recipe/[a-zA-Z-]+/(r\d+)", block)
        title = re.search(
            r'class="(?:wf-hero-component__slide-title|wf-image-tile__title'
            r'|core-tile__description-text)"[^>]*>\s*([^<]+)',
            block,
        )
        if not (recipe_id and title):
            continue
        rating = re.search(r'core-rating__counter">([\d.]+)<', block)
        duration = re.search(r'(?:__description-subline">|</core-rating><span>)([^<]+)<', block)
        recipes.append(
            {
                "id": recipe_id.group(1),
                "name": html.unescape(title.group(1)).strip(),
                # The bento grid tiles render no duration
                "minutes": parse_duration(duration.group(1) if duration else None),
                "rating": float(rating.group(1)) if rating else None,
                "section": section,
            }
        )
    return recipes


async def fetch_fantasy(cookidoo, session):
    """The For You suggestions, filtered to what fits an evening.

    Recipes without a published duration are dropped: the bento-grid tiles
    render no time, so we cannot tell whether they fit.
    """
    url = (
        f"{cookidoo.api_endpoint}/foundation/{cookidoo.localization.language}"
        f"/partials/recommendations?chunks={CHUNKS}"
    )
    headers = {
        **BROWSER_HEADERS,
        "Referer": f"{cookidoo.api_endpoint}/foundation/"
        f"{cookidoo.localization.language}/for-you",
    }
    async with session.get(url, headers=headers) as r:
        if r.status != 200:
            # The recommender is flaky; a week without it is not fatal
            print(f"  ! For You unavailable ({r.status})")
            return [], 0
        # Served as text/html even though the body is JSON
        chunks = await r.json(content_type=None)

    recipes = {}
    for name, markup in chunks.items():
        if not isinstance(markup, str):
            continue  # skips the trailing dcid
        for recipe in parse_chunk(name, markup):
            # A recipe can appear in several stripes; keep the first section
            recipes.setdefault(recipe["id"], recipe)

    no_time = sum(1 for r in recipes.values() if not r["minutes"])
    fantasy = [r for r in recipes.values() if r["minutes"] and r["minutes"] <= MAX_MINUTES]
    fantasy.sort(key=lambda r: r["minutes"])
    return fantasy, no_time


async def fetch_collections(cookidoo):
    """Every recipe in the chosen saved collection, with its editorial context."""
    if not COLLECTION:
        return []

    _total, pages = await cookidoo.count_managed_collections()
    recipes = {}
    for page in range(pages):
        for collection in await cookidoo.get_managed_collections(page=page):
            if collection.name != COLLECTION:
                continue
            for chapter in collection.chapters:
                for r in chapter.recipes:
                    recipes.setdefault(
                        r.id,
                        {
                            "id": r.id,
                            "name": r.name,
                            "minutes": minutes(r.total_time),
                            "collection": collection.name,
                            "collection_description": collection.description,
                        },
                    )
    return list(recipes.values())


def build_prompt(monday, fantasy_count):
    """The instruction that turns the three files into next week's menu."""
    slots = []
    total = 0
    for i in range(7):
        day = monday + timedelta(days=i)
        meals = MEALS[day.strftime("%A")]
        total += len(meals)
        note = "  (no supper on Friday)" if day.strftime("%A") == "Friday" else ""
        slots.append(f"- {day.strftime('%A')} {day.isoformat()}: {', '.join(meals)}{note}")

    return f"""# Menu for {monday.isoformat()} to {(monday + timedelta(days=6)).isoformat()}

Build next week's menu. Fill every slot below - {total} meals in total.

{chr(10).join(slots)}

## Inputs

- `{HISTORY_FILE}` - what we actually cooked around this same week in the last
  {YEARS_BACK} years. This is the basis: the menu should feel like these weeks.
- `{COLLECTIONS_FILE}` - recipes we have saved and like. Mix these in freely.
- `{FANTASY_FILE}` - new suggestions from the app, all {MAX_MINUTES} minutes or
  under, sorted fastest first.

## Rules

1. Mimic the history weeks and mix those recipes with the ones from the
   collection. Both are fair game for any weekday slot.
2. Weekend meals are their own thing: base Saturday and Sunday only on the
   Saturday and Sunday entries in the history. Do not put a weekday recipe on
   the weekend, or a weekend recipe on a weekday.
3. Add {fantasy_count} recipes from the fantasy pool - only where they actually
   make sense for that day and meal.
4. The history records no meal slot; a day just lists the recipes cooked that
   day. Infer lunch or dinner from the dish itself.
5. Days missing from the history were never recorded. That is missing data, not
   a day we did not cook - draw no conclusion from a gap.

## Output

For each slot give: date, weekday, meal, recipe id, recipe name, and which of
the three files it came from.
"""


async def main(fantasy_count):
    jar = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(cookie_jar=jar) as session:
        cookidoo = Cookidoo(
            session,
            cfg=CookidooConfig(
                email=os.environ["EMAIL"],
                password=os.environ["PASSWORD"],
                localization=(
                    await get_localization_options(country="ie", language="en-GB")
                )[0],
            ),
        )
        try:
            cookidoo.load_cookies(COOKIE_FILE)
            await cookidoo.get_user_info()
        except Exception:
            await cookidoo.login()
            await cookidoo.get_user_info()
            cookidoo.save_cookies(COOKIE_FILE)

        today = datetime.today().date()
        monday = next_monday(today)

        history = await fetch_history(cookidoo, monday)
        collections = await fetch_collections(cookidoo)
        fantasy, no_time = await fetch_fantasy(cookidoo, session)

        for path, data in [
            (HISTORY_FILE, history),
            (COLLECTIONS_FILE, collections),
            (FANTASY_FILE, fantasy),
        ]:
            with open(path, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        with open(PROMPT_FILE, "w") as f:
            f.write(build_prompt(monday, fantasy_count))

        print(f"planning week of {monday}")
        print(f"  {HISTORY_FILE:18} {len(history)} days from the last {YEARS_BACK} years")
        print(f"  {COLLECTIONS_FILE:18} {len(collections)} recipes"
              f" ({COLLECTION or 'no collection set'})")
        print(f"  {FANTASY_FILE:18} {len(fantasy)} recipes under {MAX_MINUTES} min"
              f" ({no_time} skipped with no published time)")
        print(f"  {PROMPT_FILE:18} asks for {fantasy_count} fantasy recipes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fantasy",
        type=int,
        default=3,
        help="how many fantasy recipes the menu should include",
    )
    args = parser.parse_args()
    asyncio.run(main(max(0, args.fantasy)))
