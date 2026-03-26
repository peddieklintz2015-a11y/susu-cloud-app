import streamlit as st
import pandas as pd
from sqlalchemy import text
from datetime import datetime
import smtplib
from email.message import EmailMessage

# --- 1. SETUP ---
st.set_page_config(page_title="RUCHANET DAILY SUSU", layout="wide")

def set_custom_style():
    st.markdown("""
    <style>
    div.stButton > button:first-child { background-color: #FFD700 !important; color: #212529 !important; font-weight: bold !important; border: none !important; }
    [data-testid="stMetricValue"] { color: #FF4500 !important; font-size: 30px !important; }
    [data-testid="stSidebar"] { background-color: #212529 !important; }
    </style>
    """, unsafe_allow_html=True)

set_custom_style()

# --- 2. DATABASE ---
conn = st.connection("postgresql", type="sql")

# --- 3. DATA FUNCTIONS (Defined at top level so they are ALWAYS available) ---
@st.cache_data(ttl=300)
def fetch_data():
    try: 
        clients_df = conn.query("SELECT * FROM clients", ttl=600)
        contributions_df = conn.query("SELECT * FROM contributions", ttl=600)
        return clients_df.fillna(""), contributions_df.fillna(0)
    except Exception as e:
        # If there's a DNS error (like in your first screenshot), show it here
        st.error(f"📡 Database connection error. Check internet or Supabase status: {e}")
        return pd.DataFrame(), pd.DataFrame()

def get_next_gen_id(reg_date):
    """
    Returns the first available ID (001, 002, etc.) for the chosen month/year.
    Format: 001/MM/YY
    """
    mm = reg_date.strftime('%m')
    yy = reg_date.strftime('%y')
    suffix = f"/{mm}/{yy}"
    
    try:
        with conn.session as s:
            # Get all existing IDs for this specific month/year
            query = text("SELECT client_id FROM clients WHERE client_id LIKE :p")
            result = s.execute(query, {"p": f"%{suffix}"}).fetchall()

            # If the month is empty, start at 001
            if not result:
                return f"001{suffix}"

            # Extract just the numeric prefixes and sort them
            existing_nums = sorted([int(row[0].split('/')[0]) for row in result])
            
            # Find the first gap in the sequence
            next_num = 1
            for num in existing_nums:
                if num == next_num:
                    next_num += 1
                else:
                    break # Found a gap! (e.g., 001, 003 -> gap is 002)
            
            return f"{str(next_num).zfill(3)}{suffix}"
    except Exception as e:
        st.error(f"ID Generation Error: {e}")
        return None

# --- 4. SECURITY GATE ---
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

# --- 5. INITIALIZE DATA (Runs ONLY after login) ---
with st.spinner("Fetching latest data..."):
    clients, contributions = fetch_data()

combined_df = pd.DataFrame()

# Logic for combined data
if not clients.empty and not contributions.empty:
    try:
        # We merge using 'client_name' because it exists in both DataFrames
        combined_df = pd.merge(
            contributions,
            clients[['client_id', 'client_name']], # Pull ID from clients
            on='client_name',                      # The shared key
            how='left'
        )
            
    except Exception as e:
        st.warning(f"Merge error: {e}")
        # If merge fails, fall back to just contributions so the app doesn't crash
        combined_df = contributions

# --- 6. NAVIGATION & PAGE ROUTING ---
menu = ["📊 Dashboard", "💸 Transactions", "📑 Digital Passbook", "🛠 Admin Tools"]
choice = st.sidebar.selectbox("Go To:", menu)

if choice == "📊 Dashboard":
    # ... (Your Dashboard code is fine) ...
    st.title("📊 Financial Overview")

    if not contributions.empty:
        total_vault = contributions['amount'].sum()
        total_fees = contributions['fee'].sum()
        net_liability = total_vault - total_fees
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Vault", f"GHS {total_vault:,.2f}")
        c2.metric("Total Commission", f"GHS {total_fees:,.2f}")
        c3.metric("Net Liability", f"GHS {(total_vault - total_fees):,.2f}")
        
        st.divider()
        st.subheader("🗓 Today's Cash Summary")
        # Get today's date as a date object
        today_date = datetime.now().date()

        if not contributions.empty:
        # Ensure the 'date' column is converted to datetime objects, then extract the date
         contributions['date_only'] = pd.to_datetime(contributions['date']).dt.date
         today_data = contributions[contributions['date_only'] == today_date]
    
         col_a, col_b = st.columns(2)
    
         # Calculate sums safely
         inflow = today_data[today_data['amount'] > 0]['amount'].sum()
          # We use abs() for the display so it looks clean (e.g., GHS 50.00 instead of GHS -50.00)
         outflow = abs(today_data[today_data['amount'] < 0]['amount'].sum())
    
         col_a.metric("Today's Inflow", f"GHS {inflow:,.2f}")
         col_b.metric("Today's Outflow", f"GHS {outflow:,.2f}")
        else:
            st.info("No data found to summarize.")
        
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
        
        # Calculate Current Status
        user_history = contributions[contributions['client_name'] == target]
        total_saved_ghs = user_history['amount'].sum()
        # We calculate total marks by looking at the 'marks_covered' column
        total_marks_saved = user_history['marks_covered'].sum() 
        
        ttype = st.radio("Type", ["Deposit", "Withdrawal"], horizontal=True)

        if ttype == "Deposit":
            num_marks = st.number_input("Number of Marks (+1)", min_value=1, step=1)
            final_amt = float(num_marks * d_mark)
            st.info(f"Adding {num_marks} marks. Value: GHS {final_amt:,.2f}")
        
        else:
            # WITHDRAWAL LOGIC
            requested_cash = st.number_input("Enter Cash to Withdraw (GHS)", min_value=0.0)
            
            # Calculate months/pages (Every 31 marks = 1 Month Commission)
            # Use math.ceil if you take commission for partial months, 
            # or floor if only for completed 31-day cycles.
            import math
            total_months = math.ceil(total_marks_saved / 31)
            total_commission_owed = total_months * d_mark
            
            total_deduction = requested_cash + total_commission_owed
            
            if requested_cash > 0:
                if total_deduction > total_saved_ghs:
                    st.error("⚠️ Insufficient Balance!")
                    st.write(f"Client has: GHS {total_saved_ghs:,.2f}")
                    st.write(f"Required (Cash + {total_months} mo. Commission): GHS {total_deduction:,.2f}")
                    can_save = False
                else:
                    st.success("✅ Balance Sufficient")
                    st.write(f"Deducting GHS {requested_cash:,.2f} + GHS {total_commission_owed:,.2f} Commission")
                    can_save = True

        # Save Button
        if st.button("Confirm & Save"):
           t_date = datetime.now()
           if ttype == "Deposit":
              db_amt = final_amt
              db_marks = num_marks
              db_fee = 0.0
        else:
             # can_save is defined in the withdrawal logic above
            if not can_save: 
             st.stop()
            db_amt = -requested_cash
            db_marks = 0 
            db_fee = total_commission_owed

    try:
        with conn.session as s:
            s.execute(
                text("""INSERT INTO contributions (client_name, amount, date, marks_covered, fee) 
                        VALUES (:n, :a, :d, :mc, :f)"""),
                {"n": target, "a": db_amt, "d": t_date, "mc": db_marks, "f": db_fee}
            )
            s.commit()
        
        # Cleaned up success message (no f-string warning)
        st.success(f"✅ Transaction recorded for {target}")
        st.rerun()
        # Receipt Layout
        st.subheader("🧾 Transaction Receipt")
        receipt_col1, receipt_col2 = st.columns(2)
        with receipt_col1:
            st.write("*RUCHANET DAILY SUSU*")
            st.write(f"Client: {target}")
            st.write(f"Type: {ttype}")
        with receipt_col2:
            st.write(f"Date: {t_date.strftime('%Y-%m-%d %H:%M')}")
            st.write(f"Amount: GHS {abs(db_amt):,.2f}")
            if db_fee > 0:
                st.write(f"Comm. Paid: GHS {db_fee:,.2f}")
        st.info("💡 You can take a screenshot of this receipt for the client.")
    except Exception as e:
                st.error(f"🚨 Database Error: {e}")
    else:
        st.error("Please register clients in Admin Tools first.")

elif choice == "📑 Digital Passbook":
    st.title("📑 Client Passbook")
    search = st.text_input("🔍 Search Client Name", placeholder="Enter name...")
    
    if not clients.empty:
        filtered = clients[clients['client_name'].str.contains(search, case=False)] if search else clients
        if not filtered.empty:
            target = st.selectbox("View Passbook For:", filtered['client_name'].tolist())
            c_info = clients[clients['client_name'] == target].iloc[0]
            
            # --- Business Logic: Page & Commission Tracking ---
            user_history = combined_df[combined_df['client_name'] == target]
            total_marks = user_history['marks_covered'].sum()
            current_balance = user_history['amount'].sum()
            
            # Calculate page progress
            completed_pages = int(total_marks // 31)
            marks_on_current_page = int(total_marks % 31)
            marks_needed_for_next = 31 - marks_on_current_page
            
            col_a, col_b = st.columns([1, 2])
            with col_a:
                photo_url = c_info.get('photo_url')
                if photo_url and str(photo_url).strip().lower() != "none":
                    st.image(photo_url, width=230)
                else:
                    st.info("👤 No photo.")
            
            with col_b:
                st.subheader(f"Account: {target} (ID: {c_info['client_id']})")
                m1, m2 = st.columns(2)
                m1.metric("Savings Balance", f"GHS {current_balance:,.2f}")
                m2.metric("Total Marks", f"{total_marks} days")
                
                # --- Page Progress Bar ---
                st.write(f"📖 *Passbook Page {completed_pages + 1}*")
                progress = marks_on_current_page / 31
                st.progress(progress)
                st.caption(f"{marks_on_current_page} marks done. {marks_needed_for_next} marks left until next page commission.")

            st.divider()
            if not user_history.empty:
                st.dataframe(user_history.sort_values(by='date', ascending=False), use_container_width=True)
    else:
        st.error("No clients registered.")

elif choice == "🛠 Admin Tools":
    st.title("🛠 Admin Dashboard")
    t1, t2, t3, t4 = st.tabs(["👤 Registration", "📧 Reports", "🗑 Data Cleanup", "💰 Commission Tracker" ])
    
    with t1:
     st.subheader("👤 Register New Client")
     # 1. Capture Photo
     photo = st.camera_input("Take Client Photo (Required)")
     with st.form("reg_form", clear_on_submit=True):
         name = st.text_input("Full Name")
         phone = st.text_input("Phone Number")
         daily = st.number_input("Daily Mark (GHS)", min_value=5.0, step=1.0)
         submit = st.form_submit_button("Register to Cloud")
         reg_date = st.date_input("Registration Date (For ID Generation)", value=datetime.now())
        
         if st.form_submit_button("Register"):
                gen_id = get_next_gen_id(reg_date)
                if not name.strip() or not phone.strip() or photo is None:
                 st.error("❌ All fields (Name, Phone, and Photo) are required")
                else:
                    try:
                         # 2. GENERATE ID
                        current_date_slug = datetime.now().strftime('%m%y') # e.g., '0326' for March 2026
                        gen_id = get_next_gen_id(current_date_slug)

                         # 3. INITIALIZE STORAGE CLIENT
                        from supabase import create_client
                        url = st.secrets["supabase_url"]
                        key = st.secrets["supabase_key"]
                        sb_client = create_client(url, key)

                         # 4. UPLOAD PHOTO TO BUCKET
                        file_path = f"{gen_id.replace('/', '_')}.jpg"
                        sb_client.storage.from_("client-photos").upload(
                        path=file_path,
                        file=photo.getvalue(),
                        file_options={"content-type": "image/jpeg"})

                          # 5. GENERATE THE LINK (p_url)
                        p_url = f"{url}/storage/v1/object/public/client-photos/{file_path}"

                         # 6. SAVE RECORD TO DATABASE
                        with conn.session as s:
                            s.execute(
                            text("""INSERT INTO clients (client_id, client_name, phone, daily_mark, photo_url)
                                VALUES (:i, :n, :p, :d, :u)"""),
                        {"i": gen_id, "n": name.strip(), "p": phone.strip(), "d": daily, "u": p_url})
                        s.commit()
                        st.success(f"✅ Registered {name} successfully! ID: {gen_id}")
                        st.balloons()
                
                    except Exception as e:
                         # This 'except' block is what clears the 11 errors!
                        st.error(f"🚨 Registration Failed: {e}")
    with t2:
        st.subheader("📧 Weekly Business Intelligence Report")
        if st.button("Generate & Send Professional Report"):
            try:
                # 1. Prepare Data Summary
                total_savings = contributions['amount'].sum()
                total_commissions = contributions['fee'].sum()
                client_count = len(clients)
                
                # 2. Build HTML Body
                html_content = f"""
                <html>
                    <body style="font-family: Arial, sans-serif; color: #333;">
                        <div style="background-color: #212529; padding: 20px; text-align: center;">
                            <h1 style="color: #FFD700; margin: 0;">RUCHANET DAILY SUSU</h1>
                            <p style="color: #ffffff;">Weekly Financial Summary</p>
                        </div>
                        <div style="padding: 20px; border: 1px solid #ddd;">
                            <h3>Executive Summary</h3>
                            <table style="width: 100%; border-collapse: collapse;">
                                <tr style="background-color: #f8f9fa;">
                                    <th style="padding: 10px; border: 1px solid #ddd; text-align: left;">Metric</th>
                                    <th style="padding: 10px; border: 1px solid #ddd; text-align: right;">Value</th>
                                </tr>
                                <tr>
                                    <td style="padding: 10px; border: 1px solid #ddd;">Total Vault Balance</td>
                                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right; font-weight: bold;">GHS {total_savings:,.2f}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 10px; border: 1px solid #ddd;">Total Commissions (Fees)</td>
                                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right; color: #28a745;">GHS {total_commissions:,.2f}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 10px; border: 1px solid #ddd;">Active Registered Clients</td>
                                    <td style="padding: 10px; border: 1px solid #ddd; text-align: right;">{client_count}</td>
                                </tr>
                            </table>
                            <p style="margin-top: 20px; font-size: 12px; color: #888;">Report generated on {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
                        </div>
                    </body>
                </html>
                """

                msg = EmailMessage()
                msg['Subject'] = f"📊 RUCHANET Report: {datetime.now().strftime('%d %b %Y')}"
                msg['From'] = st.secrets["emails"]["sender_email"]
                msg['To'] = st.secrets["emails"]["receiver_email"]
                msg.add_alternative(html_content, subtype='html')

                with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                    server.login(st.secrets["emails"]["sender_email"], st.secrets["emails"]["app_password"])
                    server.send_message(msg)
                st.success("✅ Professional report sent to management!")
            except Exception as e:
                st.error(f"Email Error: {e}")
    with t3:
        st.subheader("🛑 Restricted Data Cleanup")
        admin_entry = st.text_input("Enter Admin Password", type="password", key="cleanup_pass")
        
        if admin_entry == st.secrets["passwords"]["admin_password"]:
            if not contributions.empty:
                search_term = st.text_input("Filter by Client Name")
                f_df = contributions[contributions['client_name'].str.contains(search_term, case=False)]
                
                if not f_df.empty:
                    to_del = st.selectbox("Select entry to remove", 
                        options=f_df.apply(lambda x: f"{x['date']} | {x['client_name']} | GHS {x['amount']}", axis=1))
                    
                    if st.button("🗑️ Permanent Delete"):
                        st.session_state['undo_info'] = to_del
                        parts = to_del.split(" | ")
                        with conn.session as s:
                            s.execute(text("DELETE FROM contributions WHERE client_name = :n AND date = :d"),
                                     {"n": parts[1], "d": parts[0]})
                            s.commit()
                        st.success("Deleted. Rerunning...")
                        st.rerun()
            if 'undo_info' in st.session_state:
                if st.button("⏪ Undo Deletion"):
                    u = st.session_state['undo_info'].split(" | ")
                    with conn.session as s:
                        s.execute(text("INSERT INTO contributions (client_name, amount, date) VALUES (:n, :a, :d)"),
                                  {"n": u[1], "a": float(u[2].replace("GHS ", "").replace(",", "")), "d": u[0]})
                        s.commit()
                    del st.session_state['undo_info']
                    st.success("Restored!")
                    st.rerun()
        elif admin_entry != "":
            st.error("❌ Incorrect Admin Password")
    with t4:
     st.subheader("💰 Organization Commission Overview")
    
    report_data = []
    for index, row in clients.iterrows():
        name = row['client_name']
        rate = float(row['daily_mark'])
        
        # Calculate marks and fees
        u_history = contributions[contributions['client_name'] == name]
        total_m = u_history['marks_covered'].sum()
        fees_paid = u_history['fee'].sum()
        
        # Logic: 1 day rate for every 31 marks
        import math
        total_comm_earned = math.ceil(total_m / 31) * rate
        pending_comm = total_comm_earned - fees_paid
        
        report_data.append({
            "Client": name,
            "Rate": rate,
            "Total Marks": total_m,
            "Total Earned": total_comm_earned,
            "Fees Already Paid": fees_paid,
            "Pending Collection": max(0, pending_comm)
        })
    
    comm_df = pd.DataFrame(report_data)
    st.table(comm_df)
    
    total_to_collect = comm_df['Pending Collection'].sum()
    st.metric("Total Commission to Collect on Withdrawal", f"GHS {total_to_collect:,.2f}")