#!/usr/bin/env python3
"""Example script for cookidoo-api."""
import os, aiohttp, asyncio
from dotenv import load_dotenv

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

        print(subscription)

asyncio.run(main())