import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
from streamlit_js_eval import get_geolocation
import geocoder 
from supabase import create_client, Client

# --- 1. SECURE CLOUD CONFIGURATION ---
# These pull from your Streamlit "Secrets" vault
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(URL, KEY)

# --- 2. APP SETTINGS ---
st.set_page_config(
    page_title="AsthmaGuard",
    page_icon="🛡️",
    layout="wide"
)

# --- 3. UPDATED WHATSAPP & SOS LOGIC ---
def get_whatsapp_link(patient_name, doc_number, city, b_group, triggers, is_sos=False, ratio=0, current_pf=0, coords=None):
    # Standardize the phone number for WhatsApp API
    clean_number = ''.join(filter(str.isdigit, str(doc_number)))
    
    if is_sos:
        if coords:
            loc_link = f"https://www.google.com/maps?q={coords['latitude']},{coords['longitude']}"
        else:
            g = geocoder.ip('me')
            loc_link = f"https://www.google.com/maps?q={g.latlng[0]},{g.latlng[1]}" if g.latlng else city
        
        message = (f"🚨 *SOS EMERGENCY ALERT* 🚨%0A%0A"
                   f"*Patient:* {patient_name}%0A"
                   f"*Blood Group:* {b_group}%0A"
                   f"*Triggers:* {', '.join(triggers)}%0A"
                   f"*Location:* {loc_link}%0A%0A"
                   f"PLEASE HELP!")
    else:
        message = (f"🚨 *RESPIRATORY ALERT* 🚨%0A%0A"
                   f"*Patient:* {patient_name}%0A"
                   f"*Status:* RED ZONE ({int(ratio)}%)%0A"
                   f"*Peak Flow:* {current_pf} L/min")
    
    return f"https://wa.me/{clean_number}?text={message}"

# --- 4. DATABASE FUNCTIONS ---
def save_reading(email, reading):
    supabase.table("peak_flow_history").insert({"email": email, "date": datetime.now().isoformat(), "reading": reading}).execute()

def save_act_score(email, score):
    supabase.table("act_scores").insert({"email": email, "date": datetime.now().isoformat(), "score": score}).execute()

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
        user = res.data[0]
        return True, user.get('doctor_email', ""), user['full_name']
    return False, None, None

def register_user(name, email, acc_pw):
    try:
        supabase.table("settings").insert({"full_name": name, "sender_email": email, "account_password": acc_pw}).execute()
        return True, "Account created! Please Login."
    except: return False, "Email already registered."

# --- 5. SESSION STATE ---
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "status_label" not in st.session_state: st.session_state.status_label = "Stable"
if "status_delta" not in st.session_state: st.session_state.status_delta = "Normal"

# --- 6. UI: LOGIN/LOGOUT ---
if not st.session_state.logged_in:
    t1, t2 = st.tabs(["🔐 Login", "📝 Register"])
    with t1:
        with st.form("login"):
            e = st.text_input("Email")
            p = st.text_input("Password", type="password")
            if st.form_submit_button("Login"):
                ok, de, fn = verify_user(e, p)
                if ok:
                    st.session_state.logged_in, st.session_state.user_email = True, e
                    st.session_state.user_name, st.session_state.doctor_email = fn, de
                    st.session_state.history_df = load_history(e)
                    st.rerun()
                else: st.error("Wrong credentials.")
    with t2:
        with st.form("register"):
            fn = st.text_input("Full Name")
            em = st.text_input("Email")
            pw = st.text_input("Password", type="password")
            if st.form_submit_button("Create Account"):
                ok, msg = register_user(fn, em, pw)
                if ok: st.success(msg)
                else: st.error(msg)
else:
    # --- 7. MAIN DASHBOARD ---
    raw_loc = get_geolocation()
    user_coords = raw_loc['coords'] if raw_loc else None

    with st.sidebar:
        st.title(f"👤 {st.session_state.user_name}")
        target_city = st.text_input("📍 City:", "Karachi")
        b_group = st.selectbox("Blood Group", ["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"], index=4)
        triggers = st.multiselect("Triggers", ["Dust", "Pollen", "Smoke"], ["Dust", "Smoke"])
        doc_p = st.text_input("Doctor's WhatsApp (e.g. 923001234567)", value=st.session_state.doctor_email)
        if st.button("💾 Save Doctor Info"):
            supabase.table("settings").update({"doctor_email": doc_p}).eq("sender_email", st.session_state.user_email).execute()
            st.session_state.doctor_email = doc_p
            st.success("Saved!")
        if st.button("🚪 Sign Out"):
            st.session_state.logged_in = False
            st.rerun()

    st.title("🛡️ AsthmaGuard Dashboard")
    m1, m2 = st.columns(2)
    m1.metric("Status", st.session_state.status_label, st.session_state.status_delta)
    m2.metric("Avg Peak Flow", f"{int(st.session_state.history_df['Peak Flow (L/min)'].mean())} L/min")

    tab1, tab2, tab3, tab4 = st.tabs(["📈 Health", "🚨 SOS", "⛑️ First Aid", "📋 ACT"])

    with tab1:
        c1, c2 = st.columns([1, 2])
        with c1:
            best = st.number_input("Personal Best PF", value=500)
            today = st.number_input("Current Reading", value=450)
            if st.button("📊 Log Reading"):
                ratio = (today / best) * 100
                save_reading(st.session_state.user_email, today)
                st.session_state.history_df = load_history(st.session_state.user_email)
                if ratio >= 80: st.session_state.status_label, st.session_state.status_delta = "Green Zone", "Stable"
                elif 50 <= ratio < 80: st.session_state.status_label, st.session_state.status_delta = "Yellow Zone", "Caution"
                else: 
                    st.session_state.status_label, st.session_state.status_delta = "Red Zone", "EMERGENCY"
                    st.error("RED ZONE! Contact Doctor Immediately.")
                    if st.session_state.doctor_email:
                        alert_link = get_whatsapp_link(st.session_state.user_name, st.session_state.doctor_email, target_city, b_group, triggers, ratio=ratio, current_pf=today)
                        st.link_button("⚠️ SEND RED ZONE ALERT", alert_link)
                st.rerun()
        with c2:
            st.line_chart(st.session_state.history_df.set_index("Date")["Peak Flow (L/min)"])

    with tab2:
        st.subheader("Emergency Assistance")
        if st.session_state.doctor_email:
            sos_link = get_whatsapp_link(st.session_state.user_name, st.session_state.doctor_email, target_city, b_group, triggers, is_sos=True, coords=user_coords)
            st.link_button("🚨 SEND WHATSAPP SOS", sos_link, type="primary", use_container_width=True)
        else: st.warning("Please add a doctor's number in the sidebar.")

    with tab3:
        st.error("### ⚠️ EMERGENCY STEPS\n1. Sit upright and stay calm.\n2. Take one puff of your reliever inhaler every 30-60 seconds (up to 10 puffs).\n3. If no improvement, call for an ambulance.")

    with tab4:
        act_history = load_act_history(st.session_state.user_email)
        with st.form("act_form"):
            score = st.slider("How would you rate your asthma control this week? (5=Good, 25=Great)", 5, 25, 20)
            if st.form_submit_button("Submit Score"):
                save_act_score(st.session_state.user_email, score)
                st.rerun()
        if not act_history.empty: st.area_chart(act_history.set_index("Date")["ACT Score"])
