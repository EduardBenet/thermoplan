"""HTTP entry points for Thermoplan's Cloud Functions.

Each planning step is its own module (``prepare`` now; ``generate`` and ``save``
to come) and gets a thin HTTP wrapper here.

The functions are public at the Cloud Run level (Firebase Hosting's rewrite proxy
cannot authenticate to a private 2nd-gen function). Access control is in code:
every request must carry a Firebase ID token for a Google account whose verified
email is on the ``ALLOWED_EMAILS`` list.
"""
import asyncio
import json
import os

from firebase_admin import auth, initialize_app
from firebase_functions import https_fn, options
from firebase_functions.options import set_global_options

from prepare import gather_planning_inputs

initialize_app()

# europe-west1: the user and Cookidoo are both in Europe, and ``prepare`` makes
# ~20 sequential Cookidoo round-trips. max_instances caps a runaway at pennies.
# Region cannot be changed after the first deploy.
set_global_options(region="europe-west1", max_instances=1)


@https_fn.on_request(
    secrets=["COOKIDOO_EMAIL", "COOKIDOO_PASSWORD", "ALLOWED_EMAILS"],
    timeout_sec=120,
    memory=options.MemoryOption.MB_512,
)
def prepare(req: https_fn.Request) -> https_fn.Response:
    """Fetch next week's Cookidoo planning inputs and return them as JSON.

    Requires ``Authorization: Bearer <Firebase ID token>`` for an allowed
    account. Optional ``fantasy`` count (query string or JSON body), default 3.
    The response is the dict from ``gather_planning_inputs`` - history,
    collections, fantasy, and the built prompt - ready for the ``generate`` step.
    """
    if req.method not in ("GET", "POST"):
        return https_fn.Response("Method not allowed", status=405)
    if (denied := _check_caller(req)) is not None:
        return denied

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


def _check_caller(req: https_fn.Request) -> https_fn.Response | None:
    """Reject the request unless it is a signed-in, allow-listed Google account.

    Returns a ``Response`` to send back, or ``None`` when the caller is good.
    """
    header = req.headers.get("Authorization", "")
    token = header[7:] if header.startswith("Bearer ") else None
    if not token:
        return https_fn.Response("Missing bearer token", status=401)
    try:
        claims = auth.verify_id_token(token)
    except Exception:
        return https_fn.Response("Invalid token", status=401)

    allowed = {
        e.strip().lower()
        for e in os.environ.get("ALLOWED_EMAILS", "").split(",")
        if e.strip()
    }
    email = (claims.get("email") or "").lower()
    if not claims.get("email_verified") or email not in allowed:
        return https_fn.Response("Not authorised", status=403)
    return None


def _fantasy_count(req: https_fn.Request) -> int:
    """The requested fantasy-recipe count, from query string or JSON body."""
    raw = req.args.get("fantasy")
    if raw is None:
        raw = (req.get_json(silent=True) or {}).get("fantasy")
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 3
