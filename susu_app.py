import streamlit as st
from utils import send_weekly_report
import streamlit.components.v1 as components
import pandas as pd
import sqlite3
import time
import re
import math
from datetime import datetime
from sqlalchemy import text
from supabase import create_client

# --- 1. SETUP ---
st.set_page_config(page_title="RUCHANET DAILY SUSU", layout="wide")

# --- DATABASE CONNECTIONS & SYNC LOGIC ---
conn = st.connection("postgresql", type="sql")
menu = ["📊 Dashboard", "💸 Transactions", "📑 Digital Passbook", "🛠 Admin Tools"]

try:
    sb_client = create_client(st.secrets["supabase_url"], st.secrets["supabase_key"])
except Exception as e:
    st.error(f"Supabase Error: {e}") 
    st.stop()

def sync_data_dual(new_record):
    """Writes to Local SQLite and Cloud PostgreSQL simultaneously."""
    success_local = False
    success_cloud = False
    
    # --- LOCAL SQLITE SYNC ---
    try:
        conn_local = sqlite3.connect('susu_data.db')
        
        # 1. Create table if it doesn't exist at all
        conn_local.execute("""
            CREATE TABLE IF NOT EXISTS contributions 
            (client_id TEXT, client_name TEXT, amount REAL, date TEXT, fee REAL, marks_covered INTEGER)
        """)
        
        # 2. PRO FIX: Instead of a bare except, we check for the specific SQLite error
        try:
            conn_local.execute("ALTER TABLE contributions ADD COLUMN client_id TEXT")
        except sqlite3.OperationalError:
            # This specific error means the column already exists, so we just skip it
            pass
            
        local_df = pd.DataFrame([new_record])
        local_df.to_sql('contributions', conn_local, if_exists='append', index=False)
        conn_local.close()
        success_local = True
    except Exception as e:
        st.error(f"Local Save Error: {e}")

    # --- CLOUD POSTGRES SYNC ---
    try:
        with conn.session as s:
            s.execute(text("""
                INSERT INTO contributions (client_id, client_name, amount, date, marks_covered, fee)
                VALUES (:ci, :cn, :am, :dt, :mk, :fe)
            """), {
                "ci": new_record.get('client_id', 'N/A'),
                "cn": new_record['client_name'],
                "am": float(new_record['amount']),
                "dt": new_record['date'],
                "mk": int(new_record['marks_covered']),
                "fe": float(new_record['fee'])
            })
            s.commit()
        success_cloud = True
    except Exception as e:
        st.error(f"Cloud Sync Error: {e}")
        
    return success_local and success_cloud

    try:
        with conn.session as s:
            s.execute(text("""
                INSERT INTO contributions (client_id, client_name, amount, date, marks_covered, fee)
                VALUES (:ci, :cn, :am, :dt, :mk, :fe)
            """), {
                "ci": new_record.get('client_id', 'N/A'),
                "cn": new_record['client_name'],
                "am": float(new_record['amount']),
                "dt": new_record['date'],
                "mk": int(new_record['marks_covered']),
                "fe": float(new_record['fee'])
            })
            s.commit()
        success_cloud = True
    except Exception as e:
        st.error(f"Cloud Sync Error: {e}")
    return success_local and success_cloud

# --- PWA CONFIGURATION ---
def pwa_support():
    # Everything must be indented inside the function
    components.html("""
        <script>
            if ('serviceWorker' in navigator) {
              window.addEventListener('load', function() {
                navigator.serviceWorker.register('./sw.js').then(reg => {
                  console.log('PWA Registered');
                });
              });
            }
        </script>
    """, height=0)

# CRITICAL: You must call the function for it to run!
pwa_support()

# This line enures 're' is seen as used without causing a syntax warning
re_tool = re.compile(r'.*')

def set_custom_style():
    st.markdown("""
    <style>
    /* 1. Colors & Branding */
    div.stButton > button:first-child { background-color: #FFD700 !important; color: #212529 !important; font-weight: bold !important; border: none !important; }
    [data-testid="stMetricValue"] { color: #FF4500 !important; font-size: 30px !important; }
    [data-testid="stSidebar"] { background-color: #212529 !important; color: #F8F9FA; }
    
    /* 2. FIXED: Hide MainMenu & Deploy button but KEEP Sidebar Toggle */
    #MainMenu {visibility: hidden;}
    header [data-testid="stHeader"] {background-color: rgba(0,0,0,0);} /* Makes header transparent */
    footer {visibility: hidden;}
    
    /* 3. Mobile Tweaks */
    [data-testid="stAppViewContainer"] { padding-top: 2rem; }
    
    /* Ensure the sidebar toggle button is always visible and clickable */
    button[kind="header"] {
        visibility: visible !important;
        color: #FFD700 !important;
    }
    </style>
    
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="theme-color" content="#212529">
    """, unsafe_allow_html=True)
# Run UI Enhancements
set_custom_style()

# --- 0. MAINTENANCE MODE (SECRET CONTROL) ---
# This stops the app immediately if the secret is set to true
if st.secrets["app_settings"]["maintenance_mode"]:
    st.title("🚧 System Maintenance")
    st.warning("RUCHANET DAILY SUSU is currently undergoing scheduled updates.")
    st.info("We'll be back online shortly! 🙏")
    st.stop()

# --- 3. DATA FUNCTIONS ---
@st.cache_data(ttl=60)
def fetch_data():
    try:
        with conn.session as s:
            # We select your custom client_id AND the daily_mark
            clients_df = pd.DataFrame(s.execute(
                text("SELECT client_id, client_name, phone, daily_mark, photo_url FROM clients")
            ).mappings().all())
            
            # For contributions, ensure it has a client_name column to link back
            contributions_df = pd.DataFrame(s.execute(
                text("SELECT id, client_name, amount, date, marks_covered, fee FROM contributions")
            ).mappings().all())
            
            return clients_df, contributions_df
    except Exception as e:
        st.error(f"Mapping Error: {e}")
        return pd.DataFrame(), pd.DataFrame()
# --- 1. THE SECURITY WALL ---
def check_password():
    if "role" not in st.session_state:
        # Hide sidebar on login screen
        st.markdown("<style>[data-testid='stSidebar'] {display: none;}</style>", unsafe_allow_html=True)
        
        st.title("🔐 RUCHANET SYSTEM LOGIN")
        col1, col2 = st.columns(2)
        with col1:
            with st.form("agent_login"):
                st.subheader("👤 Agent Login")
                if st.form_submit_button("Access Collector Tools"):
                    st.session_state["role"] = "Agent"
                    st.rerun()
        with col2:
            with st.form("admin_login"):
                st.subheader("🛡️ Manager Login")
                pwd = st.text_input("Manager Password", type="password")
                if st.form_submit_button("Verify Identity"):
                    if pwd == st.secrets["passwords"]["login_password"]: 
                        st.session_state["role"] = "Manager"
                        st.rerun()
                    else:
                        st.error("Invalid Manager Password")
        
        st.stop() # This is the "Wall" that kills the script for unverified users
    return True

# Run the security check FIRST
check_password()

# --- 2. THE SECURE APP (Everything below only runs AFTER login) ---

# Fetch data only after we are sure someone is logged in
clients, contributions = fetch_data()

with st.sidebar:
    st.title("📱 RUCHANET APP")
    st.success(f"Logged in as: {st.session_state['role']}")
    
    # LOGOUT BUTTON
    if st.button("🚪 Logout / Sign Out", use_container_width=True):
        del st.session_state["role"]
        st.cache_data.clear()
        st.rerun()
    
    st.divider()
    # DYNAMIC MENU
    if st.session_state["role"] == "Manager":
        menu = ["📊 Dashboard", "💸 Transactions", "📑 Digital Passbook", "🛠 Admin Tools"]
    else:
        menu = ["💸 Transactions", "📑 Digital Passbook"]    
def draw_sidebar_log(df):
        st.divider()
        with st.expander("🕒 Quick Activity Log", expanded=False):
            if not df.empty:
                st.dataframe(df.tail(5).sort_values(by='date', ascending=False), column_order=("client_name", "amount"), hide_index=True)
            else:
                st.info("No activity yet.")

def get_next_gen_id(reg_date):
    # Format month and year: e.g., "03/26"
    mm_yy = reg_date.strftime("%m/%y")
    
    try:
        with conn.session as s:
            # IMPROVED: We fetch all IDs for the month and handle the "highest" logic in Python
            # to avoid SQL text-sorting errors (where '9' > '10')
            result = s.execute(text("""
                SELECT client_id FROM clients 
                WHERE client_id LIKE :pattern
            """), {"pattern": f"%/{mm_yy}"}).fetchall()
            
            if result:
                # Extract the numeric part of each ID: e.g., "005" from "005/03/26"
                nums = []
                for row in result:
                    try:
                        nums.append(int(row[0].split('/')[0]))
                    except (ValueError, IndexError):
                        continue
                
                if nums:
                    new_num = max(nums) + 1
                else:
                    new_num = 1
            else:
                # First client of the month
                new_num = 1
                
            # Return formatted as 3 digits: "001/03/26"
            return f"{new_num:03d}/{mm_yy}"
            
    except Exception as e:
        st.error(f"⚠️ ID Generation Error: {e}") 
        # Fallback to 001 if something goes wrong
        return f"001/{mm_yy}"

# Initialize combined_df as empty or just contributions to start
combined_df = pd.DataFrame()

if not clients.empty:
    if not contributions.empty:
        # Check if 'client_name' exists in both dataframes
        if 'client_name' in clients.columns and 'client_name' in contributions.columns:
            try:
                combined_df = pd.merge(
                    contributions, 
                    clients[['client_id', 'client_name']], 
                    on='client_name', 
                    how='left'
                )
            except Exception as e:
                st.error(f"Merge Error: {e}")
                combined_df = contributions
        else:
            st.warning("⚠️ Database Mismatch: Ensure 'client_name' exists in both tables.")
            combined_df = contributions
    else:
        # If no contributions yet, combined_df is just empty
        combined_df = pd.DataFrame()
else:
    # If no clients yet, we can't merge anything
    combined_df = contributions

    # --- 5.5 COMPACT SYSTEM STATUS BAR ---
with st.container():
    # 1. Prepare Data Safely
    c_num = len(clients) if 'clients' in locals() and not clients.empty else 0
    t_num = len(contributions) if 'contributions' in locals() and not contributions.empty else 0
    
    if 'contributions' in locals() and not contributions.empty and 'amount' in contributions.columns:
        v_sum = contributions['amount'].sum()
    else:
        v_sum = 0.0

# --- SMART AUTO-REPORT TRIGGER ---
now = datetime.now()
# 6 = Sunday, and hour >= 8 means 8 AM or later
if now.weekday() == 6 and now.hour >= 8: 
    # Use the date string as a key so it only sends ONCE per Sunday
    backup_key = f"sent_{now.strftime('%Y-%m-%d')}"
    if backup_key not in st.session_state:
        if send_weekly_report(contributions, manual=False):
            st.session_state[backup_key] = True
            st.toast(f"📧 Sunday Report Sent at {now.strftime('%I:%M %p')}", icon="📅")

# --- 6. CONSOLIDATED SIDEBAR UI ---
with st.sidebar:
    st.title("📱 App Options")
    
    # 1. NAVIGATION (At the very top)
    choice = st.selectbox("Go To:", menu)
    
    st.divider()

    # 2. COMBINED INSTALL GUIDE (Only ONE instance here to prevent errors)
    if st.checkbox("Show Install Guide", key="unique_install_check_123"):
        st.info("""
        **To Install on Phone:**
        * *Android:* Tap ⋮ and 'Install App'.
        * *iOS:* Tap Share 📤 and 'Add to Home Screen'.
        """)
    
    st.divider()

    # 3. NETWORK & SCHEMA HEALTH CHECK
    try:
        # Check if we can connect to the database
        conn.session.execute(text("SELECT 1"))
        db_status = "🟢 Online"
    except Exception:
        db_status = "🔴 Offline"

    # Check for the 'client_name' column to prevent the red error box
    schema_status = "✅ Sync OK"
    if 'clients' in locals() and not clients.empty:
        if 'client_name' not in clients.columns:
            schema_status = "⚠️ Schema Error"
    
    # Display Status as a clean "Status Bar"
    st.markdown(f"""
    <div style="background-color: #343a40; padding: 10px; border-radius: 5px; border-left: 5px solid #FFD700;">
        <p style="margin:0; font-size: 12px; color: #adb5bd;">SYSTEM STATUS</p>
        <p style="margin:0; font-weight: bold;">Cloud: {db_status} | {schema_status}</p>
    </div>
    """, unsafe_allow_html=True)

    # 4. RECENT ACTIVITY LOG
    st.divider()
    draw_sidebar_log(contributions)
    
    # DELETE THE EXTRA CHECKBOX THAT WAS HERE!
    
    st.divider()

if choice == "📊 Dashboard":
    # --- 2. THE MAIN TABLE (FIXED) ---
    # We put this HERE so it ONLY shows on the Dashboard page!
    if not combined_df.empty:
        st.write("### 📋 Recent Transaction Table")
        st.dataframe(combined_df, use_container_width=True)
    
    st.divider()

    # --- 3. MAIN DASHBOARD UI ---
    head_col, btn_col = st.columns([4, 1])
    with head_col:
        st.title("📊 Financial Overview")
    with btn_col:
        if st.button("🔄 Sync"):
            st.cache_data.clear()
            st.rerun()

    # Key Metrics Logic
    m1, m2, m3, m4 = st.columns(4)
    total_client_count = len(clients) if not clients.empty else 0
    m1.metric("👥 Total Clients", f"{total_client_count}")

    if not contributions.empty:
        df_display = contributions.copy()
        df_display['date_dt'] = pd.to_datetime(df_display['date'], errors='coerce', utc=True)
        df_display = df_display.dropna(subset=['date_dt'])
        
        total_vault = df_display['amount'].sum()
        total_commissions = df_display['fee'].sum()
        net_liability = total_vault - total_commissions
        
        today_date = datetime.now().date()
        yesterday_date = today_date - pd.Timedelta(days=1)
        
        today_total = df_display[df_display['date_dt'].dt.date == today_date]['amount'].sum()
        yesterday_total = df_display[df_display['date_dt'].dt.date == yesterday_date]['amount'].sum()
        daily_diff = today_total - yesterday_total

        m2.metric("💰 Total Vault", f"GHS {total_vault:,.2f}", delta=f"GHS {today_total:,.2f} Today")
        m3.metric("📈 Commissions", f"GHS {total_commissions:,.2f}")
        m4.metric("📉 Net Liability", f"GHS {net_liability:,.2f}", delta=f"Diff: GHS {daily_diff:,.2f}", delta_color="inverse")

        # --- 4. MONTHLY PROFIT CHART ---
        st.divider()
        st.subheader("📈 Monthly Commission Growth")
        
        df_display['Month'] = df_display['date_dt'].dt.strftime('%b %Y')
        monthly_profit = df_display.groupby('Month')['fee'].sum().reset_index()
        monthly_profit['sort_date'] = pd.to_datetime(monthly_profit['Month'])
        monthly_profit = monthly_profit.sort_values('sort_date')

        st.bar_chart(data=monthly_profit, x='Month', y='fee', color="#FFD700")

        # --- 5. DATA EXPORT ---
        with st.expander("📥 Download Records"):
            csv = contributions.to_csv(index=False).encode('utf-8')
            st.download_button("Download CSV", data=csv, file_name="susu_records.csv", mime="text/csv")
        
    else:
        m2.metric("💰 Total Vault", "GHS 0.00")
        m3.metric("📈 Commissions", "GHS 0.00")
        m4.metric("📉 Net Liability", "GHS 0.00")
        st.info("💡 Start recording transactions to see financial data.")
        # --- 3.5 MATURITY & PAYOUT ALERTS ---
    st.divider()
    st.subheader("🎯 Payout Readiness (31+ Marks)")
    
    if not contributions.empty:
        # Calculate total marks per client
        marks_summary = contributions.groupby('client_name')['marks_covered'].sum().reset_index()
        # Identify clients ready for payout (Multiples of 31)
        ready_clients = marks_summary[marks_summary['marks_covered'] >= 31]
        
        if not ready_clients.empty:
            for _, row in ready_clients.iterrows():
                cycles = int(row['marks_covered'] // 31)
                st.success(f"🌟 *{row['client_name']}* has completed *{cycles} cycle(s)* ({row['marks_covered']} total marks).")
        else:
            st.info("No clients have reached the 31-mark maturity goal yet.")
    else:
        st.info("No transaction data available to calculate maturity.")

elif choice == "💸 Transactions":
    st.title("💸 Record Transactions")
    
    if not clients.empty:
        # 1. Selection UI
        col_search, col_mode = st.columns([2, 1])
        with col_search:
            client_list = clients['client_name'].tolist()
            target = st.selectbox("Select Client", client_list)
        with col_mode:
            is_migration = st.checkbox("📂 Migration Mode")

        client_row = clients[clients['client_name'] == target].iloc[0]
        d_mark = float(client_row.get('daily_mark', 0.0))
        c_id = client_row.get('client_id', 'N/A')
        
        # --- DATA RETRIEVAL ---
        user_history = contributions[contributions['client_name'] == target] if not contributions.empty else pd.DataFrame()
        total_saved_ghs = float(user_history['amount'].sum()) if not user_history.empty else 0.0
        total_marks_saved = int(user_history['marks_covered'].sum()) if not user_history.empty else 0
        
        st.write(f"🆔 **ID:** {c_id} | 💰 **Balance:** GHS {total_saved_ghs:,.2f} | 📅 **Total Marks:** {total_marks_saved}")
        st.divider()

        # --- 2. INITIALIZE VARIABLES (Prevents NameError) ---
        ttype = st.radio("Transaction Type", ["Deposit", "Withdrawal"], horizontal=True)
        requested_cash = 0.0
        db_amt = 0.0
        db_marks = 0
        db_fee = 0.0

        if ttype == "Deposit":
            num_marks = st.number_input("Marks to add", min_value=1, step=1)
            db_amt = float(num_marks * d_mark)
            db_marks = int(num_marks)
            st.info(f"➕ **Deposit:** GHS {db_amt:,.2f}")
            
        else: # --- WITHDRAWAL LOGIC ---
            w_method = st.selectbox("Withdrawal Method", ["Full Payout (Include Commission)", "Advance Payment (No Commission Now)"])
            
            # Helper for the Agent
            if d_mark > 0:
                # Tell them the absolute max they can take if they pay commission now
                est_comm_marks = math.ceil(total_marks_saved / 32)
                max_cash_possible = float((total_marks_saved - est_comm_marks) * d_mark)
                st.success(f"💡 Max Cash (with Commission): GHS {max_cash_possible:,.2f}")

            requested_cash = st.number_input("Cash Amount (GHS)", min_value=0.0, step=d_mark)
            
            if d_mark > 0:
                marks_for_cash = int(requested_cash / d_mark)
                
                # --- CALCULATE ACTUAL DB VALUES ---
                if w_method == "Full Payout (Include Commission)":
                    num_commissions = math.ceil(marks_for_cash / 31)
                    db_fee = float(num_commissions * d_mark)
                    db_marks = -(marks_for_cash + num_commissions)
                else:
                    # Advance Payment: 0 fee now, but we check if they HAVE it
                    db_fee = 0.0
                    db_marks = -marks_for_cash
                
                db_amt = -float(requested_cash + db_fee)

                # --- THE BOUNCER CHECK (The Shadow Commission) ---
                # We calculate what the fee WOULD be (1 mark for every 31)
                shadow_fee_marks = math.ceil(marks_for_cash / 31)
                total_marks_needed_to_be_safe = marks_for_cash + shadow_fee_marks
                
                if requested_cash > 0:
                    # BLOCK if they don't have enough marks to cover cash + the "shadow" fee
                    if total_marks_saved < total_marks_needed_to_be_safe:
                        st.error("🚫 **Insufficient Reserved Marks.**")
                        st.write(f"To take GHS {requested_cash:,.2f}, the client needs **{total_marks_needed_to_be_safe} marks** "
                                 f"(Cash: {marks_for_cash} + Commission: {shadow_fee_marks}).")
                        st.write(f"Current Balance: **{total_marks_saved} marks**.")
                        st.stop()
                    
                    # BLOCK if they don't have the actual cash balance (for migrations/over-withdrawals)
                    if abs(db_amt) > (total_saved_ghs + 0.01) and not is_migration:
                        st.error(f"⚠️ **Insufficient Cash Balance.** Balance: GHS {total_saved_ghs:,.2f}")
                        st.stop()
                    
                    # UI Final Confirmation
                    if w_method == "Advance Payment (No Commission Now)":
                        st.warning(f"ℹ️ **Advance Mode**: Deducting {marks_for_cash} marks. "
                                   f"{shadow_fee_marks} marks are reserved in the account for future commission.")
                    else:
                        st.warning(f"📉 **Full Payout**: Total Deduction GHS {abs(db_amt):,.2f} (Fee: {db_fee})")

        # --- 3. SYNC & RECEIPT ---
        if st.button("🚀 Confirm & Sync Transaction"):
            new_entry = {
                'client_id': str(c_id),
                'client_name': target,
                'amount': float(db_amt),
                'date': datetime.now().isoformat(),
                'fee': float(db_fee),
                'marks_covered': int(db_marks)
            }

            if sync_data_dual(new_entry):
                st.success("✅ Transaction Saved!")
                
                # Digital Receipt for Thermal Printer
                receipt_html = f"""
                <div style="font-family:monospace; width:260px; padding:10px; border:1px solid #000; background:white; color:black;">
                    <center><h3 style="margin:0;">RUCHANET SUSU</h3></center>
                    <hr>
                    <b>Date:</b> {datetime.now().strftime('%Y-%m-%d %H:%M')}<br>
                    <b>Client:</b> {target}<br>
                    <b>ID:</b> {c_id}<br>
                    ---------------------------<br>
                    <b>Amount:</b> GHS {abs(float(requested_cash if ttype == 'Withdrawal' else db_amt)):,.2f}<br>
                    <b>Fee:</b> GHS {db_fee:,.2f}<br>
                    <b>Marks:</b> {db_marks}<br>
                    ---------------------------<br>
                    <b>New Balance:</b> GHS {total_saved_ghs + db_amt:,.2f}
                </div>
                <button onclick="window.print()" style="width:100%; padding:10px; margin-top:5px; background:#FFD700; border:none; font-weight:bold; cursor:pointer;">🖨️ Print Receipt</button>
                """
                components.html(receipt_html, height=400)
                st.balloons()
                time.sleep(1)
    else:
        st.warning("Please register clients first.")                 

elif choice == "📑 Digital Passbook":
    st.title("📑 Client Passbook")
    
    search = st.text_input("🔍 Search Client Name", placeholder="Enter name...")
    
    if not clients.empty:
        # Filter based on search input
        filtered = clients[clients['client_name'].str.contains(search, case=False)] if search else clients
        
        if not filtered.empty:
            target = st.selectbox("View Passbook For:", filtered['client_name'].tolist())
            c_info = clients[clients['client_name'] == target].iloc[0]
            
            # --- AGGREGATE DATA ---
            user_history = pd.DataFrame()
            if not contributions.empty and 'client_name' in contributions.columns:
                user_history = contributions[contributions['client_name'] == target].copy()
                total_marks = int(user_history['marks_covered'].sum())
                current_balance = float(user_history['amount'].sum())
                user_history = user_history.sort_values(by='date', ascending=False)
            else:
                total_marks = 0
                current_balance = 0.0
            
            # --- UI PROFILE DISPLAY ---
            col_a, col_b = st.columns([1, 2])
            with col_a:
                photo = c_info.get('photo_url')
                if photo and str(photo) not in ['None', 'nan', '']:
                    st.image(photo, use_container_width=True)
            
            with col_b:
                st.subheader(f"User: {target}")
                st.write(f"🆔 **ID:** {c_info.get('client_id', 'N/A')}")
                st.write(f"📞 **Phone:** {c_info.get('phone', 'N/A')}")
                
                # METRICS ROW: Including the missing Daily Rate
                m1, m2, m3 = st.columns(3)
                m1.metric("💰 Balance", f"GHS {current_balance:,.2f}")
                m2.metric("📅 Total Marks", f"{total_marks}")
                m3.metric("💳 Daily Rate", f"GHS {c_info.get('daily_mark', 0.0):,.2f}")

            st.divider()
            
            # --- TRANSACTION HISTORY & RECEIPT GENERATOR ---
            st.subheader("📜 Recent Activity")
            if not user_history.empty:
                for idx, row in user_history.iterrows():
                    t_date = pd.to_datetime(row['date']).strftime('%Y-%m-%d %H:%M')
                    t_amt = float(row['amount'])
                    t_type = "Deposit" if t_amt > 0 else "Withdrawal"
                    
                    with st.expander(f"{t_date} | {t_type} | GHS {abs(t_amt):,.2f}"):
                        col_text, col_print = st.columns([2, 1])
                        
                        with col_text:
                            st.write(f"**Amount:** GHS {abs(t_amt):,.2f}")
                            st.write(f"**Marks:** {row['marks_covered']}")
                            st.write(f"**Commission/Fee:** GHS {row.get('fee', 0.0):,.2f}")

                        with col_print:
                            # THERMAL RECEIPT (Includes Daily Rate for transparency)
                            receipt_html = f"""
                            <div id="receipt-{idx}" style="font-family: 'Courier New', monospace; width: 280px; padding: 10px; background: white; color: black; border: 1px solid #000;">
                                <center>
                                    <h4 style="margin:0;">RUCHANET DAILY SUSU</h4>
                                    <p style="font-size:10px;">Transaction Record</p>
                                </center>
                                <hr>
                                <p style="font-size:12px;">
                                    <b>Date:</b> {t_date}<br>
                                    <b>Client:</b> {target}<br>
                                    <b>ID:</b> {c_info.get('client_id')}<br>
                                    <b>Daily Rate:</b> GHS {c_info.get('daily_mark', 0.0):,.2f}<br>
                                    <b>Type:</b> {t_type}<br>
                                    ----------------------------<br>
                                    <b>Amount:</b> GHS {abs(t_amt):,.2f}<br>
                                    <b>Fee:</b> GHS {row.get('fee', 0.0):,.2f}<br>
                                    <b>Marks:</b> {row['marks_covered']}<br>
                                    ----------------------------<br>
                                    <b>Verified Digital Record</b>
                                </p>
                            </div>
                            <button onclick="printDiv('receipt-{idx}')" style="width:100%; padding:10px; margin-top:5px; background:#FFD700; border:none; font-weight:bold; cursor:pointer;">🖨️ Print Receipt</button>
                            
                            <script>
                            function printDiv(divId) {{
                                var printContents = document.getElementById(divId).innerHTML;
                                var originalContents = document.body.innerHTML;
                                var printWindow = window.open('', '', 'height=500,width=400');
                                printWindow.document.write('<html><head><title>Print Receipt</title></head><body>');
                                printWindow.document.write(printContents);
                                printWindow.document.write('</body></html>');
                                printWindow.document.close();
                                printWindow.print();
                            }}
                            </script>
                            """
                            components.html(receipt_html, height=380)
            else:
                st.info("No transaction history found.")
        else:
            st.warning("No client found.")
    else:
        st.warning("Please register clients first.")

# --- 3. ADMIN TOOLS & EMAIL ---
elif choice == "🛠 Admin Tools":
    st.title("🛠 Admin Dashboard")
    
    # Initialize tabs
    t1, t2, t3, t4, t5 = st.tabs(["👤 Registration", "📧 Reports", "🗑 Data Cleanup", "💰 Manage Profile", "🧨 Reset System"])
    
    # --- TAB 1: REGISTRATION ---
    with t1:
        st.subheader("👤 Register New Client")
        photo = st.camera_input("Take Client Photo (Required)")
    
        with st.form("reg_form", clear_on_submit=True):
            name = st.text_input("Full Name")
            phone = st.text_input("Phone Number")
            daily = st.number_input("Daily Mark (GHS)", min_value=5.0, step=1.0)
            reg_date = st.date_input("Registration Date", value=datetime.now())
            
            suggested_id = get_next_gen_id(reg_date)
            manual_id = st.text_input("Confirm Client ID", value=suggested_id, help="Format: Number/MM/YY")
            
            submit = st.form_submit_button("Register to Cloud")
            
            if submit: 
                if not name.strip() or not phone.strip() or photo is None:
                    st.error("❌ Name, Phone, and Photo are all required.")
                else:
                    try:
                        final_id = manual_id.strip() if manual_id.strip() else suggested_id
                        safe_filename = f"{final_id.replace('/', '-')}.jpg"
                        
                        sb_client.storage.from_("client-photos").upload(
                            path=safe_filename,
                            file=photo.getvalue(),
                            file_options={"content-type": "image/jpeg", "upsert": "true"}
                        )

                        base_url = st.secrets['supabase_url']
                        p_url = f"{base_url}/storage/v1/object/public/client-photos/{safe_filename}"

                        with conn.session as s:
                            s.execute(text("""
                                INSERT INTO clients (client_id, client_name, phone, daily_mark, photo_url)
                                VALUES (:i, :n, :p, :d, :u)
                            """), {
                                "i": final_id, "n": name.strip(), "p": phone.strip(), "d": daily, "u": p_url
                            })
                            s.commit()
                        
                        st.success(f"✅ Registered {name} with ID: {final_id}")
                        st.balloons()
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"🚨 Registration Failed: {e}")

    # --- TAB 2: REPORTS ---
    with t2:
        st.subheader("📊 Weekly Executive Intelligence")
        if not contributions.empty:
            contributions['date'] = pd.to_datetime(contributions['date'], errors='coerce')
            st.info(f"💾 System ready: {len(contributions)} records scanned.")
            
            if st.button("🚀 Force Send Comprehensive Weekly Report"):
                with st.spinner("📧 Sending report..."):
                    if send_weekly_report(contributions, manual=True):
                        st.success("✅ Manual Report Sent!")
                    else:
                        st.error("❌ Failed to send. Check settings.")
        else:
            st.warning("⚠️ No data found to report on.")

    # --- TAB 3: DATA CLEANUP (REVERSALS) ---
    with t3:
        st.subheader("🧹 Database Health & Reversals")
        admin_entry = st.text_input("Enter Admin Password", type="password", key="cleanup_pass")

        if admin_entry == st.secrets["passwords"]["admin_password"]:
            if not contributions.empty:
                search_term = st.text_input("🔍 Filter by Client Name", key="cleanup_filter")
                f_df = contributions[contributions['client_name'].str.contains(search_term, case=False)].copy()
                
                if not f_df.empty:
                    f_df['display'] = f_df.apply(lambda x: f"ID:{x['id']} | {x['date']} | {x['client_name']} | GHS {x['amount']}", axis=1)
                    to_del = st.selectbox("Select entry to REVERSE", options=f_df['display'], key="reversal_selector")
                    
                    if st.button("🔄 Authorize Professional Reversal"):
                        try:
                            selected_id = int(to_del.split(" | ")[0].replace("ID:", ""))
                            target_row = f_df[f_df['id'] == selected_id].iloc[0]

                            reversal_entry = {
                                'amount': -float(target_row['amount']),
                                'client_name': target_row['client_name'],
                                'date': datetime.now().isoformat(),
                                'fee': -float(target_row.get('fee', 0.0)),
                                'marks_covered': -int(target_row['marks_covered']),
                                'client_id': str(target_row.get('client_id', 'N/A'))
                            }

                            if sync_data_dual(reversal_entry):
                                with conn.session as s:
                                    s.execute(text("""
                                        INSERT INTO audit_logs (action_type, details, admin_name) 
                                        VALUES ('REVERSAL', :d, 'Manager')
                                    """), {"d": f"Reversed ID {selected_id} for {target_row['client_name']}"})
                                    s.commit()
                                
                                st.success("✅ Reversal Synced!")
                                st.cache_data.clear()
                                time.sleep(1)
                                st.rerun()
                        except Exception as e:
                            st.error(f"🚨 Reversal Failed: {e}")
                else:
                    st.info("No matching entries found.")
            else:
                st.info("The contributions database is empty.")

    # --- TAB 4: MANAGE PROFILE (THE FIX) ---
    with t4:
        st.subheader("⚙️ Secure Client Profile Manager")
        st.error("❗ Deletion removes the client and photo permanently.")

        if 'clients' in locals() and not clients.empty:
            search_query = st.text_input("🔍 Search Profile (Name or ID)", key="admin_manage_search")
            
            # Ensure the search logic is inside the 'if clients' block
            filtered = clients[
                clients['client_name'].str.contains(search_query, case=False) | 
                clients['client_id'].astype(str).str.contains(search_query, case=False)
            ]

            if not filtered.empty:
                selected_name = st.selectbox("Select Profile:", filtered['client_name'])
                c_data = filtered[filtered['client_name'] == selected_name].iloc[0]
                target_id = str(c_data['client_id']) 
                
                final_balance = 0.0
                if 'contributions' in locals() and not contributions.empty:
                    u_history = contributions[contributions['client_name'] == selected_name]
                    final_balance = float(u_history['amount'].sum()) if not u_history.empty else 0.0

                col1, col2 = st.columns([1, 2])
                with col1:
                    photo_url = c_data.get('photo_url')
                    if photo_url and str(photo_url) not in ['None', 'nan', '']:
                        st.image(photo_url, caption=f"ID: {target_id}", use_container_width=True)
                with col2:
                    st.write(f"**Name:** {c_data['client_name']}")
                    st.metric("💰 Payout Due", f"GHS {final_balance:,.2f}")

                st.divider()
                confirm_check = st.checkbox(f"⚠️ Confirm wipe for {selected_name}", key="del_check")
                
                if confirm_check:
                    wipe_pass = st.text_input("🔐 Admin Password", type="password", key="wipe_pass_input")
                    if st.button("💥 AUTHORIZE PERMANENT WIPE"):
                        if wipe_pass == st.secrets["passwords"]["admin_password"]:
                            try:
                                with st.spinner("Wiping..."):
                                    try:
                                        safe_file = target_id.replace('/', '-')
                                        sb_client.storage.from_("client-photos").remove([f"{safe_file}.jpg"])
                                    except Exception: 
                                        pass 

                                    with conn.session as s:
                                        s.execute(text("DELETE FROM contributions WHERE client_name = :n"), {"n": selected_name})
                                        s.execute(text("DELETE FROM clients WHERE client_id = :i"), {"i": target_id})
                                        s.commit()
                                st.success("🗑️ Erased successfully.")
                                st.cache_data.clear()
                                time.sleep(1.5)
                                st.rerun()
                            except Exception as e:
                                st.error(f"🚨 Wipe Failed: {e}")
            else:
                st.info("No matching profiles.")
        else:
            st.info("Database empty.")

    # --- TAB 5: RESET SYSTEM ---
    with t5:
        st.header("🧨 Factory Reset")
        confirm_reset = st.checkbox("I want to delete EVERYTHING.", key="wipe_confirm_check")
        
        if st.button("EXECUTE FULL RESET", type="primary", disabled=not confirm_reset):
            try:
                with conn.session as s:
                    s.execute(text("TRUNCATE TABLE contributions RESTART IDENTITY CASCADE;"))
                    s.execute(text("TRUNCATE TABLE clients RESTART IDENTITY CASCADE;"))
                    s.execute(text("TRUNCATE TABLE audit_logs RESTART IDENTITY CASCADE;"))
                    s.commit()
                st.success("💥 System wiped!")
                st.cache_data.clear()
                time.sleep(1.5)
                st.rerun()
            except Exception as e:
                st.error(f"Reset failed: {e}")