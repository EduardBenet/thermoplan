"""A logged-in Cookidoo client, shared by the steps that need one.

The deployed function has a read-only filesystem, so there is no cookie file to
reuse - every call logs in fresh. ``COOKIDOO_EMAIL`` / ``COOKIDOO_PASSWORD`` must
be in the environment (bound as secrets on the function).
"""
import os
from contextlib import asynccontextmanager

import aiohttp

from cookidoo_api import Cookidoo
from cookidoo_api.helpers import get_localization_options
from cookidoo_api.types import CookidooConfig


@asynccontextmanager
async def cookidoo_client():
    """Yield ``(cookidoo, session)`` inside an open aiohttp session."""
    jar = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(cookie_jar=jar) as session:
        cookidoo = Cookidoo(
            session,
            cfg=CookidooConfig(
                email=os.environ["COOKIDOO_EMAIL"],
                password=os.environ["COOKIDOO_PASSWORD"],
                localization=(
                    await get_localization_options(country="ie", language="en-GB")
                )[0],
            ),
        )
        await cookidoo.login()
        await cookidoo.get_user_info()
        yield cookidoo, session
