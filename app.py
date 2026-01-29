import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
import base64
from streamlit_js_eval import get_geolocation
import geocoder 
import webbrowser
from supabase import create_client, Client # Added for permanent cloud storage

# --- 1. SUPABASE CONFIGURATION ---
# This line tells the app to look in the Streamlit Cloud "Vault"
# If this name doesn't match the one in your dashboard exactly, it will fail
URL = st.secrets["SUPABASE_URL"] 
KEY = st.secrets["SUPABASE_KEY"]

supabase: Client = create_client(URL, KEY)

# --- 2. APP CONFIGURATION ---
st.set_page_config(
    page_title="AsthmaGuard",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CUSTOM CSS ---
st.markdown("""
    <style>
    .login-container {
        background-color: #f0f7f9;
        padding: 2rem;
        border-radius: 15px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.05);
        border: 1px solid #e0eef2;
    }
    .stButton>button {
        border-radius: 8px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 3. CLOUD DATABASE LOGIC (Supabase) ---
def save_reading(email, reading):
    data = {
        "email": email,
        "date": datetime.now().isoformat(),
        "reading": reading
    }
    supabase.table("peak_flow_history").insert(data).execute()

def save_act_score(email, score):
    data = {
        "email": email,
        "date": datetime.now().isoformat(),
        "score": score
    }
    supabase.table("act_scores").insert(data).execute()

def load_history(email):
    response = supabase.table("peak_flow_history").select("*").eq("email", email).execute()
    df = pd.DataFrame(response.data)
    if df.empty:
        return pd.DataFrame({"Date": [datetime.now()], "Peak Flow (L/min)": [500]})
    df = df.rename(columns={"date": "Date", "reading": "Peak Flow (L/min)"})
    df['Date'] = pd.to_datetime(df['Date'])
    return df

def load_act_history(email):
    response = supabase.table("act_scores").select("*").eq("email", email).execute()
    df = pd.DataFrame(response.data)
    if df.empty:
        return pd.DataFrame()
    df = df.rename(columns={"date": "Date", "score": "ACT Score"})
    df['Date'] = pd.to_datetime(df['Date'])
    return df

def verify_user(email, acc_pw):
    response = supabase.table("settings").select("*").eq("sender_email", email).execute()
    if response.data and response.data[0]['account_password'] == acc_pw:
        user = response.data[0]
        return True, user.get('app_password', ""), user.get('doctor_email', ""), user['full_name']
    return False, None, None, None

def register_user(name, email, acc_pw):
    data = {
        "full_name": name,
        "sender_email": email,
        "account_password": acc_pw
    }
    try:
        supabase.table("settings").insert(data).execute()
        return True, "Account created! Please Login."
    except:
        return False, "Email already registered."

def update_doctor_settings(email, app_pw, doc_contact):
    supabase.table("settings").update({"app_password": app_pw, "doctor_email": doc_contact}).eq("sender_email", email).execute()

def get_whatsapp_link(patient_name, doc_number, city, b_group, triggers, is_sos=False, ratio=0, current_pf=0, coords=None):
    if is_sos:
        if coords:
            loc_link = f"https://www.google.com/maps?q={coords['latitude']},{coords['longitude']}"
            loc_source = "GPS"
        else:
            g = geocoder.ip('me')
            loc_link = f"https://www.google.com/maps?q={g.latlng[0]},{g.latlng[1]}" if g.latlng else city
            loc_source = "IP"
        message = f"🚨 *SOS EMERGENCY ALERT* 🚨%0A%0A*Patient:* {patient_name}%0A*Blood Group:* {b_group}%0A*Triggers:* {', '.join(triggers)}%0A*Location:* {loc_link}%0A%0APLEASE HELP!"
    else:
        message = f"🚨 *RESPIRATORY ALERT* 🚨%0A%0A*Patient:* {patient_name}%0A*Status:* RED ZONE ({int(ratio)}%)%0A*Peak Flow:* {current_pf} L/min"
    
    clean_number = ''.join(filter(str.isdigit, str(doc_number)))
    return f"https://wa.me/{clean_number}?text={message}"

# --- 4. SESSION STATE ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "status_label" not in st.session_state:
    st.session_state.status_label = "Stable"
if "status_delta" not in st.session_state:
    st.session_state.status_delta = "Normal"
if "sos_sent" not in st.session_state:
    st.session_state.sos_sent = False

# --- 5. LOGIN & REGISTER ---
if not st.session_state.logged_in:
    with st.container():
        col_img, col_form = st.columns([1, 1], gap="large")
        with col_img:
            st.image("https://img.freepik.com/free-vector/doctor-character-background_1270-84.jpg", width="stretch")
        with col_form:
            st.markdown('<div class="login-container">', unsafe_allow_html=True)
            st.title("🛡️ AsthmaGuard ")
            t1, t2 = st.tabs(["🔐 Login", "📝 Register"])
            with t1:
                with st.form("login"):
                    e = st.text_input("Gmail Address")
                    p = st.text_input("Password", type="password")
                    if st.form_submit_button("Login", width="stretch", type="primary"):
                        ok, ap, de, fn = verify_user(e, p)
                        if ok:
                            st.session_state.logged_in = True
                            st.session_state.user_email, st.session_state.user_name = e, fn
                            st.session_state.app_password, st.session_state.doctor_email = ap, de
                            st.session_state.history_df = load_history(e)
                            st.rerun()
                        else: st.error("Invalid credentials.")
            with t2:
                with st.form("register"):
                    fn = st.text_input("Full Name")
                    em = st.text_input("Gmail Address")
                    pw = st.text_input("Password", type="password")
                    if st.form_submit_button("Create Account", width="stretch", type="primary"):
                        ok, msg = register_user(fn, em, pw)
                        if ok: st.success(msg)
                        else: st.error(msg)
            st.markdown('</div>', unsafe_allow_html=True)
else:
    # --- DASHBOARD LOGIC (Kept exactly same as your previous version) ---
    raw_loc = get_geolocation()
    user_coords = raw_loc['coords'] if raw_loc else None

    with st.sidebar:
        st.title(f"👤 {st.session_state.user_name}")
        target_city = st.text_input("📍 City:", "Karachi")
        b_group = st.selectbox("Blood Group", ["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"], index=4)
        triggers = st.multiselect("Triggers", ["Dust", "Pollen", "Smoke"], ["Dust", "Smoke"])
        with st.expander("⚙️ Settings"):
            d_phone = st.text_input("Doctor's WhatsApp #", value=st.session_state.doctor_email)
            if st.button("💾 Save"):
                update_doctor_settings(st.session_state.user_email, "", d_phone)
                st.session_state.doctor_email = d_phone
                st.success("Saved!")
        if st.button("🚪 Sign Out", width="stretch"):
            st.session_state.logged_in = False
            st.rerun()

    st.title("🖲️ AsthmaGuard Dashboard")
    m1, m2 = st.columns(2)
    m1.metric("Status", st.session_state.status_label, st.session_state.status_delta)
    m2.metric("Avg Peak Flow", f"{int(st.session_state.history_df['Peak Flow (L/min)'].mean())} L/min")

    tab1, tab2, tab3, tab4 = st.tabs(["📈 Health", "🚨 SOS", "⛑️ First Aid", "📋 ACT"])

    with tab1:
        col_calc, col_chart = st.columns([1, 1.5])
        with col_calc:
            best_pf = st.number_input("Best Peak Flow", value=500)
            today_pf = st.number_input("Today's Reading", value=450)
            if st.button("📊 Log Reading", type="primary"):
                ratio = (today_pf / best_pf) * 100
                save_reading(st.session_state.user_email, today_pf)
                st.session_state.history_df = load_history(st.session_state.user_email)
                if ratio >= 80: st.session_state.status_label, st.session_state.status_delta = "Green Zone", "Stable"
                elif 50 <= ratio < 80: st.session_state.status_label, st.session_state.status_delta = "Yellow Zone", "Caution"
                else: st.session_state.status_label, st.session_state.status_delta = "Red Zone", "EMERGENCY"
                st.rerun()
        with col_chart:
            st.line_chart(st.session_state.history_df.set_index("Date")["Peak Flow (L/min)"])

    with tab2:
        if user_coords: st.info(f"📍 GPS Locked")
        else: st.warning("📍 Locating...")
        if st.session_state.doctor_email:
            wa_link = get_whatsapp_link(st.session_state.user_name, st.session_state.doctor_email, target_city, b_group, triggers, is_sos=True, coords=user_coords)
            st.link_button("🚨 OPEN WHATSAPP SOS", wa_link, type="primary", use_container_width=True)
        else: st.warning("Save Doctor # in Sidebar Settings.")

    # (Tab 3 & 4 remain identical to your current code)
    with tab3:
        st.write("### ⛑️ Emergency Steps")
        st.error("1. Sit Upright. 2. Take 4 Puffs. 3. Wait 4 Minutes.")

    with tab4:
        act_df = load_act_history(st.session_state.user_email)
        with st.form("act"):
            s1 = st.slider("Activity limitation?", 1, 5, 5)
            if st.form_submit_button("Save ACT"):
                save_act_score(st.session_state.user_email, s1*5)
                st.rerun()

        if not act_df.empty: st.line_chart(act_df.set_index("Date")["ACT Score"])
