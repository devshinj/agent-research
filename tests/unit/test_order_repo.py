import pytest
from decimal import Decimal

from src.repository.database import Database
from src.repository.order_repo import OrderRepository
from src.types.enums import OrderSide, OrderStatus, OrderType
from src.types.models import Order


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
async def order_repo(db):
    return OrderRepository(db)


async def test_save_and_get_order(order_repo):
    order = Order(
        id="order-1", market="KRW-BTC", side=OrderSide.BUY,
        order_type=OrderType.MARKET, price=Decimal("50000000"),
        quantity=Decimal("0.001"), status=OrderStatus.FILLED,
        signal_confidence=0.8, reason="ML_SIGNAL",
        created_at=1700000000, fill_price=Decimal("50025000"),
        filled_at=1700000001, fee=Decimal("25012"),
    )
    await order_repo.save(order, user_id=1)
    result = await order_repo.get_by_id("order-1")
    assert result is not None
    assert result.fill_price == Decimal("50025000")


async def test_get_recent_orders(order_repo):
    for i in range(5):
        o = Order(
            id=f"order-{i}", market="KRW-BTC", side=OrderSide.BUY,
            order_type=OrderType.MARKET, price=Decimal("50000000"),
            quantity=Decimal("0.001"), status=OrderStatus.FILLED,
            signal_confidence=0.7, reason="ML_SIGNAL",
            created_at=1700000000 + i * 60, fill_price=Decimal("50000000"),
            filled_at=1700000001 + i * 60, fee=Decimal("25000"),
        )
        await order_repo.save(o, user_id=1)
    result = await order_repo.get_recent(user_id=1, limit=3)
    assert len(result) == 3
    assert result[0].created_at > result[1].created_at


async def test_count_today_trades(order_repo):
    o = Order(
        id="order-today", market="KRW-BTC", side=OrderSide.BUY,
        order_type=OrderType.MARKET, price=Decimal("50000000"),
        quantity=Decimal("0.001"), status=OrderStatus.FILLED,
        signal_confidence=0.7, reason="ML_SIGNAL",
        created_at=1700000000, fill_price=Decimal("50000000"),
        filled_at=1700000001, fee=Decimal("25000"),
    )
    await order_repo.save(o, user_id=1)
    count = await order_repo.count_since(user_id=1, timestamp=1700000000 - 1)
    assert count == 1
