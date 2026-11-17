from datetime import datetime, timedelta
import math
import pandas as pd
import pytz
import requests
import streamlit as st
from streamlit_js_eval import get_geolocation

# 1. 頁面基本設定
st.set_page_config(
    page_title="臺灣主要港口 UKC 動態評估系統 v3.4",
    page_icon="🚢",
    layout="centered",
)

# 時區設定（強制對齊台灣當地時間 UTC+8）
tw_tz = pytz.timezone("Asia/Taipei")
now = datetime.now(tw_tz)

st.title("🚢 臺灣主要港口 UKC 動態評估系統")
st.caption(
    f"📅 當前台灣時間：{now.strftime('%Y-%m-%d %H:%M:%S')} (CST) ｜ 數據來源：中央氣象署 Open Data (F-A0021-001)"
)

# --- 2. 臺灣主要商港與工業港資料庫 (含官方設計水深與 Z0 平移常數) ---
PORTS_DB = {
    "高雄港第二港口 (內港口)": {
        "lat": 22.55,
        "lon": 120.30,
        "depth": 17.5,
        "z0": 0.55,
        "cwa_loc": "高雄市",
    },
    "高雄港第二港口 (洲際商港區)": {
        "lat": 22.54,
        "lon": 120.31,
        "depth": 22.0,
        "z0": 0.55,
        "cwa_loc": "高雄市",
    },
    "高雄港第一港口": {
        "lat": 22.62,
        "lon": 120.27,
        "depth": 12.5,
        "z0": 0.55,
        "cwa_loc": "高雄市",
    },
    "臺北港": {
        "lat": 25.16,
        "lon": 121.38,
        "depth": 16.0,
        "z0": 1.43,
        "cwa_loc": "新北市",
    },
    "基隆港 (外港)": {
        "lat": 25.15,
        "lon": 121.74,
        "depth": 16.0,
        "z0": 0.92,
        "cwa_loc": "基隆市",
    },
    "基隆港 (內港)": {
        "lat": 25.13,
        "lon": 121.74,
        "depth": 12.0,
        "z0": 0.92,
        "cwa_loc": "基隆市",
    },
    "臺中港": {
        "lat": 24.28,
        "lon": 120.52,
        "depth": 16.0,
        "z0": 2.67,
        "cwa_loc": "臺中市",
    },
    "花蓮港 (外港)": {
        "lat": 24.00,
        "lon": 121.64,
        "depth": 10.0,
        "z0": 0.71,
        "cwa_loc": "花蓮縣",
    },
    "花蓮港 (內港)": {
        "lat": 23.99,
        "lon": 121.63,
        "depth": 9.0,
        "z0": 0.71,
        "cwa_loc": "花蓮縣",
    },
    "蘇澳港": {
        "lat": 24.58,
        "lon": 121.86,
        "depth": 16.0,
        "z0": 0.92,
        "cwa_loc": "宜蘭縣",
    },
    "麥寮港 (工業專用港)": {
        "lat": 23.80,
        "lon": 120.20,
        "depth": 24.0,
        "z0": 1.85,
        "cwa_loc": "雲林縣",
    },
    "安平港": {
        "lat": 22.98,
        "lon": 120.15,
        "depth": 12.0,
        "z0": 0.47,
        "cwa_loc": "臺南市",
    },
    "布袋港": {
        "lat": 23.37,
        "lon": 120.15,
        "depth": 6.5,
        "z0": 1.15,
        "cwa_loc": "嘉義縣",
    },
    "澎湖港 (馬公)": {
        "lat": 23.57,
        "lon": 119.58,
        "depth": 7.0,
        "z0": 1.25,
        "cwa_loc": "澎湖縣",
    },
}


# 計算距離公式 (Haversine formula)
def calculate_distance(lat1, lon1, lat2, lon2):
  R = 6371
  dlat = math.radians(lat2 - lat1)
  dlon = math.radians(lon2 - lon1)
  a = (
      math.sin(dlat / 2) ** 2
      + math.cos(math.radians(lat1))
      * math.cos(math.radians(lat2))
      * math.sin(dlon / 2) ** 2
  )
  c = 2 * math.asin(math.sqrt(a))
  return R * c


# --- 3. 實時定位 (GPS) 與港口選擇 ---
st.subheader("📍 實時定位與港口參數設定")
geo_data = get_geolocation()

default_port = "高雄港第二港口 (內港口)"

if geo_data and "coords" in geo_data:
  lat = geo_data["coords"]["latitude"]
  lon = geo_data["coords"]["longitude"]
  st.success(f"已獲取定位 GPS: {lat:.4f}, {lon:.4f}")

  min_dist = float("inf")
  closest_port = default_port
  for p_name, info in PORTS_DB.items():
    dist = calculate_distance(lat, lon, info["lat"], info["lon"])
    if dist < min_dist:
      min_dist = dist
      closest_port = p_name

  default_port = closest_port
  st.info(
      f"🎯 系統已自動判定離您最近的港口為：**{default_port}** (直線距離約 {min_dist:.1f} 公里)"
  )
else:
  st.warning(
      "⚠️ 尚未取得 GPS 授權，預設為高雄港第二港口。您可透過下方選單切換全臺任一港口。"
  )

col_port, col_draft = st.columns([2, 1])
with col_port:
  port_names = list(PORTS_DB.keys())
  default_index = (
      port_names.index(default_port) if default_port in port_names else 0
  )
  selected_port = st.selectbox("選擇或切換港口與航道", port_names, index=default_index)

with col_draft:
  draft = st.number_input(
      "船舶吃水 Draft (m)", min_value=3.0, max_value=30.0, value=14.0, step=0.1
  )

current_port_info = PORTS_DB[selected_port]
channel_depth = current_port_info["depth"]
z0_offset = current_port_info["z0"]
cwa_location = current_port_info["cwa_loc"]

st.markdown(
    f"**當前選定港口**：`{selected_port}` ｜ **氣象預報區**：`{cwa_location}` ｜ **官方設計水深**：`-{channel_depth}m` ｜ **海圖基準差 ($Z_0$)**：`+{z0_offset}m`"
)

# 使用你的最新 CWA API Key
CWA_API_KEY = "CWA-49123E01-54C4-4A72-B6E2-EC8EF61BD678"


# --- 4. 純中央氣象署官方 API 抓取與時間軸精準對齊 ---
@st.cache_data(ttl=1800)
def fetch_cwa_official_tides(api_key, location_name):
  url = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-A0021-001"
  params = {"Authorization": api_key, "LocationName": location_name}
  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
      ),
      "Accept": "application/json",
  }

  try:
    res = requests.get(url, params=params, headers=headers, timeout=10)
    if res.status_code != 200:
      return None, f"HTTP 狀態碼錯誤: {res.status_code}"

    data = res.json()
    locations = data.get("records", {}).get("location", [])

    parsed_records = []
    for loc in locations:
      if loc.get("locationName") == location_name:
        for ele in loc.get("weatherElement", []):
          ele_name = ele.get("elementName", "")
          if (
              "TideHeights" in ele_name
              or "潮位" in ele_name
              or "Tide" in ele_name
          ):
            for t in ele.get("time", []):
              t_str = t.get("dataTime") or t.get("startTime")
              val = t.get("tideHeight") or t.get("value")
              if val is None and "parameter" in t:
                for p in t["parameter"]:
                  if "潮高" in p.get("parameterName", "") or "值" in p.get(
                      "parameterName", ""
                  ):
                    val = p.get("parameterValue")

              if t_str and val is not None:
                try:
                  num_val = float(val)
                  if abs(num_val) > 10.0:
                    num_val = num_val / 100.0
                  parsed_records.append(
                      {"raw_time": t_str, "msl_tide": num_val}
                  )
                except ValueError:
                  continue
    if parsed_records:
      return parsed_records, "SUCCESS"
    return None, "API 回傳成功，但找不到對應的逐時潮高欄位"

  except Exception as e:
    return None, f"連線異常: {str(e)}"


raw_records, fetch_msg = fetch_cwa_official_tides(CWA_API_KEY, cwa_location)

if not raw_records:
  st.error(f"❌ 無法取得中央氣象署即時潮汐數據（原因：{fetch_msg}）。請檢查 API Key 是否有效或稍後重試。")
  st.stop()

current_hour_start = now.replace(minute=0, second=0, microsecond=0)
aligned_forecast = []

for rec in raw_records:
  try:
    dt_obj = datetime.fromisoformat(rec["raw_time"].replace("Z", "+00:00"))
    if dt_obj.tzinfo is None:
      dt_obj = tw_tz.localize(dt_obj)
    else:
      dt_obj = dt_obj.astimezone(tw_tz)

    if current_hour_start <= dt_obj < current_hour_start + timedelta(hours=24):
      aligned_forecast.append({"datetime": dt_obj, "msl_tide": rec["msl_tide"]})
  except Exception:
    continue

aligned_forecast.sort(key=lambda x: x["datetime"])
unique_forecast = []
seen_hours = set()
for item in aligned_forecast:
  h_key = item["datetime"].strftime("%Y-%m-%d %H")
  if h_key not in seen_hours:
    seen_hours.add(h_key)
    unique_forecast.append(item)

if not unique_forecast:
  for i, rec in enumerate(raw_records[:24]):
    unique_forecast.append({
        "datetime": current_hour_start + timedelta(hours=i),
        "msl_tide": rec["msl_tide"],
    })

# --- 5. 核心公式計算：可用水深 = 航道設計底深 + (氣象署潮高 + Z0) ---
processed_results = []
current_status = "GREEN"
current_ukc_pct = 0.0

for idx, item in enumerate(unique_forecast):
  dt_tw = item["datetime"]
  msl_tide = item["msl_tide"]

  lat_tide = round(msl_tide + z0_offset, 2)
  avail_depth = round(channel_depth + lat_tide, 2)
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

  is_now = idx == 0
  time_label = dt_tw.strftime("%m/%d %H:00") + (" (現在)" if is_now else "")

  res_dict = {
      "datetime": dt_tw,
      "預報時間": time_label,
      "氣象署潮高(MSL)": round(msl_tide, 2),
      "絕對潮高(LAT/含Z0)": lat_tide,
      "可用總水深(m)": avail_depth,
      "UKC %": round(ukc_pct, 1),
      "狀態": status,
      "status_code": status_code,
  }

  if is_now:
    current_status = status_code
    current_ukc_pct = ukc_pct

  processed_results.append(res_dict)

# --- 6. 動態背景變色 ---
bg_color_map = {"GREEN": "#e8f8f5", "YELLOW": "#fef9e7", "RED": "#fadbd8"}
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
    unsafe_allow_html=True,
)

# --- 7. 當前狀態與智慧進港時間建議 ---
st.subheader("⏱️ 當前過灘狀態評估")

if current_status == "GREEN":
  st.success(
      f"🟢 **當前時刻 ({now.strftime('%H:%M')}) 在 {selected_port} 可安全過灘入港！** (UKC 裕度: `{current_ukc_pct:.1f}%`)"
  )
elif current_status == "YELLOW":
  st.warning(
      f"🟡 **當前時刻 ({now.strftime('%H:%M')}) 在 {selected_port} 為限制通行狀況。** (UKC 裕度: `{current_ukc_pct:.1f}%`)"
  )
else:
  st.error(
      f"🔴 **當前時刻 ({now.strftime('%H:%M')}) 在 {selected_port} 禁止過灘！** 水深裕度不足 (UKC 裕度: `{current_ukc_pct:.1f}%`)"
  )

next_green = next(
    (r for r in processed_results if r["status_code"] == "GREEN"), None
)
next_yellow = next(
    (r for r in processed_results if r["status_code"] == "YELLOW"), None
)

st.info("💡 **最近可進港時間指引**：")
if next_green:
  st.markdown(
      f"- 🟢 **最近安全通行時間 (UKC ≥ 15%)**：`{next_green['預報時間']}`（絕對潮高 `{next_green['絕對潮高(LAT/含Z0)']}m`，總水深 `{next_green['可用總水深(m)']}m`）"
  )
elif next_yellow:
  st.markdown(
      f"- 🟡 **最近限制通行時間 (UKC ≥ 10%)**：`{next_yellow['預報時間']}`（絕對潮高 `{next_yellow['絕對潮高(LAT/含Z0)']}m`，總水深 `{next_yellow['可用總水深(m)']}m`）"
  )
else:
  st.markdown("- 🔴 **未來 24 小時內皆無安全進港時段**，建議調整吃水或等待大潮期。")

# --- 8. 24小時預報詳細數據表 ---
st.subheader(f"📊 {selected_port} 未來 24 小時官方潮汐與 UKC 預報表")
df_display = pd.DataFrame(processed_results).drop(
    columns=["datetime", "status_code"]
)
st.dataframe(df_display, use_container_width=True, hide_index=True)