import pytest
from decimal import Decimal
from unittest.mock import AsyncMock

from src.service.collector import Collector
from src.types.models import Candle


@pytest.fixture
def mock_upbit_client():
    client = AsyncMock()
    client.fetch_markets.return_value = (
        ["KRW-BTC", "KRW-ETH", "KRW-XRP"],
        {"KRW-BTC": "비트코인", "KRW-ETH": "이더리움", "KRW-XRP": "리플"},
    )
    client.fetch_candles.return_value = [
        Candle("KRW-BTC", "1m", 1700000000,
               Decimal("50000000"), Decimal("50100000"),
               Decimal("49900000"), Decimal("50050000"), Decimal("1.5")),
    ]
    return client


@pytest.fixture
def mock_candle_repo():
    repo = AsyncMock()
    repo.save_many.return_value = None
    return repo


def test_collector_creation(mock_upbit_client, mock_candle_repo):
    collector = Collector(
        upbit_client=mock_upbit_client,
        candle_repo=mock_candle_repo,
        timeframe=1,
        max_candles=200,
    )
    assert collector._timeframe == 1


async def test_refresh_markets(mock_upbit_client, mock_candle_repo):
    collector = Collector(mock_upbit_client, mock_candle_repo, 1, 200)
    markets = await collector.refresh_markets()
    assert markets == ["KRW-BTC", "KRW-ETH", "KRW-XRP"]
    assert collector.korean_names["KRW-BTC"] == "비트코인"
    mock_upbit_client.fetch_markets.assert_awaited_once()


async def test_collect_candles_for_market(mock_upbit_client, mock_candle_repo):
    collector = Collector(mock_upbit_client, mock_candle_repo, 1, 200)
    await collector.collect_candles(["KRW-BTC"])
    mock_upbit_client.fetch_candles.assert_awaited_once_with("KRW-BTC", 1, 200)
    mock_candle_repo.save_many.assert_awaited_once()


@pytest.fixture
def mock_upbit_client_multi():
    client = AsyncMock()
    client.fetch_markets.return_value = (
        ["KRW-BTC", "KRW-ETH"],
        {"KRW-BTC": "비트코인", "KRW-ETH": "이더리움"},
    )
    client.fetch_candles.return_value = [
        Candle("KRW-BTC", "15m", 1700000000,
               Decimal("50000000"), Decimal("50100000"),
               Decimal("49900000"), Decimal("50050000"), Decimal("1.5")),
    ]
    client.fetch_daily_candles.return_value = [
        Candle("KRW-BTC", "1D", 1700000000,
               Decimal("50000000"), Decimal("50100000"),
               Decimal("49900000"), Decimal("50050000"), Decimal("100.0")),
    ]
    return client


async def test_collect_train_candles(mock_upbit_client_multi, mock_candle_repo):
    collector = Collector(
        upbit_client=mock_upbit_client_multi,
        candle_repo=mock_candle_repo,
        timeframe=1,
        max_candles=500,
        train_timeframe=15,
        train_candles=960,
        daily_candles=30,
    )
    await collector.collect_train_candles(["KRW-BTC"])
    mock_upbit_client_multi.fetch_candles.assert_awaited_once_with("KRW-BTC", 15, 960)
    mock_upbit_client_multi.fetch_daily_candles.assert_awaited_once_with("KRW-BTC", 30)
    assert mock_candle_repo.save_many.await_count == 2
    mock_candle_repo.commit.assert_awaited_once()


def test_collector_creation_with_train_params(mock_upbit_client, mock_candle_repo):
    collector = Collector(
        upbit_client=mock_upbit_client,
        candle_repo=mock_candle_repo,
        timeframe=1,
        max_candles=200,
        train_timeframe=15,
        train_candles=960,
        daily_candles=30,
    )
    assert collector._train_timeframe == 15
    assert collector._train_candles == 960
    assert collector._daily_candles == 30
