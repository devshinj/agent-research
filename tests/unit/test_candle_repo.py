import pytest
from decimal import Decimal

from src.repository.database import Database
from src.repository.candle_repo import CandleRepository
from src.types.models import Candle


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
async def candle_repo(db):
    return CandleRepository(db)


async def test_save_and_get_candle(candle_repo):
    candle = Candle(
        market="KRW-BTC",
        timeframe="1m",
        timestamp=1700000000,
        open=Decimal("50000000"),
        high=Decimal("50100000"),
        low=Decimal("49900000"),
        close=Decimal("50050000"),
        volume=Decimal("1.5"),
    )
    await candle_repo.save(candle)
    result = await candle_repo.get_latest("KRW-BTC", "1m", limit=1)
    assert len(result) == 1
    assert result[0].market == "KRW-BTC"
    assert result[0].close == Decimal("50050000")


async def test_save_duplicate_candle_upserts(candle_repo):
    candle1 = Candle("KRW-BTC", "1m", 1700000000,
                     Decimal("50000000"), Decimal("50100000"),
                     Decimal("49900000"), Decimal("50050000"), Decimal("1.5"))
    candle2 = Candle("KRW-BTC", "1m", 1700000000,
                     Decimal("50000000"), Decimal("50200000"),
                     Decimal("49800000"), Decimal("50150000"), Decimal("2.0"))
    await candle_repo.save(candle1)
    await candle_repo.save(candle2)
    result = await candle_repo.get_latest("KRW-BTC", "1m", limit=10)
    assert len(result) == 1
    assert result[0].high == Decimal("50200000")


async def test_get_latest_returns_ordered(candle_repo):
    for i in range(5):
        c = Candle("KRW-BTC", "1m", 1700000000 + i * 60,
                   Decimal("50000000"), Decimal("50100000"),
                   Decimal("49900000"), Decimal("50050000"), Decimal("1.5"))
        await candle_repo.save(c)
    result = await candle_repo.get_latest("KRW-BTC", "1m", limit=3)
    assert len(result) == 3
    assert result[0].timestamp > result[1].timestamp


async def test_delete_older_than(candle_repo):
    old = Candle("KRW-BTC", "1m", 1000000000,
                 Decimal("50000000"), Decimal("50100000"),
                 Decimal("49900000"), Decimal("50050000"), Decimal("1.5"))
    new = Candle("KRW-BTC", "1m", 1700000000,
                 Decimal("50000000"), Decimal("50100000"),
                 Decimal("49900000"), Decimal("50050000"), Decimal("1.5"))
    await candle_repo.save(old)
    await candle_repo.save(new)
    deleted = await candle_repo.delete_older_than(1500000000)
    assert deleted == 1
    result = await candle_repo.get_latest("KRW-BTC", "1m", limit=10)
    assert len(result) == 1
