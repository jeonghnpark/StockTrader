"""LS Open API 로깅 설정 - 파일 + 콘솔 통합."""

import logging
import os
from pathlib import Path

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "api.log"


def setup_logging():
    """로깅 설정: 파일과 콘솔에 동시 기록."""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # 기존 핸들러 제거 (중복 방지)
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # 포맷터
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 파일 핸들러 (DEBUG 이상 모두 기록)
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # 콘솔 핸들러 (WARNING 이상만 표시)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    return root_logger


def get_logger(name):
    """모듈별 logger 반환."""
    return logging.getLogger(name)


def read_log_file(num_lines=50):
    """최근 N줄의 로그 읽기."""
    if not LOG_FILE.exists():
        return "로그 파일이 없습니다."

    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
            recent_lines = lines[-num_lines:]
            return "".join(recent_lines)
    except Exception as e:
        return f"로그 읽기 오류: {e}"


# 모듈 로드 시 자동 설정
setup_logging()
