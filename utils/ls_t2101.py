"""LS Open API t2111 — 선물/옵션 현재가(시세) 조회
   신규 TR: t2111 (2026.5.28 이후 필수, 기존 t2101 종료됨)
   변경 내용: 가격 필드의 자릿수 확대, InBlock/OutBlock 구조는 동일
"""

import json
import logging
import requests
from requests.exceptions import RequestException
from json.decoder import JSONDecodeError

from utils.ls_auth import api_manager, get_token_futures

logger = logging.getLogger(__name__)

TR = "t2111"
BASE_URL = "https://openapi.ls-sec.co.kr:8080"
PATH = "futureoption/market-data"
URL = f"{BASE_URL}/{PATH}"

# KRX 초당 약 3회 제한
T2111_MIN_INTERVAL_SEC = 0.34


def get_future_current_price(shcode):
    """
    선물/옵션 현재가 조회 (t2111)
    
    Parameters:
    - shcode: 선물/옵션 코드
    
    Returns:
    - OutBlock dict 또는 None
    """
    token = get_token_futures()
    if not token:
        logger.error("Failed to get authentication token")
        return None

    headers = {
        "content-type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {token}",
        "tr_cd": TR,
        "tr_cont": "N",
        "tr_cont_key": "",
    }
    
    body = {
        f"{TR}InBlock": {
            "focode": shcode
        }
    }
    
    api_manager.wait_for_next_call(TR, T2111_MIN_INTERVAL_SEC)
    try:
        res = requests.post(URL, headers=headers, data=json.dumps(body), timeout=30)
        res.raise_for_status()
        res_json = res.json()
        
        outblock_key = f"{TR}OutBlock"
        if outblock_key not in res_json:
            logger.error(f"{TR}: OutBlock not found: %s", res_json)
            return None
        
        return res_json[outblock_key]
    except (RequestException, JSONDecodeError, KeyError) as e:
        logger.error(f"{TR} call error for {shcode}: %s", e)
        return None
