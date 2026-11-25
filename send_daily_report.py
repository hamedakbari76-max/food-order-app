import os
import json
import requests
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
import gspread
from google.oauth2.service_account import Credentials

# ---------------- تنظیمات ----------------
KAVENEGAR_API_KEY = os.getenv("KAVENEGAR_API_KEY")
RECEPTOR = "09196582328"
SHEET_NAME = os.getenv("SHEET_NAME", "foodorder")

TEHRAN_TZ = ZoneInfo("Asia/Tehran")

MENU = {
    5: "کوبیده",
    6: "قرمه سبزی",
    0: "جوجه کباب",
    1: "قیمه",
    2: "عدس پلو",
    3: "جوجه کباب",
}

DAY_NAMES = {
    5: "شنبه",
    6: "یکشنبه",
    0: "دوشنبه",
    1: "سه‌شنبه",
    2: "چهارشنبه",
    3: "پنجشنبه",
    4: "جمعه",
}

# ---------------- اتصال به گوگل شیت ----------------
def get_gspread_client():
    creds_json = os.getenv("GCP_SERVICE_ACCOUNT")
    if not creds_json:
        raise RuntimeError("GCP_SERVICE_ACCOUNT پیدا نشد")

    try:
        creds_dict = json.loads(creds_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"GCP_SERVICE_ACCOUNT یک JSON معتبر نیست: {exc}"
        ) from exc

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = Credentials.from_service_account_info(
        creds_dict,
        scopes=scopes,
    )
    return gspread.authorize(credentials)


def load_today_orders():
    client = get_gspread_client()
    sh = client.open(SHEET_NAME)
    ws = sh.worksheet("Orders")

    data = ws.get_all_records()
    df = pd.DataFrame(data)

    if df.empty:
        return pd.DataFrame()

    today_str = datetime.now(TEHRAN_TZ).strftime("%Y-%m-%d")
    today_orders = df[df["date"] == today_str]

    if not today_orders.empty:
        today_orders = (
            today_orders
            .sort_values("timestamp")
            .drop_duplicates(subset=["code"], keep="last")
        )

    return today_orders

# ---------------- ساخت پیام ----------------
def build_message(orders_df):
    now = datetime.now(TEHRAN_TZ)
    day_name = DAY_NAMES.get(now.weekday(), "")
    menu_item = MENU.get(now.weekday(), "نامشخص")

    if orders_df.empty:
        yes_count = 0
    else:
        yes_count = len(
            orders_df[
                orders_df["wants"].isin(
                    ["بله", True, "TRUE", "yes", 1]
                )
            ]
        )

    message = (
        f"گزارش سفارش غذا - {day_name}\n"
        f"منو: {menu_item}\n"
        f"تعداد بله: {yes_count} نفر"
    )
    return message

# ---------------- ارسال پیامک ----------------
def send_sms(message):
    if not KAVENEGAR_API_KEY:
        raise RuntimeError("KAVENEGAR_API_KEY پیدا نشد")

    url = (
        f"https://api.kavenegar.com/v1/"
        f"{KAVENEGAR_API_KEY}/sms/send.json"
    )
    params = {
        "receptor": RECEPTOR,
        "message": message,
    }

    response = requests.get(url, params=params, timeout=15)

    print(f"HTTP status: {response.status_code}")
    print(f"Content-Type: {response.headers.get('Content-Type', 'نامشخص')}")

    if not response.ok:
        raise RuntimeError(
            f"خطا در درخواست کاوه‌نگار؛ "
            f"کد HTTP {response.status_code}: "
            f"{response.text[:300]}"
        )

    try:
        result = response.json()
    except requests.exceptions.JSONDecodeError as exc:
        raise RuntimeError(
            "پاسخ کاوه‌نگار JSON معتبر نیست؛ "
            f"کد HTTP {response.status_code}"
        ) from exc

    status = result.get("return", {}).get("status")

    if status == 200:
        print("✅ پیامک با موفقیت ارسال شد")
        print(message)
        return True

    print("❌ خطا در ارسال:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return False

# ---------------- اجرا ----------------
if __name__ == "__main__":
    print("شروع ارسال گزارش روزانه...")
    orders = load_today_orders()
    message = build_message(orders)
    send_sms(message)
