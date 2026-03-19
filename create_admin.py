import database, models, auth
from sqlalchemy.orm import Session

def create_admin():
    db = database.SessionLocal()
    admin_email = "admin@cvru.ac.in"
    db_user = db.query(models.User).filter(models.User.email == admin_email).first()
    if not db_user:
        hashed_pwd = auth.get_password_hash("admin123")
        new_admin = models.User(
            name="Platform Administrator",
            email=admin_email,
            hashed_password=hashed_pwd,
            role="admin",
            phone_number="0000000000",
            is_verified=True,
            is_suspended=False
        )
        db.add(new_admin)
        db.commit()
        print(f"Admin user created: {admin_email} / admin123")
    else:
        print("Admin user already exists.")
    db.close()

if __name__ == "__main__":
    create_admin()
