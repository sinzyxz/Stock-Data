import pandas as pd

# สร้างข้อมูลหุ้นตัวอย่าง
data = {
    "symbol": ["NVDA", "AMD", "AAPL", "MSFT", "GOOGL"],
    "open": [180.00, 200.00, 250.00, 500.00, 300.00],
    "high": [185.00, 205.00, 255.00, 510.00, 305.00],
    "low": [178.00, 198.00, 247.00, 495.00, 297.00],
    "close": [183.00, 202.00, 252.00, 505.00, 302.00],
    "volume": [1000000, 800000, 900000, 700000, 600000]
}

# แปลงข้อมูลเป็น DataFrame
df = pd.DataFrame(data)

# แสดงข้อมูล
print("US Stock Market Data")
print(df)

# คำนวณส่วนต่างราคาเปิดและปิด
df["price_change"] = df["close"] - df["open"]

print("\nPrice Change")
print(df[["symbol", "price_change"]])
