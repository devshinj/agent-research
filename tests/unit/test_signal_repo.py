import pytest

from src.repository.database import Database
from src.repository.signal_repo import SignalRepository


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
async def signal_repo(db):
    return SignalRepository(db)


async def test_save_and_get_recent(signal_repo):
    await signal_repo.save("KRW-BTC", "BUY", 0.75, 1700000000)
    await signal_repo.save("KRW-ETH", "HOLD", 0.55, 1700000001)
    await signal_repo.save("KRW-BTC", "SELL", 0.68, 1700000002)

    # Default: exclude HOLD
    results = await signal_repo.get_recent(limit=10)
    assert len(results) == 2
    assert results[0]["signal_type"] == "SELL"  # newest first
    assert results[1]["signal_type"] == "BUY"

    # Include HOLD
    results_all = await signal_repo.get_recent(limit=10, include_hold=True)
    assert len(results_all) == 3


async def test_get_stats_by_market(signal_repo):
    await signal_repo.save("KRW-BTC", "BUY", 0.80, 1700000000)
    await signal_repo.save("KRW-BTC", "HOLD", 0.55, 1700000001)
    await signal_repo.save("KRW-BTC", "HOLD", 0.52, 1700000002)
    await signal_repo.save("KRW-BTC", "SELL", 0.70, 1700000003)

    stats = await signal_repo.get_stats_by_market("KRW-BTC")
    assert stats["total_signals"] == 4
    assert stats["buy_count"] == 1
    assert stats["sell_count"] == 1
    assert stats["hold_count"] == 2
    assert 0.64 < stats["avg_confidence"] < 0.65  # (0.80+0.55+0.52+0.70)/4


async def test_get_stats_empty_market(signal_repo):
    stats = await signal_repo.get_stats_by_market("KRW-NONE")
    assert stats["total_signals"] == 0
    assert stats["buy_count"] == 0
    assert stats["sell_count"] == 0
    assert stats["hold_count"] == 0
    assert stats["avg_confidence"] == 0.0


import json


async def test_save_and_get_with_basis(signal_repo):
    basis_json = json.dumps([
        {"feature": "rsi_14", "shap": 0.15, "value": 72.3},
        {"feature": "volume_ratio_5m", "shap": 0.12, "value": 2.4},
    ])
    await signal_repo.save("KRW-BTC", "BUY", 0.82, 1700000000, basis_json)
    await signal_repo.save("KRW-ETH", "SELL", 0.65, 1700000001, None)

    results = await signal_repo.get_recent(limit=10)
    assert len(results) == 2

    # KRW-ETH is newer
    assert results[0]["basis"] is None
    # KRW-BTC has basis
    assert results[1]["basis"] == basis_json


async def test_save_without_basis_backward_compat(signal_repo):
    """Existing callers can still call save without basis argument."""
    await signal_repo.save("KRW-BTC", "BUY", 0.75, 1700000000)
    results = await signal_repo.get_recent(limit=10)
    assert len(results) == 1
    assert results[0]["basis"] is None
