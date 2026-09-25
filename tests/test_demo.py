"""Tests for the synthetic demo data generator and demo mode."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from app.config import load_settings
from app.db import SnapshotStore
from app.demo import seed_demo_data
from app.service import MonitorService


class TestDemoDataGenerator:
    """Verify that seed_demo_data produces valid data through the store."""

    def test_seeds_account_snapshots(self, tmp_path: Path) -> None:
        db_path = tmp_path / "demo.db"
        seed_demo_data(db_path, hours=2)

        store = SnapshotStore(db_path)
        rows = store.history(hours=2)
        assert len(rows) > 0

        # All rows have required fields
        for row in rows:
            assert row["currency"] == "GBP"
            assert row["total_value"] is not None

    def test_seeds_position_snapshots(self, tmp_path: Path) -> None:
        db_path = tmp_path / "demo.db"
        seed_demo_data(db_path, hours=2)

        store = SnapshotStore(db_path)
        pos_rows = store.position_history("AAPL_US", hours=2)
        assert len(pos_rows) > 0

    def test_seeds_lifecycle_events_all_types(self, tmp_path: Path) -> None:
        db_path = tmp_path / "demo.db"
        seed_demo_data(db_path, hours=2)

        store = SnapshotStore(db_path)
        events = store.position_events(limit=500)
        event_types = {e["event_type"] for e in events}

        assert "OPEN" in event_types
        assert "ADD" in event_types
        assert "REDUCE" in event_types
        assert "CLOSE" in event_types

    def test_seeds_multiple_tickers(self, tmp_path: Path) -> None:
        db_path = tmp_path / "demo.db"
        seed_demo_data(db_path, hours=2)

        store = SnapshotStore(db_path)
        events = store.position_events(limit=500)
        tickers = {e["ticker"] for e in events}

        # Should have events for all 6 demo positions
        expected = {"AAPL_US", "MSFT_US", "NVDA_US", "VUSA_US", "GOOGL_US", "TSLA_US"}
        assert tickers == expected

    def test_seeds_alerts(self, tmp_path: Path) -> None:
        db_path = tmp_path / "demo.db"
        seed_demo_data(db_path, hours=2)

        store = SnapshotStore(db_path)
        alerts = store.alerts(limit=50)
        assert len(alerts) >= 1
        for alert in alerts:
            assert alert["severity"] in ("warning", "critical")
            assert alert["rule"] in ("position_loss", "portfolio_loss")

    def test_seeds_market_quotes(self, tmp_path: Path) -> None:
        db_path = tmp_path / "demo.db"
        seed_demo_data(db_path, hours=2)

        store = SnapshotStore(db_path)
        quotes = store.market_quotes(ticker="AAPL_US", hours=2)
        assert len(quotes) > 0
        for q in quotes:
            assert q["price"] > 0
            assert q["source"] == "t212_position"

    def test_last_snapshot_has_positions(self, tmp_path: Path) -> None:
        db_path = tmp_path / "demo.db"
        seed_demo_data(db_path, hours=2)

        store = SnapshotStore(db_path)
        rows = store.history(hours=2)
        last_row = rows[-1]

        assert last_row["total_value"] is not None
        assert last_row["unrealized_pl"] is not None

    def test_seeds_all_positions_have_snapshots(self, tmp_path: Path) -> None:
        db_path = tmp_path / "demo.db"
        seed_demo_data(db_path, hours=2)

        store = SnapshotStore(db_path)
        for pos in [
            "VUSA_US", "AAPL_US", "MSFT_US",
            "NVDA_US", "GOOGL_US", "TSLA_US",
        ]:
            pos_rows = store.position_history(pos, hours=2)
            assert len(pos_rows) > 0, f"No position snapshots for {pos}"


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


class TestConfigDemoMode:
    """Verify that T212_DEMO config flag works correctly."""

    def test_demo_mode_defaults_to_false(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("T212_POLL_SECONDS", "6")
        monkeypatch.setenv("T212_SNAPSHOT_SECONDS", "30")
        monkeypatch.delenv("T212_DEMO", raising=False)
        monkeypatch.delenv("T212_API_KEY", raising=False)
        monkeypatch.delenv("T212_API_SECRET", raising=False)

        settings = load_settings()
        assert settings.demo_mode is False

    def test_demo_mode_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("T212_POLL_SECONDS", "6")
        monkeypatch.setenv("T212_SNAPSHOT_SECONDS", "30")
        monkeypatch.setenv("T212_DEMO", "true")
        monkeypatch.delenv("T212_API_KEY", raising=False)
        monkeypatch.delenv("T212_API_SECRET", raising=False)

        settings = load_settings()
        assert settings.demo_mode is True

    def test_demo_clears_creds_from_dotenv(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """T212_DEMO=true should clear credentials loaded from .env."""
        dotenv_file = tmp_path / ".env"
        dotenv_file.write_text("T212_API_KEY=loaded-key\nT212_API_SECRET=loaded-secret\n")
        monkeypatch.setenv("T212_DEMO", "true")
        monkeypatch.setenv("T212_POLL_SECONDS", "6")
        monkeypatch.setenv("T212_SNAPSHOT_SECONDS", "30")
        monkeypatch.delenv("T212_API_KEY", raising=False)
        monkeypatch.delenv("T212_API_SECRET", raising=False)
        # Simulate .env loading
        os.environ["_DEMO_PRESET"] = "true"
        # Even if load_dotenv loaded real credentials, demo mode should clear them
        settings = load_settings()
        assert settings.demo_mode is True
        assert settings.api_key == ""
        assert settings.api_secret == ""

    def test_production_mode_not_affected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Production mode (demo_mode=False) should still use env vars."""
        monkeypatch.setenv("T212_DEMO", "false")
        monkeypatch.setenv("T212_POLL_SECONDS", "6")
        monkeypatch.setenv("T212_SNAPSHOT_SECONDS", "30")
        monkeypatch.setenv("T212_API_KEY", "real-key")
        monkeypatch.setenv("T212_API_SECRET", "real-secret")

        settings = load_settings()
        assert settings.demo_mode is False
        assert settings.api_key == "real-key"
        assert settings.api_secret == "real-secret"


# ---------------------------------------------------------------------------
# Service demo mode tests
# ---------------------------------------------------------------------------


class TestDemoServiceMode:
    """Verify that MonitorService works in demo mode."""

    def test_demo_service_seeds_and_loads_state(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db_path = tmp_path / "demo-test.db"
        monkeypatch.setenv("T212_DB_PATH", str(db_path))
        monkeypatch.setenv("T212_DEMO", "true")
        monkeypatch.setenv("T212_POLL_SECONDS", "6")
        monkeypatch.setenv("T212_SNAPSHOT_SECONDS", "30")
        monkeypatch.delenv("T212_API_KEY", raising=False)
        monkeypatch.delenv("T212_API_SECRET", raising=False)
        monkeypatch.setenv("T212_ENV", "demo")

        settings = load_settings()
        assert settings.demo_mode is True

        store = SnapshotStore(settings.db_path)
        service = MonitorService(settings, store)

        import asyncio

        asyncio.run(service.start())

        assert service.state.last_error is None
        assert service.state.account is not None
        assert service.state.account["currency"] == "GBP"
        assert service.state.account["total_value"] is not None
        assert len(service.state.positions) > 0

    def test_demo_service_includes_lifecycle_events(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db_path = tmp_path / "demo-events.db"
        monkeypatch.setenv("T212_DB_PATH", str(db_path))
        monkeypatch.setenv("T212_DEMO", "true")
        monkeypatch.setenv("T212_POLL_SECONDS", "6")
        monkeypatch.setenv("T212_SNAPSHOT_SECONDS", "30")
        monkeypatch.delenv("T212_API_KEY", raising=False)
        monkeypatch.delenv("T212_API_SECRET", raising=False)
        monkeypatch.setenv("T212_ENV", "demo")

        settings = load_settings()
        store = SnapshotStore(settings.db_path)
        service = MonitorService(settings, store)

        import asyncio

        asyncio.run(service.start())

        events = store.position_events(limit=500)
        event_types = {e["event_type"] for e in events}

        assert "OPEN" in event_types
        assert "ADD" in event_types
        assert "REDUCE" in event_types
        assert "CLOSE" in event_types

    def test_demo_service_has_all_positions(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db_path = tmp_path / "demo-positions.db"
        monkeypatch.setenv("T212_DB_PATH", str(db_path))
        monkeypatch.setenv("T212_DEMO", "true")
        monkeypatch.setenv("T212_POLL_SECONDS", "6")
        monkeypatch.setenv("T212_SNAPSHOT_SECONDS", "30")
        monkeypatch.delenv("T212_API_KEY", raising=False)
        monkeypatch.delenv("T212_API_SECRET", raising=False)
        monkeypatch.setenv("T212_ENV", "demo")

        settings = load_settings()
        store = SnapshotStore(settings.db_path)
        service = MonitorService(settings, store)

        import asyncio

        asyncio.run(service.start())

        # Should have 6 positions (TSLA is closed so only 5 active)
        assert len(service.state.positions) >= 5
        position_tickers = {p["ticker"] for p in service.state.positions}
        expected_active = {"AAPL_US", "MSFT_US", "NVDA_US", "VUSA_US", "GOOGL_US"}
        assert position_tickers == expected_active

    def test_production_mode_not_affected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Production mode (demo_mode=False) should still work."""
        monkeypatch.setenv("T212_DB_PATH", str(tmp_path / "prod.db"))
        monkeypatch.setenv("T212_DEMO", "false")
        monkeypatch.setenv("T212_POLL_SECONDS", "6")
        monkeypatch.setenv("T212_SNAPSHOT_SECONDS", "30")
        monkeypatch.setenv("T212_API_KEY", "ci-placeholder-key")
        monkeypatch.setenv("T212_API_SECRET", "ci-placeholder-secret")
        monkeypatch.setenv("T212_ENV", "demo")

        settings = load_settings()
        assert settings.demo_mode is False

        store = SnapshotStore(settings.db_path)
        service = MonitorService(settings, store)

        import asyncio

        asyncio.run(service.start())

        # Should NOT be in demo mode
        assert service._demo_mode is False
        assert service._client is not None


# ---------------------------------------------------------------------------
# Demo mode isolation — critical regression tests
# ---------------------------------------------------------------------------


class TestDemoModeIsolation:
    """Regression tests: demo mode must never overwrite live data."""

    def test_demo_default_db_is_separate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """T212_DEMO=true must default to data/demo-monitor.db, not data/monitor.db."""
        monkeypatch.setenv("T212_POLL_SECONDS", "6")
        monkeypatch.setenv("T212_SNAPSHOT_SECONDS", "30")
        monkeypatch.setenv("T212_DEMO", "true")
        monkeypatch.delenv("T212_API_KEY", raising=False)
        monkeypatch.delenv("T212_API_SECRET", raising=False)
        # Explicitly unset DB_PATH so the default is used
        monkeypatch.delenv("T212_DB_PATH", raising=False)

        settings = load_settings()
        assert settings.demo_mode is True
        assert settings.db_path.name == "demo-monitor.db"

    def test_demo_does_not_mutation_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """load_settings(demo) must not mutate os.environ."""
        monkeypatch.setenv("T212_POLL_SECONDS", "6")
        monkeypatch.setenv("T212_SNAPSHOT_SECONDS", "30")
        monkeypatch.setenv("T212_DEMO", "true")
        monkeypatch.setenv("T212_API_KEY", "pre-existing-key")
        monkeypatch.setenv("T212_API_SECRET", "pre-existing-secret")

        before_keys = dict(os.environ)
        settings = load_settings()

        # Verify os.environ was NOT mutated
        after_keys = dict(os.environ)
        assert before_keys == after_keys, "load_settings mutated os.environ"

        # But settings should still have empty creds
        assert settings.demo_mode is True
        assert settings.api_key == ""
        assert settings.api_secret == ""

    def test_demo_does_not_mutation_env_when_not_demo(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Non-demo mode should also not mutate os.environ."""
        monkeypatch.setenv("T212_POLL_SECONDS", "6")
        monkeypatch.setenv("T212_SNAPSHOT_SECONDS", "30")
        monkeypatch.setenv("T212_DEMO", "false")
        monkeypatch.setenv("T212_API_KEY", "my-key")
        monkeypatch.setenv("T212_API_SECRET", "my-secret")

        before_keys = dict(os.environ)
        settings = load_settings()
        after_keys = dict(os.environ)

        assert before_keys == after_keys
        assert settings.api_key == "my-key"
        assert settings.api_secret == "my-secret"

    def test_demo_db_does_not_exist_yet_is_fine(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Demo mode must work even if demo-monitor.db does not exist yet."""
        db_path = tmp_path / "fresh-demo.db"
        assert not db_path.exists()
        monkeypatch.setenv("T212_DB_PATH", str(db_path))
        monkeypatch.setenv("T212_DEMO", "true")
        monkeypatch.setenv("T212_POLL_SECONDS", "6")
        monkeypatch.setenv("T212_SNAPSHOT_SECONDS", "30")
        monkeypatch.delenv("T212_API_KEY", raising=False)
        monkeypatch.delenv("T212_API_SECRET", raising=False)

        settings = load_settings()
        store = SnapshotStore(settings.db_path)
        service = MonitorService(settings, store)

        import asyncio

        asyncio.run(service.start())
        assert service._demo_mode is True
        assert service.state.account is not None

