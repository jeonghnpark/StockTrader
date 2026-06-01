"""LS Open API t1511 업종현재가 조회."""

import json
import logging
import time
from json.decoder import JSONDecodeError

import requests
from requests.exceptions import RequestException

from utils.ls_auth import api_manager, get_token_futures

logger = logging.getLogger(__name__)

TR = "t1511"
BASE_URL = "https://openapi.ls-sec.co.kr:8080"
PATH = "indtp/market-data"
URL = f"{BASE_URL}/{PATH}"
T1511_MIN_INTERVAL_SEC = 0.34
_CACHE = {}  # upcode -> (monotonic_ts, outblock dict | None)
_CACHE_TTL_SEC = 30.0

KOSPI_UPCODE = "101"
KOSDAQ_UPCODE = "301"


def _to_float(value):
    if value is None:
        return None
    try:
        text = str(value).replace(",", "").strip()
        if not text:
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


def _signed_change_rate(block, raw_rate):
    if raw_rate is None:
        return None

    sign_code = str(block.get("sign", "")).strip()
    # LS 시세 sign 코드: 4/5 계열은 하락으로 간주
    if sign_code in {"4", "5"}:
        return -abs(raw_rate)
    return raw_rate


def get_current(upcode):
    """t1511OutBlock dict 반환. 실패 시 None.

    Parameters:
    - upcode: 업종코드 (예: 101=코스피종합, 301=코스닥)
    """
    upcode = str(upcode).strip().zfill(3)
    if not upcode:
        raise ValueError("upcode 값이 비어 있습니다.")

    now = time.monotonic()
    if upcode in _CACHE:
        ts, data = _CACHE[upcode]
        if now - ts < _CACHE_TTL_SEC:
            return data

    access_token = get_token_futures()
    header = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {access_token}",
        "tr_cd": TR,
        "tr_cont": "N",
        "tr_cont_key": "",
    }

    body = {
        f"{TR}InBlock": {
            "upcode": upcode,
        }
    }

    api_manager.wait_for_next_call(TR, T1511_MIN_INTERVAL_SEC)
    try:
        res = requests.post(URL, headers=header, data=json.dumps(body), timeout=30)
        res.raise_for_status()
        res_json = res.json()

        if res_json.get("rsp_cd") != "00000":
            logger.warning(
                "t1511: rsp_cd error for %s: %s",
                upcode,
                res_json.get("rsp_cd"),
            )
            _CACHE[upcode] = (time.monotonic(), None)
            return None

        out_block = res_json.get(f"{TR}OutBlock")
        if not isinstance(out_block, dict):
            logger.error("t1511: OutBlock not found: %s", res_json)
            _CACHE[upcode] = (time.monotonic(), None)
            return None

        _CACHE[upcode] = (time.monotonic(), out_block)
        return out_block
    except (RequestException, JSONDecodeError, ValueError) as exc:
        logger.error("t1511 call error for %s: %s", upcode, exc)
        _CACHE[upcode] = (time.monotonic(), None)
        return None


def get_price_and_change_rate(upcode):
    """(현재지수, 전일대비 변동률) 튜플 반환. 실패 시 (None, None)."""
    out_block = get_current(upcode)
    if not out_block:
        return (None, None)

    price = _to_float(out_block.get("pricejisu"))
    change_rate = _signed_change_rate(out_block, _to_float(out_block.get("diffjisu")))
    return (price, change_rate)
