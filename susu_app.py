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

# --- 3. UI SETUP ---
st.set_page_config(page_title="RUCHANET DAILY SUSU", page_icon="🏦", layout="wide")
# --- MAIN APP LOGIC ---
if 'conn' in locals():
    # 1. LOAD MASTER DATA (Every page needs these)
    clients = conn.query("SELECT * FROM clients", ttl=0)
    contributions_df = conn.query("SELECT * FROM contributions", ttl=0)

    # Sidebar Menu
    choice = st.sidebar.selectbox("Go To:", [
        "📊 Business Dashboard", 
        "💸 Record Transaction", 
        "📋 Digital Passbook", 
        "🛠 Admin Tools"
    ])

    # --- 📊 BUSINESS DASHBOARD ---
    if choice == "📊 Business Dashboard":
        st.title("📊 Financial Overview")
        
        if not contributions_df.empty:
            # Your specific logic from Image 44
            total_vault = contributions_df['amount'].sum()
            # Default to 0 if 'fee' column doesn't exist yet
            total_fees = contributions_df['fee'].sum() if 'fee' in contributions_df.columns else 0.0
            
            c1, c2, c3 = st.columns(3)
            c1.metric("💰 Total Vault", f"GHS {total_vault:,.2f}")
            c2.metric("📈 Total Profit (Fees)", f"GHS {total_fees:,.2f}")
            c3.metric("🏦 Net Liability", f"GHS {(total_vault - total_fees):,.2f}")
            
            st.divider()
            st.subheader("Recent Activity")
            # Sorted by date latest first
            st.dataframe(contributions_df.sort_values(by='date', ascending=False), use_container_width=True)
        else:
            st.info("No transaction data found in the cloud yet.")

    # --- 💸 RECORD TRANSACTION ---
    elif choice == "💸 Record Transaction":
        st.title("💸 Transaction Entry")
        if not clients.empty:
            target = st.selectbox("Select Client", clients['client_name'].tolist())
            # Safely get the client's rate
            d_mark = clients[clients['client_name'] == target]['daily_mark'].iloc[0]
            
            col1, col2 = st.columns(2)
            with col1:
                ttype = st.radio("Transaction Type", ["Deposit", "Withdrawal"], horizontal=True)
                num_marks = st.number_input("Number of Marks", min_value=1, step=1, value=1)
                calculated_amt = float(num_marks * d_mark)
                st.info(f"💰 Rate: {calculated_amt:.2f} GHS ({num_marks} x {d_mark:.2f})")

            with col2:
                t_date = st.date_input("Transaction Date", value=datetime.now())
                is_old = st.checkbox("📍 Migration: Old data entry")

            if st.button("Confirm & Save"):
                final_val = calculated_amt if ttype == "Deposit" else -calculated_amt
                try:
                    with conn.session as s:
                        s.execute(
                            text("""INSERT INTO contributions (client_name, amount, date, marks_covered) 
                                 VALUES (:n, :a, :d, :mc)"""),
                            {"n": target, "a": final_val, "d": t_date.strftime('%Y-%m-%d'), "mc": int(num_marks)}
                        )
                        s.commit()
                    st.success(f"✅ Saved {calculated_amt:.2f} GHS for {target}")
                    st.balloons()
                except Exception as e:
                    st.error(f"Error saving: {e}")
        else:
            st.warning("No clients found. Please register one in Admin Tools.")

    # --- 📋 DIGITAL PASSBOOK ---
    elif choice == "📋 Digital Passbook":
        st.title("📋 Digital Passbook")
        if not clients.empty:
            target = st.selectbox("Search Client", clients['client_name'].tolist())
            client_profile = clients[clients['client_name'] == target].iloc[0]
            
            # Show Photo & Profile
            c1, c2 = st.columns([1, 2])
            with c1:
                if 'photo_url' in client_profile and client_profile['photo_url']:
                    st.image(client_profile['photo_url'], width=150)
                else:
                    st.warning("No Photo Available")
            with c2:
                st.subheader(target)
                st.write(f"🆔 *ID:* {client_profile.get('client_id', 'N/A')}")
                st.write(f"📞 *Phone:* {client_profile['phone']}")
                st.write(f"💰 *Daily Mark:* GHS {client_profile['daily_mark']:.2f}")

            st.divider()
            
            # Client specific history
            client_history = contributions_df[contributions_df['client_name'] == target]
            if not client_history.empty:
                st.write(f"### History for {target}")
                st.dataframe(client_history.sort_values(by='date', ascending=False), use_container_width=True)
                
                # Statement Download
                csv_data = client_history.to_csv(index=False).encode('utf-8')
                st.download_button(f"📄 Download {target}'s Statement", csv_data, f"{target}_statement.csv", "text/csv")
            else:
                st.info("No transactions found for this client.")

    # --- 🛠 ADMIN TOOLS ---
    elif choice == "🛠 Admin Tools":
        st.title("🛠 Admin Dashboard")
        t1, t2 = st.tabs(["👤 Client Registration", "💾 System Backups"])
        
        with t1:
            st.subheader("Register New Client")
            # Auto-ID Generation
            next_num = len(clients) + 1
            gen_id = f"{next_num:03d}/{datetime.now().strftime('%m/%Y')}"
            st.info(f"Assigning ID: *{gen_id}*")

            with st.form("reg_form", clear_on_submit=True):
                name = st.text_input("Full Name")
                phone = st.text_input("Phone Number")
                daily = st.number_input("Daily Mark (GHS)", min_value=1.0)
                photo = st.camera_input("Take Client Photo")
                
                if st.form_submit_button("Register to Cloud"):
                    p_url = f"https://xrqcejmtqfrztfwggsbc.supabase.co/storage/v1/object/public/client-photos/{gen_id.replace('/', '_')}.jpg"
                    try:
                        with conn.session as s:
                            s.execute(
                                text("INSERT INTO clients (client_id, client_name, phone, daily_mark, photo_url) VALUES (:i, :n, :p, :d, :u)"),
                                {"i": gen_id, "n": name, "p": phone, "d": daily, "u": p_url}
                            )
                            s.commit()
                        st.success(f"✅ {name} registered with ID: {gen_id}")
                    except Exception as e:
                        st.error(f"Error: {e}")

        with t2:
            st.subheader("Full Database Backup")
            if not contributions_df.empty:
                csv_all = contributions_df.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Download All Transactions (CSV)", csv_all, "full_backup.csv", "text/csv")