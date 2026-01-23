"""
Create admin user
"""
from app.database import SessionLocal
from app.models import User, Role
from app.utils.security import get_password_hash


def create_admin():
    """Create admin user"""
    db = SessionLocal()
    
    try:
        # Check if admin already exists
        existing_admin = db.query(User).filter(User.username == "admin").first()
        
        if existing_admin:
            print("Admin user already exists!")
            print(f"  Username: {existing_admin.username}")
            return
        
        # Get Admin role
        admin_role = db.query(Role).filter(Role.name == "Admin").first()
        
        if not admin_role:
            print("Error: Admin role not found!")
            return
        
        # Create admin user
        admin_user = User(
            name="Admin User",
            username="admin",
            password=get_password_hash("admin123"),
            role_id=admin_role.id,
            is_active=True
        )
        
        db.add(admin_user)
        db.commit()
        
        print("✅ Admin user created successfully!")
        print("  Username: admin")
        print("  Password: admin123")
        print("  ⚠️  Please change the password after first login!")
        
    except Exception as e:
        print(f"Error creating admin user: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    create_admin()
