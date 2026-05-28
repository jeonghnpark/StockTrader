import pytest
from utils import ls_g3101


def test_get_current_tsla():
    result = ls_g3101.get_current("TSLA")

    # API 호출이 성공하고 응답이 None이 아닌지 확인
    assert result is not None, "get_current('TSLA') should return a result"

    # 최소한 'price' 필드가 있는지 확인 (ls_g3101의 응답 구조에 따라 다름)
    assert "price" in result, "Result should contain 'price' field"

    # 가격이 양수인지 확인
    assert float(result["price"]) > 0, "Price should be greater than 0"
