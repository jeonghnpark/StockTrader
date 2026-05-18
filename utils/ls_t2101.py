"""LS Open API t2111 — 선물/옵션 현재가(시세) 조회
   이전 TR: t2101 (2026.5.28 이후 사용 불가)
   신규 TR: t2111 (2026.4.24 ~ 병행, 2026.5.28 이후 필수)
   변경 내용: 가격 필드의 자릿수 확대, InBlock/OutBlock 구조는 동일
"""

import json
import logging
import requests
from requests.exceptions import RequestException
from json.decoder import JSONDecodeError

from utils.ls_auth import api_manager, get_token_futures

logger = logging.getLogger(__name__)

# 신규 TR (2026.4.24 이후)
TR_NEW = "t2111"
# 기존 TR (2026.5.28까지만 유효)
TR_OLD = "t2101"

BASE_URL = "https://openapi.ls-sec.co.kr:8080"
PATH = "futureoption/market-data"
URL = f"{BASE_URL}/{PATH}"

# KRX 초당 약 3회 제한
T2111_MIN_INTERVAL_SEC = 0.34


def get_future_current_price(shcode, use_new_tr=True):
    """
    선물/옵션 현재가 조회
    
    Parameters:
    - shcode: 선물/옵션 코드
    - use_new_tr: True이면 t2111 사용, False이면 t2101 사용 (하위호환성)
    
    Returns:
    - OutBlock dict 또는 None
    """
    tr = TR_NEW if use_new_tr else TR_OLD
    
    token = get_token_futures()
    if not token:
        logger.error("Failed to get authentication token")
        return None

    headers = {
        "content-type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {token}",
        "tr_cd": tr,
        "tr_cont": "N",
        "tr_cont_key": "",
    }
    
    body = {
        f"{tr}InBlock": {
            "focode": shcode
        }
    }
    
    api_manager.wait_for_next_call(tr, T2111_MIN_INTERVAL_SEC)
    try:
        res = requests.post(URL, headers=headers, data=json.dumps(body), timeout=30)
        res.raise_for_status()
        res_json = res.json()
        
        outblock_key = f"{tr}OutBlock"
        if outblock_key not in res_json:
            logger.error(f"{tr}: OutBlock not found: %s", res_json)
            return None
        
        return res_json[outblock_key]
    except (RequestException, JSONDecodeError, KeyError) as e:
        logger.error(f"{tr} call error for {shcode}: %s", e)
        return None


def get_future_current_price_with_fallback(shcode):
    """
    신규 TR(t2111) 우선 시도, 실패 시 기존 TR(t2101) 재시도
    병행 기간(2026.4.24 ~ 2026.5.28) 동안 호환성 유지
    """
    # 1차 시도: 신규 TR (t2111)
    result = get_future_current_price(shcode, use_new_tr=True)
    if result is not None:
        return result
    
    # 2차 시도: 기존 TR (t2101) - 하위 호환성
    logger.warning(f"New TR (t2111) failed for {shcode}, retrying with old TR (t2101)")
    result = get_future_current_price(shcode, use_new_tr=False)
    if result is not None:
        logger.info(f"Old TR (t2101) succeeded for {shcode}")
        return result
    
    logger.error(f"Both TR attempts failed for {shcode}")
    return None
