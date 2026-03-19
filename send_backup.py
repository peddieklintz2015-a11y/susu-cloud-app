import pandas as pd
from sqlalchemy import create_engine
import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

# 1. Get secrets from GitHub Environment
db_url = os.getenv("SUPABASE_URL")
email_pass = os.getenv("EMAIL_PASSWORD")
my_email = "peddieklintz2015@gmail.com" # <--- Put your actual Gmail here

def run_backup():
    try:
        # Connect and download
        engine = create_engine(db_url)
        df = pd.read_sql("SELECT * FROM contributions", engine)
        df.to_csv("susu_backup.csv", index=False)

        # Prepare Email
        msg = MIMEMultipart()
        msg['From'] = my_email
        msg['To'] = my_email
        msg['Subject'] = f"📊 Weekly Susu Backup - {pd.Timestamp.now().strftime('%Y-%m-%d')}"

        # Attach CSV
        with open("susu_backup.csv", "rb") as f:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', 'attachment; filename="susu_backup.csv"')
            msg.attach(part)

        # Send via Google SMTP
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(my_email, email_pass)
        server.send_message(msg)
        server.quit()
        print("Backup sent successfully!")

    except Exception as e:
        print(f"Error: {e}")

if _name_ == "_main_":
    run_backup()
