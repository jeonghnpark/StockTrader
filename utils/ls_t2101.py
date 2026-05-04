import requests
from utils.ls_auth import get_token_futures

# 선물/옵션 현재가 조회 (t2101)
def get_future_current_price(shcode):
    token = get_token_futures()
    if not token:
        return None

    url = "https://openapi.ls-sec.co.kr:8080/futureoption/market-data"
    
    headers = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "tr_cd": "t2101",
        "tr_cont": "N",
        "mac_address": ""
    }
    
    body = {
        "t2101InBlock": {
            "focode": shcode
        }
    }
    
    try:
        res = requests.post(url, headers=headers, json=body)
        if res.status_code == 200:
            data = res.json()
            outblock = data.get("t2101OutBlock")
            if outblock:
                return outblock
    except Exception as e:
        print(f"Error fetching future price for {shcode}: {e}")
        
    return None
