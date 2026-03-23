import streamlit as st
import pandas as pd
from sqlalchemy import text
from datetime import datetime
import smtplib
from email.message import EmailMessage

# --- 1. SETUP (MUST BE FIRST) ---
st.set_page_config(page_title="RUCHANET DAILY SUSU", layout="wide")

def set_custom_style():
    st.markdown("""
    <style>
    /* Force Vibrant Buttons */
    div.stButton > button:first-child {
        background-color: #FFD700 !important;
        color: #212529 !important;
        font-weight: bold !important;
        border: none !important;
    }
    
    /* Force Energetic Metric Cards */
    [data-testid="stMetricValue"] {
        color: #FF4500 !important;
        font-size: 30px !important;
    }
    
    /* Force Sidebar Colors */
    [data-testid="stSidebar"] {
        background-color: #212529 !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- 2. DATABASE & DATA FETCH ---
conn = st.connection("postgresql", type="sql")

# Wrapped in a function to allow manual refreshing
def fetch_data():
    clients = conn.query("SELECT * FROM clients", ttl=0)
    contributions = conn.query("SELECT * FROM contributions", ttl=0)
    return clients, contributions

clients, contributions = fetch_data()

# --- 3. SECURITY GATE ---
def check_password():
    if "password_correct" not in st.session_state:
        st.title("🔐 RUCHANET SUSU ADMIN LOGIN")
        with st.form("login_form"):
            st.text_input("Admin Password", type="password", key="login_input")
            if st.form_submit_button("Log In"):
                if st.session_state["login_input"] == st.secrets["passwords"]["login_password"]:
                    st.session_state["password_correct"] = True
                    st.rerun()
                else:
                    st.error("❌ Invalid Login Password")
        return False
    return True

if not check_password():
    st.stop()

# --- 4. NAVIGATION ---
menu = ["📊 Dashboard", "💸 Transactions", "📑 Digital Passbook", "🛠 Admin Tools"]
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
        # Ensure date column is compared correctly
        today_data = contributions[contributions['date'].astype(str) == today_str]
        
        col_a, col_b = st.columns(2)
        col_a.metric("Today's Inflow", f"GHS {today_data[today_data['amount'] > 0]['amount'].sum():,.2f}")
        col_b.metric("Today's Outflow", f"GHS {abs(today_data[today_data['amount'] < 0]['amount'].sum()):,.2f}")
    else:
        st.info("No transaction data available yet.")

elif choice == "💸 Transactions":
    st.title("💸 Record Transactions")
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
            curr_month = t_date.strftime('%Y-%m')
            # Fixed month filtering logic
            has_paid = not contributions[
                (contributions['client_name'] == target) & 
                (contributions['date'].astype(str).str.startswith(curr_month)) &
                (contributions['amount'] > 0)
            ].empty
            
            fee_amt = d_mark if (not has_paid and ttype == "Deposit" and not is_old) else 0.0
            final_val = calc_amt if ttype == "Deposit" else -calc_amt

            try:
                with conn.session as s:
                    s.execute(
                        text("INSERT INTO contributions (client_name, amount, date, marks_covered, fee) VALUES (:n, :a, :d, :mc, :f)"),
                        {"n": target, "a": final_val, "d": t_date, "mc": int(num_marks), "f": fee_amt}
                    )
                    s.commit()
                st.success(f"✅ Recorded GHS {calc_amt} for {target}")
                st.rerun()
            except Exception as e:
                st.error(f"Database Error: {e}")
    else:
        st.error("Please register clients in Admin Tools first.")

# --- 📑 DIGITAL PASSBOOK PAGE ---
elif choice == "📑 Digital Passbook":
    st.title("📑 Client Passbook")
    
    # Search functionality
    search = st.text_input("🔍 Search Client Name", placeholder="Enter name to filter...")
    
    # Filter logic
    if not clients.empty:
        filtered = clients[clients['client_name'].str.contains(search, case=False)] if search else clients
        
        if not filtered.empty:
            target = st.selectbox("View Passbook For:", filtered['client_name'].tolist())
            c_info = clients[clients['client_name'] == target].iloc[0]
            
            # Layout: Photo on left, Stats on right
            col_a, col_b = st.columns([1, 2])
            
            with col_a:
                # Robust Photo Check
                photo_url = c_info.get('photo_url')
                if photo_url and str(photo_url).strip().lower() != "none":
                    try:
                        st.image(photo_url, width=230, caption=f"ID: {c_info['client_id']}")
                    except:
                        st.warning("⚠️ Image could not be loaded from storage.")
                else:
                    st.info("👤 No photo uploaded for this client.")
            
            with col_b:
                # Calculate specific balance for this user
                user_history = contributions[contributions['client_name'] == target]
                current_balance = user_history['amount'].sum() if not user_history.empty else 0.0
                
                st.subheader(f"Account: {target}")
                st.metric("Current Savings Balance", f"GHS {current_balance:,.2f}")
                st.write(f"📞 *Phone:* {c_info['phone']}")
                st.write(f"💰 *Daily Rate:* GHS {c_info['daily_mark']:.2f}")
            
            st.divider()
            
            # Transaction Table
            st.write("### 🕒 Full Transaction History")
            if not user_history.empty:
                # Formatting the dataframe for better readability
                display_df = user_history.sort_values(by='date', ascending=False).copy()
                display_df['date'] = pd.to_datetime(display_df['date']).dt.date
                
                st.dataframe(
                    display_df[['date', 'amount', 'marks_covered', 'fee']], 
                    use_container_width=True,
                    column_config={
                        "amount": st.column_config.NumberColumn("Amount (GHS)", format="%.2f"),
                        "fee": st.column_config.NumberColumn("Commission (GHS)", format="%.2f"),
                        "marks_covered": "Marks"
                    }
                )
            else:
                st.info("No transactions found for this account.")
        else:
            st.warning("No matching clients found for that search.")
    else:
        st.error("No clients registered in the system yet.")

# --- FIX 3: Registration Form Logic ---
# Move camera_input OUTSIDE the form for better reliability
if choice == "🛠 Admin Tools":
    st.title("🛠 Admin Dashboard")
    t1, t2, t3 = st.tabs(["👤 Registration", "📧 Reports", "🗑 Data Cleanup"])
    
    with t1:
        st.subheader("👤 Register New Client")
        # Camera input outside the form ensures the image buffer is captured correctly
        photo = st.camera_input("Take Client Photo (Required)")
        
        with st.form("reg_form", clear_on_submit=True):
            name = st.text_input("Full Name")
            phone = st.text_input("Phone Number")
            daily = st.number_input("Daily Mark (GHS)", min_value=1.0, step=1.0)
            submit = st.form_submit_button("Register to Cloud")
            
            if submit:
                if not name or not phone or photo is None:
                    st.error("❌ All fields including the photo are required!")
                else:
                    # Logic to save to Supabase goes here...
                    st.success(f"Registered {name}!")
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

    # --- FIX 2: Email Security ---
    with t2:
    st.subheader("Weekly Email Report")
    
    # 1. Calculate the data first so Python knows what the variables are
    total_vault = contributions['amount'].sum()
    total_fees = contributions['fee'].sum()
    report_date = datetime.now().strftime("%d %b %Y")

    if st.button("📧 Send Report"):
        try:
            msg = EmailMessage()
            msg['Subject'] = f"RUCHANET Weekly Report - {report_date}"
            
            # FIX: Use the NICKNAMES from your secrets, not the actual email strings
            msg['From'] = st.secrets["emails"]["sender_email"]
            msg['To'] = st.secrets["emails"]["receiver_email"]

            html_content = f"""
            <html>
                <body style="font-family: sans-serif; color: #333;">
                    <div style="background-color: #212529; padding: 20px; text-align: center;">
                        <h1 style="color: #FFD700; margin: 0;">RUCHANET DAILY SUSU</h1>
                    </div>
                    <div style="padding: 20px; border: 1px solid #ddd;">
                        <h3>Financial Summary</h3>
                        <p>Total Vault: <strong>GHS {total_vault:,.2f}</strong></p>
                        <p>Total Commission: <strong style="color: green;">GHS {total_fees:,.2f}</strong></p>
                    </div>
                </body>
            </html>
            """
            msg.add_alternative(html_content, subtype='html')

            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(
                    st.secrets["emails"]["sender_email"], 
                    st.secrets["emails"]["app_password"]
                )
                server.send_message(msg)
            
            st.success("✅ Report sent successfully!")
            
        except Exception as e:
            st.error(f"Email Error: {e}")

    # --- FIX 4: Secure Undo Logic ---
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
    elif admin_entry != "":
            st.error("❌ Incorrect Admin Password")

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
            st.error("Incorrect Admin Password")