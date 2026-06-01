"""LS Open API t1901 — ETF 현재가(시세) 조회
변경 사항 (2026.5.19 17:00 적용):
- nav(NAV): 8.2 → 12.2
- navchange(NAV전일대비): 8.2 → 12.2
- jnilnav(전일NAV): 8.2 → 12.2
- jnilnavchange(전일NAV전일대비): 8.2 → 12.2

필드 크기 확대로 더 정밀한 NAV 데이터 제공
"""

import json
import logging
from json.decoder import JSONDecodeError

import requests
from requests.exceptions import RequestException

from utils.ls_auth import api_manager, get_token_futures

logger = logging.getLogger(__name__)

TR = "t1901"
BASE_URL = "https://openapi.ls-sec.co.kr:8080"
PATH = "stock/market-data"
URL = f"{BASE_URL}/{PATH}"
T1901_MIN_INTERVAL_SEC = 1.1


def get_etf_current(shcode="091170"):
    """
    ETF 현재가 조회 (t1901)

    Parameters:
    - shcode: 6자리 ETF 종목코드

    Returns:
    - t1901OutBlock dict (NAV, 기초지수 등 포함) 또는 None

    주요 필드:
    - price: 현재가
    - nav: NAV (12.2 형식)
    - navchange: NAV 전일대비 (12.2 형식)
    - jnilnav: 전일 NAV (12.2 형식)
    - jnilnavchange: 전일 NAV 전일대비 (12.2 형식)
    """
    shcode = str(shcode).strip().zfill(6)
    access_token = get_token_futures()

    header = {
        "content-type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {access_token}",
        "tr_cd": TR,
        "tr_cont": "N",
        "tr_cont_key": "",
    }
    body = {f"{TR}InBlock": {"shcode": shcode}}

    api_manager.wait_for_next_call(TR, T1901_MIN_INTERVAL_SEC)
    try:
        res = requests.post(URL, headers=header, data=json.dumps(body), timeout=30)
        res.raise_for_status()
        res_json = res.json()
        if f"{TR}OutBlock" not in res_json:
            logger.error("t1901: OutBlock 없음: %s", res_json)
            return None
        return res_json[f"{TR}OutBlock"]
    except (RequestException, JSONDecodeError, KeyError) as e:
        logger.error("t1901 호출 오류 (%s): %s", shcode, e)
        return None


def get_etf_nav(shcode="091170"):
    """
    ETF NAV 조회 (편의 함수)

    Returns:
    - float: NAV 값 또는 0.0
    """
    outblock = get_etf_current(shcode)
    if not outblock:
        return 0.0

    try:
        nav = outblock.get("nav")
        if nav is None or nav == "":
            return 0.0
        return float(str(nav).replace(",", "").strip())
    except (ValueError, AttributeError):
        logger.warning("Failed to parse NAV from t1901 response for %s", shcode)
        return 0.0
