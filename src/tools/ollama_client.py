import os
import requests
import json
from typing import Optional

# Generation defaults. These are read at call time (not import time) so a
# config.py / .env override that sets the env var is always respected,
# regardless of import order.
#   num_ctx     — input context window. Ollama's default (~4096) silently
#                 truncates a long BRD + the SKILL.md system prompt, so the
#                 model never sees most of the document. We raise it sharply.
#   num_predict — max output tokens. Too low truncates the entity/relationship
#                 JSON mid-stream and the whole pass is lost on parse failure.
_DEFAULT_NUM_CTX     = 32768
_DEFAULT_NUM_PREDICT = 8192


def list_models(base_url: str) -> list[str]:
    """Return list of locally available Ollama model names."""
    resp = requests.get(f"{base_url}/api/tags", timeout=5)
    resp.raise_for_status()
    data = resp.json()
    return [m["name"] for m in data.get("models", [])]


def chat(
    base_url: str,
    model: str,
    messages: list[dict],
    temperature: float = 0.1,
    format: Optional[str] = None,
    num_ctx: Optional[int] = None,
    num_predict: Optional[int] = None,
    seed: Optional[int] = None,
) -> str:
    """
    Call Ollama /api/chat and return the assistant message content as a string.
    Pass format='json' to request JSON-mode output.

    num_ctx / num_predict default to OLLAMA_NUM_CTX / OLLAMA_NUM_PREDICT env
    vars (falling back to 32768 / 8192). Setting num_ctx is critical: without
    it Ollama uses a small default window and silently drops most of the input.

    seed — fixes Ollama's RNG so the same prompt yields the same output on every
    run. Without it, classification (entity types, etc.) drifts run-to-run even
    at temperature 0. Defaults to OLLAMA_SEED env var (falling back to 42).
    Pass seed=-1 to explicitly opt out (random each call).
    """
    nc = num_ctx if num_ctx is not None else int(
        os.environ.get("OLLAMA_NUM_CTX", _DEFAULT_NUM_CTX))
    npred = num_predict if num_predict is not None else int(
        os.environ.get("OLLAMA_NUM_PREDICT", _DEFAULT_NUM_PREDICT))
    sd = seed if seed is not None else int(os.environ.get("OLLAMA_SEED", 42))

    options = {
        "temperature": temperature,
        "num_ctx": nc,
        "num_predict": npred,
    }
    if sd is not None and sd >= 0:
        options["seed"] = sd

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": options,
    }
    if format:
        payload["format"] = format

    resp = requests.post(
        f"{base_url}/api/chat",
        json=payload,
        timeout=1800,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["message"]["content"]


def extract_json(raw: str) -> dict | list:
    """
    Robustly parse JSON from LLM output.
    Handles markdown code fences and leading/trailing whitespace.
    """
    text = raw.strip()
    # Strip ```json ... ``` or ``` ... ```
    if text.startswith("```"):
        lines = text.splitlines()
        # Drop first and last fence lines
        inner = lines[1:] if lines[0].startswith("```") else lines
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        text = "\n".join(inner).strip()

    # Find the first { or [ and last } or ]
    start = min(
        (text.find("{") if "{" in text else len(text)),
        (text.find("[") if "[" in text else len(text)),
    )
    if start == len(text):
        raise ValueError(f"No JSON object found in LLM output:\n{raw[:500]}")
    text = text[start:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Output was likely truncated mid-stream (num_predict cap). Rather than
        # discard the whole pass, salvage the complete objects extracted so far.
        salvaged = _salvage_truncated_json(text)
        if salvaged is not None:
            return salvaged
        raise


def _salvage_truncated_json(text: str):
    """
    Recover a usable object from truncated JSON — typically an array of objects
    cut off mid-element. Strategy: trim to the last complete '}' (dropping any
    partial trailing object), drop a dangling comma, then re-close any still-open
    brackets/braces. Returns the parsed value, or None if unrecoverable.
    """
    last_obj_end = text.rfind("}")
    if last_obj_end == -1:
        return None
    candidate = text[:last_obj_end + 1]

    stack = []
    in_str = False
    esc = False
    for ch in candidate:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append(ch)
        elif ch == "}":
            if stack and stack[-1] == "{":
                stack.pop()
        elif ch == "]":
            if stack and stack[-1] == "[":
                stack.pop()

    candidate = candidate.rstrip()
    if candidate.endswith(","):
        candidate = candidate[:-1]
    closers = "".join("}" if c == "{" else "]" for c in reversed(stack))
    try:
        return json.loads(candidate + closers)
    except json.JSONDecodeError:
        return None
