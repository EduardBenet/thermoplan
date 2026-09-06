"""The generate step - turn the prepared inputs into next week's menu via Gemini.

Takes the (possibly hand-edited) prompt from the ``prepare`` step plus the raw
datasets it refers to, and asks the model to fill the week. Returns plain text.
"""
import json
import os

from google import genai

MODEL = "gemini-2.5-flash"


def _block(name, data):
    return f"## `{name}` data\n```json\n{json.dumps(data, ensure_ascii=False)}\n```"


def generate_menu(prompt, history, collections, already_planned):
    """Run the planning prompt through Gemini and return the menu as text.

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
    resp = client.models.generate_content(model=MODEL, contents=contents)
    return resp.text
