import psycopg2
import os
from dotenv import load_dotenv

def init_db():
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")
    
    if not db_url:
        print("Error: DATABASE_URL not found in .env")
        return

    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        
        print(f"Connecting to database...")
        
        # Read the SQL schema file
        with open("schema_middleware.sql", "r", encoding="utf-8") as f:
            sql_script = f.read()
            
        print("Executing schema_middleware.sql...")
        cur.execute(sql_script)
        conn.commit()
        
        print("✅ Database tables created successfully!")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error initializing database: {e}")

if __name__ == "__main__":
    init_db()
