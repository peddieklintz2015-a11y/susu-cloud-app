import streamlit as st
import pandas as pd
from sqlalchemy import text
from datetime import datetime
import smtplib
from email.message import EmailMessage

# --- 1. SETUP & STYLE ---
st.set_page_config(page_title="RUCHANET DAILY SUSU", layout="wide")

# Database Connection (Ensure your secrets.toml has [connections.postgresql])
conn = st.connection("postgresql", type="sql")

def set_custom_style():
    st.markdown("""
    <style>
    div.stButton > button:first-child { background-color: #FFD700; color: #212529; font-weight: bold; border: none; }
    [data-testid="stMetricValue"] { color: #FFD700; }
    </style>
    """, unsafe_allow_html=True)

set_custom_style()

# --- 3. GLOBAL DATA FETCH (Prevents 'Unbound' errors across pages) ---
# Update your fetch to include type hints
clients: pd.DataFrame = conn.query("SELECT * FROM clients", ttl=0)
contributions: pd.DataFrame = conn.query("SELECT * FROM contributions", ttl=0)

# --- 2. SECURITY GATE (Fixed NameError & TypeError) ---
def check_password():
    if "password_correct" not in st.session_state:
        st.title("🔐 RUCHANET SUSU ADMIN LOGIN")
        with st.form("login_form"):
            # Using key="login_input" puts the value into session_state immediately
            st.text_input("Admin Password", type="password", key="login_input")
            submit_button = st.form_submit_button("Log In")
            
            if submit_button:
                # Check directly against session_state and your secrets
                if st.session_state["login_input"] == st.secrets["passwords"]["login_password"]:
                    st.session_state["password_correct"] = True
                    st.rerun()
                else:
                    st.error("❌ Invalid Login Password")
        return False
    return True

if not check_password():
    st.stop()

# --- 4. SIDEBAR NAVIGATION ---
# Ensure emojis match the 'elif' statements exactly to avoid routing bugs
menu = ["📊 Dashboard", "💸 Transactions", "📋 Digital Passbook", "🛠 Admin Tools"]
choice = st.sidebar.selectbox("Go To:", menu)

# --- 5. PAGE ROUTING ---

if choice == "📊 Dashboard":
    st.title("📊 Financial Overview")
    if not contributions.empty:
        total_vault = contributions['amount'].sum()
        total_fees = contributions['fee'].sum()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Vault", f"GHS {total_vault:,.2f}")
        c2.metric("Total Commission", f"GHS {total_fees:,.2f}")
        c3.metric("Net Liability", f"GHS {(total_vault - total_fees):,.2f}")
        
        st.divider()
        st.subheader("🗓 Today's Cash Summary")
        today_str = datetime.now().strftime('%Y-%m-%d')
        today_data = contributions[contributions['date'].astype(str) == today_str]
        
        col_a, col_b = st.columns(2)
        col_a.metric("Today's Inflow", f"GHS {today_data[today_data['amount'] > 0]['amount'].sum():,.2f}")
        col_b.metric("Today's Outflow", f"GHS {abs(today_data[today_data['amount'] < 0]['amount'].sum()):,.2f}")
    else:
        st.info("No transaction data available yet.")

elif choice == "💸 Transactions":
    st.title("💸 Record Transaction")
    if not clients.empty:
        target = st.selectbox("Select Client", clients['client_name'].tolist())
        client_row = clients[clients['client_name'] == target].iloc[0]
        d_mark = float(client_row['daily_mark'])
        
        col1, col2 = st.columns(2)
        with col1:
            ttype = st.radio("Type", ["Deposit", "Withdrawal"], horizontal=True)
            num_marks = st.number_input("Number of Marks", min_value=1, step=1)
            calc_amt = float(num_marks * d_mark)
            st.info(f"💰 Rate: {calc_amt:.2f} GHS")

        with col2:
            t_date = st.date_input("Transaction Date", value=datetime.now())
            is_old = st.checkbox("📍 Migration Entry")

        if st.button("Confirm & Save"):
            # Commission logic for first deposit of the month
            curr_month = t_date.strftime('%Y-%m')
            has_paid = not contributions[
                (contributions['client_name'] == target) & 
                (contributions['date'].astype(str).str.contains(curr_month)) &
                (contributions['amount'] > 0)
            ].empty
            
            fee_amt = d_mark if (not has_paid and ttype == "Deposit" and not is_old) else 0.0
            final_val = calc_amt if ttype == "Deposit" else -calc_amt

            with conn.session as s:
                s.execute(
                    text("INSERT INTO contributions (client_name, amount, date, marks_covered, fee) VALUES (:n, :a, :d, :mc, :f)"),
                    {"n": target, "a": final_val, "d": t_date, "mc": int(num_marks), "f": fee_amt}
                )
                s.commit()
            st.success(f"Successfully recorded GHS {calc_amt} for {target}")
            st.rerun()
    else:
        st.error("Please register clients in Admin Tools first.")

# --- 2. DIGITAL PASSBOOK ---
elif choice == "📑 Digital Passbook":
    st.title("📑 Client Passbook")
    search = st.text_input("🔍 Search Client Name")
    
    filtered = clients[clients['client_name'].str.contains(search, case=False)] if search else clients
    
    if not filtered.empty:
        target = st.selectbox("View Passbook For:", filtered['client_name'].tolist())
        c_info = clients[clients['client_name'] == target].iloc[0]
        
        col_a, col_b = st.columns([1, 2])
        with col_a:
            # SAFETY CHECK: Fixes the 'NoneType' photo error
            if c_info['photo_url'] and str(c_info['photo_url']) != "None":
                st.image(c_info['photo_url'], width=200)
            else:
                st.warning("👤 No photo on file.")
        
        with col_b:
            c_history = contributions[contributions['client_name'] == target]
            balance = c_history['amount'].sum() if not c_history.empty else 0.0
            st.subheader(target)
            st.metric("Current Balance", f"GHS {balance:,.2f}")
            st.write(f"📞 Phone: {c_info['phone']}")
        
        st.divider()
        st.write("### 🕒 Transaction History")
        if not c_history.empty:
            st.dataframe(c_history.sort_values(by='date', ascending=False), use_container_width=True)
        else:
            st.info("No transactions found.")
    else:
        st.error("No matching clients found.")

# --- 3. ADMIN TOOLS ---
elif choice == "🛠 Admin Tools":
    st.title("🛠 Admin Dashboard")
    t1, t2, t3 = st.tabs(["👤 Registration", "📧 Reports", "🗑 Data Cleanup"])

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
            total_vault = 0.00
            total_fees = 0.00
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
                        server.login("peddieklintz2015@gmail.com", "")
                        server.send_message(msg)
                    st.success("Report sent!")
                except Exception as e:
                    st.error(f"Failed to send email: {e}")

    with t3:
        st.subheader("🛑 Restricted Data Cleanup")
        # Pulling password from secrets
        admin_entry = st.text_input("Enter Admin Password", type="password", key="cleanup_pass")
        
        # Check against the correct secret path
        if admin_entry == st.secrets["passwords"]["admin_password"]:
            st.success("Admin Access Granted: Deletion Tool Unlocked")
            
            # Use 'contributions' to match your global fetch at Line 25
    if not contributions.empty:
                search_term = st.text_input("Filter by Client Name", key="cleanup_search")
                # Create a filtered view
                f_df = contributions[contributions['client_name'].str.contains(search_term, case=False)]
                
                if not f_df.empty:
                    to_del = st.selectbox("Select entry to remove", 
                        options=f_df.apply(lambda x: f"{x['date']} | {x['client_name']} | GHS {x['amount']}", axis=1))
                    
                    if st.button("🗑️ Permanent Delete"):
                        # Save to session state for the Undo button
                        st.session_state['undo_info'] = to_del
                        parts = to_del.split(" | ")
                        
                        with conn.session as s:
                            s.execute(text("DELETE FROM contributions WHERE client_name = :n AND date = :d"),
                                     {"n": parts[1], "d": parts[0]})
                            s.commit()
                        st.success("Record Deleted.")
                        st.rerun()
                else:
                    st.info("No Transaction found for this search.")

# --- NEW CLIENT DELETE SECTION ---
    st.divider()
    st.subheader("👤 Permanent Client Removal")
    st.warning("🚨 CRITICAL: This deletes the client and ALL history.")

        # 1. Fetch latest clients from Supabase
    cleanup_clients = conn.query("SELECT * FROM clients", ttl=0)

    if not cleanup_clients.empty:
            # 2. Dropdown to select the profile
            client_to_wipe = st.selectbox(
                "Select Client Profile to Delete", 
                options=cleanup_clients['client_name'].tolist(),
                key="cleanup_client_profile_list"
            )
            
            # 3. Security Checkbox
            confirm_profile_del = st.checkbox(f"I confirm I want to wipe {client_to_wipe} from the system.")
            
            if st.button("❌ Delete Client Profile Permanently"):
                if confirm_profile_del:
                    with conn.session as s:
                        # Use the 'text' wrapper to fix the red errors from Image 12
                        s.execute(text("DELETE FROM contributions WHERE client_name = :n"), {"n": client_to_wipe})
                        s.execute(text("DELETE FROM clients WHERE client_name = :n"), {"n": client_to_wipe})
                        s.commit()
                    st.success(f"🔥 {client_to_wipe} removed successfully.")
                    st.rerun()
                else:
                    st.error("Please check the confirmation box first.")

                            # --- THE UNDO BUTTON (Properly Indented) ---
    if 'undo_info' in st.session_state:
            st.warning(f"Recently Deleted: {st.session_state['undo_info']}")
            if st.button("⏪ Undo Deletion"):
                u = st.session_state['undo_info'].split(" | ")
                with conn.session as s:
                    s.execute(text("INSERT INTO contributions (client_name, amount, date) VALUES (:n, :a, :d)"),
                              {"n": u[1], "a": float(u[2].replace("GHS ", "").replace(",", "")), "d": u[0]})
                    s.commit()
                del st.session_state['undo_info']
                st.success("Transaction Restored!")
                st.rerun()
        
            elif admin_entry != "":
                st.error("❌ Incorrect Admin Password")