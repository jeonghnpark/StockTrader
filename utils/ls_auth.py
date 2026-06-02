"""LS Open API OAuth 토큰 및 API 호출 간격 제어 (simple_trading api_auth 패턴)."""

import logging
import os
import time
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv

from utils.logging_config import get_logger

load_dotenv()

logger = get_logger(__name__)

APP_FUTURES_KEY_TEST = os.getenv("EBEST-OPEN-API-APP-KEY-FUTURES-TEST")
APP_FUTURES_SECRET_TEST = os.getenv("EBEST-OPEN-API-SECRET-KEY-FUTURES-TEST")

# 주식전용용
# APP_FUTURES_KEY_TEST = os.getenv("EBEST-OPEN-API-APP-KEY-TEST")
# APP_FUTURES_SECRET_TEST = os.getenv("EBEST-OPEN-API-SECRET-KEY-TEST")

# EBEST-OPEN-API-APP-KEY-TEST=PS0af8zqmwco4ntPCnVLY2txiatbP375EdqI
# EBEST-OPEN-API-SECRET-KEY-TEST=tUGQ3cvnoEaJ3oHigBpLgpI8lKyt6To6
EBEST_OPEN_API_APP_KEY = os.getenv("EBEST-OPEN-API-APP-KEY")
EBEST_OPEN_API_SECRET_KEY = os.getenv("EBEST-OPEN-API-SECRET-KEY")

cached_token_futures = None
token_expiry_futures = None


def get_token_foreign_stock():

    global cached_token_futures, token_expiry_futures
    now = datetime.now()
    if cached_token_futures and token_expiry_futures and token_expiry_futures > now:
        return cached_token_futures

    url = "https://openapi.ls-sec.co.kr:8080/oauth2/token"
    headers = {"content-type": "application/x-www-form-urlencoded"}
    params = {
        "appkey": EBEST_OPEN_API_APP_KEY,
        "appsecretkey": EBEST_OPEN_API_SECRET_KEY,
        "grant_type": "client_credentials",
        "scope": "oob",
    }

    request = requests.post(url, data=params, headers=headers, timeout=30)
    response_data = request.json()

    if "access_token" not in response_data:
        logger.error(
            "LS token response: %s status=%s", response_data, request.status_code
        )
        raise ValueError(
            f"LS API 응답에 access_token이 없습니다. .env 키를 확인하세요. 응답: {response_data}"
        )

    new_token = response_data["access_token"]
    cached_token_futures = new_token
    expiry_in = int(response_data.get("expires_in", 3600))
    token_expiry_futures = now + timedelta(seconds=max(60, expiry_in - 120))

    return new_token


def get_token_futures():
    """주식 시세(t1101 등)에 사용하는 토큰. simple_trading과 동일하게 futures 테스트 키 사용."""
    global cached_token_futures, token_expiry_futures
    now = datetime.now()
    if cached_token_futures and token_expiry_futures and token_expiry_futures > now:
        return cached_token_futures

    url = "https://openapi.ls-sec.co.kr:8080/oauth2/token"
    headers = {"content-type": "application/x-www-form-urlencoded"}
    params = {
        "appkey": EBEST_OPEN_API_APP_KEY,
        "appsecretkey": EBEST_OPEN_API_SECRET_KEY,
        "grant_type": "client_credentials",
        "scope": "oob",
    }

    request = requests.post(url, data=params, headers=headers, timeout=30)
    response_data = request.json()

    if "access_token" not in response_data:
        logger.error(
            "LS token response: %s status=%s", response_data, request.status_code
        )
        raise ValueError(
            f"LS API 응답에 access_token이 없습니다. .env 키를 확인하세요. 응답: {response_data}"
        )

    new_token = response_data["access_token"]
    cached_token_futures = new_token
    expiry_in = int(response_data.get("expires_in", 3600))
    token_expiry_futures = now + timedelta(seconds=max(60, expiry_in - 120))

    return new_token


class ApiCallManager:
    """TR별 최소 호출 간격(초당 호출 제한)을 맞추기 위한 싱글톤."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.last_call_time = {}
        return cls._instance

    def wait_for_next_call(self, api_name, time_for_a_call):
        current_time = time.time()
        if api_name in self.last_call_time:
            elapsed_time = current_time - self.last_call_time[api_name]
            if elapsed_time < time_for_a_call:
                time.sleep(time_for_a_call - elapsed_time)
        self.last_call_time[api_name] = time.time()


api_manager = ApiCallManager()
