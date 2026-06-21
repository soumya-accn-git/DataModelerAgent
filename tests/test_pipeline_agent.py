"""Tests for the CDM pipeline orchestrator."""
import pytest
from unittest.mock import MagicMock, patch


def test_brd_hash_is_deterministic():
    from src.agents.pipeline_agent import _brd_hash
    text = "Sample BRD content"
    assert _brd_hash(text) == _brd_hash(text)
    assert len(_brd_hash(text)) == 16


def test_brd_hash_differs_for_different_content():
    from src.agents.pipeline_agent import _brd_hash
    assert _brd_hash("text A") != _brd_hash("text B")


def test_cached_domain_returns_none_for_missing_file(tmp_path, monkeypatch):
    from src.agents import pipeline_agent
    monkeypatch.setattr(pipeline_agent, "GENERATED_DIR", str(tmp_path))
    result = pipeline_agent._load_cached_domain("nonexistent_hash")
    assert result is None
