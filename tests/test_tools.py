"""Tests for LightWeightChartsMCP server tools."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _run(coro):
    """Run a coroutine in a fresh event loop (Py3.14+ compatible)."""
    return asyncio.new_event_loop().run_until_complete(coro)


@pytest.fixture(scope="session")
def db():
    from core import db as dbmod
    dbmod.get_collection()
    dbmod.build_name_index()
    return dbmod


@pytest.fixture(scope="session")
def collection():
    from core.config import COLLECTION, DB_PATH
    import chromadb
    client = chromadb.PersistentClient(path=DB_PATH)
    return client.get_collection(COLLECTION)


class TestDatabase:
    def test_chromadb_has_entries(self, collection):
        assert collection.count() > 0, "ChromaDB should have entries"


class TestLookup:
    @pytest.mark.parametrize("name", ["createChart", "IChartApi", "ISeriesApi"])
    def test_lookup_found(self, db, name):
        results = db.search_by_name(name)
        assert results is not None
        assert len(results) > 0, f"Lookup for '{name}' should find results"


class TestSearch:
    @pytest.mark.parametrize("query", ["candlestick series", "price scale", "create chart"])
    def test_search_returns_results(self, db, query):
        result = _run(db.query_async(query, n=3))
        metas = result.get("metadatas", [[]])[0] if isinstance(result.get("metadatas"), list) else []
        assert len(metas) > 0, f"Search for '{query}' should return results"


class TestBrowse:
    def test_browse_namespace(self, collection):
        all_meta = collection.get(include=["metadatas"])
        from collections import Counter
        ns_counts = Counter(m.get("namespace", "?") for m in all_meta["metadatas"])
        assert len(ns_counts) > 0, "Should have namespaces"


class TestValidate:
    def test_validate_valid_chart(self):
        from core.validator import call_validator
        code = (
            "import { createChart, CandlestickSeries } from 'lightweight-charts';\n"
            "const chart = createChart(document.getElementById('container'));\n"
            "const series = chart.addSeries(CandlestickSeries);\n"
            "series.setData([{ time: '2024-01-01', open: 100, high: 110, low: 95, close: 105 }]);\n"
            "chart.timeScale().fitContent();"
        )
        result = _run(call_validator(code))
        assert result["success"], f"Valid chart code should pass: {result.get('errors', [])}"

    def test_validate_deprecated_v3_api(self):
        from core.validator import call_validator
        code = (
            "import { createChart } from 'lightweight-charts';\n"
            "const chart = createChart(document.getElementById('container'));\n"
            "const series = chart.addCandlestickSeries();"
        )
        result = _run(call_validator(code))
        warnings = result.get("warnings", [])
        assert any("addCandlestickSeries" in w.get("text", "") for w in warnings), "Should warn about deprecated v3 API"


class TestScaffold:
    def test_scaffold_basic_chart(self):
        from templates.templates import get_template
        code = get_template("basic_chart", "MyChart")
        assert "createChart" in code
        assert "lightweight-charts" in code

    def test_scaffold_react_integration(self):
        from templates.templates import get_template
        code = get_template("react_integration", "MyComponent")
        assert "createChart" in code or "lightweight-charts" in code
