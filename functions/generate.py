"""The generate step - turn the prepared inputs into next week's menu via Gemini.

Takes the (possibly hand-edited) prompt from the ``prepare`` step plus the raw
datasets it refers to, and asks the model to fill the week. Returns structured
data: ``{"days": [{"date", "weekday", "meals": [{meal, recipe_name, recipe_id,
source, note}]}]}``.
"""
import json
import os

from google import genai
from google.genai import types

MODEL = "gemini-3.6-flash"

MENU_SCHEMA = {
    "type": "object",
    "properties": {
        "days": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "ISO date, YYYY-MM-DD"},
                    "weekday": {"type": "string"},
                    "meals": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "meal": {
                                    "type": "string",
                                    "description": "lunch, dinner, starter, extra, ...",
                                },
                                "recipe_name": {"type": "string"},
                                "recipe_id": {"type": "string"},
                                "source": {
                                    "type": "string",
                                    "enum": [
                                        "already_planned",
                                        "history",
                                        "collections",
                                        "fantasy",
                                        "other",
                                    ],
                                },
                                "note": {"type": "string"},
                            },
                            "required": ["meal", "recipe_name", "source"],
                        },
                    },
                },
                "required": ["date", "weekday", "meals"],
            },
        }
    },
    "required": ["days"],
}


def _block(name, data):
    return f"## `{name}` data\n```json\n{json.dumps(data, ensure_ascii=False)}\n```"


def generate_menu(prompt, history, collections, already_planned):
    """Run the planning prompt through Gemini and return the menu as a dict.

    Requires ``GEMINI_API_KEY`` in the environment (bound as a secret).
    """
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    contents = "\n\n".join(
        [
            prompt,
            _block("already_planned", already_planned),
            _block("history", history),
            _block("collections", collections),
        ]
    )
    resp = client.models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=MENU_SCHEMA,
        ),
    )

    if resp.text:
        return json.loads(resp.text)

    # No text part - safety block, recitation, token limit, ...
    reason = None
    try:
        reason = resp.candidates[0].finish_reason
    except (AttributeError, IndexError, TypeError):
        pass
    raise RuntimeError(f"the model returned no menu (finish_reason={reason})")
