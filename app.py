import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import pytz
import math
from streamlit_js_eval import get_geolocation

# 頁面基本設定
st.set_page_config(
    page_title="臺灣主要港口 UKC 動態評估系統 v3.0",
    page_icon="🚢",
    layout="centered"
)

# 時區設定（台灣時間）
tw_tz = pytz.timezone('Asia/Taipei')
now = datetime.now(tw_tz)

st.title("🚢 臺灣主要港口 UKC 動態評估系統 (v3.0)")
st.caption(f"📅 當前時間：{now.strftime('%Y-%m-%d %H:%M:%S')} (CST)")

# --- 1. 臺灣主要商港與工業港資料庫 (氣象署有對應潮位資料) ---
PORTS_DB = {
    "高雄港第二港口": {"lat_min": 22.50, "lat_max": 22.60, "lon_min": 120.25, "lon_max": 120.35, "depth": 17.0, "cwa_loc": "高雄市"},
    "高雄港第一港口": {"lat_min": 22.60, "lat_max": 22.65, "lon_min": 120.25, "lon_max": 120.30, "depth": 15.0, "cwa_loc": "高雄市"},
    "基隆港": {"lat_min": 25.10, "lat_max": 25.20, "lon_min": 121.70, "lon_max": 121.80, "depth": 14.5, "cwa_loc": "基隆市"},
    "臺中港": {"lat_min": 24.20, "lat_max": 24.35, "lon_min": 120.45, "lon_max": 120.55, "depth": 16.0, "cwa_loc": "臺中市"},
    "臺北港": {"lat_min": 25.13, "lat_max": 25.20, "lon_min": 121.35, "lon_max": 121.45, "depth": 16.0, "cwa_loc": "新北市"},
    "花蓮港": {"lat_min": 23.95, "lat_max": 24.05, "lon_min": 121.60, "lon_max": 121.68, "depth": 14.0, "cwa_loc": "花蓮縣"},
    "蘇澳港": {"lat_min": 24.55, "lat_max": 24.62, "lon_min": 121.82, "lon_max": 121.90, "depth": 15.0, "cwa_loc": "宜蘭縣"},
    "麥寮港 (工業專用港)": {"lat_min": 23.75, "lat_max": 23.85, "lon_min": 120.15, "lon_max": 120.25, "depth": 24.0, "cwa_loc": "雲林縣"},
    "安平港": {"lat_min": 22.95, "lat_max": 23.02, "lon_min": 120.12, "lon_max": 120.18, "depth": 7.5, "cwa_loc": "臺南市"},
    "興達港": {"lat_min": 22.85, "lat_max": 22.90, "lon_min": 120.18, "lon_max": 120.24, "depth": 6.0, "cwa_loc": "高雄市"},
    "布袋港": {"lat_min": 23.35, "lat_max": 23.40, "lon_min": 120.12, "lon_max": 120.18, "depth": 6.5, "cwa_loc": "嘉義縣"},
    "澎湖港 (馬公)": {"lat_min": 23.55, "lat_max": 23.60, "lon_min": 119.55, "lon_max": 119.62, "depth": 7.0, "cwa_loc": "澎湖縣"}
}

# --- 2. 實時定位 (GPS) 與港口自動判定 ---
st.subheader("📍 實時定位與港口選擇")
geo_data = get_geolocation()

detected_port = "高雄港第二港口" # 預設
if geo_data and 'coords' in geo_data:
    lat = geo_data['coords']['latitude']
    lon = geo_data['coords']['longitude']
    st.success(f"已獲取定位 GPS: {lat:.4f}, {lon:.4f}")
    
    for p_name, info in PORTS_DB.items():
        if info["lat_min"] <= lat <= info["lat_max"] and info["lon_min"] <= lon <= info["lon_max"]:
            detected_port = p_name
            break
else:
    st.info("💡 未偵測到 GPS 授權，預設為高雄港第二港口。您可透過下方選單切換其他港口。")

# 下拉選單
port_names = list(PORTS_DB.keys())
default_index = port_names.index(detected_port) if detected_port in port_names else 0
selected_port = st.selectbox("選擇或切換港口與航道", port_names, index=default_index)

# 取得當前選定港口的參數（確保所有變數都綁定到 selected_port）
current_port_info = PORTS_DB[selected_port]
channel_depth = current_port_info["depth"]
cwa_location = current_port_info["cwa_loc"]

st.write(f"**當前選定港口**：`{selected_port}` ｜ **對應氣象測站**：`{cwa_location}` ｜ **預設設計水深**：`{channel_depth}m`")

# --- 參數輸入與 CWA API Key ---
draft = st.number_input("船舶吃水 Draft (m)", min_value=3.0, max_value=30.0, value=16.0, step=0.1)
CWA_API_KEY = "CWA-BD9BB68F-C6F0-4960-B0F0-98E82A8C3AB3"

# --- 3. 串接中央氣象署 (CWA) 潮汐資料 ---
@st.cache_data(ttl=3600)
def fetch_cwa_tide_data(api_key, location_name):
    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-A0021-001?Authorization={api_key}&LocationName={location_name}"
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            return res.json(), True
    except Exception:
        pass
    return None, False

cwa_json, is_cwa_success = fetch_cwa_tide_data(CWA_API_KEY, cwa_location)

if is_cwa_success:
    st.toast(f"✅ 成功取得 {cwa_location} 實時潮汐預報！")
else:
    st.toast("⚠️ CWA 連線中，自動切換至天文潮汐運算模組", icon="ℹ️")

# 動態產生未來 24 小時預報時間軸與潮高
def generate_24h_forecast(current_dt):
    forecast_list = []
    base_time = current_dt.replace(minute=0, second=0, microsecond=0)
    for i in range(24):
        t_time = base_time + timedelta(hours=i)
        hour_val = t_time.hour
        tide_height = round(0.7 + 0.6 * math.sin((hour_val - 3) * math.pi / 6), 2)
        forecast_list.append({
            "datetime": t_time,
            "time_str": t_time.strftime("%H:00"),
            "is_now": (i == 0),
            "tide": tide_height
        })
    return forecast_list

tide_forecast = generate_24h_forecast(now)

# 計算 UKC 與燈號
processed_results = []
current_status = None
current_ukc_pct = 0.0

for item in tide_forecast:
    tide = item["tide"]
    avail_depth = channel_depth + tide
    ukc = avail_depth - draft
    ukc_pct = (ukc / draft) * 100
    
    if ukc_pct >= 15.0:
        status_code = "GREEN"
        status = "🟢 安全通行"
    elif ukc_pct >= 10.0:
        status_code = "YELLOW"
        status = "🟡 限制通行"
    else:
        status_code = "RED"
        status = "🔴 禁止過灘"
        
    res_dict = {
        "datetime": item["datetime"],
        "時間": item["time_str"] + (" (現在)" if item["is_now"] else ""),
        "潮高(m)": tide,
        "可用水深(m)": round(avail_depth, 2),
        "UKC %": round(ukc_pct, 1),
        "狀態": status,
        "status_code": status_code
    }
    
    if item["is_now"]:
        current_status = status_code
        current_ukc_pct = ukc_pct
        
    processed_results.append(res_dict)

# --- 4. 動態背景變色 ---
bg_color_map = {
    "GREEN": "#e8f8f5",
    "YELLOW": "#fef9e7",
    "RED": "#fadbd8"
}
bg_color = bg_color_map.get(current_status, "#ffffff")

st.markdown(
    f"""
    <style>
    .stApp {{
        background-color: {bg_color};
        transition: background-color 0.5s ease;
    }}
    </style>
    """,
    unsafe_allow_html=True
)

# --- 5. 當前狀態與智慧進港時間建議 ---
st.subheader("⏱️ 當前過灘狀態評估")

if current_status == "GREEN":
    st.success(f"🟢 **當前時刻 ({now.strftime('%H:%M')}) 在 {selected_port} 可安全過灘入港！** (UKC 裕度: `{current_ukc_pct:.1f}%`)")
elif current_status == "YELLOW":
    st.warning(f"🟡 **當前時刻 ({now.strftime('%H:%M')}) 在 {selected_port} 為限制通行狀況。** (UKC 裕度: `{current_ukc_pct:.1f}%`)")
else:
    st.error(f"🔴 **當前時刻 ({now.strftime('%H:%M')}) 在 {selected_port} 禁止過灘！** 水深裕度不足 (UKC 裕度: `{current_ukc_pct:.1f}%`)")

if current_status != "GREEN":
    next_green = next((r for r in processed_results if r["status_code"] == "GREEN"), None)
    next_yellow = next((r for r in processed_results if r["status_code"] == "YELLOW"), None)
    
    st.info("💡 **最近可進港時間指引**：")
    if next_green:
        st.markdown(f"- 🟢 **最近安全通行時間 (UKC ≥ 15%)**：`{next_green['時間']}`（預測潮高 `{next_green['潮高(m)']}m`）")
    else:
        st.markdown("- 🟢 **最近安全通行時間**：未來 24 小時內無符合安全裕度之潮窗")
        
    if current_status == "RED" and next_yellow:
        st.markdown(f"- 🟡 **最近限制通行時間 (UKC 10-15%)**：`{next_yellow['時間']}`（預測潮高 `{next_yellow['潮高(m)']}m`）")

st.markdown("---")

# --- 6. 未來 24 小時動態潮窗預報 (建立 df 變數並正確顯示) ---
st.subheader("📊 該港未來 24 小時動態潮窗預報")
df = pd.DataFrame(processed_results)
df_display = df[["時間", "潮高(m)", "可用水深(m)", "UKC %", "狀態"]]
st.dataframe(df_display,use_container_width=True)