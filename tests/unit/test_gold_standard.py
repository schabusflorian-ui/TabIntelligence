"""Tests for gold standard dataset creation."""

import json
import tempfile
from pathlib import Path

import pytest

from scripts.create_gold_standard import (
    create_gold_standard,
    _extract_values_from_result,
    _extract_parsing_from_result,
)


@pytest.fixture
def sample_expected():
    return {
        "description": "Test fixture",
        "model_info": {"file": "test.xlsx", "sheets": 2},
        "expected_triage": [
            {"sheet_name": "IS", "tier": 1, "decision": "PROCESS_HIGH"},
            {"sheet_name": "Notes", "tier": 4, "decision": "SKIP"},
        ],
        "expected_mappings": [
            {"original_label": "Revenue", "canonical_name": "revenue", "sheet": "IS"},
            {"original_label": "COGS", "canonical_name": "cogs", "sheet": "IS"},
        ],
        "acceptable_alternatives": {
            "revenue": ["revenue"],
            "cogs": ["cogs", "cost_of_sales"],
        },
    }


@pytest.fixture
def sample_result():
    return {
        "file": "test.xlsx",
        "timestamp": "2026-03-12T00:00:00Z",
        "sample_line_items": [
            {
                "original_label": "Revenue",
                "canonical_name": "revenue",
                "sheet": "IS",
                "values": {"FY2024": 1000, "FY2025": 1200},
                "provenance": {
                    "parsing": {
                        "is_bold": False,
                        "is_formula": False,
                        "is_subtotal": False,
                        "hierarchy_level": 1,
                    },
                },
            },
            {
                "original_label": "COGS",
                "canonical_name": "cogs",
                "sheet": "IS",
                "values": {"FY2024": -600, "FY2025": -700},
                "provenance": {
                    "parsing": {
                        "is_bold": False,
                        "is_formula": True,
                        "is_subtotal": False,
                        "hierarchy_level": 1,
                    },
                },
            },
        ],
    }


class TestCreateGoldStandard:

    def test_basic_creation(self, sample_expected):
        gold = create_gold_standard(sample_expected)

        assert gold["version"] == "1.0.0"
        assert gold["description"] == "Test fixture"
        assert len(gold["expected_triage"]) == 2
        assert len(gold["expected_mappings"]) == 2
        assert gold["expected_completeness"]["total_min_items"] == 2

    def test_with_result(self, sample_expected, sample_result):
        gold = create_gold_standard(sample_expected, sample_result)

        assert "revenue" in gold["expected_values"]
        assert "cogs" in gold["expected_values"]
        assert gold["expected_values"]["revenue"]["FY2024"]["value"] == 1000
        assert len(gold["expected_parsing"]) == 2
        assert gold["metadata"]["values_verified"] is False

    def test_without_result(self, sample_expected):
        gold = create_gold_standard(sample_expected)

        assert gold["expected_values"] == {}
        assert gold["expected_parsing"] == []

    def test_completeness_per_sheet(self, sample_expected):
        gold = create_gold_standard(sample_expected)

        assert "IS" in gold["expected_completeness"]["statements"]
        assert gold["expected_completeness"]["statements"]["IS"]["min_items"] == 2

    def test_carries_forward_alternatives(self, sample_expected):
        gold = create_gold_standard(sample_expected)

        assert gold["acceptable_alternatives"]["cogs"] == ["cogs", "cost_of_sales"]


class TestExtractValues:

    def test_extracts_numeric_values(self, sample_result):
        values = _extract_values_from_result(sample_result)

        assert "revenue" in values
        assert values["revenue"]["FY2024"]["value"] == 1000
        assert values["revenue"]["FY2024"]["tolerance_pct"] == 1.0

    def test_skips_unmapped(self):
        result = {
            "sample_line_items": [
                {"canonical_name": "unmapped", "values": {"FY2024": 100}},
            ],
        }
        values = _extract_values_from_result(result)
        assert len(values) == 0

    def test_skips_none_values(self):
        result = {
            "sample_line_items": [
                {"canonical_name": "revenue", "values": {"FY2024": None}},
            ],
        }
        values = _extract_values_from_result(result)
        assert "revenue" not in values or "FY2024" not in values.get("revenue", {})


class TestExtractParsing:

    def test_extracts_parsing_attrs(self, sample_result):
        parsing = _extract_parsing_from_result(sample_result)

        assert len(parsing) == 2
        revenue = next(p for p in parsing if p["canonical_name"] == "revenue")
        assert revenue["is_bold"] is False
        cogs = next(p for p in parsing if p["canonical_name"] == "cogs")
        assert cogs["is_formula"] is True

    def test_skips_unmapped(self):
        result = {
            "sample_line_items": [
                {"canonical_name": "unmapped", "provenance": {"parsing": {"is_bold": True}}},
            ],
        }
        parsing = _extract_parsing_from_result(result)
        assert len(parsing) == 0
