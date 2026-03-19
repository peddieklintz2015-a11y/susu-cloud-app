import streamlit as st
import pandas as pd
from sqlalchemy import text
from datetime import datetime

def set_custom_style():
    st.markdown("""
    <style>
    /* Vibrant Buttons */
    div.stButton > button:first-child {
        background-color: #FFD700;
        color: #212529;
        font-weight: bold;
        border: none;
    }
    
    /* Energetic Metric Cards */
    [data-testid="stMetricValue"] {
        color: #FF4500;
        font-size: 30px;
    }
    
    /* Sleek Sidebar */
    [data-testid="stSidebar"] {
        background-color: #212529;
        color: #F8F9FA;
    }
    </style>
""", unsafe_allow_html=True)

# Run this once at the start
set_custom_style()

# --- 1. SECURITY GATE (MUST BE FIRST) ---
def check_password():
    if "password_correct" not in st.session_state:
        st.title("🔐 RUCHANET SUSU ADMIN LOGIN")
        
        # Wrapping in a form makes the "Enter" key work
        with st.form("login_form"):
            pwd = st.text_input("Admin Password", type="password")
            submit_button = st.form_submit_button("Log In")
            
            if submit_button:
                if pwd == st.secrets["password"]:
                    st.session_state["password_correct"] = True
                    st.rerun()
                else:
                    st.error("❌ Invalid Password")
        return False
    return True

# Stop the app here if not logged in
if not check_password():
    st.stop()

# --- 1. INITIALIZE CLOUD CONNECTION ---
# This connects to your Supabase via the secrets you set up
conn = st.connection("postgresql",type="sql")

# --- 2. SECURITY GATE ---
def check_password():
    if "password_correct" not in st.session_state:
        st.title("🔐 Ruchanet Susu Security")
        
        # Wrapping this in a form allows the "Enter" key to work
        with st.form("login_form"):
            pwd = st.text_input("Admin Password", type="password")
            submit_button = st.form_submit_button("Log In")
            
            if submit_button:
                if pwd == st.secrets["password"]:
                    st.session_state["password_correct"] = True
                    st.rerun()
                else:
                    st.error("❌ Invalid Password")
        return False
    return True

# --- 3. UI SETUP ---
st.set_page_config(page_title="RUCHANET DAILY SUSU", page_icon="🏦", layout="wide")

# --- 4. NAVIGATION ---
st.sidebar.title("🏦 Main Menu")
choice = st.sidebar.radio("Go To:", [
    "📊 Business Dashboard", 
    "💸 Record Transaction",
    "🔎 Digital Passbook",
    "🗑️ Admin Tools"
])
# --- 5. MODULES ---
# --- MAIN APP LOGIC ---
if 'conn' in locals():
    # THE MASTER QUERY: Load this once at the top so every page works!
    clients = conn.query("SELECT * FROM clients", ttl=0)

    # SIDEBAR MENU
    choice = st.sidebar.selectbox("Go To:", ["📊 Business Dashboard", "💸 Record Transaction", "📋 Digital Passbook", "🛠 Admin Tools"])

    # 1. BUSINESS DASHBOARD
    if choice == "📊 Business Dashboard":
        st.title("📊 Financial Overview")
        df = conn.query("SELECT * FROM contributions", ttl=0)
        
        if not df.empty:
            # Your specific logic from Image 44
            total_vault = df['amount'].sum()
            # If you don't have a 'fee' column yet, this defaults to 0 to prevent crashes
            total_fees = df['fee'].sum() if 'fee' in df.columns else 0.0
            
            c1, c2, c3 = st.columns(3)
            c1.metric("💰 Total Vault", f"GHS {total_vault:,.2f}")
            c2.metric("📈 Total Profit", f"GHS {total_fees:,.2f}")
            c3.metric("🏦 Net Liability", f"GHS {(total_vault - total_fees):,.2f}")
            
            st.divider()
            st.subheader("Recent Activity")
            st.dataframe(df.sort_values(by='date', ascending=False), use_container_width=True)
        else:
            st.info("No data found in the cloud yet.")

    # 2. RECORD TRANSACTION
    elif choice == "💸 Record Transaction":
        st.title("💸 Transaction Entry")
        if not clients.empty:
            target = st.selectbox("Select Client", clients['client_name'].tolist())
            client_data = clients[clients['client_name'] == target].iloc[0]
            d_mark = client_data['daily_mark']
            
            col1, col2 = st.columns(2)
            with col1:
                ttype = st.radio("Transaction Type", ["Deposit", "Withdrawal"], horizontal=True)
                num_marks = st.number_input("Number of Marks", min_value=1, step=1)
                calculated_amt = float(num_marks * d_mark)
                st.info(f"💰 Rate: {calculated_amt:.2f} GHS ({num_marks} x {d_mark})")

            with col2:
                t_date = st.date_input("Transaction Date", value=datetime.now())
            
            if st.button("Confirm & Save"):
                final_val = calculated_amt if ttype == "Deposit" else -calculated_amt
                try:
                    with conn.session as s:
                        s.execute(
                            text("""INSERT INTO contributions (client_name, amount, date, marks_covered) 
                                 VALUES (:n, :a, :d, :mc)"""),
                            {"n": target, "a": final_val, "d": t_date, "mc": num_marks}
                        )
                        s.commit()
                    st.success(f"✅ Saved {calculated_amt} GHS for {target}")
                    st.balloons()
                except Exception as e:
                    st.error(f"Error: {e}")
        else:
            st.warning("Please register a client first.")

    # 3. DIGITAL PASSBOOK
    elif choice == "📋 Digital Passbook":
        st.title("📋 Digital Passbook")
        if not clients.empty:
            target = st.selectbox("Search Client", clients['client_name'].tolist())
            row = clients[clients['client_name'] == target].iloc[0]
            
            # Show Profile & Photo
            c1, c2 = st.columns([1, 2])
            with c1:
                if row['photo_url']: st.image(row['photo_url'], width=150)
                else: st.warning("No Photo")
            with c2:
                st.subheader(target)
                st.write(f"🆔 ID: {row['client_id']}")
                st.write(f"📞 Phone: {row['phone']}")
            
            # History & Statement
            history = conn.query(f"SELECT date, amount, marks_covered FROM contributions WHERE client_name = '{target}'", ttl=0)
            if not history.empty:
                st.dataframe(history, use_container_width=True)
                csv = history.to_csv(index=False).encode('utf-8')
                st.download_button(f"📄 Download {target}'s Statement", csv, f"{target}.csv", "text/csv")

    # 4. ADMIN TOOLS
    elif choice == "🛠 Admin Tools":
        st.title("🛠 Admin Dashboard")
        t1, t2 = st.tabs(["👤 Register", "💾 Backup"])
        with t1:
            # ID Generation logic
            next_num = len(clients) + 1
            gen_id = f"{next_num:03d}/{datetime.now().strftime('%m/%Y')}"
            st.info(f"Next ID: {gen_id}")
            
            with st.form("reg_form"):
                n = st.text_input("Full Name")
                p = st.text_input("Phone")
                d = st.number_input("Daily Mark", min_value=1.0)
                photo = st.camera_input("Client Photo")
                if st.form_submit_button("Register"):
                    # Photo logic and Insert logic...
                    st.success(f"Registered {n}!")
        with t2:
            all_data = conn.query("SELECT * FROM contributions", ttl=0)
            if not all_data.empty:
                st.download_button("📥 Download Full Backup", all_data.to_csv().encode('utf-8'), "backup.csv")