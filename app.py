import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from streamlit_js_eval import get_geolocation
from supabase import create_client, Client

# --- 1. SUPABASE CONFIGURATION ---
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(URL, KEY)

# --- 2. APP CONFIGURATION ---
st.set_page_config(page_title="AsthmaGuard", page_icon="🛡️", layout="wide", initial_sidebar_state="expanded")

# --- CUSTOM CSS ---
st.markdown("""
    <style>
    .login-container { background-color: #f0f7f9; padding: 2rem; border-radius: 15px; border: 1px solid #e0eef2; }
    .stButton>button { border-radius: 8px; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. DATABASE FUNCTIONS ---
def save_reading(email, reading):
    supabase.table("peak_flow_history").insert({"email": email, "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "reading": reading}).execute()

def save_act_score(email, score):
    supabase.table("act_scores").insert({"email": email, "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "score": score}).execute()

def load_history(email):
    res = supabase.table("peak_flow_history").select("*").eq("email", email).execute()
    df = pd.DataFrame(res.data)
    if df.empty: return pd.DataFrame(columns=["Date", "Peak Flow (L/min)"])
    df = df.rename(columns={"date": "Date", "reading": "Peak Flow (L/min)"})
    df['Date'] = pd.to_datetime(df['Date'])
    return df.sort_values("Date")

def load_act_history(email):
    res = supabase.table("act_scores").select("*").eq("email", email).execute()
    df = pd.DataFrame(res.data)
    if df.empty: return pd.DataFrame(columns=["Date", "ACT Score"])
    df = df.rename(columns={"date": "Date", "score": "ACT Score"})
    df['Date'] = pd.to_datetime(df['Date'])
    return df.sort_values("Date")

# --- PDF GENERATION LOGIC (Now correctly includes ACT) ---
def generate_report_html(name, city, b_group, triggers, history_df, act_df):
    history_html = history_df.tail(15).to_html(index=False)
    act_html = act_df.tail(10).to_html(index=False) if not act_df.empty else "<p>No ACT data available.</p>"
    return f"""
    <html><body style="font-family: Arial; padding: 20px;">
    <h1 style="color: #2E86C1;">AsthmaGuard AI - Medical Report</h1>
    <hr>
    <h3>Patient Profile</h3>
    <p><b>Name:</b> {name} | <b>City:</b> {city} | <b>Blood Group:</b> {b_group}</p>
    <p><b>Triggers:</b> {', '.join(triggers)}</p>
    <hr>
    <h3>Peak Flow History (Last 15 Readings)</h3>
    {history_html}
    <hr>
    <h3>ACT Score History</h3>
    {act_html}
    </body></html>
    """

# --- AUTH LOGIC ---
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "status_label" not in st.session_state: st.session_state.status_label = "Stable"
if "status_delta" not in st.session_state: st.session_state.status_delta = "Normal"

if not st.session_state.logged_in:
    col_img, col_form = st.columns([1, 1])
    with col_img: st.image("https://img.freepik.com/free-vector/doctor-character-background_1270-84.jpg", width=500)
    with col_form:
        st.markdown('<div class="login-container">', unsafe_allow_html=True)
        st.title("🛡️ AsthmaGuard")
        t1, t2 = st.tabs(["🔐 Login", "📝 Register"])
        with t1:
            with st.form("login"):
                e, p = st.text_input("Email"), st.text_input("Password", type="password")
                if st.form_submit_button("Login", use_container_width=True):
                    res = supabase.table("settings").select("*").eq("sender_email", e).execute()
                    if res.data and res.data[0]['account_password'] == p:
                        st.session_state.logged_in, st.session_state.user_email, st.session_state.user_name = True, e, res.data[0]['full_name']
                        st.session_state.doctor_email = res.data[0].get('doctor_email', "")
                        st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
else:
    # FRESH DATA FETCH
    history_df = load_history(st.session_state.user_email)
    act_df = load_act_history(st.session_state.user_email)
    raw_loc = get_geolocation()
    user_coords = raw_loc['coords'] if raw_loc else None

    with st.sidebar:
        st.title(f"👤 {st.session_state.user_name}")
        target_city = st.text_input("📍 Current City:", "Karachi")
        b_group = st.selectbox("Blood Group", ["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"], index=4)
        triggers = st.multiselect("Known Triggers", ["Dust", "Pollen", "Smoke"], ["Dust", "Smoke"])
        if st.button("🚪 Sign Out", use_container_width=True): st.session_state.logged_in = False; st.rerun()

    st.title("🖲️ AsthmaGuard Dashboard")
    m1, m2 = st.columns(2)
    m1.metric("Current Status", st.session_state.status_label, st.session_state.status_delta)
    m2.metric("Avg Peak Flow", f"{int(history_df['Peak Flow (L/min)'].mean()) if not history_df.empty else 0} L/min")

    tab1, tab2, tab3, tab4 = st.tabs(["📈 Health Tracker", "🚨 EMERGENCY SOS (WhatsApp)", "⛑️ First Aid Guide", "📋 Control Test (ACT)"])

    # SHARED PDF DATA
    full_report = generate_report_html(st.session_state.user_name, target_city, b_group, triggers, history_df, act_df)

    with tab1:
        st.subheader("📋 Expiratory Flow Rate (EFR)")
        c1, c2 = st.columns([1, 1.5])
        with c1:
            with st.container(border=True):
                best = st.number_input("Your Best Peak Flow (L/min)", 100, 800, 500)
                now = st.number_input("Today's Peak Flow (L/min)", 50, 800, 450)
                if st.button("📊 Calculate & Log Reading", use_container_width=True):
                    ratio = (now / best) * 100
                    save_reading(st.session_state.user_email, now)
                    st.session_state.status_label = "Green Zone" if ratio >= 80 else "Yellow Zone" if ratio >= 50 else "Red Zone"
                    st.rerun()
            st.download_button("📥 Download Full Medical PDF Report", full_report, file_name="Medical_Report.html", mime="text/html", use_container_width=True)
        with c2:
            st.subheader("📅 7-Day Respiratory Trend")
            if not history_df.empty: st.line_chart(history_df.tail(7).set_index("Date")["Peak Flow (L/min)"])

    with tab2:
        st.error("🔴 **EMERGENCY PROTOCOL ACTIVATED**")
        st.link_button("🚨 OPEN WHATSAPP SOS", f"https://wa.me/{st.session_state.doctor_email}?text=SOS", type="primary", use_container_width=True)
        st.map(pd.DataFrame({'lat': [user_coords['latitude'] if user_coords else 24.86], 'lon': [user_coords['longitude'] if user_coords else 67.00]}))

    with tab3:
        st.subheader("⛑️ Scenario-Based First Aid")
        with st.expander("🟡 I feel an attack starting (Yellow Zone)"):
            st.write("* **Stop activity**\n* **Remove triggers**\n* **Inhaler:** 2 puffs\n* **Wait:** 15 mins")
        with st.expander("🔴 Acute Asthma Attack (Red Zone)"):
            st.error("Follow the 4 x 4 Rule: 1. Sit Upright. 2. Take 4 Puffs. 3. Wait 4 Minutes. 4. Call Help.")

    with tab4:
        st.subheader("📋 Asthma Control Test™ (ACT)")
        col_f, col_c = st.columns([1, 1.5])
        with col_f:
            with st.form("act_form"):
                q1 = st.select_slider("Activity limitation?", options=[1, 2, 3, 4, 5])
                q2 = st.select_slider("Shortness of breath?", options=[1, 2, 3, 4, 5])
                q3 = st.select_slider("Night symptoms?", options=[1, 2, 3, 4, 5])
                q4 = st.select_slider("Inhaler use?", options=[1, 2, 3, 4, 5])
                q5 = st.select_slider("Control rating?", options=[1, 2, 3, 4, 5])
                if st.form_submit_button("Calculate ACT Score", use_container_width=True):
                    save_act_score(st.session_state.user_email, q1+q2+q3+q4+q5); st.rerun()
            st.download_button("📥 Download ACT History (Last 30 Days)", full_report, file_name="ACT_Report.html", mime="text/html", use_container_width=True)
        with col_c:
            if not act_df.empty: st.line_chart(act_df.set_index("Date")["ACT Score"])
