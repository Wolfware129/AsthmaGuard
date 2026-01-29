import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from streamlit_js_eval import get_geolocation
import geocoder 
from supabase import create_client, Client

# --- 1. SUPABASE CONFIGURATION (Cloud Database) ---
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

# --- CUSTOM CSS FOR STYLING ---
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

# --- 3. DATABASE FUNCTIONS (SUPABASE CLOUD) ---
def save_reading(email, reading):
    supabase.table("peak_flow_history").insert({"email": email, "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "reading": reading}).execute()

def save_act_score(email, score):
    supabase.table("act_scores").insert({"email": email, "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "score": score}).execute()

def load_history(email):
    res = supabase.table("peak_flow_history").select("*").eq("email", email).execute()
    df = pd.DataFrame(res.data)
    if df.empty:
        return pd.DataFrame({"Date": [datetime.now()], "Peak Flow (L/min)": [500]})
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
        if coords:
            loc_link = f"http://maps.google.com/?q={coords['latitude']},{coords['longitude']}"
            loc_source = "GPS"
        else:
            g = geocoder.ip('me')
            if g.latlng:
                loc_link = f"http://maps.google.com/?q={g.latlng[0]},{g.latlng[1]}"
                loc_source = "IP"
            else:
                loc_link = f"{city}"
                loc_source = "Manual"
        message = f"🚨 *SOS EMERGENCY ALERT* 🚨%0A%0A*Patient:* {patient_name}%0A*Blood Group:* {b_group}%0A*Triggers:* {', '.join(triggers)}%0A*Location ({loc_source}):* {loc_link}%0A%0APLEASE SEND HELP IMMEDIATELY!"
    else:
        message = f"🚨 *RESPIRATORY ALERT* 🚨%0A%0A*Patient:* {patient_name}%0A*Status:* RED ZONE ({int(ratio)}%)%0A*Peak Flow:* {current_pf} L/min%0A%0APlease advise."
    clean_number = ''.join(filter(str.isdigit, str(doc_number)))
    return f"https://wa.me/{clean_number}?text={message}"

# --- SESSION STATE ---
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "status_label" not in st.session_state: st.session_state.status_label = "Stable"
if "status_delta" not in st.session_state: st.session_state.status_delta = "Normal"
if "sos_sent" not in st.session_state: st.session_state.sos_sent = False

# --- 5. LOGIN & REGISTER ---
if not st.session_state.logged_in:
    with st.container():
        col_img, col_form = st.columns([1, 1], gap="large")
        with col_img:
            st.image("https://img.freepik.com/free-vector/doctor-character-background_1270-84.jpg", use_container_width=True)
        with col_form:
            st.markdown('<div class="login-container">', unsafe_allow_html=True)
            st.title("🛡️ AsthmaGuard ")
            st.write("### Secure Access")
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
                            st.session_state.app_password, st.session_state.doctor_email = ap if ap else "", de if de else ""
                            st.session_state.history_df = load_history(e)
                            st.rerun()
                        else: st.error("Invalid credentials.")
            with t2:
                with st.form("register"):
                    fn = st.text_input("Full Name")
                    em = st.text_input("Your Gmail Address")
                    pw = st.text_input("Password", type="password")
                    if st.form_submit_button("Register Account", use_container_width=True, type="primary"):
                        ok, msg = register_user(fn, em, pw)
                        if ok: st.success(msg)
                        else: st.error(msg)
            st.markdown("---")
            st.markdown("""
                **Your Intelligent Respiratory Health Partner**
                * 📈 **Smart Tracking:** Monitor Peak Flow trends daily.
                * 🚨 **SOS Dispatch:** Instantly alert your doctor.
                * 📋 **ACT Tests:** Automated Scoring.
                * ⛑️ **First Aid:** Quick-access protocols.
            """)
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
        st.markdown("---")
        with st.expander("⚙️ System Settings", expanded=not st.session_state.doctor_email):
            st.caption("Enter Doctor's WhatsApp Number (with Country Code, e.g., 923001234567)")
            d_phone = st.text_input("Doctor's WhatsApp #", value=st.session_state.doctor_email)
            u_pw = st.text_input("App Password (Optional)", type="password", value=st.session_state.app_password) 
            if st.button("💾 Save Settings", use_container_width=True):
                update_doctor_settings(st.session_state.user_email, u_pw, d_phone)
                st.session_state.app_password, st.session_state.doctor_email = u_pw, d_phone
                st.success("Settings Saved!")
        if st.button("🚪 Sign Out", use_container_width=True):
            st.session_state.logged_in = False
            st.rerun()

    st.title("🖲️ AsthmaGuard Dashboard")
    m1, m2 = st.columns(2)
    m1.metric("Current Status", st.session_state.status_label, st.session_state.status_delta)
    m2.metric("Avg Peak Flow", f"{int(st.session_state.history_df['Peak Flow (L/min)'].mean())} L/min")

    tab1, tab2, tab3, tab4 = st.tabs(["📈 Health Tracker", "🚨 EMERGENCY SOS (WhatsApp)", "⛑️ First Aid Guide", "📋 Control Test (ACT)"])

    def create_pdf_download():
        history_rows = "".join([f"<tr><td>{row['Date'].strftime('%Y-%m-%d')}</td><td>{row['Peak Flow (L/min)']}</td></tr>" for _, row in st.session_state.history_df.iterrows()])
        return f"""<html><body style="font-family: Arial; padding: 20px;"><h1 style="color: #2E86C1;">AsthmaGuard AI - Medical Report</h1><hr><h3>Patient Profile</h3><p><b>Name:</b> {st.session_state.user_name}</p><p><b>Blood Group:</b> {b_group}</p><p><b>Location:</b> {target_city}</p><p><b>Triggers:</b> {', '.join(triggers)}</p><hr><h3>Respiratory History (Peak Flow)</h3><table border="1" style="width: 100%; border-collapse: collapse;">{history_rows}</table></body></html>"""

    with tab1:
        col_calc, col_chart = st.columns([1, 1.5], gap="large")
        with col_calc:
            st.subheader("📋 Expiratory Flow Rate (EFR)")
            with st.container(border=True):
                best_pf = st.number_input("Your Best Peak Flow (L/min)", 100, 800, 500)
                today_pf = st.number_input("Today's Peak Flow (L/min)", 50, 800, 450)
                if st.button("📊 Calculate & Log Reading", use_container_width=True, type="primary"):
                    ratio = (today_pf / best_pf) * 100
                    save_reading(st.session_state.user_email, today_pf)
                    st.session_state.history_df = load_history(st.session_state.user_email)
                    if ratio >= 80: st.session_state.status_label, st.session_state.status_delta = "Green Zone", "Stable"
                    elif 50 <= ratio < 80: st.session_state.status_label, st.session_state.status_delta = "Yellow Zone", "Caution"
                    else:
                        st.session_state.status_label, st.session_state.status_delta = "Red Zone", "EMERGENCY"
                        st.error("⚠️ CRITICAL ALERT: Please contact doctor.")
                    st.rerun()
            st.download_button("📥 Download Full Medical PDF Report", create_pdf_download(), f"AsthmaGuard_Report.html", "text/html", use_container_width=True)
        with col_chart:
            st.subheader("📅 7-Day Respiratory Trend")
            st.line_chart(st.session_state.history_df.set_index("Date")["Peak Flow (L/min)"])

    with tab2:
        st.error("🔴 **EMERGENCY PROTOCOL ACTIVATED**")
        if user_coords: st.info(f"📍 GPS Locked: Lat {user_coords['latitude']:.4f}, Lon {user_coords['longitude']:.4f}")
        col_btn, col_map = st.columns([1, 1])
        with col_btn:
            if st.session_state.doctor_email:
                wa_link = get_whatsapp_link(st.session_state.user_name, st.session_state.doctor_email, target_city, b_group, triggers, True, coords=user_coords)
                st.link_button("🚨 OPEN WHATSAPP SOS", wa_link, type="primary", use_container_width=True)
            else: st.warning("⚠️ Save Doctor's WhatsApp Number in settings.")

    with tab3:
        st.subheader("⛑️ Scenario-Based First Aid")
        with st.expander("🟡 I feel an attack starting (Yellow Zone)"):
            st.write("- **Stop activity:** Stop all physical movement immediately.\n- **Remove triggers:** Move away from smoke, dust, or cold air.\n- **Inhaler:** Take **2 puffs** of your rescue inhaler.\n- **Wait:** Stay still for 15 minutes.")
        with st.expander("🔴 Acute Asthma Attack (Red Zone)"):
            st.error("Follow the 4 x 4 Rule:")
            st.write("1. **Sit Upright.**\n2. **Take 4 Puffs.**\n3. **Wait 4 Minutes.**\n4. **Call Help.**")

    with tab4:
        st.subheader("📋 Asthma Control Test™ (ACT)")
        col_form, col_act_chart = st.columns([1, 1.5], gap="large")
        act_df = load_act_history(st.session_state.user_email)
        with col_form:
            with st.form("act_form"):
                q1 = st.select_slider("1. Activity limitation at work/home/school?", [1, 2, 3, 4, 5])
                q2 = st.select_slider("2. Frequency of shortness of breath?", [1, 2, 3, 4, 5])
                q3 = st.select_slider("3. Waking up at night with symptoms?", [1, 2, 3, 4, 5])
                q4 = st.select_slider("4. Frequency of rescue inhaler use?", [1, 2, 3, 4, 5])
                q5 = st.select_slider("5. How would you rate your control?", [1, 2, 3, 4, 5])
                if st.form_submit_button("Calculate ACT Score", use_container_width=True):
                    save_act_score(st.session_state.user_email, q1+q2+q3+q4+q5)
                    st.rerun()
        with col_act_chart:
            if not act_df.empty: st.line_chart(act_df.set_index("Date")["ACT Score"])
