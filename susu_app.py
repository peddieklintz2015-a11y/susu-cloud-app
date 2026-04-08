import streamlit as st
from utils import send_weekly_report
import streamlit.components.v1 as components
import pandas as pd
import time
import re
import math
from datetime import datetime
from sqlalchemy import text
from supabase import create_client

import hashlib

def hash_password(password):
    """Encodes password for security."""
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_password_auth(typed_password, stored_hash):
    """Checks if the typed password matches the one in the cloud."""
    return hash_password(typed_password) == stored_hash

# --- 1. SETUP ---
st.set_page_config(
    page_title="MY SUSU APP", 
    page_icon="💰", 
    layout="wide"
)

# --- DATABASE CONNECTIONS & SYNC LOGIC ---
conn = st.connection("postgresql", type="sql")
menu = ["📊 Dashboard", "💸 Transactions", "📑 Digital Passbook", "🛠 Admin Tools"]

try:
    sb_client = create_client(st.secrets["supabase_url"], st.secrets["supabase_key"])
except Exception as e:
    st.error(f"Supabase Error: {e}") 
    st.stop()

# --- 🧩 THE SAAS BRIDGE (INSERTION) ---
# This defines the variables your 46 errors are looking for.

tid = st.session_state.get("tenant_id")
role = st.session_state.get("account_role", "tenant")

# 1. Fetch the data once
try:
    with conn.session as s:
        if role == "developer":
            raw_clients = s.execute(text("SELECT * FROM clients")).mappings().all()
            raw_contribs = s.execute(text("SELECT * FROM contributions")).mappings().all()
        else:
            raw_clients = s.execute(text("SELECT * FROM clients WHERE tenant_id = :tid"), {"tid": tid}).mappings().all()
            raw_contribs = s.execute(text("SELECT * FROM contributions WHERE tenant_id = :tid"), {"tid": tid}).mappings().all()
    
    # 2. Create the DataFrames
    clients = pd.DataFrame(raw_clients)
    contributions = pd.DataFrame(raw_contribs)

    # 3. THE MAGIC ALIASES (This kills the 46 errors)
    # This makes sure 'clients' AND 'clients_df' both point to the same data.
    clients_df = clients
    contributions_df = contributions

except Exception as e:
    # If the database is empty or errors, we create empty frames so the app doesn't crash
    clients = clients_df = pd.DataFrame()
    contributions = contributions_df = pd.DataFrame()
    st.error(f"Cloud Bridge Syncing... {e}")

# --- END OF INSERTION ---
# Your existing code (Dashboard, Transactions, etc.) starts below this line....

def sync_to_cloud(new_record):
    """Strictly saves to Supabase Cloud."""
    # Ensure the tenant ID is attached for SaaS security
    new_record['tenant_id'] = st.session_state.get("tenant_id")
    
    try:
        # Save to your Supabase 'contributions' table
        sb_client.table("contributions").insert(new_record).execute()
        st.success("✅ Transaction synced to RUCHANET Cloud!")
        return True
    except Exception as e:
        st.error(f"❌ Cloud Sync Error: {e}")
        return False

def auth_gate():
        if "tenant_id" not in st.session_state:
           st.title("🚀 Welcome to MY SUSU APP: Cloud Portal")
        st.markdown("""
        *The ultimate cloud solution for your Susu business.*
        * ✅ Secure Cloud Storage**
        * ✅ Real-time Client Passbooks**
        * ✅ Automated Sunday Reports**
        * ✅ **Only GHS 99.90 / Month**
        """)
        st.divider()
        tab1, tab2 = st.tabs(["🔐 Business Login", "✨ Register (14-Day Trial)"])

        with tab1:
            with st.form("login"):
                email = st.text_input("Business Email")
                pwd = st.text_input("Password", type="password")
                
                if st.form_submit_button("Login to Dashboard", type="primary"):
                    # 1. Fetch the user from Supabase
                    res = sb_client.table("tenants").select("*").eq("admin_email", email).execute()
                    
                    # 2. Check if user exists and password is correct
                    if res.data and check_password_auth(pwd, res.data[0]['password_hash']):
                        user = res.data[0]
                        
                        # 3. Save session data
                        st.session_state["tenant_id"] = user['id']
                        st.session_state["biz_name"] = user['business_name']
                        
                        # 4. Handle the Developer vs Tenant role
                        # This looks for the 'account_role' column you added to your table
                        st.session_state["account_role"] = user.get('account_role', 'tenant')
                        
                        st.success(f"Welcome back, {user['business_name']}!")
                        st.rerun()
                    else:
                        st.error("Invalid credentials. Please check your email/password.")

        with tab2:
            with st.form("signup"):
                new_biz = st.text_input("Organization/Susu Name")
                new_email = st.text_input("Admin Email")
                new_pwd = st.text_input("Create Password", type="password")
                if st.form_submit_button("Start My 14-Day Trial"):
                    hashed = hash_password(new_pwd)
                    # Create the new Tenant with trial settings
                    sb_client.table("tenants").insert({
                        "business_name": new_biz,
                        "admin_email": new_email,
                        "password_hash": hashed,
                        "price_ghs": 99.9,
                        "is_subscribed": False,
                        "account_role": "tenant"
                    }).execute()
                    st.success("Account created! Please switch to the Login tab.")
        st.stop()

def get_tenant_id():
    return st.session_state.get("tenant_id")

# --- GLOBAL PWA INJECTION ---
# Place this right after your imports and set_page_config
st.markdown(
    """
    <link rel="manifest" href="./manifest.json">
    <script>
        if ('serviceWorker' in navigator) {
          window.addEventListener('load', function() {
            navigator.serviceWorker.register('./sw.js').then(function(reg) {
              console.log('PWA ServiceWorker registered');
            });
          });
        }
    </script>
    """, 
    unsafe_allow_html=True
)

st.markdown(
    """
    <style>
        /* 1. Global Dark Background */
        .stApp { background-color: #0E1117 !important; }

        /* 2. Force White Text */
        h1, h2, h3, p, label, span, .stMarkdown p {
            color: #FFFFFF !important;
            -webkit-text-fill-color: #FFFFFF !important;
        }

        /* 3. THE BUTTON FIX - Targeted to exclude header icons */
        /* We target buttons that are NOT inside the header */
        div:not([data-testid="stHeader"]) button[kind="primary"],
        div:not([data-testid="stHeader"]) button[data-testid="baseButton-primary"] {
            background-color: #FF484B !important; 
            color: #FFFFFF !important;
            -webkit-text-fill-color: #FFFFFF !important;
            border: none !important;
            border-radius: 8px !important;
            -webkit-appearance: none !important;
            box-shadow: none !important;
        }

        /* 4. Fix the Search/Download icons in Dataframes */
        /* This ensures the icons remain visible on the dark background */
        button[title="Download as CSV"], button[title="Search"] {
            background-color: transparent !important;
            color: white !important;
        }
    </style>
    """,
    unsafe_allow_html=True
)

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
# --- UPDATED DATA FUNCTIONS (SaaS CLOUD-ONLY) ---

@st.cache_data(ttl=10) # Reduced TTL for fresher SaaS data
def fetch_clients():
    """Fetches the client list from the cloud."""
    try:
        with conn.session as s:
            df = pd.DataFrame(s.execute(
                text("SELECT client_id, client_name, phone, daily_mark, photo_url FROM clients")
            ).mappings().all())
            return df
    except Exception as e:
        st.error(f"Client Fetch Error: {e}")
        return pd.DataFrame()

def get_cloud_client_stats(client_name):
    """
    SAAS CRITICAL: Calculates balance directly in the Database.
    Prevents downloading the whole contributions table to the phone.
    """
    try:
        with conn.session as s:
            result = s.execute(text("""
                SELECT 
                    COALESCE(SUM(amount), 0) as total_cash, 
                    COALESCE(SUM(marks_covered), 0) as total_marks 
                FROM contributions 
                WHERE client_name = :name
            """), {"name": client_name}).mappings().first()
            return {
                "total_cash": float(result['total_cash']),
                "total_marks": int(result['total_marks'])
            }
    except Exception as e:
        st.error(f"Balance Sync Error: {e}")
        return {"total_cash": 0.0, "total_marks": 0}

def cloud_db_insert(table, record):
    """
    Replaces sync_data_dual. 
    Writes directly to the cloud and returns the new Row ID.
    """
    try:
        # Using the Supabase client you initialized earlier
        res = sb_client.table(table).insert(record).execute()
        if res.data:
            return {"success": True, "id": res.data[0].get('id')}
        return {"success": False, "error": "No data returned"}
    except Exception as e:
        return {"success": False, "error": str(e)}

# --- 1. THE SECURITY WALL ---
def check_password():
    if "role" not in st.session_state:
        st.title("🔐 RUCHANET SYSTEM LOGIN")
        col1, col2 = st.columns(2)
        
        with col1:
            with st.form("agent_login"):
                st.subheader("👤 Agent Login")
                # CHANGED: Added type="primary" and use_container_width
                if st.form_submit_button("Access Collector Tools", type="primary", use_container_width=True):
                    st.session_state["role"] = "Agent"
                    st.rerun()
                    
        with col2:
            with st.form("admin_login"):
                st.subheader("🛡️ Manager Login")
                pwd = st.text_input("Manager Password", type="password")
                # CHANGED: Added type="primary" and use_container_width
                if st.form_submit_button("Verify Identity", type="primary", use_container_width=True):
                    if pwd == st.secrets["passwords"]["login_password"]: 
                        st.session_state["role"] = "Manager"
                        st.rerun()
                    else:
                        st.error("Invalid Manager Password")
        
        st.stop() 
    return True
# Run the security check FIRST
check_password()

# --- 2. THE SECURE APP (Everything below only runs AFTER login) ---
st.markdown(
        """
        <style>
            /* 1. Header and Sidebar Fixes */
            header[data-testid="stHeader"] {
                background-color: #0E1117 !important;
                color: white !important;
            }
            [data-testid="stSidebar"] { display: flex !important; }
            [data-testid="stSidebarCollapseButton"] { 
                display: flex !important; 
                color: white !important;
            }
            [data-testid="stSidebarCollapseButton"] svg { fill: white !important; }

            /* 2. UNIVERSAL BUTTON FIX (For Register & Search) */
            /* This forces all 'Primary' buttons to stay Red on iPhone */
            button[kind="primary"],
            button[data-testid="baseButton-primary"],
            .stButton button[kind="primary"] {
                background-color: #FF484B !important;
                color: white !important;
                -webkit-text-fill-color: white !important;
                -webkit-appearance: none !important; /* Kills the white block effect */
                border: none !important;
                border-radius: 8px !important;
                font-weight: 700 !important;
                opacity: 1 !important;
                visibility: visible !important;
                width: 100% !important;
            }

            /* 3. Button Text Visibility */
            button[data-testid="baseButton-primary"] p {
                color: white !important;
                -webkit-text-fill-color: white !important;
            }

            /* 4. Secondary Buttons (Optional: Make them dark grey instead of white) */
            button[kind="secondary"],
            button[data-testid="baseButton-secondary"] {
                background-color: #262730 !important;
                color: white !important;
                -webkit-text-fill-color: white !important;
                border: 1px solid #475569 !important;
                -webkit-appearance: none !important;
            }
        </style>
        """,
        unsafe_allow_html=True
    )
# --- 1. UPDATED DATA FETCHING (Fixes the "Undefined" errors in your photo) ---
# We use these names to match what your existing code expects
clients_df, contributions_df = pd.DataFrame(), pd.DataFrame()

# Get IDs from session
tid = st.session_state.get("tenant_id")
role = st.session_state.get("account_role", "tenant") 

with st.spinner("Syncing Cloud Data..."):
    try:
        with conn.session as s:
            if role == "developer":
                # Super Admin: Sees EVERYTHING for maintenance
                clients_df = pd.DataFrame(s.execute(text("SELECT * FROM clients")).mappings().all())
                contributions_df = pd.DataFrame(s.execute(text("SELECT * FROM contributions")).mappings().all())
            else:
                # Regular Tenant: Only sees their own business data
                clients_df = pd.DataFrame(s.execute(
                    text("SELECT * FROM clients WHERE tenant_id = :tid"), {"tid": tid}
                ).mappings().all())
                contributions_df = pd.DataFrame(s.execute(
                    text("SELECT * FROM contributions WHERE tenant_id = :tid"), {"tid": tid}
                ).mappings().all())
    except Exception as e:
        st.error(f"Sync Error: {e}")

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

def generate_susu_receipt(idx, date_val, client_name, amount, marks, bal_after=None):
    # Handle both datetime objects and strings safely
    if isinstance(date_val, datetime):
        date_display = date_val.strftime("%Y-%m-%d %H:%M:%S")
    else:
        date_display = str(date_val)
        
    t_type_label = "DEPOSIT" if amount > 0 else "WITHDRAWAL"
    
    bal_html = ""
    if bal_after is not None:
        bal_before = float(bal_after - amount)
        bal_html = f"""
        <tr><td>Prev. Balance:</td><td style="text-align:right;">GHS {bal_before:,.2f}</td></tr>
        <tr style="font-weight:bold;"><td>New Balance:</td><td style="text-align:right;">GHS {bal_after:,.2f}</td></tr>
        """

    receipt_html = f"""
    <div id="receipt-{idx}" style="font-family: 'Courier New', monospace; width: 280px; padding: 15px; background: white; color: black; border: 1px solid #ddd; line-height: 1.2;">
        <center>
            <h3 style="margin:0;">MY SUSU APP</h3>
            <p style="font-size:10px; margin:2px;">Rural Christian Network Savings</p>
            <p style="font-size:11px; margin:0;">* TRANSACTION RECEIPT *</p>
        </center>
        <hr style="border-top: 1px dashed #000;">
        <div style="font-size:12px;">
            <b>Date/Time:</b> {date_display}<br>
            <b>Client:</b> {client_name}<br>
            <b>Type:</b> {t_type_label}<br>
        </div>
        <hr style="border-top: 1px dashed #000;">
        <table style="width:100%; font-size:13px; font-weight:bold;">
            <tr><td>Amount:</td><td style="text-align:right;">GHS {abs(amount):,.2f}</td></tr>
            <tr><td>Marks:</td><td style="text-align:right;">{abs(marks)}</td></tr>
        </table>
        <hr style="border-top: 1px dashed #000;">
        <table style="width:100%; font-size:12px;">
            {bal_html}
        </table>
        <hr style="border-top: 1px dashed #000;">
        <center><p style="font-size:12px;"><span style="font-style: italic;">Thank you for saving with RUCHANET SUSU!</span><br>Verified Digital Record</p></center>
    </div>
    <button onclick="printDiv('receipt-{idx}')" style="width:100%; padding:10px; margin-top:8px; background:#FFD700; border:none; font-weight:bold; cursor:pointer;">🖨️ Print Receipt</button>
    <script>
    function printDiv(divId) {{
        var content = document.getElementById(divId).innerHTML;
        var win = window.open('', '', 'height=600,width=450');
        win.document.write('<html><body style="font-family:monospace;">' + content + '</body></html>');
        win.document.close();
        setTimeout(function() {{ win.print(); win.close(); }}, 500);
    }}
    </script>
    """
    return components.html(receipt_html, height=400)

def get_next_gen_id(reg_date):
    # 1. Get the month/year suffix from the user's chosen date (e.g., "01/26")
    mm_yy = reg_date.strftime("%m/%y")
    
    try:
        with conn.session as s:
            # 2. Find all IDs that ALREADY exist for this specific month/year
            # This ensures if you pick Jan, it counts Jan; if you pick Feb, it counts Feb.
            result = s.execute(text("""
                SELECT client_id FROM clients 
                WHERE client_id LIKE :pattern
            """), {"pattern": f"%/{mm_yy}"}).fetchall()
            
            if result:
                nums = []
                for row in result:
                    try:
                        # 3. Extract the prefix number (the part before the first '/')
                        # Splits "159/01/26" into "159"
                        prefix = int(row[0].split('/')[0])
                        nums.append(prefix)
                    except (ValueError, IndexError):
                        continue
                
                # 4. Find the highest number in THAT month and add 1
                new_num = max(nums) + 1 if nums else 1
            else:
                # 5. If no clients exist for this month yet, start at 1
                new_num = 1
                
            # Return as 3 digits: "001/01/26"
            return f"{new_num:03d}/{mm_yy}"
            
    except Exception as e:
        st.error(f"⚠️ ID Generation Error: {e}") 
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
    if role == "developer":
        st.warning("🛠️ SUPER ADMIN MODE: Viewing global system data.")
    
    st.title(f"📊 {st.session_state.get('biz_name', 'Business')} Overview")
    
    # 1. LAYOUT DEFINITION (Fixes the col_refresh error)
    m1, m2, m3, m4, col_refresh = st.columns([1, 1, 1, 1, 0.3])

    # 2. REFRESH BUTTON LOGIC
    with col_refresh:
        # Added a unique key to prevent 'Duplicate Widget ID' errors
        if st.button("🔄", key="dash_refresh_btn", help="Refresh Dashboard Data"):
            st.cache_data.clear()
            st.rerun()

    # 3. METRICS SECTION
    m1.metric("👥 Total Clients", len(clients_df))

    if not contributions_df.empty:
        total_vault = contributions_df['amount'].sum()
        total_commissions = contributions_df['fee'].sum()
        
        # Date processing for deltas
        contributions_df['date_dt'] = pd.to_datetime(contributions_df['date'])
        today_date = datetime.now().date()
        today_total = contributions_df[contributions_df['date_dt'].dt.date == today_date]['amount'].sum()

        m2.metric("💰 Total Vault", f"GHS {total_vault:,.2f}", delta=f"GHS {today_total:,.2f} Today")
        m3.metric("📈 Commissions", f"GHS {total_commissions:,.2f}")
        m4.metric("📉 Net Liability", f"GHS {(total_vault - total_commissions):,.2f}")

        # 4. MONTHLY CHART
        st.divider()
        contributions_df['Month'] = contributions_df['date_dt'].dt.strftime('%b %Y')
        monthly_profit = contributions_df.groupby('Month')['fee'].sum().reset_index()
        st.bar_chart(data=monthly_profit, x='Month', y='fee', color="#FF484B")
        
        # 5. 31-MARK MATURITY ALERTS
        st.subheader("🎯 Payout Readiness (31+ Marks)")
        marks_summary = contributions_df.groupby('client_name')['marks_covered'].sum().reset_index()
        ready = marks_summary[marks_summary['marks_covered'] >= 31]
        if not ready.empty:
            for _, row in ready.iterrows():
                st.success(f"🌟 {row['client_name']} has {row['marks_covered']} marks.")
        
        # 6. CSV EXPORT
        with st.expander("📥 Download Business Records"):
            csv = contributions_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Download CSV", 
                data=csv, 
                file_name=f"{st.session_state.get('biz_name', 'Business')}_records.csv", 
                mime="text/csv",
                key="dash_csv_download"
            )
    else:
        st.info("No transaction data available yet.")

elif choice == "💸 Transactions":
    st.title("💸 Record Transactions")
    
    if not clients_df.empty:
        # FIX: Added 'col_refresh' to the columns definition here
        col_search, col_mode, col_date, col_refresh = st.columns([2, 1, 1, 1])
        
        with col_search:
            target = st.selectbox("Select Client", clients_df['client_name'].tolist())
        with col_mode:
            is_migration = st.checkbox("📂 Migration Mode")
        with col_date:
            # Handle date vs datetime for migration mode
            if is_migration:
                sel_date = st.date_input("Transaction Date", value=datetime.now().date())
                final_timestamp = datetime.combine(sel_date, datetime.now().time())
            else:
                final_timestamp = datetime.now()
                st.info(f"Date: {final_timestamp.strftime('%Y-%m-%d')}")

        # REFRESH BUTTON: Now correctly assigned to col_refresh
        with col_refresh:
            st.write("") 
            if st.button("🔄 Refresh", key="trans_refresh_btn", use_container_width=True):
                st.cache_data.clear()
                st.rerun()

        # Get Client Metadata from our global clients_df
        client_row = clients_df[clients_df['client_name'] == target].iloc[0]
        d_mark = float(client_row.get('daily_mark', 0.0))
        c_id = client_row.get('client_id', 'N/A')
        
        # --- SAAS UPDATE: Fetch live balance from Cloud DB ---
        with st.spinner("Syncing Ledger..."):
            stats = get_cloud_client_stats(target) 
            total_saved_ghs = stats['total_cash']
            total_marks_saved = stats['total_marks']
        
        st.write(f"🆔 **ID:** {c_id} | 💰 **Balance:** GHS {total_saved_ghs:,.2f} | 📅 **Total Marks:** {total_marks_saved}")
        st.divider()

        ttype = st.radio("Transaction Type", ["Deposit", "Withdrawal"], horizontal=True)
        db_amt, db_marks, db_fee = 0.0, 0, 0.0

        if ttype == "Deposit":
            num_marks = st.number_input("Marks to add", min_value=1, step=1)
            db_amt = float(num_marks * d_mark)
            db_marks = int(num_marks)
            st.info(f"➕ **Deposit:** GHS {db_amt:,.2f}")
        else:
            w_method = st.selectbox("Withdrawal Method", ["Full Payout (Include Commission)", "Advance Payment (No Commission Now)"])
            requested_cash = st.number_input("Cash Amount (GHS)", min_value=0.0, step=float(d_mark))
            
            if requested_cash > 0:
                if (requested_cash % d_mark) != 0:
                    st.error(f"🚫 Not a multiple of GHS {d_mark}")
                    st.stop()
                
                marks_for_cash = int(requested_cash / d_mark)
                if w_method == "Full Payout (Include Commission)":
                    num_commissions = math.ceil(marks_for_cash / 31)
                    db_fee = float(num_commissions * d_mark)
                    db_marks = -(marks_for_cash + num_commissions)
                else:
                    db_fee = 0.0
                    db_marks = -marks_for_cash
                
                db_amt = -float(requested_cash + db_fee)

                if not is_migration:
                    required_marks = abs(db_marks) 
                    if total_marks_saved < required_marks:
                        st.error(f"🚫 Insufficient Marks. Need {required_marks}, have {total_marks_saved}")
                        st.stop()
                    if abs(db_amt) > (total_saved_ghs + 0.01):
                        st.error("⚠️ Insufficient Cash Balance.")
                        st.stop()

        st.divider()
        if st.button("🚀 Confirm & Sync Transaction", use_container_width=True, type="primary"):
            new_entry = {
                'client_id': str(c_id), 
                'client_name': target, 
                'amount': db_amt,
                # Ensure date is stored as a string for Supabase
                'date': final_timestamp.strftime('%Y-%m-%d %H:%M:%S') if isinstance(final_timestamp, datetime) else str(final_timestamp),
                'fee': db_fee, 
                'marks_covered': db_marks,
                'tenant_id': st.session_state.get("tenant_id")
            }
            
            with st.spinner("Authorizing with RUCHANET Cloud..."):
                response = cloud_db_insert("contributions", new_entry)
            
            if response['success']:
                st.success("✅ Transaction Synced!")
                
                generate_susu_receipt(
                    idx=response['id'], 
                    date_val=final_timestamp, 
                    client_name=target, 
                    amount=db_amt, 
                    marks=db_marks, 
                    bal_after=total_saved_ghs + db_amt
                )
                
                st.cache_data.clear()
                time.sleep(3) 
                st.rerun()
            else:
                st.error(f"❌ Cloud Sync Failed: {response['error']}")

    else:
        st.warning("Please register clients first.")                 

elif choice == "📑 Digital Passbook":
    st.title("📑 Client Passbook")
    
    # 1. Fetch fresh client list for the search
    clients = fetch_clients()
    search = st.text_input("🔍 Search Client Name", key="passbook_search")
    
    if not clients.empty:
        filtered = clients[clients['client_name'].str.contains(search, case=False)] if search else clients
        
        if not filtered.empty:
            target = st.selectbox("View Passbook For:", filtered['client_name'].tolist())
            c_info = filtered[filtered['client_name'] == target].iloc[0]
            target_name = c_info['client_name']
            
            # 2. SAAS UPDATE: Fetch ONLY this client's history from Cloud
            # We no longer filter a global 'contributions' DataFrame
            with st.spinner(f"Loading history for {target_name}..."):
                try:
                    with conn.session as s:
                        user_history = pd.DataFrame(s.execute(
                            text("""
                                SELECT id, amount, date, marks_covered, fee 
                                FROM contributions 
                                WHERE client_name = :name 
                                ORDER BY date DESC
                            """), {"name": target_name}
                        ).mappings().all())
                except Exception as e:
                    st.error(f"History Fetch Error: {e}")
                    user_history = pd.DataFrame()

            # 3. Calculate metrics from the specific history
            current_bal = user_history['amount'].sum() if not user_history.empty else 0.0
            total_marks = int(user_history['marks_covered'].sum()) if not user_history.empty else 0
            daily_rate = float(c_info.get('daily_mark', 0.0))

            # --- HEADER LAYOUT ---
            col_img, col_details = st.columns([1, 2])
            
            with col_img:
                p_url = c_info.get('photo_url')
                if p_url and pd.notna(p_url):
                    st.image(p_url, width=220)
                else:
                    st.warning("👤 No Photo")
            
            with col_details:
                st.subheader(target_name)
                st.write(f"🆔 **ID:** {c_info.get('client_id', 'N/A')}")
                st.write(f"📞 **Contact:** {c_info.get('phone', 'N/A')}")
                st.markdown("---")
                
                m_col1, m_col2, m_col3 = st.columns(3)
                m_col1.caption("💰 Balance")
                m_col1.write(f"**GHS {current_bal:,.2f}**")
                m_col2.caption("📅 Marks")
                m_col2.write(f"**{total_marks}**")
                m_col3.caption("📉 Rate")
                m_col3.write(f"**GHS {daily_rate:,.2f}**")

            st.divider()

            # --- HISTORY SECTION ---
            if not user_history.empty:
                st.write("### 🕒 Recent Activity")
                for idx, row in user_history.iterrows():
                    # Parse date safely
                    raw_date = row['date']
                    date_str = raw_date.strftime('%Y-%m-%d %H:%M') if hasattr(raw_date, 'strftime') else str(raw_date)
                    
                    t_label = f"{date_str} | GHS {abs(row['amount']):,.2f}"
                    with st.expander(t_label):
                        generate_susu_receipt(
                            idx=row['id'], 
                            date_val=raw_date, 
                            client_name=target_name, 
                            amount=row['amount'], 
                            marks=row['marks_covered'],
                            bal_after=None # History view doesn't need running balance calc for every row
                        )
            else:
                st.info("No transaction history found in the cloud.")
        else:
            st.warning("No client found.")
    else:
        st.warning("Please register clients first.")

# --- 3. ADMIN TOOLS & EMAIL ---
elif choice == "🛠 Admin Tools":
    st.title("🛠 Business Management")
    tid = st.session_state.get("tenant_id")
    
    t1, t2, t3, t4, t5 = st.tabs(["👤 Registration", "📧 Reports", "🧹 Data Cleanup", "💰 Manage Profile", "🧨 Reset System"])
    
    # --- TAB 1: REGISTRATION (With SaaS Isolation & Compression) ---
    with t1:
        st.subheader("👤 Register New Client")
        reg_choice = st.radio("Source:", ["Live Camera", "Library"], horizontal=True)
        photo = st.camera_input("Photo") if reg_choice == "Live Camera" else st.file_uploader("Upload", type=["jpg", "png"])
        
        reg_date = st.date_input("Registration Date", value=datetime.now())
        suggested_id = get_next_gen_id(reg_date) # Uses your ID generator

        with st.form("reg_form", clear_on_submit=True):
            name = st.text_input("Full Name")
            phone = st.text_input("Phone Number")
            daily = st.number_input("Daily Mark (GHS)", min_value=5.0, step=1.0)
            manual_id = st.text_input("Confirm Client ID", value=suggested_id)
            
            if st.form_submit_button("Register to Cloud", type="primary", use_container_width=True):
                if not name or not phone or photo is None:
                    st.error("❌ All fields and photo are required.")
                else:
                    try:
                        # PHOTO COMPRESSION
                        from PIL import Image
                        import io
                        img = Image.open(photo).convert("RGB")
                        img.thumbnail((500, 500))
                        buf = io.BytesIO()
                        img.save(buf, format="JPEG", quality=65, optimize=True)
                        
                        safe_path = f"tenant_{tid}/{manual_id.replace('/', '-')}.jpg"
                        sb_client.storage.from_("client-photos").upload(path=safe_path, file=buf.getvalue(), file_options={"content-type":"image/jpeg", "upsert":"true"})
                        p_url = f"{st.secrets['supabase_url']}/storage/v1/object/public/client-photos/{safe_path}"

                        with conn.session as s:
                            s.execute(text("INSERT INTO clients (client_id, client_name, phone, daily_mark, photo_url, tenant_id) VALUES (:i, :n, :p, :d, :u, :tid)"),
                                      {"i": manual_id, "n": name, "p": phone, "d": daily, "u": p_url, "tid": tid})
                            s.commit()
                        st.success(f"✅ Registered {name}")
                        st.cache_data.clear()
                        time.sleep(2)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

    # --- TAB 2: REPORTS (Multi-User) ---
    with t2:
        st.subheader("📊 Executive Intelligence")
        user_email = st.session_state.get("admin_email")
        if st.button("🚀 Force Send Comprehensive Weekly Report"):
            with st.spinner("Sending..."):
                if send_weekly_report(contributions_df, manual=True, target_email=user_email):
                    st.success(f"✅ Report Sent to {user_email}!")

    # --- TAB 3: DATA CLEANUP & AUDIT (RETAINED) ---
    with t3:
        st.subheader("🧹 Database Health & Reversals")
        admin_entry = st.text_input("Admin Password", type="password")
        if admin_entry == st.secrets["passwords"]["admin_password"]:
            if not contributions_df.empty:
                st.markdown("### ⏪ Quick Undo")
                recent_data = contributions_df.sort_values(by='date', ascending=False).head(10)
                id_to_wipe = st.selectbox("Select Transaction ID:", recent_data['id'].tolist())
                
                if st.button("🗑️ Delete Entry & Log Audit"):
                    try:
                        with conn.session as s:
                            s.execute(text("DELETE FROM contributions WHERE id = :id AND tenant_id = :tid"), {"id": id_to_wipe, "tid": tid})
                            s.execute(text("INSERT INTO audit_logs (action_type, details, tenant_id) VALUES ('MANUAL_DELETE', :d, :tid)"), 
                                      {"d": f"Deleted Trans ID {id_to_wipe}", "tid": tid})
                            s.commit()
                        st.success("Deleted and Audited.")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

    # --- TAB 4: MANAGE PROFILE (RETAINED) ---
    with t4:
        st.subheader("⚙️ Profile Manager")
        if not clients_df.empty:
            target_name = st.selectbox("Select Profile", clients_df['client_name'].tolist())
            c_data = clients_df[clients_df['client_name'] == target_name].iloc[0]
            
            col1, col2 = st.columns([1, 2])
            with col1:
                st.image(c_data['photo_url'], width=150)
            with col2:
                st.write(f"*ID:* {c_data['client_id']}")
                if st.button(f"🗑️ Delete {target_name}"):
                    if st.checkbox("Confirm permanent deletion?"):
                        with conn.session as s:
                            s.execute(text("DELETE FROM clients WHERE client_id = :i AND tenant_id = :tid"), 
                                      {"i": c_data['client_id'], "tid": tid})
                            s.commit()
                        st.cache_data.clear()
                        st.rerun()

    # SUPER ADMIN TAB
    if role == "developer":
        with st.expander("🛡️ DEVELOPER MAINTENANCE"):
            st.write("### 🏢 System-Wide Tenants")
            tenants = pd.DataFrame(sb_client.table("tenants").select("*").execute().data)
            st.dataframe(tenants)

    # --- TAB 5: RESET SYSTEM ---
    with t5:
        st.header("🧨 Factory Reset")
        if st.checkbox("Delete ALL MY business records permanently?"):
            reset_pass = st.text_input("Confirm Admin Password", type="password")
            if st.button("🚨 EXECUTE FULL WIPE"):
                if reset_pass == st.secrets["passwords"]["admin_password"]:
                    with conn.session as s:
                        s.execute(text("DELETE FROM contributions WHERE tenant_id = :tid"), {"tid": tid})
                        s.execute(text("DELETE FROM clients WHERE tenant_id = :tid"), {"tid": tid})
                        s.commit()
                    st.success("Wiped.")
                    st.rerun()