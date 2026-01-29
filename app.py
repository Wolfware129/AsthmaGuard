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
    if df.empty: return pd.DataFrame({"Date": [datetime.now()], "Peak Flow (L/min)": [500]})
    df = df.rename(columns={"date": "Date", "reading": "Peak Flow (L/min)"})
    df['Date'] = pd.to_datetime(df['Date'])
    return df

def load_act_history(email):
    res = supabase.table("act_scores").select("*").eq("email", email).execute()
    df = pd.DataFrame(res.data)
    if df.empty: return pd.DataFrame()
    df = df.rename(columns={"date": "Date", "score": "ACT Score"})
    df['Date'] = pd.to_datetime(df['Date'])
    return df

def verify_user(email, acc_pw):
    res = supabase.table("settings").select("*").eq("sender_email", email).execute()
    if res.data and res.data[0]['account_password'] == acc_pw:
        data = res.data[0]
        return True, data.get('doctor_email', ""), data['full_name']
    return False, None, None

def register_user(name, email, acc_pw):
    try:
        supabase.table("settings").insert({"full_name": name, "sender_email": email, "account_password": acc_pw}).execute()
        return True, "Account created!"
    except: return False, "Error."

def update_doctor_settings(email, doc_contact):
    supabase.table("settings").update({"doctor_email": doc_contact}).eq("sender_email", email).execute()

# --- PDF GENERATION LOGIC ---
def generate_report_html(name, city, b_group, triggers, history_df, act_df=None):
    history_html = history_df.to_html(index=False)
    act_html = act_df.to_html(index=False) if act_df is not None and not act_df.empty else "<p>No ACT data available.</p>"
    
    report_content = f"""
    <html><body style="font-family: sans-serif;">
    <h1 style="color: #2E86C1;">AsthmaGuard Medical Report</h1>
    <p><b>Patient:</b> {name} | <b>Location:</b> {city}</p>
    <p><b>Blood Group:</b> {b_group} | <b>Triggers:</b> {", ".join(triggers)}</p>
    <hr>
    <h3>Peak Flow History</h3>{history_html}
    <hr>
    <h3>ACT Score History</h3>{act_html}
    </body></html>
    """
    return report_content

def get_whatsapp_link(patient_name, doc_number, city, b_group, triggers, is_sos=False, ratio=0, current_pf=0, coords=None):
    if is_sos:
        loc_link = f"http://maps.google.com/?q={coords['latitude']},{coords['longitude']}" if coords else city
        message = f"🚨 *SOS EMERGENCY ALERT* 🚨%0APatient: {patient_name}%0ALocation: {loc_link}"
    else:
        message = f"🚨 *ALERT* 🚨%0APatient: {patient_name}%0APeak Flow: {current_pf}"
    clean_number = ''.join(filter(str.isdigit, str(doc_number)))
    return f"https://wa.me/{clean_number}?text={message}"

# --- APP LOGIC ---
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "status_label" not in st.session_state: st.session_state.status_label = "Stable"
if "status_delta" not in st.session_state: st.session_state.status_delta = "Normal"

if not st.session_state.logged_in:
    col_img, col_form = st.columns([1, 1])
    with col_img: st.image("https://img.freepik.com/free-vector/doctor-character-background_1270-84.jpg", use_container_width=True)
    with col_form:
        st.title("🛡️ AsthmaGuard")
        t1, t2 = st.tabs(["🔐 Login", "📝 Register"])
        with t1:
            with st.form("login"):
                e, p = st.text_input("Email"), st.text_input("Password", type="password")
                if st.form_submit_button("Login", use_container_width=True):
                    ok, de, fn = verify_user(e, p)
                    if ok:
                        st.session_state.logged_in, st.session_state.user_email, st.session_state.user_name, st.session_state.doctor_email = True, e, fn, de
                        st.session_state.history_df = load_history(e); st.rerun()
else:
    raw_loc = get_geolocation()
    user_coords = raw_loc['coords'] if raw_loc else None

    with st.sidebar:
        st.title(f"👤 {st.session_state.user_name}")
        target_city = st.text_input("📍 City:", "Karachi")
        b_group = st.selectbox("Blood Group", ["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"], index=4)
        triggers = st.multiselect("Triggers", ["Dust", "Pollen", "Smoke"], ["Dust", "Smoke"])
        d_phone = st.text_input("Doctor's WhatsApp #", value=st.session_state.doctor_email)
        if st.button("💾 Save Settings"): update_doctor_settings(st.session_state.user_email, d_phone); st.success("Saved!")
        if st.button("🚪 Sign Out"): st.session_state.logged_in = False; st.rerun()

    st.title("🖲️ AsthmaGuard Dashboard")
    m1, m2 = st.columns(2)
    m1.metric("Current Status", st.session_state.status_label, st.session_state.status_delta)
    m2.metric("Avg Peak Flow", f"{int(st.session_state.history_df['Peak Flow (L/min)'].mean())} L/min")

    tab1, tab2, tab3, tab4 = st.tabs(["📈 Health Tracker", "🚨 EMERGENCY SOS (WhatsApp)", "⛑️ First Aid Guide", "📋 Control Test (ACT)"])

    # SHARED PDF DATA
    full_report_html = generate_report_html(st.session_state.user_name, target_city, b_group, triggers, st.session_state.history_df, load_act_history(st.session_state.user_email))

    with tab1:
        st.subheader("📋 Expiratory Flow Rate (EFR)")
        col_calc, col_chart = st.columns([1, 1.5])
        with col_calc:
            with st.container(border=True):
                best_pf = st.number_input("Your Best Peak Flow", 100, 800, 500)
                today_pf = st.number_input("Today's Peak Flow", 50, 800, 450)
                if st.button("📊 Calculate & Log Reading", use_container_width=True):
                    ratio = (today_pf / best_pf) * 100
                    save_reading(st.session_state.user_email, today_pf)
                    st.session_state.history_df = load_history(st.session_state.user_email)
                    st.session_state.status_label = "Green Zone" if ratio >= 80 else "Yellow Zone" if ratio >= 50 else "Red Zone"
                    st.rerun()
            st.write(f"Condition: {st.session_state.status_label}")
            # FUNCTIONAL DOWNLOAD BUTTON 1
            st.download_button("📥 Download Full Medical PDF Report", full_report_html, file_name="AsthmaGuard_Report.html", mime="text/html", use_container_width=True)
        with col_chart: st.line_chart(st.session_state.history_df.set_index("Date")["Peak Flow (L/min)"])

    with tab2:
        st.error("🔴 **EMERGENCY PROTOCOL ACTIVATED**")
        if st.session_state.doctor_email:
            st.link_button("🚨 OPEN WHATSAPP SOS", get_whatsapp_link(st.session_state.user_name, st.session_state.doctor_email, target_city, b_group, triggers, True, coords=user_coords), type="primary", use_container_width=True)
        st.map(pd.DataFrame({'lat': [user_coords['latitude'] if user_coords else 24.86], 'lon': [user_coords['longitude'] if user_coords else 67.00]}))

    with tab3:
        st.subheader("⛑️ Scenario-Based First Aid")
        with st.expander("🟡 I feel an attack starting (Yellow Zone)"): st.write("Stop activity, take 2 puffs, wait 15 mins.")
        with st.expander("🔴 Acute Asthma Attack (Red Zone)"): st.write("1. Sit Upright. 2. Take 4 Puffs. 3. Wait 4 Minutes. 4. Call Help.")
        with st.expander("⚪ No Inhaler is Available"): st.write("Stay upright, pursed-lip breathing, stay calm.")

    with tab4:
        st.subheader("📋 Asthma Control Test™ (ACT)")
        col_f, col_c = st.columns([1, 1.5])
        with col_f:
            st.info("Answer questions (1 = Worst, 5 = Best)")
            with st.form("act_form"):
                qs = [st.select_slider(f"Question {i+1}", options=[1, 2, 3, 4, 5]) for i in range(5)]
                if st.form_submit_button("Calculate ACT Score", use_container_width=True):
                    save_act_score(st.session_state.user_email, sum(qs)); st.rerun()
        with col_c:
            act_history = load_act_history(st.session_state.user_email)
            if not act_history.empty: st.line_chart(act_history.set_index("Date")["ACT Score"])
            # FUNCTIONAL DOWNLOAD BUTTON 2
            st.download_button("📥 Download ACT History (Last 30 Days)", full_report_html, file_name="ACT_Report.html", mime="text/html", use_container_width=True)
