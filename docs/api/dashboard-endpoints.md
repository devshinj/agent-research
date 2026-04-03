# Dashboard API Endpoints

## REST

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/health | Health check |
| GET | /api/dashboard/summary | 총 자산, PnL, 포지션 수 |
| GET | /api/portfolio/positions | 보유 포지션 목록 |
| GET | /api/portfolio/history?page&size | 거래 이력 (페이징) |
| GET | /api/portfolio/daily | 일별 성과 |
| GET | /api/strategy/screening | 스크리닝 현황 |
| GET | /api/strategy/signals | 시그널 로그 |
| GET | /api/strategy/model-status | 모델 상태 |
| GET | /api/risk/status | 리스크 상태 |
| POST | /api/control/pause | 매매 일시 중지 |
| POST | /api/control/resume | 매매 재개 |

## WebSocket

`WS /ws/live` — real-time updates

Message types: price_update, position_update, trade_executed, signal_fired, risk_alert, summary_update
