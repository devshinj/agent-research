# Upbit API Limits

## REST API
- Rate limit: 10 requests/second (exchange API key 없이)
- Candle API: 최대 200개/요청
- Ticker API: 복수 종목 한번에 조회 가능

## WebSocket
- 연결당 최대 15개 구독
- 종목 수 > 15일 경우 다중 연결 필요
- ping/pong 간격: 120초 이내
