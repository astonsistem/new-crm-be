"""
Script to create an admin user account
Run this script to create or reset the admin account
"""
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import User, Role
from app.utils.security import get_password_hash
import getpass


def create_admin():
    """Create or update admin user"""
    db = SessionLocal()
    
    try:
        print("=" * 60)
        print("CREATE ADMIN ACCOUNT")
        print("=" * 60)
        
        # Get admin details from user input
        admin_name = input("Enter admin name (default: Admin): ").strip() or "Admin"
        admin_username = input("Enter admin username (default: admin): ").strip() or "admin"
        
        # Get password securely
        while True:
            admin_password = getpass.getpass("Enter admin password (min 6 chars): ")
            if len(admin_password) >= 6:
                confirm_password = getpass.getpass("Confirm password: ")
                if admin_password == confirm_password:
                    break
                else:
                    print("❌ Passwords don't match. Try again.\n")
            else:
                print("❌ Password must be at least 6 characters.\n")
        
        # Check if Admin role exists
        admin_role = db.query(Role).filter(Role.name == "Admin").first()
        
        if not admin_role:
            print("\n⚠️  Admin role not found. Creating Admin role...")
            admin_role = Role(
                name="Admin",
                description="Administrator with full access",
                permissions=[],  # Admin has all permissions by default
                scope="ADMIN"
            )
            db.add(admin_role)
            db.commit()
            db.refresh(admin_role)
            print("✅ Admin role created")
        
        # Check if admin user already exists
        existing_admin = db.query(User).filter(User.username == admin_username).first()
        
        if existing_admin:
            print(f"\n⚠️  User '{admin_username}' already exists. Updating password...")
            existing_admin.password = get_password_hash(admin_password)
            existing_admin.name = admin_name
            existing_admin.role_id = admin_role.id
            existing_admin.customer_id = None  # Admin users don't have customer_id
            existing_admin.is_active = True
            db.commit()
            print(f"✅ Admin user '{admin_username}' updated successfully!")
        else:
            # Create new admin user
            hashed_password = get_password_hash(admin_password)
            
            admin_user = User(
                name=admin_name,
                username=admin_username,
                password=hashed_password,
                role_id=admin_role.id,
                customer_id=None,  # Admin users don't have customer_id
                is_active=True
            )
            
            db.add(admin_user)
            db.commit()
            db.refresh(admin_user)
            
            print(f"\n✅ Admin user created successfully!")
        
        print("\n" + "=" * 60)
        print("ADMIN ACCOUNT DETAILS")
        print("=" * 60)
        print(f"Name:     {admin_name}")
        print(f"Username: {admin_username}")
        print(f"Role:     {admin_role.name} (Scope: {admin_role.scope})")
        print(f"Status:   Active")
        print("=" * 60)
        print("\n✅ You can now login with these credentials!")
        
    except Exception as e:
        print(f"\n❌ Error creating admin user: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    create_admin()
