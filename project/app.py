import streamlit as st
import pandas as pd
from datetime import datetime
from services.tiktok_api import TikTokService
from services.processor import DataProcessor
from services.image_match import ImageMatcher
from utils.config import THEME_COLOR, BG_COLOR
import time

# ── PRIVATE API CONFIGURATION ──
# Hardcoding these keys here hides them from the sidebar UI
API_CONFIG = {
    "APIFY_TOKEN": "apify_api_dnMdXey1suNihTQbGrOQRDImPI04pu4jVAZi",
    "GEMINI_KEY": "AIzaSy..." # Paste your actual Gemini key here
}

# Initialize Services
api_service = TikTokService()
processor = DataProcessor()

# ── PAGE SETUP ──
st.set_page_config(page_title="TikTrend Bot MVP", layout="wide")

st.markdown(f"""
<style>
    .stApp {{ background-color: {BG_COLOR}; color: white; }}
    .bot-terminal {{
        background: #000; border: 1px solid {THEME_COLOR}; color: {THEME_COLOR};
        font-family: monospace; padding: 15px; border-radius: 8px; height: 120px;
        overflow-y: auto; margin-bottom: 20px;
    }}
    .trend-card {{
        background: #151515; border-left: 5px solid {THEME_COLOR};
        padding: 20px; margin-bottom: 15px; border-radius: 0 10px 10px 0;
    }}
    .intent-badge {{
        background: {THEME_COLOR}; color: white; padding: 2px 10px;
        border-radius: 4px; font-size: 10px; font-weight: bold;
    }}
</style>
""", unsafe_allow_html=True)

# ── STATE MANAGEMENT ──
if 'results' not in st.session_state:
    st.session_state['results'] = []

# ── SIDEBAR CONTROLS ──
with st.sidebar:
    st.header("🤖 BOT CONTROL")
    mode = st.selectbox("Scan Mode", ["Hashtag", "Keyword", "User Account"])
    query = st.text_input("Target Term", value="#womensfashion")
    
    st.divider()
    st.header("⚙️ FILTERS")
    limit = st.slider("Max Videos", 5, 50, 15)
    min_views_input = st.number_input("Minimum Views", value=1000)
    min_likes_input = st.number_input("Minimum Likes", value=0)
    sort_by = st.selectbox("Sort Live Feed By", ["Views", "Likes", "Date"])
    
    # API Key inputs removed from here to keep the UI clean
    
    st.divider()
    if st.button("⚡ EXECUTE SCAN", use_container_width=True):
        progress_bar = st.progress(0)
        status_text = st.empty()

        status_text.text("Connecting to TikTok API...")
        progress_bar.progress(25)

        # Ensure the fetch_data method in your TikTokService handles the hidden token
        raw_data = api_service.fetch_data(query, mode, limit)

        status_text.text("Analyzing Buyer Intent & Engagement...")
        progress_bar.progress(75)

        st.session_state['results'] = processor.analyze_trends(raw_data, min_views_input)

        progress_bar.progress(100)
        status_text.text("Scan Complete!")
        time.sleep(1)
        status_text.empty()
        progress_bar.empty()

# ── MAIN DASHBOARD ──
st.title("TikTrend Dashboard")
tab1, tab2, tab3 = st.tabs(["📊 LIVE FEED", "🔎 VISUAL MATCH", "📥 EXPORT"])

with tab1:
    if st.session_state['results']:
        display_data = [v for v in st.session_state['results'] if v['Views'] >= min_views_input and v.get('Likes', 0) >= min_likes_input]
        
        if sort_by == "Views":
            display_data.sort(key=lambda x: x['Views'], reverse=True)
        elif sort_by == "Likes":
            display_data.sort(key=lambda x: x.get('Likes', 0), reverse=True)

        col1, col2 = st.columns(2)
        for i, vid in enumerate(display_data):
            target_col = col1 if i % 2 == 0 else col2
            with target_col:
                badge = '<span class="intent-badge">🔥 HIGH INTENT</span>' if vid['High Intent'] else ""
                st.markdown(f"""
                <div class="trend-card">
                    <div style="display:flex; justify-content:space-between;">
                        <b>@{vid['Creator']}</b> {badge}
                    </div>
                    <p style="font-size:14px; color:#ddd; margin:10px 0;">{vid['Description'][:130]}...</p>
                    <div style="font-size:12px; color:#888;">
                        👁️ {vid['Views']:,} | ❤️ {vid.get('Likes', 0):,} | 📅 {vid['Date']}
                    </div>
                    <div style="margin-top:10px;">
                        <a href="{vid['URL']}" target="_blank" style="color:#25d366; text-decoration:none;">View Video →</a>
                    </div>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("System idle. Run a scan to see live data.")

with tab2:
    st.subheader("🔎 Live Visual Deep Search")
    st.write("Upload an image to trigger a NEW search across TikTok for 100% style matches.")
    
    uploaded_file = st.file_uploader("Upload clothing photo", type=['jpg', 'png', 'jpeg'])
    
    if uploaded_file:
        st.image(uploaded_file, width=200, caption="Search Reference")

        with st.spinner("Analyzing image and searching TikTok database..."):
            # Using the hidden keys from API_CONFIG
            ranked_matches, query_used, error = ImageMatcher.get_ranked_matches(
                uploaded_file,
                apify_token=API_CONFIG["APIFY_TOKEN"],
                gemini_key=API_CONFIG["GEMINI_KEY"]
            )

            if error or not ranked_matches:
                st.warning("No direct matches found for this specific style in the live database.")
            else:
                st.success(f"Found {len(ranked_matches)} exact matches based on visual analysis!")

                for match in ranked_matches:
                    # Adjusting key names based on your common data structure
                    score_val = match.get('score', match.get('similarity_score', 0))
                    score_pct = int(score_val * 100)
                    
                    st.markdown(f"""
                    <div style="background:#1a1a1a; padding:15px; border-radius:10px; border-left: 5px solid {THEME_COLOR}; margin-bottom:10px;">
                        <div style="display:flex; justify-content:space-between;">
                            <b>Style Match Found</b>
                            <span style="color:{THEME_COLOR}; font-weight:bold;">{score_pct}% Similarity</span>
                        </div>
                        <p style="font-size:13px; color:#ddd; margin:8px 0;">{match.get('description', match.get('Description', 'No description available'))}</p>
                        <div style="font-size:11px; color:#888; margin-bottom:8px;">
                            👁️ {match.get('views', match.get('Views', 0)):,} Views | ❤️ {match.get('likes', match.get('Likes', 0)):,} Likes
                        </div>
                        <a href="{match.get('url', match.get('URL', '#'))}" target="_blank" style="color:{THEME_COLOR}; font-weight:bold; text-decoration:none;">Open in TikTok →</a>
                    </div>
                    """, unsafe_allow_html=True)

with tab3:
    if st.session_state['results']:
        df = pd.DataFrame(st.session_state['results'])
        st.dataframe(df, use_container_width=True)
        st.download_button("📥 DOWNLOAD CSV", df.to_csv(index=False).encode('utf-8'), "trends.csv")