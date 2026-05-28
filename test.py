from utils import ls_g3101
from utils import portfolio

print(ls_g3101.get_current("RKLB", "nasdaq"))

prc = portfolio.get_current_price("TSLA")
print(prc)


prc = portfolio.get_current_price("A7566000")
print(prc)
