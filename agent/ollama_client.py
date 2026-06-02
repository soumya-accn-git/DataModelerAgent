import requests
import json
from typing import Optional

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
) -> str:
    """
    Call Ollama /api/chat and return the assistant message content as a string.
    Pass format='json' to request JSON-mode output.
    """
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": 4096,
        },
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
    return json.loads(text)
