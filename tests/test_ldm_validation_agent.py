"""Tests for the LDM validation agent."""
import pytest


def test_import():
    from src.agents.ldm_validation_agent import run_validation_agent, run_with_repair
    assert callable(run_validation_agent)
    assert callable(run_with_repair)


def test_structural_check_catches_missing_prefix():
    from src.agents.ldm_validation_agent import _check_structural

    ldm = {
        "dimension_tables": [{"table_name": "Product", "columns": []}],
        "fact_tables": [],
    }
    issues = _check_structural(ldm)
    assert isinstance(issues, list)
    assert any("DIM_" in str(i) or "prefix" in str(i).lower() for i in issues)
