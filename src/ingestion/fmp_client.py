
import os
import requests
from dotenv import load_dotenv

# โหลดค่าจากไฟล์ .env
load_dotenv()

# อ่าน API Key จาก Environment Variable
API_KEY = os.getenv("FMP_API_KEY")

# URL หลักของ FMP
BASE_URL = "https://financialmodelingprep.com/stable"


def fetch_daily_prices(symbol, start_date, end_date):
    """
    ดึงข้อมูลราคาหุ้นรายวันจาก FMP

    symbol: ชื่อหุ้น เช่น AAPL
    start_date: วันเริ่มต้น เช่น 2025-11-18
    end_date: วันสิ้นสุด เช่น 2026-11-18
    """

    # ตรวจสอบ API Key
    if not API_KEY:
        raise ValueError("ไม่พบ FMP_API_KEY ในไฟล์ .env")

    # สร้าง URL ของ Endpoint
    endpoint = f"{BASE_URL}/historical-price-eod/full"

    # กำหนด Parameters ที่จะส่งไปให้ API
    params = {
        "symbol": symbol,
        "from": start_date,
        "to": end_date,
        "apikey": API_KEY
    }

    # ส่ง HTTP GET Request
    response = requests.get(
        endpoint,
        params=params,
        timeout=30
    )

    # ตรวจสอบ HTTP Status Code
    response.raise_for_status()

    # แปลง JSON Response เป็น Python Object
    data = response.json()

    # ตรวจสอบรูปแบบข้อมูล
    if not isinstance(data, list):
        raise ValueError(f"API ส่งข้อมูลไม่ใช่ List: {data}")

    return data
