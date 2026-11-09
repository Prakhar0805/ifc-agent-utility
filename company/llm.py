# One Gemini client for the colleagues and the judge. Key from GEMINI_API_KEY, never from a file.
import os
import time

import openai

MODEL = os.environ.get("COMPANY_MODEL", "gemini-3.1-flash-lite")
_client = None


def chat(messages):
    global _client
    if _client is None:
        _client = openai.OpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                                api_key=os.environ["GEMINI_API_KEY"], max_retries=10)
    for attempt in range(30):  # free tier: 503 "high demand" for minutes at a time
        try:
            r = _client.chat.completions.create(model=MODEL, messages=messages)
            break
        except (openai.InternalServerError, openai.RateLimitError):
            if attempt == 29:
                raise
            time.sleep(30)
    return (r.choices[0].message.content or "").strip()
