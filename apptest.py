import streamlit as st
import pandas as pd
from pyproj import Transformer
import folium
from streamlit_folium import st_folium

# 1. 網頁基本設定 (寬螢幕模式)
st.set_page_config(layout="wide", page_title="臺灣老樹物種空間分布")

# 自訂 CSS 樣式（模擬原 R 版本的 Info-box 與統計盒）
st.markdown("""
    <style>
    .info-box { background-color: #e8f4f8; border-left: 4px solid #2196F3; padding: 10px; margin: 10px 0; border-radius: 4px; font-size: 14px; color: #1a1a1a; }
    .stat-box { background-color: #fff3e0; border-left: 4px solid #FF9800; padding: 8px; margin: 5px 0; border-radius: 4px; font-size: 14px; color: #1a1a1a; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

st.title("🌳 臺灣老樹物種空間分布")

# 2. 側邊欄：檔案上傳
with st.sidebar:
    st.header("📂 資料輸入")
    uploaded_file = st.file_uploader("上傳 Excel 檔案", type=["xlsx", "xls"])
    st.markdown("---")

# 如果尚未上傳檔案，顯示提示
if uploaded_file is None:
    st.info("💡 請先在左側上傳老樹的 Excel 檔案以開始分析。")
else:
    # 讀取資料並清洗欄位
    df_raw = pd.read_excel(uploaded_file)
    df_raw.columns = df_raw.columns.str.strip()
    
    # 🕵️‍♂️ 座標欄位自動偵測 (TWD97 X/Y)
    x_col_list = [c for c in df_raw.columns if '97' in c and ('X' in c or '經' in c) or c.lower() == 'x']
    y_col_list = [c for c in df_raw.columns if '97' in c and ('Y' in c or '緯' in c) or c.lower() == 'y']
    
    if not x_col_list or not y_col_list:
        st.error("❌ 找不到 TWD97 座標欄位，請確認 Excel 包含「97經度/X」與「97緯度/Y」。")
        st.stop()
        
    x_col, y_col = x_col_list[0], y_col_list[0]
    
    # 排除座標缺失值並確保為數字
    df_clean = df_raw.dropna(subset=[x_col, y_col]).copy()
    df_clean[x_col] = pd.to_numeric(df_clean[x_col], errors='coerce')
    df_clean[y_col] = pd.to_numeric(df_clean[y_col], errors='coerce')
    df_clean = df_clean.dropna(subset=[x_col, y_col])
    
    # 🗺️ 座標轉換 (TWD97 EPSG:3826 -> WGS84 EPSG:4326)
    transformer = Transformer.from_crs("epsg:3826", "epsg:4326", always_xy=True)
    lngs, lats = transformer.transform(df_clean[x_col].values, df_clean[y_col].values)
    df_clean['LNG'] = lngs
    df_clean['LAT'] = lats
    
    # 🕵️‍♂️ 自動偵測：行政區、物種、編號欄位
    city_col = [c for c in df_clean.columns if any(k in c for k in ['城市', '縣市', '行政區', 'county', 'city'])][0] if [c for c in df_clean.columns if any(k in c for k in ['城市', '縣市', '行政區', 'county', 'city'])] else None
    sp_col = [c for c in df_clean.columns if any(k in c for k in ['物種', 'species', '樹種', 'tree'])][0] if [c for c in df_clean.columns if any(k in c for k in ['物種', 'species', '樹種', 'tree'])] else None
    id_col = [c for c in df_clean.columns if any(k in c.lower() for k in ['編號', '序號', '樹號', 'id', 'no'])][0] if [c for c in df_clean.columns if any(k in c.lower() for k in ['編號', '序號', '樹號', 'id', 'no'])] else None

    # 3. 側邊欄：多功能互動篩選器
    with st.sidebar:
        # 🗺 行政區篩選（支援全選功能）
        st.subheader("🗺 行政區篩選")
        if city_col:
            unique_cities = sorted(df_clean[city_col].dropna().unique())
            
            # 使用 Session State 來控制全選狀態
            if "select_all_cities" not in st.session_state:
                st.session_state.select_all_cities = True
                
            select_all = st.checkbox("全選 / 取消全選", value=st.session_state.select_all_cities, key="city_toggle")
            
            # 根據全選勾選框，動態調整預選清單
            default_cities = unique_cities if select_all else []
            selected_cities = st.multiselect("選擇縣市/行政區", options=unique_cities, default=default_cities)
        else:
            st.warning("找不到行政區相關欄位")
            selected_cities = []

        st.markdown("---")
        
        # 🌿 物種篩選
        st.subheader("🌿 物種篩選")
        if sp_col:
            unique_species = sorted(df_clean[sp_col].dropna().unique())
            species_options = ["全部物種"] + unique_species
            selected_species = st.selectbox("選擇特定物種", options=species_options, index=0)
        else:
            st.warning("找不到物種相關欄位")
            selected_species = "全部物種"

        st.markdown("---")
        
        # 🔢 編號欄位選擇器
        st.subheader("🔢 編號欄位")
        st.markdown('<div class="info-box">滑鼠移至標記上方即顯示編號（tooltip）；點擊標記可在 popup 中查看完整資訊。</div>', unsafe_allow_html=True)
        
        all_cols = list(df_clean.columns)
        if id_col and id_col in all_cols:
            # 將偵測到的編號欄位排到最前面作為預設
            all_cols.insert(0, all_cols.pop(all_cols.index(id_col)))
        
        chosen_id_col = st.selectbox("選擇要作為編號的欄位", options=all_cols, index=0)

    # 4. 資料過濾邏輯（按下開始分析或自動連動，Streamlit 預設會自動連動）
    df_filtered = df_clean.copy()
    
    if city_col and selected_cities:
        df_filtered = df_filtered[df_filtered[city_col].isin(selected_cities)]
    elif city_col and not selected_cities:
        # 如果沒選任何城市，強制排空資料
        df_filtered = df_filtered.iloc[0:0]
        
    if sp_col and selected_species != "全部物種":
        df_filtered = df_filtered[df_filtered[sp_col] == selected_species]

    # 5. 側邊欄下方：顯示數據統計盒
    with st.sidebar:
        st.markdown("---")
        st.subheader("📊 資料統計")
        st.markdown(f'<div class="stat-box">📍 筆數：{len(df_filtered)} 筆</div>', unsafe_allow_html=True)
        if sp_col and not df_filtered.empty:
            st.markdown(f'<div class="stat-box">🌿 物種數：{df_filtered[sp_col].nunique()} 種</div>', unsafe_allow_html=True)
        if city_col and not df_filtered.empty:
            st.markdown(f'<div class="stat-box">🏙 城市數：{df_filtered[city_col].nunique()} 區</div>', unsafe_allow_html=True)

    # 6. 主畫面分頁 (Tabs) 呈現
    tab1, tab2 = st.tabs(["🗺 互動地圖", "📋 資料表"])
    
    if df_filtered.empty:
        st.warning("⚠️ 目前篩選條件下無資料，請調整左側篩選器。")
    else:
        # ── 頁籤 1：互動地圖 ──
        with tab1:
            st.markdown('<div class="info-box">💡 滑鼠移至標記上方顯示編號；點擊標記查看詳細資訊；滑鼠滾輪縮放地圖。</div>', unsafe_allow_html=True)
            
            # (這裡保持原本的 Folium 地圖設定，為了排版簡化，以下為地圖渲染代碼...)
            center_lat = df_filtered['LAT'].mean()
            center_lng = df_filtered['LNG'].mean()
            m = folium.Map(location=[center_lat, center_lng], zoom_start=11, tiles="OpenStreetMap")
            
            # ... 這裡省略你原本寫的點位 for 迴圈 (請保留你原本的點位程式碼) ...
            for idx, row in df_filtered.iterrows():
                label_val = str(row[chosen_id_col]) if chosen_id_col else str(idx + 1)
                  folium.CircleMarker(
                    location=[row['LAT'], row['LNG']],
                     radius=6,
                     color="#B71C1C",       # 換成深紅色外框（或用 "red"）
                     weight=1,              # 外框線條粗細，調細一點更像圓點
                     fill=True,
                     fill_color="#E53935",  # 換成亮紅色填滿（或用 "red"）
                     fill_opacity=0.85,     # 提高一點透明度讓顏色更飽和
                     popup=folium.Popup(popup_html, max_width=250),
                     tooltip=folium.Tooltip(label_val, permanent=False)
                    ).add_to(m)
            
            # 渲染地圖
            st_folium(m, width="100%", height=550, returned_objects=[])

            # ──────────────────────────────────────────────────────────────────
            # ➕ 這裡開始加入：匯出地圖圖片控制面板 (完美復刻 R 版本)
            # ──────────────────────────────────────────────────────────────────
            st.markdown("""
                <div style="background-color: #f3e5f5; border-left: 4px solid #9C27B0; padding: 12px; border-radius: 6px; margin-top: 15px;">
                    <h6 style="margin: 0 0 8px 0; color: #6A1B9A; font-weight: bold; font-size:16px;">🖼 匯出互動地圖為圖片</h6>
                </div>
            """, unsafe_allow_html=True)
            
            # 讓使用者調整解析度寬高
            col_w, col_h = st.columns(2)
            with col_w:
                img_width = st.number_input("圖片寬度 (px)", value=1200, min_value=400, max_value=4000, step=100)
            with col_h:
                img_height = st.number_input("圖片高度 (px)", value=800, min_value=300, max_value=3000, step=100)
                
            if st.button("🔄 產生高解析度地圖圖片（請稍候約 5 秒）", type="primary"):
                with st.spinner("⏳ 正在啟動背景瀏覽器進行高解析度截圖..."):
                    try:
                        import os
                        import time
                        from selenium import webdriver
                        from selenium.webdriver.chrome.service import Service
                        
                        tmp_html = "temp_map.html"
                        m.save(tmp_html)
                        
                        options = webdriver.ChromeOptions()
                        options.add_argument('--headless')
                        options.add_argument('--no-sandbox')
                        options.add_argument('--disable-dev-shm-usage')
                        options.add_argument('--disable-gpu')
                        options.add_argument(f'--window-size={img_width},{img_height}')
                        
                        # ── 👑 雲端 Linux 與 本地 Windows 環境自動雙棲適配 ──
                        # 檢查是否在 Streamlit Cloud (Linux) 運作，且有系統自帶的 Chromium
                        if os.path.exists("/usr/bin/chromium"):
                            options.binary_location = "/usr/bin/chromium"
                            
                        if os.path.exists("/usr/bin/chromedriver"):
                            # 雲端直接使用 packages.txt 裝好的系統驅動
                            service = Service("/usr/bin/chromedriver")
                        else:
                            # 如果在自己電腦 (Windows)，才動態載入 webdriver-manager
                            from webdriver_manager.chrome import ChromeDriverManager
                            service = Service(ChromeDriverManager().install())
                        
                        # 啟動瀏覽器
                        driver = webdriver.Chrome(service=service, options=options)
                        
                        abs_path = os.path.abspath(tmp_html)
                        driver.get(f"file:///{abs_path}")
                        time.sleep(4) # 給雲端多一點緩衝時間載入 OSM 地圖 tiles
                        
                        img_path = "map_output.png"
                        driver.save_screenshot(img_path)
                        driver.quit()
                        
                        if os.path.exists(tmp_html):
                            os.remove(tmp_html)
                            
                        with open(img_path, "rb") as file:
                            st.session_state.map_img_bytes = file.read()
                            
                        if os.path.exists(img_path):
                            os.remove(img_path)
                            
                        st.success("🎉 圖片產生成功！請點擊下方按鈕下載。")
                        
                    except Exception as e:
                        st.error(f"❌ 產生圖片失敗，錯誤訊息: {e}")
            
            # 如果記憶體中有成功產生的圖片，顯示真正的下載按鈕
            if "map_img_bytes" in st.session_state:
                st.download_button(
                    label="⬇ 下載地圖圖片 (PNG)",
                    data=st.session_state.map_img_bytes,
                    file_name="老樹空間分布地圖.png",
                    mime="image/png",
                    use_container_width=True
                )

        # ── 頁籤 2：資料表與下載 ──
        with tab2:
            st.markdown("### 篩選後的完整資料")
            
            # 提供 Excel 下載按鈕（模仿原 R 版本的 downloadHandler）
            # 為了方便下載，先將轉換好的經緯度合併進去
            df_export = df_filtered.copy()
            df_export = df_export.rename(columns={'LNG': 'WGS84經度', 'LAT': 'WGS84緯度'})
            
            # 轉換為 Excel 二進位資料供下載
            import io
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_export.to_excel(writer, index=False, sheet_name='老樹篩選結果')
            
            st.download_button(
                label="⬇ 匯出篩選結果 Excel",
                data=buffer.getvalue(),
                file_name="老樹資料篩選結果_python.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
            # 顯示表格
            st.dataframe(df_filtered, use_container_width=True)
