import streamlit as st
import pandas as pd
import time
import math
import smtplib
from datetime import datetime
from sqlalchemy import text
from email.message import EmailMessage
from supabase import create_client

# --- 0. MAINTENANCE MODE (SECRET CONTROL) ---
# This stops the app immediately if the secret is set to true
if st.secrets["app_settings"]["maintenance_mode"]:
    st.title("🚧 System Maintenance")
    st.warning("RUCHANET DAILY SUSU is currently undergoing scheduled updates.")
    st.info("We'll be back online shortly! 🙏")
    st.stop()

# --- 1. SETUP ---
st.set_page_config(page_title="RUCHANET DAILY SUSU", layout="wide")

def set_custom_style():
    st.markdown("""
    <style>
    div.stButton > button:first-child { background-color: #FFD700 !important; color: #212529 !important; font-weight: bold !important; border: none !important; }
    [data-testid="stMetricValue"] { color: #FF4500 !important; font-size: 30px !important; }
    [data-testid="stSidebar"] { background-color: #212529 !important; color: #F8F9FA; }
    </style>
    """, unsafe_allow_html=True)

set_custom_style()

# --- 2. DATABASE & CLOUD SETUP ---
conn = st.connection("postgresql", type="sql")

# Initialize Supabase once at the start
try:
    sb_client = create_client(
        st.secrets["supabase_url"], 
        st.secrets["supabase_key"]
    )
except Exception as e:
    st.error(f"Critical Error: Supabase configuration missing! {e}")
    st.stop()

# --- 3. DATA FUNCTIONS ---
@st.cache_data(ttl=60)
def fetch_data():
    try:
        with conn.session as s:
            # Fetching as dictionaries often helps Pandas handle SQL types better
            clients_df = pd.DataFrame(s.execute(text("SELECT * FROM clients")).mappings().all())
            contributions_df = pd.DataFrame(s.execute(
                text("SELECT id, client_name, amount, date, marks_covered, fee FROM contributions")
            ).mappings().all())
            
            if not contributions_df.empty:
                # FIX: Use format='ISO8601' or let pandas infer to handle the timestamps seen in your error
                contributions_df['date'] = pd.to_datetime(contributions_df['date'], errors='coerce')
                contributions_df['amount'] = pd.to_numeric(contributions_df['amount'], errors='coerce').fillna(0)
                contributions_df['fee'] = pd.to_numeric(contributions_df['fee'], errors='coerce').fillna(0)
                contributions_df['marks_covered'] = pd.to_numeric(contributions_df['marks_covered'], errors='coerce').fillna(0)
            
            return clients_df, contributions_df
    except Exception as e:
        st.error(f"Failed to fetch data: {e}")
        return pd.DataFrame(), pd.DataFrame()

def get_next_gen_id(reg_date):
    # Format month and year: e.g., "03/26"
    mm_yy = reg_date.strftime("%m/%y")
    
    try:
        with conn.session as s:
            # Look for IDs ending with the current month/year
            result = s.execute(text("""
                SELECT client_id FROM clients 
                WHERE client_id LIKE :pattern 
                ORDER BY client_id DESC LIMIT 1
            """), {"pattern": f"%/{mm_yy}"}).fetchone()
            
            if result:
                # If result is "005/03/26", take "005", make it 5, add 1 = 6
                last_id = result[0]
                last_num = int(last_id.split('/')[0])
                new_num = last_num + 1
            else:
                # First client of the month
                new_num = 1
                
            # Return formatted as 3 digits: "001/03/26"
            return f"{new_num:03d}/{mm_yy}"
    except Exception as e:
        # We 'use' e here by printing it to the screen
        st.error(f"⚠️ Database Error: {e}") 
        
        # Fallback if database is empty or fails
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
combined_df = pd.merge(contributions, clients[['client_id', 'client_name']], on='client_name', how='left') if not clients.empty else contributions

# --- 6. NAVIGATION ---
menu = ["📊 Dashboard", "💸 Transactions", "📑 Digital Passbook", "🛠 Admin Tools"]
choice = st.sidebar.selectbox("Go To:", menu)

if choice == "📊 Dashboard":
    st.title("📊 Financial Overview")
    if not contributions.empty and len(contributions) > 0:
        total_vault = contributions['amount'].sum()
        total_commissions = contributions['fee'].sum()
        net_liability = total_vault - total_commissions 
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Vault (Cash)", f"GHS {total_vault:,.2f}")
        m2.metric("Org. Commissions", f"GHS {total_commissions:,.2f}")
        m3.metric("Net Client Liability", f"GHS {net_liability:,.2f}")

        chart_df = contributions.copy()
        chart_df['Month'] = chart_df['date'].dt.strftime('%b %Y')
        monthly_profit = chart_df.groupby('Month')['fee'].sum().reset_index()
        st.bar_chart(data=monthly_profit, x='Month', y='fee')
    else:
        st.info("👋 Welcome! Start by registering a client and recording a deposit.")

elif choice == "💸 Transactions":
    st.title("💸 Record Transactions")
    if not clients.empty:
        # 1. Select Client and Get Data
        target = st.selectbox("Select Client", clients['client_name'].tolist())
        client_row = clients[clients['client_name'] == target].iloc[0]
        d_mark = float(client_row['daily_mark'])
        c_phone = str(client_row['phone']) 
        
        user_history = contributions[contributions['client_name'] == target]
        total_saved_ghs = user_history['amount'].sum()
        total_marks_saved = user_history['marks_covered'].sum() 
        
        # --- NEW: PROGRESS TRACKER ---
        # Calculate current cycle progress (0 to 31)
        current_cycle_marks = total_marks_saved % 31
        progress_percent = min(current_cycle_marks / 31, 1.0)
        st.write(f"📊 **Current Month Progress:** {current_cycle_marks}/31 Marks")
        st.progress(progress_percent)
        # -----------------------------

        ttype = st.radio("Type", ["Deposit", "Withdrawal"], horizontal=True)
        can_save = True
        db_amt, db_marks, db_fee = 0.0, 0, 0.0

        if ttype == "Deposit":
            num_marks = st.number_input("Number of Marks to add", min_value=1, step=1)
            db_amt = float(num_marks * d_mark)
            db_marks = num_marks
            st.info(f"Value: GHS {db_amt:,.2f} | Marks to be added: {num_marks}")
        else:
            requested_cash = st.number_input("Cash to Withdraw (GHS)", min_value=0.0,)
            
            # --- NEW: MATH.CEIL FEE CALCULATION ---
            # Charge 1 mark for every month (or part of a month) they have saved
            # e.g., 32 marks = 2 months = 2 * daily_mark fee
            months_count = math.ceil(total_marks_saved / 31) if total_marks_saved > 0 else 1
            db_fee = months_count * d_mark
            # --------------------------------------
            
            total_deduction = requested_cash + db_fee
            db_amt = -requested_cash 
            
            if requested_cash > 0:
                if total_deduction > total_saved_ghs:
                    st.error(f"⚠️ Insufficient Balance! (Total needed: GHS {total_deduction:,.2f})")
                    can_save = False
                else:
                    st.warning(f"Deducting GHS {requested_cash:,.2f} + GHS {db_fee:,.2f} Service Fee ({months_count} months)")

        # 2. Confirm and Save Logic
        if st.button("Confirm & Save") and can_save:
            try:
                now = datetime.now()
                with conn.session as s:
                    s.execute(text("""
                        INSERT INTO contributions (client_name, amount, date, marks_covered, fee) 
                        VALUES (:n, :a, :d, :mc, :f)
                    """), {"n": target, "a": db_amt, "d": now, "mc": db_marks, "f": db_fee})
                    s.commit()

                # --- CALCULATE WHATSAPP DATA ---
                new_balance = total_saved_ghs + db_amt
                formatted_phone = f"233{c_phone[-9:]}" 
                
                receipt_msg = (
                    f"✨ *RUCHANET DAILY SUSU* ✨%0A"
                    f"---------------------------%0A"
                    f"👤 *Client:* {target}%0A"
                    f"📝 *Type:* {ttype}%0A"
                    f"💵 *Amount:* GHS {abs(db_amt):,.2f}%0A"
                    f"🕒 *Time:* {now.strftime('%I:%M %p')}%0A"
                    f"---------------------------%0A"
                    f"⭐ *NEW BALANCE:* GHS {new_balance:,.2f}%0A"
                    f"---------------------------%0A"
                    f"Thank you for saving! 🙏"
                )
                wa_link = f"https://wa.me/{formatted_phone}?text={receipt_msg}"

                # 3. SUCCESS UI
                st.toast(f"✅ {ttype} Recorded! New Balance: GHS {new_balance:,.2f}", icon="💰")
                st.balloons()

                # SHOW WHATSAPP BUTTON
                st.markdown(f"""
                    <a href="{wa_link}" target="_blank">
                        <button style="background-color: #25D366; color: white; padding: 15px; border: none; border-radius: 10px; width: 100%; font-weight: bold; cursor: pointer; font-size: 16px;">
                            🟢 Send WhatsApp Receipt
                        </button>
                    </a>
                """, unsafe_allow_html=True)
                
                time.sleep(1)
                if st.button("Refresh App"):
                    st.rerun()

            except Exception as e:
                st.error(f"🚨 Transaction Failed: {e}")
                st.toast("Error saving to database", icon="❌")
    else:
        st.error("Please register clients in Admin Tools first.")

elif choice == "📑 Digital Passbook":
    # 1. Setup the Print Header (Hidden on web, visible on print)
    current_date = datetime.now().strftime("%d %B, %Y")
    logo_url = "https://raw.githubusercontent.com/peddieklintz2015-a11y/susu-cloud-app/main/logo.jpeg"
    
    st.markdown(f"""
        <style>
        .print-header {{ display: none; }}
        @media print {{
            .print-header {{ display: flex !important; flex-direction: column; align-items: center; text-align: center; margin-bottom: 20px; }}
            .print-header img {{ width: 100px; }}
            section[data-testid="stSidebar"], .stActionButton, header {{ display: none !important; }}
        }}
        </style>
        <div class="print-header">
            <img src="{logo_url}">
            <h1>RUCHANET DAILY SUSU</h1>
            <p>Generated on: {current_date}</p>
        </div>
    """, unsafe_allow_html=True)

    st.title("📑 Client Passbook")
    search = st.text_input("🔍 Search Client Name", placeholder="Enter name...")
    
    if not clients.empty:
        filtered = clients[clients['client_name'].str.contains(search, case=False)] if search else clients
        
        if not filtered.empty:
            target = st.selectbox("View Passbook For:", filtered['client_name'].tolist())
            c_info = clients[clients['client_name'] == target].iloc[0]
            
            # --- Business Logic ---
            user_history = contributions[contributions['client_name'] == target].copy()
            total_marks = user_history['marks_covered'].sum() if not user_history.empty else 0
            current_balance = user_history['amount'].sum() if not user_history.empty else 0.0
            
            # UI Display
            col_a, col_b = st.columns([1, 2])
            with col_a:
                if c_info.get('photo_url'):
                    st.image(c_info['photo_url'], use_container_width=True)
            with col_b:
                st.subheader(f"Account: {target}")
                m1, m2 = st.columns(2)
                m1.metric("💰 Balance", f"GHS {current_balance:,.2f}")
                m2.metric("📅 Marks", f"{total_marks}")

            st.divider()
            
            # --- THE FIX: NEW ACTION ROW ---
            col_s1, col_s2 = st.columns(2)
            with col_s1:
                # WhatsApp Button
                formatted_phone = f"233{str(c_info['phone'])[-9:]}"
                wa_msg = f"📑 RUCHANET PASSBOOK%0AClient: {target}%0ABalance: GHS {current_balance:,.2f}"
                st.markdown(f'<a href="https://wa.me/{formatted_phone}?text={wa_msg}" target="_blank"><button style="background-color: #25D366; color: white; border: none; padding: 10px; border-radius: 8px; width: 100%; cursor: pointer; font-weight: bold;">🟢 WhatsApp</button></a>', unsafe_allow_html=True)
            
            with col_s2:
                # REPLACES PDF FUNCTION: Browser Print Button
                st.markdown("""
                    <button onclick="window.print()" style="background-color: #007bff; color: white; border: none; padding: 10px; border-radius: 8px; width: 100%; cursor: pointer; font-weight: bold;">
                        🖨️ Print / Save PDF
                    </button>
                """, unsafe_allow_html=True)

            # History Table
            if not user_history.empty:
                st.write("### 📝 History")
                user_h_display = user_history.copy()
                user_h_display['date'] = pd.to_datetime(user_h_display['date']).dt.strftime('%Y-%m-%d %H:%M')
                st.dataframe(user_h_display.sort_values(by='date', ascending=False)[['date', 'amount', 'marks_covered', 'fee']], use_container_width=True)
            else:
                st.info("No transaction history yet.") # Added this to close the 'if not user_history.empty'

# --- 3. ADMIN TOOLS & EMAIL ---
elif choice == "🛠 Admin Tools":
    st.title("🛠 Admin Dashboard")
       # FIX: This line defines t4. Ensure it exists before "with t4:"
    t1, t2, t3, t4 = st.tabs(["👤 Registration", "📧 Reports", "🗑 Data Cleanup", "💰 Manage Profile"])
    
    with t1:
        st.subheader("👤 Register New Client")
        photo = st.camera_input("Take Client Photo (Required)")
    
        with st.form("reg_form", clear_on_submit=True):
            name = st.text_input("Full Name")
            phone = st.text_input("Phone Number")
            daily = st.number_input("Daily Mark (GHS)", min_value=5.0, step=1.0)
            reg_date = st.date_input("Registration Date", value=datetime.now())
            
            suggested_id = get_next_gen_id(reg_date)
            st.info(f"Next Available ID: {suggested_id}")
            
            submit = st.form_submit_button("Register to Cloud")
            
            if submit: 
                if not name.strip() or not phone.strip() or photo is None:
                    st.error("❌ All fields (Name, Phone, and Photo) are required")
                else:
                    try:
                        gen_id = get_next_gen_id(reg_date)
                        # Format filename for storage
                        file_path = f"{gen_id.replace('/', '_')}.jpg"
                        
                        # 1. Upload Photo to Supabase Storage
                        sb_client.storage.from_("client-photos").upload(
                            path=file_path,
                            file=photo.getvalue(),
                            file_options={"content-type": "image/jpeg"}
                        )

                        # 2. Construct Public URL
                        p_url = f"{st.secrets['supabase_url']}/storage/v1/object/public/client-photos/{file_path}"

                        # 3. Save to SQL Database
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
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"🚨 Registration Failed: {e}")

    with t3:
        st.subheader("🛑 Restricted Data Cleanup")
        admin_entry = st.text_input("Enter Admin Password", type="password", key="cleanup_pass")
        
        if admin_entry == st.secrets["passwords"]["admin_password"]:
            if not contributions.empty:
                search_term = st.text_input("Filter by Client Name")
                f_df = contributions[contributions['client_name'].str.contains(search_term, case=False)]
                
                if not f_df.empty:
                    options_list = f_df.apply(lambda x: f"{x['date']} | {x['client_name']} | GHS {x['amount']}", axis=1).tolist()
                    to_del = st.selectbox("Select entry to remove", options=options_list)
                    
                    if st.button("🗑️ Permanent Delete"):
                        parts = to_del.split(" | ")
                        with conn.session as s:
                            s.execute(text("DELETE FROM contributions WHERE client_name = :n AND date = :d"),
                                     {"n": parts[1], "d": parts[0]})
                            s.commit()
                        st.rerun()

    with t4:
        st.subheader("⚙️ Secure Client Profile Manager")
        st.error("❗ *CRITICAL AREA*: Deletion removes the client, photo, and history permanently.")

        if not clients.empty:
            search_query = st.text_input("🔍 Search Profile (Name or ID)", key="admin_manage_search")
            
            filtered = clients[
                clients['client_name'].str.contains(search_query, case=False) | 
                clients['client_id'].str.contains(search_query, case=False)
            ]

            if not filtered.empty:
                selected_name = st.selectbox("Select Profile:", filtered['client_name'])
                c_data = filtered[filtered['client_name'] == selected_name].iloc[0]
                target_id = c_data['client_id']
                
                u_history = contributions[contributions['client_name'] == selected_name]
                final_balance = u_history['amount'].sum()
                
                col1, col2 = st.columns([1, 2])
                with col1:
                    if c_data['photo_url']:
                        st.image(c_data['photo_url'], caption=f"ID: {target_id}", use_container_width=True)
                with col2:
                    st.write(f"*Name:* {c_data['client_name']}")
                    st.write(f"*Phone:* {c_data['phone']}")
                    st.write(f"*Payout Due:* GHS {final_balance:,.2f}")

                st.markdown("---")
                
                confirm_check = st.checkbox(f"I confirm I want to wipe {target_id} forever.", key="del_check")
                
                if confirm_check:
                    admin_pass = st.text_input("🔐 Admin Password Required", type="password", key="wipe_pass_input")
                    
                    # ... existing code ...
                    if st.button("💥 AUTHORIZE PERMANENT WIPE"):
                        if admin_pass == st.secrets["passwords"]["admin_password"]:
                            try:
                                    # 1. Storage Cleanup
                                file_path = f"{target_id.replace('/', '_')}.jpg"
                                try:
                                    sb_client.storage.from_("client-photos").remove([file_path])
                                except Exception: # Removed 'as storage_err'
                                    st.warning("Note: Could not delete photo file (it may have been missing).") # Removed 'f'

                                # 2. Database Cleanup
                                with conn.session as s:
                                    s.execute(text("DELETE FROM contributions WHERE client_name = :n"), {"n": selected_name})
                                    s.execute(text("DELETE FROM clients WHERE client_id = :i"), {"i": target_id})
                                    s.commit()

                                # 3. Success Feedback & Audit Email
                                st.toast(f"🗑️ {target_id} wiped successfully.", icon="💥")
                                
                                # Send Audit Email
                                try:
                                    audit_msg = EmailMessage()
                                    audit_msg['Subject'] = f"🚨 SECURITY ALERT: Profile Deleted ({target_id})"
                                    audit_msg['From'] = st.secrets["emails"]["sender_email"]
                                    audit_msg['To'] = st.secrets["emails"]["receiver_email"]
                                    audit_msg.set_content(f"Deleted: {selected_name}\nID: {target_id}\nPayout: GHS {final_balance}\nTime: {datetime.now()}")
                                    
                                    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                                        server.login(st.secrets["emails"]["sender_email"], st.secrets["emails"]["app_password"])
                                        server.send_message(audit_msg)
                                except Exception:
                                    pass # Ensure app doesn't crash if email fails

                                time.sleep(1)
                                st.rerun()
                                
                            except Exception as e:
                                st.error(f"🚨 Wipe Failed: {e}")
                        else:
                            st.error("❌ Incorrect Password.")
            else:
                st.info("No matching profiles.")
        else:
            st.info("Database empty.")