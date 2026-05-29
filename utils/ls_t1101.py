"""LS Open API t1101 — 국내 주식 현재가·종목명(hname) 등."""

import json
import logging
from json.decoder import JSONDecodeError

import requests
from requests.exceptions import RequestException

from utils.ls_auth import api_manager, get_token_futures

logger = logging.getLogger(__name__)

TR = "t1101"
BASE_URL = "https://openapi.ls-sec.co.kr:8080"
PATH = "stock/market-data"
URL = f"{BASE_URL}/{PATH}"
# KRX 초당 약 3회 제한 (simple_trading t2101 등과 동일 간격)
T1101_MIN_INTERVAL_SEC = 0.34


def get_current(shcode="005930"):
    """
    t1101OutBlock dict 반환. 실패 시 None.
    shcode: 6자리 종목코드 문자열.
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

    api_manager.wait_for_next_call(TR, T1101_MIN_INTERVAL_SEC)
    try:
        res = requests.post(URL, headers=header, data=json.dumps(body), timeout=30)
        res.raise_for_status()
        res_json = res.json()
        if f"{TR}OutBlock" not in res_json:
            logger.error("t1101: OutBlock 없음: %s", res_json)
            return None
        return res_json[f"{TR}OutBlock"]
    except (RequestException, JSONDecodeError, KeyError) as e:
        logger.error("t1101 호출 오류 (%s): %s", shcode, e)
        return None


def get_current_with_fallback(shcode="005930"):
    """
    1차 시도: shcode 그대로
    2차 시도: shcode.KS 붙여서 재시도 (일부 ETF 등 필요)
    """
    shcode = str(shcode).strip()

    # 1차 시도
    result = get_current(shcode)
    if result is not None:
        return result

    # 2차 시도: .KS 붙여서 재시도
    if not shcode.endswith(".KS") and not shcode.endswith(".KQ"):
        logger.warning(
            "t1101: First attempt failed for %s, retrying with .KS suffix", shcode
        )
        result = get_current(f"{shcode}.KS")
        print("\nKS를 붙여야함!!!!!!!!!!!!!!!!!!!!!!!!! real? \n")
        if result is not None:
            return result

    logger.error("t1101: All attempts failed for %s", shcode)
    return None
