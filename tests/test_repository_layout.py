import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("DATABASE_URL", "")

from app.dashboard_main import app
from app import dashboard_main


def test_application_routes_are_registered():
    paths = {route.path for route in app.routes}
    assert {
        "/",
        "/datastatus",
        "/compare",
        "/api/search",
        "/api/diagnostics",
        "/api/kpis",
        "/static",
    }.issubset(paths)


def test_template_and_static_directories_exist():
    assert (PROJECT_ROOT / "templates" / "index.html").is_file()
    assert (PROJECT_ROOT / "templates" / "datastatus.html").is_file()
    assert (PROJECT_ROOT / "templates" / "compare.html").is_file()
    assert (PROJECT_ROOT / "static").is_dir()


def test_quarter_ids_resolve_to_calendar_quarter_ends():
    assert dashboard_main.quarter_end_for_id("2026Q2").date() == date(2026, 6, 30)
    assert dashboard_main.quarter_id_for_end_date(date(2026, 6, 30)) == "2026Q2"
    assert dashboard_main.quarter_id_for_end_date(date(2026, 6, 29)) is None


def test_quarter_comparison_calculates_position_status_and_deltas(monkeypatch):
    rows = [
        {
            "fund_name": "Fund A",
            "isin": "SE0000000001",
            "security_name": "New",
            "previous_exists": False,
            "current_exists": True,
            "previous_market_value_sek": None,
            "current_market_value_sek": Decimal("500"),
            "previous_weight": None,
            "current_weight": Decimal("0.10"),
            "total_count": 8,
        },
        {
            "fund_name": "Fund A",
            "isin": "SE0000000002",
            "security_name": "Increased",
            "previous_exists": True,
            "current_exists": True,
            "previous_market_value_sek": Decimal("100"),
            "current_market_value_sek": Decimal("120"),
            "previous_weight": Decimal("0.20"),
            "current_weight": Decimal("0.30"),
            "total_count": 8,
        },
        {
            "fund_name": "Fund A",
            "isin": "SE0000000003",
            "security_name": "Decreased",
            "previous_exists": True,
            "current_exists": True,
            "previous_market_value_sek": Decimal("300"),
            "current_market_value_sek": Decimal("250"),
            "previous_weight": Decimal("0.30"),
            "current_weight": Decimal("0.20"),
            "total_count": 8,
        },
        {
            "fund_name": "Fund A",
            "isin": "SE0000000004",
            "security_name": "Exited",
            "previous_exists": True,
            "current_exists": False,
            "previous_market_value_sek": Decimal("10"),
            "current_market_value_sek": None,
            "previous_weight": Decimal("0.10"),
            "current_weight": None,
            "total_count": 8,
        },
    ]

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, _query, params):
            assert params["limit"] == 4
            assert params["offset"] == 4
            assert params["previous_date"] == date(2026, 3, 31)
            assert params["current_date"] == date(2026, 6, 30)
            return SimpleNamespace(
                mappings=lambda: SimpleNamespace(all=lambda: rows)
            )

    monkeypatch.setattr(dashboard_main, "DB_CONNECTED", True)
    monkeypatch.setattr(
        dashboard_main,
        "engine",
        SimpleNamespace(connect=FakeConnection),
    )

    result = dashboard_main.get_quarter_comparison(
        "2026Q1",
        "2026Q2",
        {"2026Q1": date(2026, 3, 31), "2026Q2": date(2026, 6, 30)},
        page=2,
        page_size=4,
    )

    assert result["total_count"] == 8
    assert [item["status"] for item in result["items"]] == [
        "Ny position",
        "Ökad position",
        "Minskad position",
        "Avslutad position",
    ]
    assert result["items"][1]["weight_change"] == Decimal("0.10")
    assert result["items"][1]["market_value_change_sek"] == Decimal("20")
    assert result["items"][2]["market_value_change_sek"] == Decimal("-50")
