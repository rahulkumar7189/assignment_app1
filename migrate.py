from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

def migrate():
    # Helper to add column if it doesn't exist
    def add_column_if_not_exists(table, column, type_def):
        with engine.connect() as conn:
            try:
                # Check if column exists
                res = conn.execute(text(f"""
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name='{table}' AND column_name='{column}';
                """))
                if res.fetchone():
                    print(f"Column {column} already exists in {table}.")
                    return

                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {type_def};"))
                conn.commit()
                print(f"Added column {column} to {table}.")
            except Exception as e:
                print(f"Error processing {column} on {table}: {e}")

    print("Starting migrations...")
    
    # Users table updates
    add_column_if_not_exists("users", "phone_number", "VARCHAR")
    add_column_if_not_exists("users", "is_suspended", "BOOLEAN DEFAULT FALSE")
    add_column_if_not_exists("users", "is_verified", "BOOLEAN DEFAULT FALSE")

    # Help requests table updates
    add_column_if_not_exists("help_requests", "advance_paid", "BOOLEAN DEFAULT FALSE")
    add_column_if_not_exists("help_requests", "is_urgent_print", "BOOLEAN DEFAULT FALSE")

    # Create new tables
    with engine.connect() as conn:
        try:
            print("Checking tables...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS activity_logs (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    action VARCHAR,
                    details TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))
            
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS system_settings (
                    id SERIAL PRIMARY KEY,
                    allowed_email_domain VARCHAR DEFAULT 'cvru.ac.in',
                    admin_approval_required BOOLEAN DEFAULT FALSE,
                    commission_percentage FLOAT DEFAULT 10.0,
                    payment_system_enabled BOOLEAN DEFAULT TRUE,
                    platform_notice TEXT
                );
            """))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS milestones (
                    id SERIAL PRIMARY KEY,
                    request_id INTEGER REFERENCES help_requests(id),
                    amount FLOAT,
                    description TEXT,
                    status VARCHAR DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS disputes (
                    id SERIAL PRIMARY KEY,
                    request_id INTEGER REFERENCES help_requests(id),
                    raised_by_id INTEGER REFERENCES users(id),
                    reason TEXT,
                    status VARCHAR DEFAULT 'open',
                    admin_notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS marketplace_items (
                    id SERIAL PRIMARY KEY,
                    title VARCHAR,
                    description TEXT,
                    file_path VARCHAR,
                    price FLOAT DEFAULT 0.0,
                    item_type VARCHAR,
                    admin_id INTEGER REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))
            
            # Default settings
            res = conn.execute(text("SELECT COUNT(*) FROM system_settings"))
            if res.scalar() == 0:
                conn.execute(text("INSERT INTO system_settings (allowed_email_domain) VALUES ('cvru.ac.in')"))
                print("Inserted default system settings.")

            conn.commit()
            print("Completed table checks.")
        except Exception as e:
            print(f"Error creating tables: {e}")

    print("Migrations completed successfully.")

if __name__ == "__main__":
    migrate()
