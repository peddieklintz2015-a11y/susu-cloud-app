import streamlit as st
import pandas as pd
from sqlalchemy import text
from datetime import datetime

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
    "👤 Register New Client", 
    "💸 Record Transaction", 
    "🔎 Digital Passbook", 
    "🗑️ Admin Tools"
])

# --- 5. MODULES ---

# --- DASHBOARD ---
if choice == "📊 Business Dashboard":
    st.title("📊 Financial Overview")
    df = conn.query("SELECT * FROM contributions", ttl=0)
    
    if not df.empty:
        total_vault = df['amount'].sum()
        total_fees = df['fee'].sum()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("💰 Total Vault", f"GHS {total_vault:,.2f}")
        c2.metric("📈 Total Profit (Fees)", f"GHS {total_fees:,.2f}")
        c3.metric("🏦 Net Liability", f"GHS {(total_vault - total_fees):,.2f}")
        
        st.divider()
        st.subheader("Recent Activity")
        st.dataframe(df.sort_values(by='date', ascending=False), use_container_width=True)
    else:
        st.info("No data found in the cloud yet.")

# --- REGISTRATION ---
elif choice == "👤 Register New Client":
    st.title("👤 Client Onboarding")
    with st.form("registration"):
        name = st.text_input("Full Name")
        phone = st.text_input("Phone Number")
        daily = st.number_input("Daily Contribution Amount (GHS)", min_value=1.0)
        submit = st.form_submit_button("Register to Cloud")
        
        if submit and name:
            with conn.session as s:
                s.execute(
                    text("INSERT INTO clients (client_name, phone, daily_mark) VALUES (:n, :p, :d)"),
                    params={"n": name, "p": phone, "d": daily}
                )
                s.commit()
            st.success(f"✅ {name} is now registered!")

# --- TRANSACTIONS (WITH 31-DAY & OLD DATA LOGIC) ---
elif choice == "💸 Record Transaction":
    st.title("💸 Transaction Entry")
    clients = conn.query("SELECT client_name, daily_mark FROM clients", ttl=0)
    
    if not clients.empty:
        target = st.selectbox("Select Client", clients['client_name'].tolist())
        d_mark = clients[clients['client_name'] == target]['daily_mark'].values[0]
        
        col1, col2 = st.columns(2)
        with col1:
            ttype = st.radio("Transaction Type", ["Deposit", "Withdrawal"], horizontal=True)
            amt = st.number_input("Amount (GHS)", min_value=1.0)
        
        with col2:
            t_date = st.date_input("Transaction Date", value=datetime.now())
            is_old = st.checkbox("📍 Migration: This is an old deposit from paper book")

        if st.button("Confirm & Save"):
        try:
            # 1. THE 31-DAY & DATE LOGIC
            p_day = t_date.day
            m_year = t_date.strftime("%m/%Y")
            
            # 2. THE OLD DATA LOGIC
            # If it's old data (is_old checked), we use the full amount. 
            # Otherwise, we handle it as a normal deposit/withdrawal.
            val = float(amt) if ttype == "Deposit" else -float(amt)

            # 3. DATABASE INSERTION
            with conn.session as s:
                s.execute(
                    text("""
                        INSERT INTO contributions (
                            client_name, amount, date, month_year, passbook_day
                        ) 
                        VALUES (:n, :a, :d, :my, :pd)
                    """),
                    {
                        "n": target,
                        "a": val,
                        "d": t_date.strftime('%Y-%m-%d'), # Formats date for backdating
                        "my": m_year,
                        "pd": int(p_day) # Ensures day is a standard number
                    }
                )
                s.commit()
            
            st.success(f"✅ Recorded GHS {amt} for {target} on {m_year}")
            st.balloons()
            
        except Exception as e:
            st.error(f"Failed to save: {e}")
    else:
        st.warning("Please register a client first.")

# --- PASSBOOK VIEW ---
elif choice == "🔎 Digital Passbook":
    st.title("🔎 Digital Passbook Search")
    clients = conn.query("SELECT client_name FROM clients", ttl=0)
    if not clients.empty:
        user = st.selectbox("View Passbook For:", clients['client_name'].tolist())
        data = conn.query("SELECT date, amount, fee, passbook_day, month_year FROM contributions WHERE client_name = :n ORDER BY date DESC", 
                          params={"n": user}, ttl=0)
        
        if not data.empty:
            st.metric("Current Savings Balance", f"GHS {data['amount'].sum():,.2f}")
            st.dataframe(data, use_container_width=True)
        else:
            st.info("No records found for this client.")

# --- DELETE / ADMIN ---
elif choice == "🗑️ Admin Tools":
    st.title("🗑️ Administrative Controls")
    st.warning("Deletion is permanent and cannot be undone.")
    
    clients = conn.query("SELECT client_name FROM clients", ttl=0)
    if not clients.empty:
        to_delete = st.selectbox("Select Client to DELETE", clients['client_name'].tolist())
        confirm = st.checkbox(f"I am sure I want to delete {to_delete}")
        
        if st.button("EXECUTE PERMANENT DELETE") and confirm:
            with conn.session as s:
                # Delete from both tables
                s.execute(text("DELETE FROM contributions WHERE client_name = :n"), params={"n": to_delete})
                s.execute(text("DELETE FROM clients WHERE client_name = :n"), params={"n": to_delete})
                s.commit()
            st.success(f"💥 {to_delete} has been removed from the cloud.")
            st.rerun()