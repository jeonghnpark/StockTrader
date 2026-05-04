import pandas as pd
import os

print(3)
current_abs = os.path.dirname(os.path.abspath(__file__))
print(current_abs)
csv = os.path.join(current_abs, "../../data/trade_history.csv")
df = pd.read_csv(csv)
# print(df)

df["ticker"] = df["ticker"].str.replace(r"\.(KS|KQ)$", "", regex=True)
df.to_csv("./data/trade_history.csv", index=False)
