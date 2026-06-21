"""Tests for the Ollama client wrapper."""
import pytest
import json


def test_extract_json_parses_clean_json():
    from src.tools.ollama_client import extract_json
    raw = '{"entities": [{"name": "Product", "type": "dimension"}]}'
    result = extract_json(raw)
    assert isinstance(result, dict)
    assert result["entities"][0]["name"] == "Product"


def test_extract_json_handles_markdown_fences():
    from src.tools.ollama_client import extract_json
    raw = '```json\n{"name": "Test"}\n```'
    result = extract_json(raw)
    assert result["name"] == "Test"


def test_extract_json_raises_for_garbage():
    from src.tools.ollama_client import extract_json
    with pytest.raises((ValueError, Exception)):
        extract_json("this is not json at all !!!")
