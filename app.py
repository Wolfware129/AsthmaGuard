import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
from streamlit_js_eval import get_geolocation
import geocoder 
from supabase import create_client, Client

# --- 1. SUPABASE CONFIGURATION ---
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(URL, KEY)

# --- 2. APP CONFIGURATION ---
st.set_page_config(page_title="AsthmaGuard", page_icon="🛡️", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
    <style>
    .login-container { background-color: #f0f7f9; padding: 2rem; border-radius: 15px; border: 1px solid #e0eef2; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. DATABASE FUNCTIONS ---
def load_history(email):
    try:
        res = supabase.table("peak_flow_history").select("*").eq("email", email).execute()
        df = pd.DataFrame(res.data)
        if df.empty:
            # SAFETY: Return a default row so the math doesn't break
            return pd.DataFrame({"Date": [datetime.now()], "Peak Flow (L/min)": [0]})
        df = df.rename(columns={"date": "Date", "reading": "Peak Flow (L/min)"})
        df['Date'] = pd.to_datetime(df['Date'])
        return df
    except:
        return pd.DataFrame({"Date": [datetime.now()], "Peak Flow (L/min)": [0]})

def verify_user(email, acc_pw):
    res = supabase.table("settings").select("*").eq("sender_email", email).execute()
    if res.data and res.data[0]['account_password'] == acc_pw:
        user = res.data[0]
        return True, user.get('doctor_email', ""), user['full_name']
    return False, None, None

# --- 4. SESSION STATE ---
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "status_label" not in st.session_state: st.session_state.status_label = "Stable"
if "status_delta" not in st.session_state: st.session_state.status_delta = "Normal"

# --- 5. LOGIN UI ---
if not st.session_state.logged_in:
    col_img, col_form = st.columns([1, 1])
    with col_img:
        # FIXED: use_container_width replaces the error in your screenshot
        st.image("https://img.freepik.com/free-vector/doctor-character-background_1270-84.jpg", use_container_width=True)
    with col_form:
        st.markdown('<div class="login-container">', unsafe_allow_html=True)
        st.title("🛡️ AsthmaGuard")
        with st.form("login_form"):
            e = st.text_input("Gmail Address")
            p = st.text_input("Password", type="password")
            if st.form_submit_button("Login", type="primary"):
                ok, de, fn = verify_user(e, p)
                if ok:
                    st.session_state.logged_in = True
                    st.session_state.user_email, st.session_state.user_name = e, fn
                    st.session_state.doctor_email = de
                    st.session_state.history_df = load_history(e) # Load data HERE
                    st.rerun()
                else: st.error("Invalid credentials.")
        st.markdown('</div>', unsafe_allow_html=True)
else:
    # --- 6. DASHBOARD ---
    with st.sidebar:
        st.title(f"👤 {st.session_state.user_name}")
        if st.button("🚪 Sign Out"):
            st.session_state.logged_in = False
            st.rerun()

    st.title("🖲️ AsthmaGuard Dashboard")
    
    # SAFETY CHECK: Ensure history_df exists before showing metrics
    if "history_df" not in st.session_state:
        st.session_state.history_df = load_history(st.session_state.user_email)

    m1, m2 = st.columns(2)
    m1.metric("Status", st.session_state.status_label, st.session_state.status_delta)
    
    # Calculate Average safely
    avg_pf = int(st.session_state.history_df['Peak Flow (L/min)'].mean())
    m2.metric("Avg Peak Flow", f"{avg_pf} L/min")

    st.subheader("Your Progress")
    st.line_chart(st.session_state.history_df.set_index("Date")["Peak Flow (L/min)"])
