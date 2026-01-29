import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from streamlit_js_eval import get_geolocation
import geocoder 
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

def update_doctor_settings(email, doc_contact):
    supabase.table("settings").update({"doctor_email": doc_contact}).eq("sender_email", email).execute()

# --- 4. SOS MESSAGE & WHATSAPP LOGIC (RESTORED) ---
def get_whatsapp_link(patient_name, doc_number, city, b_group, triggers, is_sos=False, ratio=0, current_pf=0, coords=None):
    if is_sos:
        if coords:
            loc_link = f"http://maps.google.com/?q={coords['latitude']},{coords['longitude']}"
            loc_source = "GPS"
        else:
            g = geocoder.ip('me')
            loc_link = f"http://maps.google.com/?q={g.latlng[0]},{g.latlng[1]}" if g.latlng else city
            loc_source = "IP/Manual"
        message = f"🚨 *SOS EMERGENCY ALERT* 🚨%0A%0A*Patient:* {patient_name}%0A*Blood Group:* {b_group}%0A*Triggers:* {', '.join(triggers)}%0A*Location:* {loc_link}%0A%0APLEASE SEND HELP!"
    else:
        message = f"🚨 *RESPIRATORY ALERT* 🚨%0A%0A*Patient:* {patient_name}%0A*Peak Flow:* {current_pf} L/min"
    
    clean_number = ''.join(filter(str.isdigit, str(doc_number)))
    return f"https://wa.me/{clean_number}?text={message}"

# --- PDF GENERATION ---
def generate_report_html(name, city, b_group, triggers, history_df, act_df):
    history_html = history_df.tail(15).to_html(index=False)
    act_html = act_df.tail(10).to_html(index=False) if not act_df.empty else "<p>No ACT data.</p>"
    return f"<html><body><h1>AsthmaGuard Report</h1><p><b>Patient:</b> {name}</p><hr>{history_html}<hr>{act_html}</body></html>"

# --- AUTH LOGIC ---
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "status_label" not in st.session_state: st.session_state.status_label = "Stable"
if "status_delta" not in st.session_state: st.session_state.status_delta = "Normal"

if not st.session_state.logged_in:
    col_img, col_form = st.columns([1, 1])
    with col_img: st.image("https://img.freepik.com/free-vector/doctor-character-background_1270-84.jpg", width=500)
    with col_form:
        st.title("🛡️ AsthmaGuard")
        with st.form("login"):
            e, p = st.text_input("Email"), st.text_input("Password", type="password")
            if st.form_submit_button("Login", use_container_width=True):
                res = supabase.table("settings").select("*").eq("sender_email", e).execute()
                if res.data and res.data[0]['account_password'] == p:
                    st.session_state.logged_in, st.session_state.user_email, st.session_state.user_name = True, e, res.data[0]['full_name']
                    st.session_state.doctor_email = res.data[0].get('doctor_email', "")
                    st.rerun()
else:
    history_df = load_history(st.session_state.user_email)
    act_df = load_act_history(st.session_state.user_email)
    raw_loc = get_geolocation()
    user_coords = raw_loc['coords'] if raw_loc else None

    with st.sidebar:
        st.title(f"👤 {st.session_state.user_name}")
        target_city = st.text_input("📍 Current City:", "Karachi")
        b_group = st.selectbox("Blood Group", ["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"], index=4)
        triggers = st.multiselect("Known Triggers", ["Dust", "Pollen", "Smoke"], ["Dust", "Smoke"])
        # RESTORED SYSTEM SETTINGS
        with st.expander("⚙️ System Settings"):
            d_phone = st.text_input("Doctor's WhatsApp #", value=st.session_state.doctor_email)
            if st.button("💾 Save Settings", use_container_width=True):
                update_doctor_settings(st.session_state.user_email, d_phone)
                st.session_state.doctor_email = d_phone
                st.success("Saved!")
        if st.button("🚪 Sign Out", use_container_width=True): st.session_state.logged_in = False; st.rerun()

    st.title("🖲️ AsthmaGuard Dashboard")
    m1, m2 = st.columns(2)
    m1.metric("Current Status", st.session_state.status_label, st.session_state.status_delta)
    m2.metric("Avg Peak Flow", f"{int(history_df['Peak Flow (L/min)'].mean()) if not history_df.empty else 0} L/min")

    tab1, tab2, tab3, tab4 = st.tabs(["📈 Health Tracker", "🚨 EMERGENCY SOS (WhatsApp)", "⛑️ First Aid Guide", "📋 Control Test (ACT)"])

    report_content = generate_report_html(st.session_state.user_name, target_city, b_group, triggers, history_df, act_df)

    with tab1:
        st.subheader("📋 Expiratory Flow Rate (EFR)")
        c1, c2 = st.columns([1, 1.5])
        with c1:
            best = st.number_input("Your Best Peak Flow (L/min)", 100, 800, 500)
            now = st.number_input("Today's Peak Flow (L/min)", 50, 800, 450)
            if st.button("📊 Calculate & Log Reading", use_container_width=True):
                save_reading(st.session_state.user_email, now)
                st.rerun()
            st.download_button("📥 Download Full Medical PDF Report", report_content, file_name="Report.html", mime="text/html", use_container_width=True)
        with c2: st.line_chart(history_df.tail(7).set_index("Date")["Peak Flow (L/min)"])

    with tab2:
        st.error("🔴 **EMERGENCY PROTOCOL ACTIVATED**")
        # RESTORED ADVANCED SOS LINK
        if st.session_state.doctor_email:
            wa_link = get_whatsapp_link(st.session_state.user_name, st.session_state.doctor_email, target_city, b_group, triggers, True, coords=user_coords)
            st.link_button("🚨 OPEN WHATSAPP SOS", wa_link, type="primary", use_container_width=True)
        else: st.warning("Save Doctor's number in Sidebar Settings!")
        st.map(pd.DataFrame({'lat': [user_coords['latitude'] if user_coords else 24.86], 'lon': [user_coords['longitude'] if user_coords else 67.00]}))

    with tab3:
        st.subheader("⛑️ Scenario-Based First Aid")
        with st.expander("🟡 I feel an attack starting"): st.write("Stop activity, take 2 puffs, wait 15m.")
        with st.expander("🔴 Acute Asthma Attack"): st.error("4x4 Rule: Sit up, 4 puffs, wait 4 mins, call help.")

    with tab4:
        st.subheader("📋 Asthma Control Test™ (ACT)")
        with st.form("act"):
            score = sum([st.slider(f"Q{i+1}", 1, 5, 3) for i in range(5)])
            if st.form_submit_button("Calculate ACT Score"):
                save_act_score(st.session_state.user_email, score); st.rerun()
        st.download_button("📥 Download ACT History", report_content, file_name="ACT.html", mime="text/html", use_container_width=True)
