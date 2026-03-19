import streamlit as st
import pandas as pd
from sqlalchemy import text
from datetime import datetime

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
            pwd = st.text_input("Admin Password", type="password")
            submit_button = st.form_submit_button("Log In")
            
            if submit_button:
                if pwd == st.secrets["password"]:
                    st.session_state["password_correct"] = True
                    st.rerun()
                else:
                    st.error("❌ Invalid Password")
        return False
    return True

# Stop the app here if not logged in
if not check_password():
    st.stop()

# --- 1. INITIALIZE CLOUD CONNECTION ---
# This connects to your Supabase via the secrets you set up
conn = st.connection("postgresql",type="sql")

# --- 2. SECURITY GATE ---
def check_password():
    if "password_correct" not in st.session_state:
        st.title("🔐 Ruchanet Susu Security")
        
        # Wrapping this in a form allows the "Enter" key to work
        with st.form("login_form"):
            pwd = st.text_input("Admin Password", type="password")
            submit_button = st.form_submit_button("Log In")
            
            if submit_button:
                if pwd == st.secrets["password"]:
                    st.session_state["password_correct"] = True
                    st.rerun()
                else:
                    st.error("❌ Invalid Password")
        return False
    return True

# --- 3. UI SETUP ---
st.set_page_config(page_title="RUCHANET DAILY SUSU", page_icon="🏦", layout="wide")

# --- 4. NAVIGATION ---
st.sidebar.title("🏦 Main Menu")
choice = st.sidebar.radio("Go To:", [
    "📊 Business Dashboard", 
    "👤 Register New Client", 
    "💸 Record Transaction", 
    "🔎 Digital Passbook", 
    "🗑️ Admin Tools"
])

# --- 5. MODULES ---

# --- DASHBOARD ---
if choice == "📊 Business Dashboard":
    st.title("📊 Financial Overview")
    df = conn.query("SELECT * FROM contributions", ttl=0)
    
    if not df.empty:
        total_vault = df['amount'].sum()
        total_fees = df['fee'].sum()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("💰 Total Vault", f"GHS {total_vault:,.2f}")
        c2.metric("📈 Total Profit (Fees)", f"GHS {total_fees:,.2f}")
        c3.metric("🏦 Net Liability", f"GHS {(total_vault - total_fees):,.2f}")
        
        st.divider()
        st.subheader("Recent Activity")
        st.dataframe(df.sort_values(by='date', ascending=False), use_container_width=True)
    else:
        st.info("No data found in the cloud yet.")

# --- REGISTRATION ---
elif choice == "👤 Register New Client":
        st.title("👤 Register New Client")
        
        # 1. Generate ID (001/03/2026)
        try:
            res = conn.query("SELECT COUNT(*) as count FROM clients", ttl=0)
            next_num = int(res['count'].iloc[0]) + 1
            gen_id = f"{next_num:03d}/{datetime.now().strftime('%m/%Y')}"
            st.info(f"Generated ID: *{gen_id}*")
        except:
            gen_id = "001/" + datetime.now().strftime('%m/%Y')

        with st.form("reg_form", clear_on_submit=True):
            name = st.text_input("Full Name")
            phone = st.text_input("Phone Number")
            daily = st.number_input("Daily Mark (GHS)", min_value=1.0, step=1.0)
            
            # Use camera_input for instant photos!
            photo = st.camera_input("Take Client Photo")
            
            if photo is not None:
                # Check file size (in bytes)
                file_size = photo.size / 1024  # Convert to KB
                if file_size > 500:
                    st.warning(f"⚠️ This photo is {file_size:.1f}KB. Try to stay under 500KB to save space.")
            
            if st.form_submit_button("Register to Cloud"):
                p_url = None
                # If they took a photo, we link the URL (Upload requires 'supabase' library, 
                # so for now we store the public URL path based on their ID)
                if photo:
                    p_url = f"https://xrqcejmtqfrztfwggsbc.supabase.co/storage/v1/object/public/client-photos/{gen_id.replace('/', '_')}.jpg"
                
                try:
                    with conn.session as s:
                        s.execute(
                            text("INSERT INTO clients (client_id, client_name, phone, daily_mark, photo_url) VALUES (:i, :n, :p, :d, :u)"),
                            {"i": gen_id, "n": name, "p": phone, "d": daily, "u": p_url}
                        )
                        s.commit()
                    st.success(f"✅ {name} registered successfully!")
                    st.balloons()
                except Exception as e:
                    st.error(f"Error: {e}")

# --- TRANSACTIONS (WITH 31-DAY & OLD DATA LOGIC) ---
elif choice == "💸 Record Transaction":
        st.title("💸 Transaction Entry")

        # 1. Download the client list
        clients = conn.query("SELECT client_name, daily_mark FROM clients", ttl=0)

        # 2. Check the list
        if not clients.empty:
            target = st.selectbox("Select Client", clients['client_name'].tolist())
            d_mark = clients[clients['client_name'] == target]['daily_mark'].iloc[0]
            
            col1, col2 = st.columns(2)
            with col1:
                ttype = st.radio("Transaction Type", ["Deposit", "Withdrawal"], horizontal=True)
                num_marks = st.number_input("Number of Marks", min_value=1, step=1)
                calculated_amt = float(num_marks * d_mark)
                st.info(f"💰 Rate: {calculated_amt:.2f} GHS")

        with col2:
            t_date = st.date_input("Transaction Date", value=datetime.now())
            is_old = st.checkbox("📍 Migration: Old deposit from paper book")

        if st.button("Confirm & Save"):
            try:
                p_day = t_date.day
                m_year = t_date.strftime("%m/%Y")
                
                # Make it negative if it's a withdrawal
                final_val = calculated_amt if ttype == "Deposit" else -calculated_amt

                with conn.session as s:
                    s.execute(
                        text("""
                            INSERT INTO contributions (
                                client_name, amount, date, month_year, 
                                passbook_day, marks_covered
                            ) 
                            VALUES (:n, :a, :d, :my, :pd, :mc)
                        """),
                        {
                            "n": target,
                            "a": final_val,
                            "d": t_date.strftime('%Y-%m-%d'),
                            "my": m_year,
                            "pd": int(p_day),
                            "mc": int(num_marks)
                        }
                    )
                    s.commit()
                
                st.success(f"✅ Saved {num_marks} marks ({calculated_amt} GHS) for {target}")
                st.balloons()
            except Exception as e:
                st.error(f"Error: {e}")

# --- PASSBOOK VIEW ---
elif choice == "🔎 Digital Passbook":
    st.title("🔎 Digital Passbook Search")
    profile = conn.query(f"SELECT * FROM clients WHERE client_name = '{target}'", ttl=0)
        
    if not profile.empty:
            c1, c2 = st.columns([1, 2])
            with c1:
                image_url = profile['photo_url'].iloc[0]
                if image_url:
                    st.image(image_url, width=150, caption=f"ID: {profile['client_id'].iloc[0]}")
                else:
                    st.warning("No photo available.")
            with c2:
                st.write(f"*Full Name:* {profile['client_name'].iloc[0]}")
                st.write(f"*ID:* {profile['client_id'].iloc[0]}")
                st.write(f"*Daily Mark:* GHS {profile['daily_mark'].iloc[0]}")

# Filter data for just this client
client_history = conn.query(f"SELECT date, amount, marks_covered FROM contributions WHERE client_name = '{target}'", ttl=0)

if not client_history.empty:
    st.table(client_history) # Shows a clean list
    
    # Simple Download for the Client
    client_csv = client_history.to_csv(index=False).encode('utf-8')
    st.download_button(
        label=f"📄 Download {target}'s Statement",
        data=client_csv,
        file_name=f"{target}_statement.csv",
        mime='text/csv',
    )

# --- DELETE / ADMIN ---
elif choice == "🗑️ Admin Tools":
    st.title("🗑️ Administrative Controls")
    st.warning("Deletion is permanent and cannot be undone.")
    
    clients = conn.query("SELECT client_name FROM clients", ttl=0)
    if not clients.empty:
        to_delete = st.selectbox("Select Client to DELETE", clients['client_name'].tolist())
        confirm = st.checkbox(f"I am sure I want to delete {to_delete}")
        
        if st.button("EXECUTE PERMANENT DELETE") and confirm:
            with conn.session as s:
                # Delete from both tables
                s.execute(text("DELETE FROM contributions WHERE client_name = :n"), params={"n": to_delete})
                s.execute(text("DELETE FROM clients WHERE client_name = :n"), params={"n": to_delete})
                s.commit()
            st.success(f"💥 {to_delete} has been removed from the cloud.")
            st.rerun()

            # Get all data from the cloud
all_data = conn.query("SELECT * FROM contributions", ttl=0)

if not all_data.empty:
    # Convert data to a CSV file (Excel friendly)
    csv = all_data.to_csv(index=False).encode('utf-8')
    
    st.download_button(
        label="📥 Download Full Database Backup",
        data=csv,
        file_name=f"susu_backup_{datetime.now().strftime('%Y-%m-%d')}.csv",
        mime='text/csv',
    )