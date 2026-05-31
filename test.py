from utils import ls_g3101, ls_g3106, ls_t1101, ls_t2111
from utils import portfolio


# 해외주식 현재가 조회
# prc = portfolio.get_current_price("TSLA")
prc = ls_g3106.get_current("TSLA", "nasdaq")
print(prc)

# 국내 선물 현재가 조회
# prc = portfolio.get_current_price("A7566000")
# prc = ls_t2101.get_future_current_price("A7566000")
# print(prc)

# 국내주식 현재가 조회
# prc_kr_stock = ls_t1101.get_current("005930")
# print(prc_kr_stock)

# prc = ls_t1101.get_current_with_fallback("459580")
# print(prc)
