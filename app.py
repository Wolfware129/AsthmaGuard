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

# --- 3. DATABASE FUNCTIONS (CLOUD) ---
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
        return True, data.get('app_password', ""), data.get('doctor_email', ""), data['full_name']
    return False, None, None, None

def register_user(name, email, acc_pw):
    try:
        supabase.table("settings").insert({"full_name": name, "sender_email": email, "account_password": acc_pw}).execute()
        return True, "Account created! Please Login."
    except: return False, "Email already registered."

def update_doctor_settings(email, app_pw, doc_contact):
    supabase.table("settings").update({"app_password": app_pw, "doctor_email": doc_contact}).eq("sender_email", email).execute()

def get_whatsapp_link(patient_name, doc_number, city, b_group, triggers, is_sos=False, ratio=0, current_pf=0, coords=None):
    if is_sos:
        loc_link = f"http://maps.google.com/?q={coords['latitude']},{coords['longitude']}" if coords else city
        message = f"🚨 *SOS EMERGENCY ALERT* 🚨%0A%0A*Patient:* {patient_name}%0A*Blood Group:* {b_group}%0A*Triggers:* {', '.join(triggers)}%0A*Location:* {loc_link}%0A%0APLEASE SEND HELP!"
    else:
        message = f"🚨 *RESPIRATORY ALERT* 🚨%0A%0A*Patient:* {patient_name}%0A*Status:* RED ZONE ({int(ratio)}%)%0A*Peak Flow:* {current_pf} L/min"
    clean_number = ''.join(filter(str.isdigit, str(doc_number)))
    return f"https://wa.me/{clean_number}?text={message}"

# --- SESSION STATE ---
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "status_label" not in st.session_state: st.session_state.status_label = "Stable"
if "status_delta" not in st.session_state: st.session_state.status_delta = "Normal"

# --- LOGIN & REGISTER ---
if not st.session_state.logged_in:
    col_img, col_form = st.columns([1, 1], gap="large")
    with col_img:
        st.image("https://img.freepik.com/free-vector/doctor-character-background_1270-84.jpg", use_container_width=True)
    with col_form:
        st.markdown('<div class="login-container">', unsafe_allow_html=True)
        st.title("🛡️ AsthmaGuard ")
        t1, t2 = st.tabs(["🔐 Secure Login", "📝 Create Account"])
        with t1:
            with st.form("login"):
                e = st.text_input("Your Gmail Address")
                p = st.text_input("Password", type="password")
                if st.form_submit_button("Login", use_container_width=True, type="primary"):
                    ok, ap, de, fn = verify_user(e, p)
                    if ok:
                        st.session_state.logged_in = True
                        st.session_state.user_email, st.session_state.user_name = e, fn
                        st.session_state.doctor_email = de if de else ""
                        st.session_state.history_df = load_history(e)
                        st.rerun()
                    else: st.error("Invalid credentials.")
        with t2:
            with st.form("register"):
                fn, em, pw = st.text_input("Full Name"), st.text_input("Your Gmail Address"), st.text_input("Password", type="password")
                if st.form_submit_button("Register Account", use_container_width=True, type="primary"):
                    ok, msg = register_user(fn, em, pw); st.success(msg) if ok else st.error(msg)
        st.markdown('</div>', unsafe_allow_html=True)
else:
    raw_loc = get_geolocation()
    user_coords = raw_loc['coords'] if raw_loc else None

    with st.sidebar:
        st.title(f"👤 {st.session_state.user_name}")
        st.subheader("📄 Medical Report Profile")
        target_city = st.text_input("📍 Current City:", "Karachi")
        b_group = st.selectbox("Blood Group", ["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"], index=4)
        triggers = st.multiselect("Known Triggers", ["Dust", "Pollen", "Smoke"], ["Dust", "Smoke"])
        with st.expander("⚙️ System Settings"):
            d_phone = st.text_input("Doctor's WhatsApp #", value=st.session_state.doctor_email)
            if st.button("💾 Save Settings", use_container_width=True):
                update_doctor_settings(st.session_state.user_email, "", d_phone)
                st.session_state.doctor_email = d_phone; st.success("Saved!")
        if st.button("🚪 Sign Out", use_container_width=True): st.session_state.logged_in = False; st.rerun()

    st.title("🖲️ AsthmaGuard Dashboard")
    m1, m2 = st.columns(2)
    m1.metric("Current Status", st.session_state.status_label, st.session_state.status_delta)
    m2.metric("Avg Peak Flow", f"{int(st.session_state.history_df['Peak Flow (L/min)'].mean())} L/min")

    tab1, tab2, tab3, tab4 = st.tabs(["📈 Health Tracker", "🚨 EMERGENCY SOS (WhatsApp)", "⛑️ First Aid Guide", "📋 Control Test (ACT)"])

    # TAB 1: HEALTH TRACKER
    with tab1:
        st.subheader("📋 Expiratory Flow Rate (EFR)")
        col_calc, col_chart = st.columns([1, 1.5], gap="large")
        with col_calc:
            with st.container(border=True):
                best_pf = st.number_input("Your Best Peak Flow (L/min)", 100, 800, 500)
                today_pf = st.number_input("Today's Peak Flow (L/min)", 50, 800, 450)
                if st.button("📊 Calculate & Log Reading", use_container_width=True, type="primary"):
                    ratio = (today_pf / best_pf) * 100
                    save_reading(st.session_state.user_email, today_pf)
                    st.session_state.history_df = load_history(st.session_state.user_email)
                    if ratio >= 80: st.session_state.status_label, st.session_state.status_delta = "Green Zone", "Stable"
                    elif 50 <= ratio < 80: st.session_state.status_label, st.session_state.status_delta = "Yellow Zone", "Caution"
                    else: st.session_state.status_label, st.session_state.status_delta = "Red Zone", "EMERGENCY"
                    st.rerun()
            st.write(f"Condition: {st.session_state.status_label}")
            st.button("📥 Download Full Medical PDF Report", use_container_width=True)
        with col_chart:
            st.subheader("📅 7-Day Respiratory Trend")
            st.line_chart(st.session_state.history_df.set_index("Date")["Peak Flow (L/min)"])

    # TAB 2: EMERGENCY SOS (Matches your Screenshot)
    with tab2:
        st.error("🔴 **EMERGENCY PROTOCOL ACTIVATED**")
        if user_coords: st.info(f"📍 GPS Locked: Lat {user_coords['latitude']:.4f}, Lon {user_coords['longitude']:.4f}")
        col_btn, col_map = st.columns([1, 1])
        with col_btn:
            if st.session_state.doctor_email:
                wa_link = get_whatsapp_link(st.session_state.user_name, st.session_state.doctor_email, target_city, b_group, triggers, True, coords=user_coords)
                st.link_button("🚨 OPEN WHATSAPP SOS", wa_link, type="primary", use_container_width=True)
                st.caption("Clicking this will open WhatsApp with your location and emergency message pre-typed.")
            else: st.warning("⚠️ Save Doctor's # in settings first.")
        with col_map:
            st.markdown("**🏥 Nearby Hospitals**")
            st.map(pd.DataFrame({'lat': [user_coords['latitude'] if user_coords else 24.86], 'lon': [user_coords['longitude'] if user_coords else 67.00]}))

    # TAB 3: FIRST AID GUIDE (Matches your Screenshot)
    with tab3:
        st.subheader("⛑️ Scenario-Based First Aid")
        with st.expander("🟡 I feel an attack starting (Yellow Zone)"):
            st.write("* **Stop activity:** Stop all physical movement immediately.\n* **Remove triggers:** Move away from smoke, dust, or cold air.\n* **Inhaler:** Take **2 puffs** of your rescue inhaler.\n* **Wait:** Stay still for 15 minutes.")
        with st.expander("🔴 Acute Asthma Attack (Red Zone)"):
            st.error("Follow the 4 x 4 Rule:")
            st.write("1. **Sit Upright.**\n2. **Take 4 Puffs.**\n3. **Wait 4 Minutes.**\n4. **Call Help.**")
        with st.expander("⚪ No Inhaler is Available"):
            st.write("* Stay Upright.\n* Pursed-Lip Breathing.\n* Stay Calm.")

    # TAB 4: ACT TEST (Matches your Screenshot)
    with tab4:
        st.subheader("📋 Asthma Control Test™ (ACT)")
        col_form, col_act_chart = st.columns([1, 1.5], gap="large")
        act_df = load_act_history(st.session_state.user_email)
        with col_form:
            st.info("Answer these questions based on the last 4 weeks. (1 = Worst, 5 = Best)")
            with st.form("act_form"):
                q1 = st.select_slider("Activity limitation at work/home/school?", options=[1, 2, 3, 4, 5])
                q2 = st.select_slider("Frequency of shortness of breath?", options=[1, 2, 3, 4, 5])
                q3 = st.select_slider("Waking up at night with symptoms?", options=[1, 2, 3, 4, 5])
                q4 = st.select_slider("Frequency of rescue inhaler use?", options=[1, 2, 3, 4, 5])
                q5 = st.select_slider("How would you rate your control?", options=[1, 2, 3, 4, 5])
                if st.form_submit_button("Calculate ACT Score", use_container_width=True):
                    save_act_score(st.session_state.user_email, q1+q2+q3+q4+q5); st.rerun()
            if not act_df.empty: st.write(f"Latest Score: {act_df.iloc[-1]['ACT Score']}/25")
        with col_act_chart:
            st.subheader("📊 ACT Score History")
            if not act_df.empty: st.line_chart(act_df.set_index("Date")["ACT Score"])
            st.button("📥 Download ACT History (Last 30 Days)", use_container_width=True)
