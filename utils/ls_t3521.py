"""LS Open API t3521 해외지수/환율/선물 조회."""

import json
import logging
import time
from json.decoder import JSONDecodeError

import requests
from requests.exceptions import RequestException

from utils.ls_auth import api_manager, get_token_foreign_stock

logger = logging.getLogger(__name__)

TR = "t3521"
BASE_URL = "https://openapi.ls-sec.co.kr:8080"
PATH = "stock/investinfo"
URL = f"{BASE_URL}/{PATH}"
T3521_MIN_INTERVAL_SEC = 0.34
_CACHE = {}  # kind:symbol -> (monotonic_ts, outblock dict | None)
_CACHE_TTL_SEC = 30.0


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


def _pick_float(block, keys):
    for key in keys:
        val = _to_float(block.get(key))
        if val is not None:
            return val
    return None


def _signed_change_rate(block, raw_rate):
    if raw_rate is None:
        return None

    sign_code = str(block.get("sign", "")).strip()
    # LS 시세 sign 코드: 4/5 계열은 하락으로 간주
    if sign_code in {"4", "5"}:
        return -abs(raw_rate)
    return raw_rate


def get_current(kind, symbol):
    """t3521 OutBlock 반환. 실패 시 None."""
    kind = str(kind).strip().upper()
    symbol = str(symbol).strip().upper()

    if kind not in {"S", "R", "F"}:
        raise ValueError("kind는 S(해외지수), R(해외환율), F(해외선물)만 지원합니다.")
    if not symbol:
        raise ValueError("symbol 값이 비어 있습니다.")

    cache_key = f"{kind}:{symbol}"
    now = time.monotonic()
    if cache_key in _CACHE:
        ts, data = _CACHE[cache_key]
        if now - ts < _CACHE_TTL_SEC:
            return data

    access_token = get_token_foreign_stock()
    header = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {access_token}",
        "tr_cd": TR,
        "tr_cont": "N",
        "tr_cont_key": "",
    }

    body = {
        f"{TR}InBlock": {
            "kind": kind,
            "symbol": symbol,
        }
    }

    api_manager.wait_for_next_call(TR, T3521_MIN_INTERVAL_SEC)
    try:
        res = requests.post(URL, headers=header, data=json.dumps(body), timeout=30)
        res.raise_for_status()
        res_json = res.json()

        if res_json.get("rsp_cd") != "00000":
            logger.warning(
                "t3521: rsp_cd error for %s/%s: %s",
                kind,
                symbol,
                res_json.get("rsp_cd"),
            )
            _CACHE[cache_key] = (time.monotonic(), None)
            return None

        out_block = res_json.get(f"{TR}OutBlock")
        if not isinstance(out_block, dict):
            logger.error("t3521: OutBlock not found: %s", res_json)
            _CACHE[cache_key] = (time.monotonic(), None)
            return None

        _CACHE[cache_key] = (time.monotonic(), out_block)
        return out_block
    except (RequestException, JSONDecodeError, ValueError) as exc:
        logger.error("t3521 call error for %s/%s: %s", kind, symbol, exc)
        _CACHE[cache_key] = (time.monotonic(), None)
        return None


def get_price_and_change_rate(kind, symbol):
    """(현재가, 전일대비 변동률) 튜플 반환. 실패 시 (None, None)."""
    out_block = get_current(kind, symbol)
    if not out_block:
        return (None, None)

    price = _pick_float(
        out_block,
        [
            "price",
            "curpr",
            "close",
            "last",
            "now",
        ],
    )
    change_rate = _pick_float(
        out_block,
        [
            "diff",
            "rate",
            "diffprat",
            "chg_rate",
            "change_rate",
            "drate",
        ],
    )
    return (price, _signed_change_rate(out_block, change_rate))
