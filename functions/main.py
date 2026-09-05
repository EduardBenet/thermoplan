"""HTTP entry points for Thermoplan's Cloud Functions.

Each planning step is its own module (``prepare`` now; ``generate`` and ``save``
to come) and gets a thin HTTP wrapper here.
"""
import asyncio
import json

from firebase_functions import https_fn, options
from firebase_functions.options import set_global_options

from prepare import gather_planning_inputs

# europe-west1: the user and Cookidoo are both in Europe, and ``prepare`` makes
# ~20 sequential Cookidoo round-trips. max_instances caps a runaway at pennies.
# Region cannot be changed after the first deploy.
set_global_options(region="europe-west1", max_instances=1)


@https_fn.on_request(
    secrets=["COOKIDOO_EMAIL", "COOKIDOO_PASSWORD"],
    timeout_sec=120,
    memory=options.MemoryOption.MB_512,
    cors=options.CorsOptions(cors_origins="*", cors_methods=["get", "post"]),
)
def prepare(req: https_fn.Request) -> https_fn.Response:
    """Fetch next week's Cookidoo planning inputs and return them as JSON.

    Optional ``fantasy`` count (query string or JSON body), default 3. The
    response is the dict from ``gather_planning_inputs`` - history, collections,
    fantasy, and the built prompt - ready to hand to the ``generate`` step.
    """
    if req.method not in ("GET", "POST"):
        return https_fn.Response("Method not allowed", status=405)

    try:
        data = asyncio.run(gather_planning_inputs(_fantasy_count(req)))
    except KeyError as err:
        # A secret / env var is missing
        return https_fn.Response(f"Missing configuration: {err}", status=500)
    except Exception as err:  # Cookidoo login and the For You endpoint are flaky
        return https_fn.Response(f"Planning fetch failed: {err}", status=502)

    return https_fn.Response(
        json.dumps(data, ensure_ascii=False),
        content_type="application/json; charset=utf-8",
    )


def _fantasy_count(req: https_fn.Request) -> int:
    """The requested fantasy-recipe count, from query string or JSON body."""
    raw = req.args.get("fantasy")
    if raw is None:
        raw = (req.get_json(silent=True) or {}).get("fantasy")
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 3
