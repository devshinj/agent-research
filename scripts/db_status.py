"""DB 캔들 수집 현황 조회 CLI."""
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "paper_trader.db"


def main() -> None:
    if not DB_PATH.exists():
        print(f"DB not found: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    # 타임프레임별 요약
    cur.execute(
        """SELECT timeframe, COUNT(*), COUNT(DISTINCT market),
                  MIN(timestamp), MAX(timestamp)
           FROM candles GROUP BY timeframe ORDER BY timeframe"""
    )
    rows = cur.fetchall()

    if not rows:
        print("No candle data.")
        conn.close()
        return

    print("=== Candle Summary ===")
    print(f"{'TF':<6} {'Rows':>8} {'Markets':>8} {'From':>20} {'To':>20}")
    print("-" * 66)
    for tf, cnt, markets, oldest, newest in rows:
        t_from = datetime.fromtimestamp(oldest, tz=timezone.utc).strftime("%Y-%m-%d %H:%M") if oldest else "N/A"
        t_to = datetime.fromtimestamp(newest, tz=timezone.utc).strftime("%Y-%m-%d %H:%M") if newest else "N/A"
        print(f"{tf:<6} {cnt:>8,} {markets:>8} {t_from:>20} {t_to:>20}")

    # 마켓별 상세 (인자로 timeframe 지정 가능)
    tf_filter = sys.argv[1] if len(sys.argv) > 1 else None
    if tf_filter:
        print(f"\n=== {tf_filter} per Market ===")
        cur.execute(
            """SELECT market, COUNT(*), MIN(timestamp), MAX(timestamp)
               FROM candles WHERE timeframe=? GROUP BY market ORDER BY market""",
            (tf_filter,),
        )
        for market, cnt, oldest, newest in cur.fetchall():
            t_from = datetime.fromtimestamp(oldest, tz=timezone.utc).strftime("%m-%d %H:%M")
            t_to = datetime.fromtimestamp(newest, tz=timezone.utc).strftime("%m-%d %H:%M")
            print(f"  {market:<12} {cnt:>6,} rows  {t_from} ~ {t_to}")

    conn.close()


if __name__ == "__main__":
    main()
