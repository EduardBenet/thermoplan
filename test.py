#!/usr/bin/env python3
"""Example script for cookidoo-api."""
import os, json, aiohttp, asyncio
from dotenv import load_dotenv

from datetime import datetime, timedelta

from cookidoo_api import Cookidoo
from cookidoo_api.helpers import (
    get_country_options,
    get_language_options,
    get_localization_options,
)
from cookidoo_api.types import (
    CookidooAdditionalItem,
    CookidooConfig,
    CookidooIngredientItem,
)

load_dotenv()

HISTORY_FILE = "recipe_history.jsonl"

async def main():
    """Run main example function."""
    # Use CookieJar(unsafe=True) to support cross-domain cookies during login
    jar = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(cookie_jar=jar) as session:
        # Show all country_codes, languages and some localizations
        _country_codes = await get_country_options()
        _languages = await get_language_options()
        _localizations_ch = await get_localization_options(country="ch")
        _localizations_en = await get_localization_options(language="en")

        # Create Cookidoo instance with email and password. The OAuth2 client
        # identifiers default to the mobile app's public ones, nothing else to
        # configure (see docs/oauth-client.md)
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

        # Try to reuse saved cookies, otherwise login fresh
        cookie_file = ".cookies"
        try:
            cookidoo.load_cookies(cookie_file)
            await cookidoo.get_user_info()
        except Exception:
            await cookidoo.login()
            await cookidoo.get_user_info()
            cookidoo.save_cookies(cookie_file)

        # Info
        subscription = await cookidoo.get_active_subscription()

        # One record per planned day, the sample unit for the meal planner
        days = []

        today = datetime.today().date()
        for y in range(3):
            print(y)
            start_date = today - timedelta(days = 386+365*y)
            end_date = today - timedelta(days = 344+365*y)

            # Snap to Monday boundaries so full weeks are covered
            date = start_date - timedelta(days=start_date.weekday())          # previous (or same) Monday
            end_date = end_date - timedelta(days=end_date.weekday()) + timedelta(weeks=1)  # next Monday after end_date's week

            while date < end_date:
                print(date)

                # Returns only the days of that week which have entries
                for calday in await cookidoo.get_recipes_in_calendar_week(date):
                    day = datetime.strptime(calday.id, "%Y-%m-%d").date()
                    days.append(
                        {
                            "date": calday.id,
                            "weekday": day.strftime("%A"),
                            "recipes": [
                                {
                                    "id": recipe.id,
                                    "name": recipe.name,
                                    "minutes": round(float(recipe.total_time) / 60)
                                    if recipe.total_time
                                    else None,
                                    "url": recipe.url,
                                }
                                for recipe in calday.recipes
                            ],
                            "custom_recipe_ids": calday.customer_recipe_ids,
                        }
                    )
                date+=timedelta(weeks=1)

        days.sort(key=lambda day: day["date"])
        with open(HISTORY_FILE, "w") as f:
            for day in days:
                f.write(json.dumps(day, ensure_ascii=False) + "\n")
        print(f"wrote {len(days)} days to {HISTORY_FILE}")
        

asyncio.run(main())
