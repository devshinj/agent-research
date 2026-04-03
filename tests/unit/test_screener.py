from decimal import Decimal

from src.service.screener import Screener
from src.config.settings import ScreeningConfig


def make_config(**overrides: object) -> ScreeningConfig:
    defaults = dict(
        min_volume_krw=Decimal("500000000"),
        min_volatility_pct=Decimal("1.0"),
        max_volatility_pct=Decimal("15.0"),
        max_coins=3,
        refresh_interval_min=30,
        always_include=(),
    )
    defaults.update(overrides)
    return ScreeningConfig(**defaults)  # type: ignore[arg-type]


def make_ticker(market: str, volume: str, change: str) -> dict:
    return {
        "market": market,
        "price": Decimal("50000000"),
        "volume_24h": Decimal(volume),
        "change_rate": Decimal(change),
        "timestamp": 1700000000,
    }


NAMES = {
    "KRW-BTC": "비트코인",
    "KRW-ETH": "이더리움",
    "KRW-XRP": "리플",
    "KRW-DOGE": "도지코인",
}


def test_filter_by_volume():
    screener = Screener(make_config())
    tickers = [
        make_ticker("KRW-BTC", "1000000000", "0.03"),
        make_ticker("KRW-DOGE", "100000000", "0.05"),
    ]
    result = screener.screen(tickers, NAMES)
    assert len(result) == 1
    assert result[0].market == "KRW-BTC"
    assert result[0].korean_name == "비트코인"


def test_filter_by_volatility_range():
    screener = Screener(make_config())
    tickers = [
        make_ticker("KRW-BTC", "1000000000", "0.03"),
        make_ticker("KRW-SHIB", "1000000000", "0.20"),
        make_ticker("KRW-USDT", "1000000000", "0.001"),
    ]
    result = screener.screen(tickers, NAMES)
    assert len(result) == 1
    assert result[0].market == "KRW-BTC"


def test_max_coins_limit():
    screener = Screener(make_config())
    tickers = [
        make_ticker(f"KRW-COIN{i}", str(1000000000 - i * 100000000), "0.05")
        for i in range(5)
    ]
    result = screener.screen(tickers)
    assert len(result) == 3


def test_sorted_by_score_descending():
    screener = Screener(make_config())
    tickers = [
        make_ticker("KRW-LOW", "600000000", "0.02"),
        make_ticker("KRW-HIGH", "2000000000", "0.08"),
    ]
    result = screener.screen(tickers)
    assert result[0].market == "KRW-HIGH"


def test_empty_tickers():
    screener = Screener(make_config())
    result = screener.screen([])
    assert result == []


def test_korean_name_fallback():
    screener = Screener(make_config())
    tickers = [make_ticker("KRW-NEW", "1000000000", "0.03")]
    result = screener.screen(tickers, {})
    assert result[0].korean_name == "NEW"


def test_always_include_bypasses_filters():
    config = make_config(always_include=("KRW-DOGE",))
    screener = Screener(config)
    tickers = [
        make_ticker("KRW-BTC", "1000000000", "0.03"),
        make_ticker("KRW-DOGE", "100000000", "0.005"),  # below volume & volatility
    ]
    result = screener.screen(tickers, NAMES)
    assert any(r.market == "KRW-DOGE" for r in result)
    assert result[0].market == "KRW-DOGE"  # forced coins come first


def test_always_include_respects_max_coins():
    config = make_config(max_coins=2, always_include=("KRW-BTC", "KRW-ETH"))
    screener = Screener(config)
    tickers = [
        make_ticker("KRW-BTC", "1000000000", "0.03"),
        make_ticker("KRW-ETH", "800000000", "0.04"),
        make_ticker("KRW-XRP", "2000000000", "0.05"),
    ]
    result = screener.screen(tickers, NAMES)
    assert len(result) == 2
    markets = {r.market for r in result}
    assert "KRW-BTC" in markets
    assert "KRW-ETH" in markets
