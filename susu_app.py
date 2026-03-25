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
    
clients_df, contributions_df = fetch_data()

# --- SAFETY CHECK FOR DROPDOWNS ---
if not clients_df.empty:
    client_names = clients_df['name'].unique().tolist()
else:
    client_names = []

# --- SAFETY CHECK FOR DROPDOWNS ---
if not clients_df.empty:
    client_names = clients_df['name'].unique().tolist()
else:
    client_names = []

def get_next_gen_id(month_year):
    try:
        with conn.session as s:
            # We look for the maximum ID that matches the current month pattern
            query = text("SELECT client_id FROM clients WHERE client_id LIKE :pattern")
            result = s.execute(query, {"pattern": f"%/{month_year}"}).fetchall()

            if not result:
                return f"001/{month_year}"

            # Extract the numeric parts and find the max
            # This handles cases like ['001/0326', '002/0326']
            numeric_parts = [int(row[0].split('/')[0]) for row in result]
            next_number = max(numeric_parts) + 1
            
            # Return the new ID padded with zeros (e.g., 005/0326)
            return f"{str(next_number).zfill(3)}/{month_year}"

    except Exception as e:
        # Instead of just returning 001, we log the error so we know something is wrong
        st.error(f"Error generating ID: {e}")
        # Return None or raise the error so the app doesn't save a duplicate 001
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
        combined_df = pd.merge(
            contributions, 
            clients[['client_id', 'client_name']], 
            on='client_id', 
            how='left'
        )
    except Exception as e:
        st.warning(f"Merge error: {e}")
        combined_df = contributions
else:
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
    # ... (Your Transactions code is fine) ...
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

elif choice == "📑 Digital Passbook":
    # ... (Your Passbook code is fine) ...
    st.title("📑 Client Passbook")
    search = st.text_input("🔍 Search Client Name", placeholder="Enter name to filter...")
    if not clients.empty:
        filtered = clients[clients['client_name'].str.contains(search, case=False)] if search else clients
        if not filtered.empty:
            target = st.selectbox("View Passbook For:", filtered['client_name'].tolist())
            c_info = clients[clients['client_name'] == target].iloc[0]
            col_a, col_b = st.columns([1, 2])
            with col_a:
                photo_url = c_info.get('photo_url')
                if photo_url and str(photo_url).strip().lower() != "none":
                    st.image(photo_url, width=230, caption=f"ID: {c_info['client_id']}")
                else:
                    st.info("👤 No photo uploaded.")
            with col_b:
                user_history = contributions[contributions['client_name'] == target]
                current_balance = user_history['amount'].sum() if not user_history.empty else 0.0
                st.subheader(f"Account: {target}")
                st.metric("Current Savings Balance", f"GHS {current_balance:,.2f}")
                st.write(f"📞 Phone: {c_info['phone']}")
                st.write(f"💰 Daily Rate: GHS {c_info['daily_mark']:.2f}")
            st.divider()
            if not user_history.empty:
                display_df = user_history.sort_values(by='date', ascending=False).copy()
                st.dataframe(display_df[['date', 'amount', 'marks_covered', 'fee']], use_container_width=True)
    else:
        st.error("No clients registered.")

elif choice == "🛠 Admin Tools":
    st.title("🛠 Admin Dashboard")
    t1, t2, t3 = st.tabs(["👤 Registration", "📧 Reports", "🗑 Data Cleanup"])
    
    with t1:
     st.subheader("👤 Register New Client")
     # 1. Capture Photo
     photo = st.camera_input("Take Client Photo (Required)")
    with st.form("reg_form", clear_on_submit=True):
        name = st.text_input("Full Name")
        phone = st.text_input("Phone Number")
        daily = st.number_input("Daily Mark (GHS)", min_value=1.0, step=1.0)
        submit = st.form_submit_button("Register to Cloud")
        
        if submit:
            if not name.strip() or not phone.strip() or photo is None:
              st.error("❌ All fields (Name, Phone, and Photo) are required")
            else:
                try:
                    # 2. GENERATE ID
                    gen_id = get_next_gen_id()

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
        st.subheader("Weekly Email Report")
    if st.button("📧 Send Report"):
        try:
                msg = EmailMessage()
                msg['Subject'] = "Susu Weekly Update"
                msg['From'] = st.secrets["emails"]["sender_email"]
                msg['To'] = st.secrets["emails"]["receiver_email"]
                
                html_content = f"<h2>RUCHANET DAILY SUSU</h2><p>Report Date: {datetime.now()}</p>"
                msg.add_alternative(html_content, subtype='html')

                with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                    server.login(st.secrets["emails"]["sender_email"], st.secrets["emails"]["app_password"])
                    server.send_message(msg)
                st.success("✅ Report sent!")
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