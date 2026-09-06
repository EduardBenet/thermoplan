"""The save step - write the finalised menu into the Cookidoo calendar.

Add-only and idempotent: for each day it adds the requested recipe ids that are
not already in that day's calendar. It never removes anything - a recipe you
dropped in the app that was already pinned stays until you remove it in Cookidoo.
Custom (self-created) recipes are reported as unsupported for now.
"""
import re
from datetime import datetime

from cookidoo_client import cookidoo_client

_CATALOGUE_ID = re.compile(r"^r\d+$")


async def save_menu(days):
    """Add each day's recipes to the calendar, skipping ones already there.

    ``days``: ``[{"date": "YYYY-MM-DD", "recipe_ids": [...]}, ...]``.
    Returns a summary dict.
    """
    wanted = {}
    for entry in days:
        date = str(entry.get("date", "")).strip()
        ids = [str(i).strip() for i in entry.get("recipe_ids", []) if str(i).strip()]
        if date and ids:
            wanted.setdefault(date, []).extend(ids)

    if not wanted:
        return {"added": 0, "already_there": 0, "unsupported": [], "days": []}

    dates = sorted(datetime.strptime(d, "%Y-%m-%d").date() for d in wanted)

    added = already = 0
    unsupported = []
    report = []

    async with cookidoo_client() as (cookidoo, _session):
        existing = {}
        for calday in await cookidoo.get_recipes_in_calendar_week(dates[0]):
            existing[calday.id] = {r.id for r in calday.recipes} | set(
                calday.customer_recipe_ids or []
            )

        for date in dates:
            key = date.isoformat()
            here = existing.get(key, set())
            to_add = []
            for rid in dict.fromkeys(wanted[key]):  # de-dupe, keep order
                if rid in here:
                    already += 1
                elif _CATALOGUE_ID.match(rid):
                    to_add.append(rid)
                else:
                    unsupported.append(f"{key}: {rid}")

            if to_add:
                await cookidoo.add_recipes_to_calendar(date, to_add)
                added += len(to_add)
            report.append({"date": key, "added": to_add})

    return {
        "added": added,
        "already_there": already,
        "unsupported": unsupported,
        "days": report,
    }
