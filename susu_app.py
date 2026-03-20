import streamlit as st
import pandas as pd
from sqlalchemy import text
from datetime import datetime
import smtplib
from email.message import EmailMessage

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
            st.text_input("Admin Password", type="password", key="login_input")
            submit_button = st.form_submit_button("Log In")
            
            if submit_button("Log In"):
                if   st.session_state["login input"] == st.secrets["passwords"]["login_password"]:
                    st.session_state["password_correct"] = True
                    st.rerun()
                else:
                    st.error("❌ Invalid Login Password")
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
    # Load Master Data (Global access for all pages)
    clients = conn.query("SELECT * FROM clients", ttl=0)
    df = conn.query("SELECT * FROM contributions", ttl=0)

    choice = st.sidebar.selectbox("Go To:", ["📊 Dashboard", "💸 Transactions", "📋 Passbook", "🛠 Admin Tools"])

    # --- 1. DASHBOARD & DAILY SUMMARY ---
    if choice == "📊 Dashboard":
        st.title("📊 Financial Overview")
        if not df.empty:
            # Stats for the top row
            total_vault = df['amount'].sum()
            total_fees = df['fee'].sum() if 'fee' in df.columns else 0.0
            
            c1, c2, c3 = st.columns(3)
            c1.metric("💰 Total Vault", f"GHS {total_vault:,.2f}")
            c2.metric("📈 Total Commission", f"GHS {total_fees:,.2f}")
            c3.metric("🏦 Net Liability", f"GHS {(total_vault - total_fees):,.2f}")

            st.divider()
            
            # DAILY SUMMARY (Cash-on-hand check)
            st.subheader("📅 Today's Cash Summary")
            today = datetime.now().strftime('%Y-%m-%d')
            today_df = df[df['date'].astype(str) == today]
            
            if not today_df.empty:
                inflow = today_df[today_df['amount'] > 0]['amount'].sum()
                outflow = today_df[today_df['amount'] < 0]['amount'].abs().sum()
                k1, k2 = st.columns(2)
                k1.metric("Today's Inflow", f"GHS {inflow:.2f}")
                k2.metric("Today's Outflow", f"GHS {outflow:.2f}")
            else:
                st.info("No cash recorded today yet.")
        else:
            st.info("No data yet.")

    # --- 2. TRANSACTIONS & COMMISSION LOGIC ---
    elif choice == "💸 Transactions":
        st.title("💸 Record Transaction")
        if not clients.empty:
            target = st.selectbox("Select Client", clients['client_name'].tolist())
            d_mark = clients[clients['client_name'] == target]['daily_mark'].iloc[0]
            
            col1, col2 = st.columns(2)
            with col1:
                ttype = st.radio("Type", ["Deposit", "Withdrawal"])
                num_marks = st.number_input("Marks", min_value=1, step=1)
                calc_amt = float(num_marks * d_mark)
                st.info(f"💰 Rate: {calc_amt:.2f} GHS")
            
            t_date = st.date_input("Date", value=datetime.now())

            if st.button("Confirm & Save"):
                # COMMISSION CHECK: Is this the first deposit of the month?
                curr_month = t_date.strftime('%Y-%m')
                has_paid_this_month = not df[(df['client_name'] == target) & (df['date'].astype(str).str.contains(curr_month))].empty
                
                fee_amt = 0.0
                if not has_paid_this_month and ttype == "Deposit":
                    fee_amt = float(d_mark) # Take 1 full mark
                    st.warning(f"Commission of GHS {fee_amt} will be recorded.")

                final_val = calc_amt if ttype == "Deposit" else -calc_amt
                
                with conn.session as s:
                    s.execute(text("INSERT INTO contributions (client_name, amount, date, marks_covered, fee) VALUES (:n, :a, :d, :mc, :f)"),
                              {"n": target, "a": final_val, "d": t_date, "mc": num_marks, "f": fee_amt})
                    s.commit()
                st.success("Transaction Saved!")

    # --- 3. ADMIN TOOLS & EMAIL ---
    elif choice == "🛠 Admin Tools":
        st.title("🛠 Admin Dashboard")
        t1, t2, t3= st.tabs( ["👤 Registration", "📧 Reports", "🗑️ Data Cleanup"])
        with t1:
            st.subheader("👤 Register New Client")
            
            # 1. Automatic ID Generation (Safe from blanks)
            if not clients.empty:
                next_num = len(clients) + 1
            else:
                next_num = 1
            gen_id = f"{next_num:03d}/{datetime.now().strftime('%m/%Y')}"
            st.info(f"Next available ID: *{gen_id}*")

            with st.form("reg_form", clear_on_submit=True):
                name = st.text_input("Full Name (Required)")
                phone = st.text_input("Phone Number (Required)")
                daily = st.number_input("Daily Mark (GHS)", min_value=1.0, step=1.0)
                photo = st.camera_input("Take Client Photo (Required)")
                
                submit = st.form_submit_button("Register to Cloud")
                
                if submit:
                         # BLANK FIELD VALIDATION
                    if not name.strip() or not phone.strip() or photo is None:
                        st.error("❌ All fields (Name, Phone, and Photo) are required!")
                    else:
                        # Proceed with save...
                        st.success(f"Registered {name}!")
                        try:
                            # Standardize filename for storage
                            file_path = f"{gen_id.replace('/', '_')}.jpg"
                            p_url = f"https://xrqcejmtqfrztfwggsbc.supabase.co/storage/v1/object/public/client-photos/{file_path}"
                            
                            with conn.session as s:
                                s.execute(
                                    text("""INSERT INTO clients (client_id, client_name, phone, daily_mark, photo_url) 
                                         VALUES (:i, :n, :p, :d, :u)"""),
                                    {"i": gen_id, "n": name.strip(), "p": phone.strip(), "d": daily, "u": p_url}
                                )
                                s.commit()
                            st.success(f"✅ Success! {name} registered with ID: {gen_id}")
                            st.balloons()
                            st.rerun() # Refresh list immediately
                        except Exception as e:
                            st.error(f"Cloud Error: {e}")
            
        with t2:
            st.subheader("Weekly Email Report")
            my_email = st.text_input("Receiver Email", value="peddieklintz2015@gmail.com")
            if st.button("📧 Send Report to My Inbox"):
                try:
                    # Basic Email Logic
                    msg = EmailMessage()
                    msg.set_content(f"Susu Weekly Report\nTotal Vault: GHS {total_vault}\nProfit: GHS {total_fees}")
                    msg['Subject'] = f"Susu Weekly Update - {datetime.now().strftime('%Y-%m-%d')}"
                    msg['From'] = "peddieklintz2015@gmail.com"
                    msg['To'] = my_email

                    # Note: You need a Gmail App Password for this to work
                    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                        server.login("peddieklintz2015@gmail.com", "rmsrmhkewwnvhqvl")
                        server.send_message(msg)
                    st.success("Report sent!")
                except Exception as e:
                    st.error(f"Failed to send email: {e}")

        with t3:
            st.subheader("🛑 Restricted Data Cleanup")
            # Pulling password from secrets.toml
            admin_entry = st.text_input("Enter Admin Password", type="password")
            
            if admin_entry == st.secrets["passwords"]["admin_password"]:
                st.success("Admin Access Granted:Deletion Tool Unlocked")
                # --- SEARCHABLE DELETE ---
                st.write("### 🔎 Search & Delete Transaction")
                search_term = st.text_input("Filter by Client Name")
                
                if not df.empty:
                    # Filter list based on search
                    f_df = df[df['client_name'].str.contains(search_term, case=False)] if search_term else df.head(10)
                    
                    to_del = st.selectbox("Select entry to remove", 
                      f_df.apply(lambda x: f"{x['date']} | {x['client_name']} | GHS {x['amount']}", axis=1))
                    
                    if st.button("🗑️ Permanent Delete"):
                        # Store in session state for Undo BEFORE deleting
                        st.session_state['undo_info'] = to_del
                        
                        parts = to_del.split(" | ")
                        with conn.session as s:
                            s.execute(text("DELETE FROM contributions WHERE client_name = :n AND date = :d AND amount = :a"), 
                                      {"n": parts[1], "d": parts[0], "a": float(parts[2].replace("GHS ", ""))})
                            s.commit()
                        st.rerun()

                # --- THE UNDO BUTTON ---
                if 'undo_info' in st.session_state:
                    st.warning(f"Recently Deleted: {st.session_state['undo_info']}")
                    if st.button("⏪ Undo Deletion"):
                        u = st.session_state['undo_info'].split(" | ")
                        with conn.session as s:
                            s.execute(text("INSERT INTO contributions (client_name, amount, date) VALUES (:n, :a, :d)"),
                                      {"n": u[1], "a": float(u[2].replace("GHS ", "")), "d": u[0]})
                            s.commit()
                        del st.session_state['undo_info'] # Clear log
                        st.success("Transaction Restored!")
                        st.rerun()
            elif admin_pass != "":
                st.error("Incorrect Admin Password")