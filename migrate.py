import sqlite3
import pandas as pd
from sqlalchemy import create_engine

# 1. Connect to your LOCAL database
local_conn = sqlite3.connect('susu.db')

# 2. Connect to your CLOUD Supabase (Paste your URI here)
cloud_url = "postgresql://postgres:Rh1AeSxgC06AI1p5@db.xrqcejmtqfrztfwggsbc.supabase.co:5432/postgres"
engine = create_engine(cloud_url)

# 3. Move 'clients' table
print("Moving clients...")
df_clients = pd.read_sql("SELECT * FROM clients", local_conn)
df_clients.to_sql('clients', engine, if_exists='replace', index=False)

# 4. Move 'contributions' table
print("Moving contributions...")
df_contribs = pd.read_sql("SELECT * FROM contributions", local_conn)
df_contribs.to_sql('contributions', engine, if_exists='replace', index=False)

print("✅ Migration Complete! Your data is now in the Cloud.")
local_conn.close()