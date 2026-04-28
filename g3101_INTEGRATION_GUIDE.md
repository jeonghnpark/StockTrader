# g3101 해외주식 API 통합 가이드

## 현재 상태

### 작성 완료
- `utils/ls_g3101.py` — LS Open API g3101 모듈 (해외주식 현재가/종목명)
- `test_g3101_tsla.py` — TSLA 테스트 스크립트
- `utils/ls_auth.py` — SSL 검증 비활성화 (테스트용 임시)

### API 요청 구조
```
POST /overseas-stock/market-data
Body:
{
  "g3101InBlock": {
    "-keysymbol": "ex)82TSLA",    // 거래소프리픽스 + 티커
    "-exchcd": "82",              // 82=NASDAQ, 81=NYSE
    "-symbol": "TSLA"             // 종목코드
  }
}
```

### API 응답 필드 (예정)
- `-symbol`: 종목코드 (TSLA)
- `-korname`: 한글종목명
- `-price`: 현재가 (Number, 15.6자릿수)
- `-exchg`: 거래소명
- `-currency`: 통화코드 (USD 등)
- `-diff`: 변동가
- `-rate`: 등락률
- `-volume`: 거래량
- `-high`: 고가
- `-low`: 저가
- `-open`: 시가
- 등 (자세한 필드는 API 문서 참조)

---

## 다음 단계: portfolio.py에 통합

### 1. `get_current_price()` 수정

```python
def get_current_price(ticker):
    if str(ticker).strip().upper() == FX_HEDGE_TICKER:
        return get_exchange_rate()
    
    # 국내 종목 (기존)
    shcode = _ls_shcode_from_ticker(ticker)
    if shcode:
        ob = _get_ls_t1101_cached(shcode)
        return _ls_price_to_float(ob)
    
    # 해외 종목 — g3101으로 변경 (NEW)
    symbol = _extract_overseas_symbol(ticker)  # TSLA, AAPL 등
    if symbol:
        ob = _get_ls_g3101_cached(symbol)
        return _ls_price_to_float(ob)
    
    # 위 모두 실패 시 yfinance 폴백
    try:
        stock = yf.Ticker(ticker)
        ...
```

### 2. 해외 티커 형식 정의
- TSLA, AAPL, MSFT 등 알파벳만: `_extract_overseas_symbol()` 반환
- 6자리 숫자 또는 `.KS`/`.KQ` 접미사: 국내로 간주

### 3. 캐싱 추가
```python
_LS_G3101_CACHE = {}  # symbol -> (ts, data)
_LS_G3101_CACHE_TTL_SEC = 60.0

def _get_ls_g3101_cached(symbol):
    # 동일 종목 연속 조회 시 캐시 재사용
```

### 4. `get_company_name()` 수정
```python
def get_company_name(ticker):
    ...
    # 해외 종목: LS g3101에서 한글명 조회
    symbol = _extract_overseas_symbol(ticker)
    if symbol:
        ob = _get_ls_g3101_cached(symbol)
        if ob and ob.get('-korname'):
            name = str(ob['-korname']).strip()
            _NAME_CACHE[ticker] = name
            return name
    ...
```

---

## 테스트 환경 제한

현재 LS증권 테스트 환경에서 g3101(해외주식)이 완전히 지원되지 않아:
- API 호출은 성공(00000)하지만
- "해당종목이 없습니다" 응답

**해결 방법:**
1. LS증권 운영 담당자에게 테스트 계정의 g3101 권한 요청
2. 또는 **운영 환경(실계좌 키)에서 테스트** — 실시간 시세 수신 가능

---

## 구현 체크리스트

- [ ] `ls_g3101.py` 검증 완료
- [ ] `portfolio.py`에서 `get_current_price()` 수정
- [ ] `portfolio.py`에서 `get_company_name()` 수정
- [ ] 캐싱 로직 추가
- [ ] 해외 티커 형식 파싱 함수 작성
- [ ] 통합 테스트 (StockTrader app에서 TSLA 등 입력)
- [ ] SSL `verify=False` 제거 (운영 환경에서는 필수)

---

## 참고 사항

- `test_g3101_tsla.py`는 테스트용 스크립트이므로, 통합 후 삭제 권장
- SSL 검증 비활성화는 **테스트/개발 환경 전용** (운영 환경에서는 인증서 갱신 필요)
- 해외주식 캐싱 TTL(60초)은 국내 주식과 동일하므로 필요시 조정
