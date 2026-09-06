"""HTTP entry points for Thermoplan's Cloud Functions.

Each planning step is its own module (``prepare`` now; ``generate`` and ``save``
to come) and gets a thin HTTP wrapper here.

The functions are public at the Cloud Run level (Firebase Hosting's rewrite proxy
cannot authenticate to a private 2nd-gen function). Access control is in code:
every request must carry a Firebase ID token for a Google account that has the
``access`` custom claim (granted with ``set_access.py``).
"""
import asyncio
import json

from firebase_admin import auth, initialize_app
from firebase_functions import https_fn, options
from firebase_functions.options import set_global_options

from generate import generate_menu
from prepare import gather_planning_inputs
from save import save_menu

initialize_app()

# europe-west1: the user and Cookidoo are both in Europe, and ``prepare`` makes
# ~20 sequential Cookidoo round-trips. max_instances caps a runaway at pennies.
# Region cannot be changed after the first deploy.
set_global_options(region="europe-west1", max_instances=1)


@https_fn.on_request(
    secrets=["COOKIDOO_EMAIL", "COOKIDOO_PASSWORD"],
    timeout_sec=120,
    memory=options.MemoryOption.MB_512,
    # Cloud Run must accept the unauthenticated call from Hosting's rewrite proxy;
    # _check_caller does the real access control (Firebase token + access claim).
    invoker="public",
)
def prepare(req: https_fn.Request) -> https_fn.Response:
    """Fetch next week's Cookidoo planning inputs and return them as JSON.

    Requires ``Authorization: Bearer <Firebase ID token>`` for an allowed
    account. Optional planning knobs (query string or JSON body): ``weeks_ahead``
    (1 = next week), ``fantasy_count``, ``years_back``, ``window_weeks``,
    ``max_minutes``, ``collection``. The response is the dict from
    ``gather_planning_inputs`` - history, collections, prompt - for ``generate``.
    """
    if req.method not in ("GET", "POST"):
        return https_fn.Response("Method not allowed", status=405)
    if (denied := _check_caller(req)) is not None:
        return denied

    try:
        data = asyncio.run(gather_planning_inputs(**_params(req)))
    except KeyError as err:
        # A secret / env var is missing
        return https_fn.Response(f"Missing configuration: {err}", status=500)
    except Exception as err:  # Cookidoo login and the For You endpoint are flaky
        return https_fn.Response(f"Planning fetch failed: {err}", status=502)

    return https_fn.Response(
        json.dumps(data, ensure_ascii=False),
        content_type="application/json; charset=utf-8",
    )


@https_fn.on_request(
    secrets=["GEMINI_API_KEY"],
    timeout_sec=180,
    memory=options.MemoryOption.MB_512,
    invoker="public",
)
def generate(req: https_fn.Request) -> https_fn.Response:
    """Turn the prepared inputs into next week's menu via Gemini.

    POST body: ``prompt`` (the edited planning prompt) plus the datasets it
    refers to - ``history``, ``collections``, ``already_planned``. Returns
    ``{"menu": "<text>"}``.
    """
    if req.method != "POST":
        return https_fn.Response("Method not allowed", status=405)
    if (denied := _check_caller(req)) is not None:
        return denied

    body = req.get_json(silent=True) or {}
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        return https_fn.Response("Missing prompt", status=400)

    try:
        menu = generate_menu(
            prompt,
            body.get("history", []),
            body.get("collections", []),
            body.get("already_planned", []),
        )
    except KeyError as err:
        return https_fn.Response(f"Missing configuration: {err}", status=500)
    except Exception as err:
        return https_fn.Response(f"Generation failed: {err}", status=502)

    return https_fn.Response(
        json.dumps({"menu": menu}, ensure_ascii=False),
        content_type="application/json; charset=utf-8",
    )


@https_fn.on_request(
    secrets=["COOKIDOO_EMAIL", "COOKIDOO_PASSWORD"],
    timeout_sec=120,
    memory=options.MemoryOption.MB_512,
    invoker="public",
)
def save(req: https_fn.Request) -> https_fn.Response:
    """Write the finalised menu into the Cookidoo calendar (add-only).

    POST body: ``days`` - ``[{"date": "YYYY-MM-DD", "recipe_ids": [...]}, ...]``.
    Returns ``{"added", "already_there", "unsupported", "days"}``.
    """
    if req.method != "POST":
        return https_fn.Response("Method not allowed", status=405)
    if (denied := _check_caller(req)) is not None:
        return denied

    days = (req.get_json(silent=True) or {}).get("days")
    if not isinstance(days, list) or not days:
        return https_fn.Response("Missing days", status=400)

    try:
        result = asyncio.run(save_menu(days))
    except KeyError as err:
        return https_fn.Response(f"Missing configuration: {err}", status=500)
    except Exception as err:
        return https_fn.Response(f"Save failed: {err}", status=502)

    return https_fn.Response(
        json.dumps(result, ensure_ascii=False),
        content_type="application/json; charset=utf-8",
    )


def _check_caller(req: https_fn.Request) -> https_fn.Response | None:
    """Reject the request unless it carries a valid ID token with ``access``.

    ``check_revoked`` makes a disabled account or a revoked session lose access
    immediately rather than at token expiry. The ``access`` custom claim is
    granted per user with ``set_access.py`` - the policy lives in Firebase Auth,
    not in an env var.

    Returns a ``Response`` to send back, or ``None`` when the caller is good.
    """
    header = req.headers.get("Authorization", "")
    token = header[7:] if header.startswith("Bearer ") else None
    if not token:
        return https_fn.Response("Missing bearer token", status=401)
    try:
        claims = auth.verify_id_token(token, check_revoked=True)
    except Exception:
        return https_fn.Response("Invalid token", status=401)

    if not claims.get("access"):
        return https_fn.Response("Not authorised", status=403)
    return None


def _params(req: https_fn.Request) -> dict:
    """Planning knobs from the query string or JSON body, clamped to sane ranges.

    Anything missing or unparseable falls through to ``gather_planning_inputs``'s
    own defaults (so it is simply left out of the returned dict).
    """
    body = req.get_json(silent=True) or {}
    out: dict = {}

    def clamp(key, lo, hi):
        raw = req.args.get(key, body.get(key))
        if raw is None or raw == "":
            return
        try:
            out[key] = max(lo, min(hi, int(raw)))
        except (TypeError, ValueError):
            pass

    clamp("fantasy_count", 0, 20)
    clamp("years_back", 1, 6)
    clamp("window_weeks", 0, 8)
    clamp("max_minutes", 10, 600)
    clamp("weeks_ahead", 1, 8)

    collection = req.args.get("collection", body.get("collection"))
    if isinstance(collection, str):
        out["collection"] = collection.strip() or None

    return out
