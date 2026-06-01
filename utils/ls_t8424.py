"""LS Open API t8424 업종코드 조회."""

import json
import logging
from json.decoder import JSONDecodeError

import requests
from requests.exceptions import RequestException

from utils.ls_auth import api_manager, get_token_futures

logger = logging.getLogger(__name__)

TR = "t8424"
BASE_URL = "https://openapi.ls-sec.co.kr:8080"
PATH = "indtp/market-data"
URL = f"{BASE_URL}/{PATH}"
T8424_MIN_INTERVAL_SEC = 1.1


def get_current(gubun1=""):
    """t8424OutBlock(list) 반환. 실패 시 None.

    Parameters:
    - gubun1: 구분1 (빈 문자열이면 전체 업종코드 목록)
    """
    gubun1 = str(gubun1).strip()

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
            "gubun1": gubun1,
        }
    }

    api_manager.wait_for_next_call(TR, T8424_MIN_INTERVAL_SEC)
    try:
        res = requests.post(URL, headers=header, data=json.dumps(body), timeout=30)
        res.raise_for_status()
        res_json = res.json()

        if res_json.get("rsp_cd") != "00000":
            logger.warning(
                "t8424: rsp_cd error for gubun1=%s: %s",
                gubun1,
                res_json.get("rsp_cd"),
            )
            return None

        out_block = res_json.get(f"{TR}OutBlock")
        if not isinstance(out_block, list):
            logger.error("t8424: OutBlock not found: %s", res_json)
            return None

        return out_block
    except (RequestException, JSONDecodeError, ValueError) as exc:
        logger.error("t8424 call error for gubun1=%s: %s", gubun1, exc)
        return None
