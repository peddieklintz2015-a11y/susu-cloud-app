import pandas as pd
from sqlalchemy import create_engine
import os
from datetime import datetime
from utils import send_weekly_report  # This pulls from our new file

def run_automated_report():
    try:
        # 1. Connect using GitHub Secrets
        DB_URL = os.getenv("DB_URL")
        engine = create_engine(DB_URL)
        
        # 2. Fetch Data
        df = pd.read_sql("SELECT * FROM contributions", engine)
        
        # 3. Clean Dates
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        
        # 4. Run the Report
        if send_weekly_report(df, manual=False):
            print(f"✅ Success: Report sent at {datetime.now()}")
        else:
            print("❌ Failed: Function returned False")
            
    except Exception as e:
        print(f"🚨 Report failed: {e}")

if __name__ == "__main__":
    run_automated_report()