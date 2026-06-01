"""LS Open API g3101 — 해외주식 API 현재가 조회"""

import json
import logging
from json.decoder import JSONDecodeError

import requests
from requests.exceptions import RequestException
import os

from utils.ls_auth import api_manager, get_token_futures, get_token_foreign_stock

logger = logging.getLogger(__name__)

TR = "g3101"
BASE_URL = "https://openapi.ls-sec.co.kr:8080"
PATH = "overseas-stock/market-data"
URL = f"{BASE_URL}/{PATH}"
G3101_MIN_INTERVAL_SEC = 0.12


def get_current(symbol, exchange="NASDAQ"):
    """
    현재가(float) 반환. 실패 시 None.

    Parameters:
    - symbol: 해외 주식 티커 (예: TSLA, AAPL) - 대문자로 자동 변환
    - exchange: 거래소 명 ("NASDAQ" 또는 "NYSE"), 기본값 "NASDAQ"

    Returns:
    - float: 현재가 (성공)
    - None: 실패 또는 응답 코드 오류
    """

    symbol = str(symbol).strip().upper()
    exchange = str(exchange).strip().upper()

    # 거래소명 → exchcd 매핑
    exchange_map = {
        "NASDAQ": "82",
        "NYSE": "81",
    }
    if exchange in exchange_map:
        exchcd = exchange_map[exchange]
    else:
        raise ValueError(
            f"지원하지 않는 거래소: {exchange} (지원: {', '.join(exchange_map.keys())})"
        )

    access_token = get_token_foreign_stock()
    header = {
        "content-type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {access_token}",
        "tr_cd": TR,
        "tr_cont": "N",
        "tr_cont_key": "",
    }

    body = {
        f"{TR}InBlock": {
            "exchcd": exchcd,
            "symbol": symbol,
            "delaygb": "R",
        }
    }

    api_manager.wait_for_next_call(TR, G3101_MIN_INTERVAL_SEC)
    try:
        res = requests.post(URL, headers=header, data=json.dumps(body), timeout=30)
        res.raise_for_status()
        res_json = res.json()

        # 최상위 레벨의 응답 코드 확인 (0000 = 성공)
        if res_json.get("rsp_cd") != "00000":
            logger.warning(
                "g3101: rsp_cd error for %s: %s", symbol, res_json.get("rsp_cd")
            )
            return None

        if f"{TR}OutBlock" not in res_json:
            logger.error("g3101: OutBlock not found: %s", res_json)
            return None

        return res_json[f"{TR}OutBlock"]
        # out_block = res_json[f"{TR}OutBlock"]

        # # 현재가 추출
        # price_str = out_block.get("price", "").strip()
        # if not price_str or price_str == "0":
        #     logger.warning("g3101: no price for %s", symbol)
        #     return None

        # return float(price_str)
    except (RequestException, JSONDecodeError, KeyError, ValueError) as e:
        logger.error("g3101 call error for %s: %s", symbol, e)
        return None
