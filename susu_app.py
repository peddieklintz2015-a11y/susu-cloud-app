import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import sqlite3
import time
import re
import math
import smtplib
from datetime import datetime
from sqlalchemy import text
from email.message import EmailMessage
from supabase import create_client

# --- 1. SETUP ---
st.set_page_config(page_title="RUCHANET DAILY SUSU", layout="wide")

# --- UPDATED SYNC LOGIC ---
def sync_data_dual(new_record):
    """Writes to Local SQLite and Cloud PostgreSQL simultaneously with standardized dates."""
    success_local = False
    success_cloud = False
    
    # 1. LOCAL STORAGE (SQLite)
    try:
        conn_local = sqlite3.connect('susu_data.db')
        conn_local.execute("""
            CREATE TABLE IF NOT EXISTS contributions 
            (client_name TEXT, amount REAL, date TEXT, fee REAL, marks_covered INTEGER)
        """)
        
        # Standardize record for SQLite
        local_df = pd.DataFrame([new_record])
        if 'id' in local_df.columns:
            local_df = local_df.drop(columns=['id'])
            
        local_df.to_sql('contributions', conn_local, if_exists='append', index=False)
        conn_local.close()
        success_local = True
    except Exception as e:
        st.error(f"Local Save Error: {e}")

    # 2. CLOUD STORAGE (PostgreSQL)
    try:
        with conn.session as s:
            s.execute(text("""
                INSERT INTO contributions (client_name, amount, date, marks_covered, fee)
                VALUES (:cn, :am, :dt, :mk, :fe)
            """), {
                "cn": new_record['client_name'],
                "am": float(new_record['amount']),
                "dt": new_record['date'], # Already ISO string from the button logic
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

# --- 4. DATABASE CONNECTIONS ---
conn = st.connection("postgresql", type="sql")
try:
    sb_client = create_client(st.secrets["supabase_url"], st.secrets["supabase_key"])
except Exception as e:
    st.error(f"Supabase Error: {e}") 
    st.stop()

# --- 6. NAVIGATION & INSTALL GUIDE ---
with st.sidebar:
    st.title("📱 App Options")
    
    # Combined Install Guide
    if st.checkbox("Show Install Guide"):
        st.info("""
        *To Install on Phone:*
        * *Android:* Tap ⋮ and 'Install App'.
        * *iOS:* Tap Share 📤 and 'Add to Home Screen'.
        """)
    
    st.divider()

menu = ["📊 Dashboard", "💸 Transactions", "📑 Digital Passbook", "🛠 Admin Tools"]

set_custom_style()

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

def send_weekly_report(contributions_df, manual=False):
    try:
        now_dt = datetime.now()
        today = now_dt.date()
        start_of_week = today - pd.Timedelta(days=today.weekday())
        end_of_week = start_of_week + pd.Timedelta(days=6)
        
        week_data = contributions_df[
            (contributions_df['date'].dt.date >= start_of_week) & 
            (contributions_df['date'].dt.date <= end_of_week)
        ].copy()
        
        if week_data.empty and not manual:
            return False 

        week_data['Day'] = week_data['date'].dt.strftime('%A')
        day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        summary = week_data.groupby('Day').agg({
            'amount': [lambda x: x[x > 0].sum(), lambda x: abs(x[x < 0].sum())],
            'fee': 'sum'
        }).reindex(day_order).fillna(0)
        summary.columns = ['Deposits', 'Withdrawals', 'Commissions']

        table_rows = ""
        for day, row in summary.iterrows():
            bg_color = "#f9f9f9" if day in ['Saturday', 'Sunday'] else "#ffffff"
            table_rows += f"""
            <tr style="background-color: {bg_color}; border-bottom: 1px solid #eee;">
                <td style="padding: 10px;"><b>{day}</b></td>
                <td style="padding: 10px; text-align: right;">{row['Deposits']:,.2f}</td>
                <td style="padding: 10px; text-align: right;">{row['Withdrawals']:,.2f}</td>
                <td style="padding: 10px; text-align: right; color: #27ae60;">{row['Commissions']:,.2f}</td>
            </tr>"""

        total_vault = contributions_df['amount'].sum()
        weekly_commissions = summary['Commissions'].sum()

        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; color: #333;">
                <div style="background-color: #212529; padding: 25px; text-align: center; border-radius: 8px 8px 0 0;">
                    <h1 style="color: #FFD700; margin: 0;">RUCHANET WEEKLY SUMMARY</h1>
                    <p style="color: #fff; margin: 5px 0 0 0;">Week: {start_of_week.strftime('%d %b')} - {end_of_week.strftime('%d %b, %Y')}</p>
                </div>
                <div style="padding: 20px; border: 1px solid #ddd;">
                    <h3>📈 Weekly Cash Flow</h3>
                    <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
                        <thead style="background-color: #f2f2f2;">
                            <tr>
                                <th style="padding: 10px; text-align: left;">Day</th>
                                <th style="padding: 10px; text-align: right;">Deposits (GHS)</th>
                                <th style="padding: 10px; text-align: right;">Withdr. (GHS)</th>
                                <th style="padding: 10px; text-align: right;">Comm. (GHS)</th>
                            </tr>
                        </thead>
                        <tbody>{table_rows}</tbody>
                    </table>
                    <div style="margin-top: 25px; background: #f4f4f4; padding: 15px; border-radius: 5px;">
                        <p style="margin: 5px 0;"><b>Total Weekly Commission:</b> GHS {weekly_commissions:,.2f}</p>
                        <p style="margin: 5px 0; font-size: 18px; color: #2c3e50;"><b>Final Vault Balance: GHS {total_vault:,.2f}</b></p>
                    </div>
                    <p style="font-size: 12px; color: #888; margin-top: 20px;">Generated at: {now_dt.strftime('%Y-%m-%d %I:%M %p')}</p>
                </div>
            </body>
        </html>
        """

        msg = EmailMessage()
        msg['Subject'] = f"📊 {'AUTO' if not manual else 'MANUAL'} Report: {start_of_week.strftime('%d %b')}"
        msg['From'] = st.secrets["emails"]["sender_email"]
        msg['To'] = st.secrets["emails"]["receiver_email"]
        msg.add_alternative(html_content, subtype='html')

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(st.secrets["emails"]["sender_email"], st.secrets["emails"]["app_password"])
            server.send_message(msg)
        return True
    except Exception as e:
        if manual: 
            st.error(f"Error: {e}")
        return False

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
    
# --- 4. SECURITY ---
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

# --- 5. DATA INIT ---
clients, contributions = fetch_data()

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

# --- DISPLAY DATA ---
if not combined_df.empty:
    st.dataframe(combined_df)
else:
    st.write("No data to display yet.")

    # --- 5.5 COMPACT SYSTEM STATUS BAR ---
with st.container():
    # 1. Prepare Data Safely
    c_num = len(clients) if 'clients' in locals() and not clients.empty else 0
    t_num = len(contributions) if 'contributions' in locals() and not contributions.empty else 0
    
    if 'contributions' in locals() and not contributions.empty and 'amount' in contributions.columns:
        v_sum = contributions['amount'].sum()
    else:
        v_sum = 0.0

    # 2. Horizontal Layout (4 columns)
    # [3, 1, 1, 2] means the Title and Vault get more space than the simple counts
    st_c1, st_c2, st_c3, st_c4 = st.columns([3, 1, 1, 2])

    with st_c1:
        st.markdown("#### ⚡ Live System Monitor")
    
    with st_c2:
        st.markdown(f"👥 **Clients** \n`{c_num}`")
    
    with st_c3:
        st.markdown(f"📝 **Trans.** \n`{t_num}`")
    
    with st_c4:
        st.markdown(f"💰 **Total Vault** \n`GHS {v_sum:,.2f}`")

    st.divider()

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

# --- 6. NAVIGATION ---
menu = ["📊 Dashboard", "💸 Transactions", "📑 Digital Passbook", "🛠 Admin Tools"]
with st.sidebar:
    st.title("📱 App Options")
    
    # --- NETWORK & SCHEMA HEALTH CHECK ---
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
    
    # Display Status as a clean "Status Bar" in the sidebar
    st.markdown(f"""
    <div style="background-color: #343a40; padding: 10px; border-radius: 5px; border-left: 5px solid #FFD700;">
        <p style="margin:0; font-size: 12px; color: #adb5bd;">SYSTEM STATUS</p>
        <p style="margin:0; font-weight: bold;">Cloud: {db_status} | {schema_status}</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.divider()

choice = st.sidebar.selectbox("Go To:", menu)

if choice == "📊 Dashboard":
    # 1. Header & Quick Refresh
    head_col, btn_col = st.columns([4, 2])
    with head_col:
        st.title("📊 Financial Overview")
    with btn_col:
        if st.button("🔄 Sync & Refresh"):
            st.cache_data.clear()
            st.rerun()

    # 2. Key Metrics Logic
    m1, m2, m3, m4 = st.columns(4)
    total_client_count = len(clients) if not clients.empty else 0
    m1.metric("👥 Total Clients", f"{total_client_count}")

    if not contributions.empty:
        # Create a copy for date processing to avoid SettingWithCopy warnings
        df_display = contributions.copy()
        df_display['date_dt'] = pd.to_datetime(df_display['date'], errors='coerce', utc=True)
        df_display = df_display.dropna(subset=['date_dt'])
        
        # Calculate Totals
        total_vault = df_display['amount'].sum()
        total_commissions = df_display['fee'].sum()
        net_liability = total_vault - total_commissions 
        
        # --- DAILY DIFFERENCE LOGIC ---
        today_date = datetime.now().date()
        yesterday_date = today_date - pd.Timedelta(days=1)
        
        today_total = df_display[df_display['date_dt'].dt.date == today_date]['amount'].sum()
        yesterday_total = df_display[df_display['date_dt'].dt.date == yesterday_date]['amount'].sum()
        daily_diff = today_total - yesterday_total

        # Display Metrics
        m2.metric(
            label="💰 Total Vault", 
            value=f"GHS {total_vault:,.2f}",
            delta=f"GHS {today_total:,.2f} Today"
        )
        m3.metric("📈 Commissions", f"GHS {total_commissions:,.2f}")
        m4.metric(
            label="📉 Net Liability", 
            value=f"GHS {net_liability:,.2f}",
            delta=f"Diff: GHS {daily_diff:,.2f}",
            delta_color="inverse" 
        )

        # --- 3. MONTHLY PROFIT CHART ---
        st.write("---") # Visual separator
        st.subheader("📈 Monthly Commission Growth")
        
        # Grouping by month
        df_display['Month'] = df_display['date_dt'].dt.strftime('%b %Y')
        monthly_profit = df_display.groupby('Month')['fee'].sum().reset_index()
        
        # Sorting by date to ensure the chart flows correctly
        monthly_profit['sort_date'] = pd.to_datetime(monthly_profit['Month'])
        monthly_profit = monthly_profit.sort_values('sort_date')

        st.bar_chart(data=monthly_profit, x='Month', y='fee', color="#FFD700")

        # --- 4. DATA EXPORT ---
        csv = contributions.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Export History (CSV)", data=csv, file_name="susu_records.csv", mime="text/csv")
        
    else:
        m2.metric("💰 Total Vault", "GHS 0.00")
        m3.metric("📈 Commissions", "GHS 0.00")
        m4.metric("📉 Net Liability", "GHS 0.00")
        st.info("💡 Start recording transactions to see financial data.")

elif choice == "💸 Transactions":
    st.title("💸 Record Transactions")
    
    if not clients.empty:
        # 1. Select Client
        client_list = clients['client_name'].tolist()
        target = st.selectbox("Select Client", client_list)
        
        client_row = clients[clients['client_name'] == target].iloc[0]
        d_mark = float(client_row['daily_mark'])
        
        # --- DATA RETRIEVAL ---
        if not contributions.empty and 'client_name' in contributions.columns:
            user_history = contributions[contributions['client_name'] == target]
            total_saved_ghs = float(user_history['amount'].sum())
            total_marks_saved = int(user_history['marks_covered'].sum())
        else:
            user_history = pd.DataFrame()
            total_saved_ghs = 0.0
            total_marks_saved = 0
        
        # --- PROGRESS TRACKER (FIXED EXCEPTIONS) ---
        try:
            current_cycle_marks = float(total_marks_saved % 31)
            progress_val = current_cycle_marks / 31.0
            safe_progress = float(max(0.0, min(progress_val, 1.0)))
        except (ZeroDivisionError, TypeError, ValueError):
            current_cycle_marks = 0.0
            safe_progress = 0.0
        
        st.write(f"📊 *Current Month Progress:* **{int(current_cycle_marks)}/31** Marks")
        st.progress(safe_progress)
        st.write(f"💰 **Total Balance:** GHS {total_saved_ghs:,.2f}")

        st.divider()

        # --- 2. TRANSACTION INPUTS ---
        ttype = st.radio("Type", ["Deposit", "Withdrawal"], horizontal=True)
        
        # BACKDATING / MIGRATION LOGIC
        is_migration = st.checkbox("Migrate Old Data (Backdate)")
        if is_migration:
            selected_date = st.date_input("Select Transaction Date", value=datetime.now().date())
            trans_date = datetime.combine(selected_date, datetime.now().time())
        else:
            trans_date = datetime.now()

        can_save = True
        db_amt, db_marks, db_fee = 0.0, 0, 0.0

        if ttype == "Deposit":
            num_marks = st.number_input("Number of Marks to add", min_value=1, step=1)
            db_amt = float(num_marks * d_mark)
            db_marks = num_marks
            st.info(f"💰 Value: GHS {db_amt:,.2f} | 📈 Marks: +{num_marks}")
           # --- Withdrawal logic --- #
        else: 
            requested_cash = st.number_input("Cash to Withdraw (GHS)", min_value=0.0, step=1.0)
            if is_migration:
                db_fee = st.number_input("Service Fee (GHS)", min_value=0.0, value=0.0)
            else:
                months_count = math.ceil(total_marks_saved / 31) if total_marks_saved > 0 else 1
                db_fee = float(months_count * d_mark)
            
            total_deduction = requested_cash + db_fee
            
            if requested_cash > 0:
                if total_deduction > (total_saved_ghs + 0.01):
                    st.error(f"⚠️ Insufficient Balance! (Available: GHS {total_saved_ghs:,.2f})")
                    can_save = False
                else:
                    # IMPORTANT: Ensure db_amt is a clear negative float
                    db_amt = -float(total_deduction)
                    st.warning(f"Deducting Total: GHS {total_deduction:,.2f} (Cash + Fee)")

        # --- 3. THE SYNC BUTTON ---
        if st.button("🚀 Confirm & Sync Transaction"):
            if can_save and (db_amt != 0):
                # Prepare the entry with ISO date to prevent the Pandas crash
                new_entry = {
                    'amount': float(db_amt),
                    'client_name': target,
                    'date': trans_date.isoformat(), # Standardized format for both DBs
                    'fee': float(db_fee),
                    'marks_covered': int(db_marks) if ttype == "Deposit" else 0
                }

                # Run the dual sync
                is_synced = sync_data_dual(new_entry)

                if is_synced:
                    # Clear cache so the Dashboard recalculates totals immediately
                    st.cache_data.clear() 
                    st.success(f"✅ Transaction Recorded for {target}!")
                    st.balloons()
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("❌ Sync failed. Check connection.")
            else:
                st.error("Invalid amount or insufficient balance.")
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
            
            # --- SAFETY FIX: Handle history even if contributions is empty ---
            if not contributions.empty and 'client_name' in contributions.columns:
                user_history = contributions[contributions['client_name'] == target].copy()
                total_marks = user_history['marks_covered'].sum() if 'marks_covered' in user_history.columns else 0
                current_balance = user_history['amount'].sum() if 'amount' in user_history.columns else 0.0
            else:
                user_history = pd.DataFrame()
                total_marks = 0
                current_balance = 0.0
            
            # --- UI Display ---
            col_a, col_b = st.columns([1, 2])
            with col_a:
                # Check if photo exists, otherwise show a generic user icon
                if c_info.get('photo_url') and str(c_info['photo_url']) != 'None':
                    st.image(c_info['photo_url'], use_container_width=True)
                else:
                    st.info("No photo available")
            
            with col_b:
                st.subheader(f"Account: {target}")
                st.write(f"🆔 *ID:* {c_info.get('client_id', 'N/A')}")
                st.write(f"📞 *Phone:* {c_info.get('phone', 'N/A')}")
                
                m1, m2 = st.columns(2)
                m1.metric("💰 Balance", f"GHS {current_balance:,.2f}")
                m2.metric("📅 Marks", f"{total_marks}")

            st.divider()
            
            # --- ACTION ROW ---
            col_s1, col_s2 = st.columns(2)
            with col_s1:
                # WhatsApp Share
                formatted_phone = f"233{str(c_info['phone'])[-9:]}"
                wa_msg = f"📑 RUCHANET PASSBOOK%0A👤 Client: {target}%0A💰 Balance: GHS {current_balance:,.2f}%0A📅 Total Marks: {total_marks}"
                st.markdown(f'''
                    <a href="https://wa.me/{formatted_phone}?text={wa_msg}" target="_blank">
                        <button style="background-color: #25D366; color: white; border: none; padding: 10px; border-radius: 8px; width: 100%; cursor: pointer; font-weight: bold;">
                            🟢 Send via WhatsApp
                        </button>
                    </a>
                ''', unsafe_allow_html=True)
            
            with col_s2:
                # Print Function
                st.markdown("""
                    <button onclick="window.print()" style="background-color: #007bff; color: white; border: none; padding: 10px; border-radius: 8px; width: 100%; cursor: pointer; font-weight: bold;">
                        🖨️ Print / Save PDF
                    </button>
                """, unsafe_allow_html=True)

            # History Table
            st.write("### 📝 Transaction History")
            if not user_history.empty:
                user_h_display = user_history.copy()
                # Clean up date formatting for display
                user_h_display['date'] = pd.to_datetime(user_h_display['date']).dt.strftime('%Y-%m-%d %I:%M %p')
                
                # Filter display columns safely
                cols = [c for c in ['date', 'amount', 'marks_covered', 'fee'] if c in user_h_display.columns]
                st.dataframe(user_h_display.sort_values(by='date', ascending=False)[cols], use_container_width=True)
            else:
                st.info("No transaction history recorded yet.")
        else:
            st.warning("🔍 No client matches your search.")
    else:
        st.error("Please register clients in Admin Tools first.")

# --- 3. ADMIN TOOLS & EMAIL ---
elif choice == "🛠 Admin Tools":
    st.title("🛠 Admin Dashboard")
       # FIX: This line defines t4. Ensure it exists before "with t4:"
    t1, t2, t3, t4, t5 = st.tabs(["👤 Registration", "📧 Reports", "🗑 Data Cleanup", "💰 Manage Profile", "🧨 Reset System"])
    
    with t1:
        st.subheader("👤 Register New Client")
        # Keep camera outside the form
        photo = st.camera_input("Take Client Photo (Required)")
    
        with st.form("reg_form", clear_on_submit=True):
            name = st.text_input("Full Name")
            phone = st.text_input("Phone Number")
            daily = st.number_input("Daily Mark (GHS)", min_value=5.0, step=1.0)
            reg_date = st.date_input("Registration Date", value=datetime.now())
            
            # Show the ID they are about to get
            suggested_id = get_next_gen_id(reg_date)
            st.info(f"Next Available ID: {suggested_id}")
            
            submit = st.form_submit_button("Register to Cloud")
            
            if submit: 
                if not name.strip() or not phone.strip() or photo is None:
                    st.error("❌ All fields (Name, Phone, and Photo) are required")
                else:
                    try:
                        # 1. Generate the ID and create a safe filename
                        gen_id = get_next_gen_id(reg_date)
                        # This replaces "/" with "-" so "001/03/26" becomes "001-03-26.jpg"
                        file_name = f"{gen_id.replace('/', '-')}.jpg"
                        
                        # 2. Upload Photo to Supabase Storage with 'upsert'
                        sb_client.storage.from_("client-photos").upload(
                            path=file_name,
                            file=photo.getvalue(),
                            file_options={"content-type": "image/jpeg", "upsert": "true"}
                        )

                        # 3. Construct Public URL
                        base_url = st.secrets['supabase_url']
                        p_url = f"{base_url}/storage/v1/object/public/client-photos/{file_name}"

                        # 4. Save to SQL Database
                        with conn.session as s:
                            s.execute(text("""
                                INSERT INTO clients (client_id, client_name, phone, daily_mark, photo_url)
                                VALUES (:i, :n, :p, :d, :u)
                            """), {
                                "i": gen_id, 
                                "n": name.strip(), 
                                "p": phone.strip(), 
                                "d": daily, 
                                "u": p_url
                            })
                            s.commit()
                        
                        st.success(f"✅ Registered {name} successfully!")
                        st.balloons()
                        time.sleep(2)
                        st.rerun()

                    except Exception as e:
                        # This will catch the 403 error if your Storage Policies aren't set yet
                        st.error(f"🚨 Registration Failed: {e}")

    with t2:
        st.subheader("📊 Weekly Executive Intelligence")
        if st.button("🚀 Force Send Comprehensive Weekly Report"):
            if send_weekly_report(contributions, manual=True):
                st.success(f"✅ Report sent successfully at {datetime.now().strftime('%I:%M %p')}!")

    with t3:
        # 1. Health Check (Always at the top)
        st.subheader("🧹 Database Health & Integrity")
        if 'clients' in locals() and not clients.empty:
            id_pattern = r'^\d{3}/\d{2}/\d{2}$'
            invalid_ids = clients[~clients['client_id'].str.match(id_pattern, na=False)]
            if not invalid_ids.empty:
                st.error(f"⚠️ Found {len(invalid_ids)} IDs with incorrect formatting!")
                st.dataframe(invalid_ids[['client_id', 'client_name', 'phone']])
            else:
                st.success("✅ All Client IDs follow the correct format.")
        
        st.divider()

        # 2. Deletion Logic (Logged version)
        st.subheader("🛑 Restricted Data Cleanup")
        admin_entry = st.text_input("Enter Admin Password", type="password", key="cleanup_pass")
        
        if admin_entry == st.secrets["passwords"]["admin_password"]:
            if not contributions.empty:
                search_term = st.text_input("Filter by Client Name", key="cleanup_filter")
                f_df = contributions[contributions['client_name'].str.contains(search_term, case=False)].copy()
                
                if not f_df.empty:
                    # Using the row index (x.name) ensures we delete the EXACT record chosen
                    f_df['display'] = f_df.apply(lambda x: f"ROW:{x.name} | {x['date']} | {x['client_name']} | GHS {x['amount']}", axis=1)
                    to_del = st.selectbox("Select entry to remove", options=f_df['display'])
                    
                    if st.button("🗑️ Permanent Delete Entry"):
                        # Extract the unique index
                        selected_row_idx = int(to_del.split(" | ")[0].replace("ROW:", ""))
                        target_row = f_df.loc[selected_row_idx]

                        try:
                            with conn.session as s:
                                # A. RECORD THE ACTION IN AUDIT LOG
                                s.execute(text("""
                                    INSERT INTO audit_logs (action_type, details, admin_name)
                                    VALUES (:type, :details, :admin)
                                """), {
                                    "type": "TRANSACTION_DELETE",
                                    "details": f"Deleted GHS {target_row['amount']} for {target_row['client_name']} (Original Date: {target_row['date']})",
                                    "admin": "System Admin"
                                })
                                
                                # B. DELETE THE ACTUAL RECORD
                                s.execute(text("""
                                    DELETE FROM contributions 
                                    WHERE client_name = :n AND date = :d AND amount = :a
                                """), {
                                    "n": target_row['client_name'], 
                                    "d": target_row['date'], 
                                    "a": target_row['amount']
                                })
                                s.commit()
                            
                            st.toast("Security log updated & entry deleted.", icon="🛡️")
                            st.cache_data.clear() 
                            time.sleep(2)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Action failed: {e}")
                else:
                    st.info("No matching entries found.")
            else:
                st.info("No transactions to clean.")

    with t4:
        st.subheader("⚙️ Secure Client Profile Manager")
        st.error("❗ *CRITICAL AREA*: Deletion removes the client, photo, and history permanently.")

        # Check if the clients table is defined and has data
        if 'clients' in locals() and not clients.empty:
            search_query = st.text_input("🔍 Search Profile (Name or ID)", key="admin_manage_search")
            
            # Filter the clients dataframe based on search
            filtered = clients[
                clients['client_name'].str.contains(search_query, case=False) | 
                clients['client_id'].str.contains(search_query, case=False)
            ]

            if not filtered.empty:
                selected_name = st.selectbox("Select Profile to Manage:", filtered['client_name'])
                
                # Fetch specific client data
                c_data = filtered[filtered['client_name'] == selected_name].iloc[0]
                target_id = str(c_data['client_id']) 
                
                # --- START OF SAFETY FIX FOR LINE 597 ---
                final_balance = 0.0
                u_history = pd.DataFrame() 

                # Only try to filter if contributions is not empty AND contains the 'client_name' column
                if 'contributions' in locals() and not contributions.empty:
                    if 'client_name' in contributions.columns:
                        u_history = contributions[contributions['client_name'] == selected_name]
                        if not u_history.empty:
                            final_balance = u_history['amount'].sum()
                # --- END OF SAFETY FIX ---

                # Display Profile Info
                col1, col2 = st.columns([1, 2])
                with col1:
                    if c_data.get('photo_url'):
                        st.image(c_data['photo_url'], caption=f"ID: {target_id}", use_container_width=True)
                with col2:
                    st.write(f"**Name:** {c_data['client_name']}")
                    st.write(f"**Phone:** {c_data['phone']}")
                    st.write(f"**Payout Due:** GHS {final_balance:,.2f}")

                st.markdown("---")
                
                # Security Checkpoint
                confirm_check = st.checkbox(f"I confirm I want to wipe {target_id} forever.", key="del_check")
                
                if confirm_check:
                    admin_pass = st.text_input("🔐 Admin Password Required", type="password", key="wipe_pass_input")
                    
                    if st.button("💥 AUTHORIZE PERMANENT WIPE"):
                        if admin_pass == st.secrets["passwords"]["admin_password"]:
                            try:
                                # 1. Cleanup Cloud Storage Photo
                                safe_filename = target_id.replace('/', '-')
                                file_path = f"{safe_filename}.jpg"
                                try:
                                    sb_client.storage.from_("client-photos").remove([file_path])
                                except Exception:
                                    pass # Ignore if photo doesn't exist

                                # 2. Database Cleanup
                                with conn.session as s:
                                    # Use safe deletion logic
                                    s.execute(text("DELETE FROM contributions WHERE client_name = :n"), {"n": selected_name})
                                    s.execute(text("DELETE FROM clients WHERE client_id = :i"), {"i": target_id})
                                    s.commit()

                                st.toast(f"🗑️ {target_id} wiped successfully.", icon="💥")
                                st.cache_data.clear() # Forces app to refresh data
                                time.sleep(1.5)
                                st.rerun()
                                
                            except Exception as e:
                                st.error(f"🚨 Wipe Failed: {e}")
                        else:
                            st.error("❌ Incorrect Admin Password.")
            else:
                st.info("No matching profiles found for your search.")
        else:
            st.info("The client database is currently empty. No profiles to manage.")

    with t5:
        st.header("🧨 Factory Reset & Security")
        
        # --- 1. SYSTEM WIPE LOGIC ---
        st.subheader("🔥 Step 1: Wipe System")
        st.error("WARNING: This action is permanent! It deletes all clients, photos, and money records.")
        
        confirm_reset = st.checkbox("I have backed up my data and want to delete EVERYTHING.", key="wipe_confirm_check")
        
        if st.button("EXECUTE FULL RESET", type="primary", disabled=not confirm_reset):
            try:
                with conn.session as s:
                    # Reset tables and ID counters
                    s.execute(text("TRUNCATE TABLE contributions RESTART IDENTITY CASCADE;"))
                    s.execute(text("TRUNCATE TABLE clients RESTART IDENTITY CASCADE;"))
                    # Log the reset action itself before wiping the logs
                    s.execute(text("TRUNCATE TABLE audit_logs RESTART IDENTITY CASCADE;"))
                    s.execute(text("""
                        INSERT INTO audit_logs (action_type, details, admin_name) 
                        VALUES ('SYSTEM_RESET', 'Full factory reset performed.', 'System Admin')
                    """))
                    s.commit()
                
                # Clear Supabase Storage
                try:
                    files = sb_client.storage.from_("client-photos").list()
                    if files:
                        file_names = [f['name'] for f in files if f['name'] != '.emptyKeepFile']
                        if file_names:
                            sb_client.storage.from_("client-photos").remove(file_names)
                except Exception:
                    pass 

                st.success("💥 System wiped successfully!")
                st.cache_data.clear()
                time.sleep(2)
                st.rerun()
                
            except Exception as e:
                # FIX: Using 'e' here removes the VS Code warning
                st.error(f"Reset failed: {e}")

        st.divider()

        # --- 2. SECURITY AUDIT & HISTORY ---
        st.subheader("🛡️ Security Audit & History")
        
        # Display Last Reset Date
        try:
            reset_info = conn.query("SELECT created_at FROM audit_logs WHERE action_type = 'SYSTEM_RESET' ORDER BY created_at DESC LIMIT 1")
            if not reset_info.empty:
                last_reset = pd.to_datetime(reset_info.iloc[0]['created_at']).strftime('%B %d, %Y at %H:%M')
                st.info(f"📅 **Current Cycle Started:** {last_reset}")
            else:
                st.info("📅 **Current Cycle:** No reset recorded yet.")
        except Exception as e:
            st.error(f"Could not fetch cycle history: {e}")

        if st.button("📋 View Recent Admin Actions"):
            try:
                audit_query = "SELECT created_at, action_type, details FROM audit_logs ORDER BY created_at DESC LIMIT 15"
                logs_df = conn.query(audit_query)
                if not logs_df.empty:
                    logs_df['created_at'] = pd.to_datetime(logs_df['created_at']).dt.strftime('%Y-%m-%d %H:%M')
                    st.table(logs_df)
                else:
                    st.write("No logs found.")
            except Exception as e:
                st.error(f"Log error: {e}")
        st.subheader("sqlite Local Database Viewer")
    if st.button("📂 Load Local DB Records"):
        try:
            conn_local = sqlite3.connect('susu_data.db')
            local_df = pd.read_sql_query("SELECT * FROM contributions", conn_local)
            conn_local.close()
            
            if not local_df.empty:
                st.write(f"Total Local Records: {len(local_df)}")
                st.dataframe(local_df, use_container_width=True)
            else:
                st.info("The local database is empty.")
        except Exception as e:
            st.error(f"Could not read local DB: {e}")