import streamlit as st
import io
import pandas as pd
from sqlalchemy import text
from datetime import datetime
import smtplib
from email.message import EmailMessage
import math

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

# --- 2. DATABASE ---
conn = st.connection("postgresql", type="sql")

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
    if not contributions.empty:
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
        st.info("No records yet.")

elif choice == "💸 Transactions":
    st.title("💸 Record Transactions")
    if not clients.empty:
        target = st.selectbox("Select Client", clients['client_name'].tolist())
        client_row = clients[clients['client_name'] == target].iloc[0]
        d_mark = float(client_row['daily_mark'])
        
        user_history = contributions[contributions['client_name'] == target]
        total_saved_ghs = user_history['amount'].sum()
        total_marks_saved = user_history['marks_covered'].sum() 
        
        ttype = st.radio("Type", ["Deposit", "Withdrawal"], horizontal=True)
        can_save = True
        db_amt, db_marks, db_fee = 0.0, 0, 0.0

        if ttype == "Deposit":
            num_marks = st.number_input("Number of Marks", min_value=1, step=1)
            db_amt = float(num_marks * d_mark)
            db_marks = num_marks
            st.info(f"Value: GHS {db_amt:,.2f}")
        else:
            requested_cash = st.number_input("Cash to Withdraw (GHS)", min_value=0.0)
            total_months = math.ceil(total_marks_saved / 31)
            db_fee = total_months * d_mark
            total_deduction = requested_cash + db_fee
            db_amt = -requested_cash
            
            if total_deduction > total_saved_ghs and requested_cash > 0:
                st.error("⚠️ Insufficient Balance!")
                can_save = False
            else:
                st.write(f"Deducting GHS {requested_cash:,.2f} + GHS {db_fee:,.2f} Fee")

        if st.button("Confirm & Save") and can_save:
            try:
                with conn.session as s:
                    s.execute(text("INSERT INTO contributions (client_name, amount, date, marks_covered, fee) VALUES (:n, :a, :d, :mc, :f)"),
                        {"n": target, "a": db_amt, "d": datetime.now(), "mc": db_marks, "f": db_fee})
                    s.commit()
                st.success(f"Transaction recorded for {target}")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")
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
    
    # Define tabs
    t1, t2, t3, t4 = st.tabs(["👤 Registration", "📧 Reports", "🗑 Data Cleanup", "💰 Commission Tracker & Client Search"])
    
    # --- TAB 1: REGISTRATION ---
    with t1:
        st.subheader("👤 Register New Client")
        
        # 1. Capture Photo (Indented inside t1)
        photo = st.camera_input("Take Client Photo (Required)")

        # 2. Registration Form (Indented inside t1)
        with st.form("reg_form", clear_on_submit=True):
            name = st.text_input("Full Name")
            phone = st.text_input("Phone Number (10 Digits)")
            daily = st.number_input("Daily Mark (GHS)", min_value=5.0, step=1.0)
            reg_date = st.date_input("Registration Date", value=datetime.now())
            
            submit = st.form_submit_button("Register to Cloud")
            
            if submit: 
                if not name.strip() or not phone.strip() or photo is None:
                    st.error("❌ All fields (Name, Phone, and Photo) are required")
                else:
                    try:
                        with conn.session as s:
                            # --- DUPLICATE CHECK ---
                            check_query = text("SELECT client_name FROM clients WHERE phone = :p")
                            existing = s.execute(check_query, {"p": phone.strip()}).fetchone()
                            
                            if existing:
                                st.error(f"🚫 Error: Phone number already registered to *{existing[0]}*")
                            else:
                                # 1. Generate ID
                                gen_id = get_next_gen_id(reg_date)

                                # 2. Supabase Upload
                                from supabase import create_client
                                sb_client = create_client(st.secrets["supabase_url"], st.secrets["supabase_key"])

                                file_path = f"{gen_id.replace('/', '_')}.jpg"
                                sb_client.storage.from_("client-photos").upload(
                                    path=file_path,
                                    file=photo.getvalue(),
                                    file_options={"content-type": "image/jpeg"}
                                )

                                # 3. Public URL
                                p_url = f"{st.secrets['supabase_url']}/storage/v1/object/public/client-photos/{file_path}"

                                # 4. Database Insert
                                s.execute(text("""
                                    INSERT INTO clients (client_id, client_name, phone, daily_mark, photo_url)
                                    VALUES (:i, :n, :p, :d, :u)
                                """), {"i": gen_id, "n": name.strip(), "p": phone.strip(), "d": daily, "u": p_url})
                                s.commit()
                                
                                st.success(f"✅ Registered {name} successfully! ID: {gen_id}")
                                st.balloons()
                                st.rerun()
                    except Exception as e:
                        st.error(f"🚨 Registration Failed: {e}")

    # --- TAB 2: REPORTS ---
    with t2:
        st.subheader("📧 Business intelligence & Backups")
        
        col_rep, col_dl = st.columns(2)
        
        with col_rep:
            st.info("Management Reporting")
            if st.button("📧 Send Professional Email Report"):
                try:
                    total_savings = contributions['amount'].sum()
                    total_commissions = contributions['fee'].sum()
                    
                    html_content = f"""
                    <html>
                        <body style="font-family: Arial, sans-serif;">
                            <h2 style="color: #FFD700; background: #212529; padding: 10px;">RUCHANET DAILY SUSU</h2>
                            <p><b>Total Vault:</b> GHS {total_savings:,.2f}</p>
                            <p><b>Total Fees:</b> GHS {total_commissions:,.2f}</p>
                            <p>Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
                        </body>
                    </html>
                    """
                    msg = EmailMessage()
                    msg['Subject'] = f"📊 RUCHANET Summary {datetime.now().strftime('%d %b')}"
                    msg['From'] = st.secrets["emails"]["sender_email"]
                    msg['To'] = st.secrets["emails"]["receiver_email"]
                    msg.add_alternative(html_content, subtype='html')

                    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                        server.login(st.secrets["emails"]["sender_email"], st.secrets["emails"]["app_password"])
                        server.send_message(msg)
                    st.success("✅ Email Sent!")
                except Exception as e:
                    st.error(f"Email failed: {e}") # This uses 'e' to clear your VS Code warning

        with col_dl:
            st.info("Offline Data Backup")
            # Create Excel File in memory
            if not clients.empty:
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    clients.to_excel(writer, index=False, sheet_name='All_Clients')
                    if not contributions.empty:
                        contributions.to_excel(writer, index=False, sheet_name='Contributions')
                
                st.download_button(
                    label="📥 Download All Data (Excel)",
                    data=buffer.getvalue(),
                    file_name=f"Ruchanet_Backup_{datetime.now().strftime('%Y_%m_%d')}.xlsx",
                    mime="application/vnd.ms-excel"
                )
            else:
                st.warning("No data to download.")

    # --- TAB 3: DATA CLEANUP ---
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
                        st.session_state['undo_info'] = to_del
                        parts = to_del.split(" | ")
                        with conn.session as s:
                            s.execute(text("DELETE FROM contributions WHERE client_name = :n AND date = :d"),
                                     {"n": parts[1], "d": parts[0]})
                            s.commit()
                        st.success("Deleted. Rerunning...")
                        st.rerun()

    # --- TAB 4: COMMISSION TRACKER ---
    with t4:
        st.subheader("💰 Commission & Client Search")
        if not clients.empty:
            search_query = st.text_input("🔍 Search Client by Name or ID")
            filtered_clients = clients[
                clients['client_name'].str.contains(search_query, case=False) | 
                clients['client_id'].str.contains(search_query, case=False)
            ]

            if not filtered_clients.empty:
                selected_name = st.selectbox("Select client", filtered_clients['client_name'])
                c_data = clients[clients['client_name'] == selected_name].iloc[0]
                
                col1, col2 = st.columns([1, 2])
                with col1:
                    st.image(c_data['photo_url'], caption=f"ID: {c_data['client_id']}", use_container_width=True)
                with col2:
                    st.markdown(f"### {c_data['client_name']}")
                    u_history = contributions[contributions['client_name'] == selected_name]
                    total_m = u_history['marks_covered'].sum()
                    fees_paid = u_history['fee'].sum()
                    
                    import math
                    total_comm_earned = math.ceil(total_m / 31) * float(c_data['daily_mark'])
                    pending_comm = total_comm_earned - fees_paid
                    
                    st.metric("Pending Commission", f"GHS {max(0, pending_comm):,.2f}")
                    st.progress(min((total_m % 31) / 31, 1.0), text=f"{total_m % 31}/31 marks to next fee")
            else:
                st.warning("No clients match your search.")