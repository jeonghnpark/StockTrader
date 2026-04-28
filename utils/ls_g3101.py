"""LS Open API g3101 — 해외 주식 현재가·종목명(korname) 등."""

import json
import logging
from json.decoder import JSONDecodeError

import requests
from requests.exceptions import RequestException

from utils.ls_auth import api_manager, get_token_futures

logger = logging.getLogger(__name__)

TR = "g3101"
BASE_URL = "https://openapi.ls-sec.co.kr:8080"
PATH = "overseas-stock/market-data"
URL = f"{BASE_URL}/{PATH}"
G3101_MIN_INTERVAL_SEC = 0.34

# 거래소 프리픽스
EXCHANGE_PREFIX = {
    "81": "ex)81",  # NYSE
    "82": "ex)82",  # NASDAQ
}


def get_current(symbol, exchcd="82"):
    """
    g3101OutBlock dict 반환. 실패 시 None.

    Parameters:
    - symbol: 해외 주식 티커 (예: TSLA, AAPL) - 대문자로 자동 변환
    - exchcd: 거래소 코드 (81=뉴욕, 82=나스닥, 기본값 나스닥)

    API 문서 기반:
    - keysymbol: ex)82TSLA 형식 (거래소프리픽스 + 티커)
    - exchcd: 거래소 코드
    - symbol: 종목코드 (TSLA)
    """
    symbol = str(symbol).strip().upper()
    exchcd = str(exchcd).strip()

    # keysymbol = "ex)82TSLA" 형식으로 조합
    prefix = EXCHANGE_PREFIX.get(exchcd, "ex)82")
    keysymbol = f"{prefix}{symbol}"

    access_token = get_token_futures()
    header = {
        "content-type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {access_token}",
        "tr_cd": TR,
        "tr_cont": "N",
        "tr_cont_key": "",
    }

    body = {
        # f"{TR}InBlock": {
        #     "keysymbol": keysymbol,
        #     "exchcd": exchcd,
        #     "symbol": symbol,
        # }
        f"{TR}InBlock": {
            "keysymbol": keysymbol,
            "exchcd": exchcd,
            "symbol": symbol,
        }
    }

    api_manager.wait_for_next_call(TR, G3101_MIN_INTERVAL_SEC)
    try:
        res = requests.post(
            URL, headers=header, data=json.dumps(body), timeout=30, verify=False
        )
        res.raise_for_status()
        res_json = res.json()

        logger.info("g3101 response: %s", res_json)

        if f"{TR}OutBlock" not in res_json:
            logger.error("g3101: OutBlock not found: %s", res_json)
            return None
        return res_json[f"{TR}OutBlock"]
    except (RequestException, JSONDecodeError, KeyError) as e:
        logger.error("g3101 call error: %s", e)
        return None
