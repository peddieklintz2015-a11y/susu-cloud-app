import pandas as pd
from datetime import datetime
import smtplib
from email.message import EmailMessage # <--- THIS FIXES THE RED ERROR
import streamlit as st  # <--- THIS FIXES THE 'st' ERRORS
import hashlib

def hash_password(password):
    """Encodes password for security."""
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_password_auth(password, hashed):
    """Checks if entered password matches the cloud record."""
    return hash_password(password) == hashed

def send_weekly_report(contributions_df, manual=False, target_email=None):
    try:
        now_dt = datetime.now()
        today = now_dt.date()
        
        # Ensure 'date' is datetime objects for filtering
        if not pd.api.types.is_datetime64_any_dtype(contributions_df['date']):
            contributions_df['date'] = pd.to_datetime(contributions_df['date'])
            
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
        
        # Calculate daily summaries
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
                    <h1 style="color: #FFD700; margin: 0;">{st.session_state.get('biz_name', 'RUCHANET')} WEEKLY SUMMARY</h1>
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
                </div>
            </body>
        </html>
        """

        # Credentials
        SENDER = st.secrets["emails"]["sender_email"]
        APP_PW = st.secrets["emails"]["app_password"]
        
        # Use target_email from session state if provided, else use default receiver
        RECEIVER = target_email if target_email else st.secrets["emails"]["receiver_email"]

        msg = EmailMessage()
        msg['Subject'] = f"📊 {'AUTO' if not manual else 'MANUAL'} Report: {st.session_state.get('biz_name')} ({start_of_week.strftime('%d %b')})"
        msg['From'] = SENDER
        msg['To'] = RECEIVER
        msg.add_alternative(html_content, subtype='html')

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(SENDER, APP_PW)
            server.send_message(msg)
        return True
    except Exception as e:
        if manual: 
            st.error(f"Email Error: {e}")
        return False