"""
Database initialization script
Creates tables and inserts initial data (roles and admin user)
"""
from sqlalchemy.orm import Session
from app.database import engine, Base, SessionLocal
from app.models import Role, User
from app.utils.security import get_password_hash


def init_db():
    """Initialize database with tables and seed data"""
    
    # Create all tables
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully!")
    
    # Create session
    db: Session = SessionLocal()
    
    try:
        # Check if roles already exist
        existing_roles = db.query(Role).count()
        
        if existing_roles == 0:
            print("\nSeeding roles...")
            
            # Create roles
            roles = [
                Role(name="Admin", description="Administrator with full access"),
                Role(name="Sales", description="Sales team member"),
                Role(name="Customer Level 1", description="Customer with Level 1 access"),
                Role(name="Customer Level 2", description="Customer with Level 2 access"),
                Role(name="Customer Level 3", description="Customer with Level 3 access"),
            ]
            
            for role in roles:
                db.add(role)
                print(f"  - Created role: {role.name}")
            
            db.commit()
            print("Roles created successfully!")
            
            # Create default admin user (optional)
            print("\nCreating default admin user...")
            admin_role = db.query(Role).filter(Role.name == "Admin").first()
            
            admin_user = User(
                name="Admin User",
                username="admin",
                password=get_password_hash("admin123"),  # Change this in production!
                role_id=admin_role.id,
                is_active=True
            )
            db.add(admin_user)
            db.commit()
            print("Admin user created successfully!")
            print("  Username: admin")
            print("  Password: admin123")
            print("  ⚠️  Please change the admin password immediately!")
            
        else:
            print("Database already initialized. Skipping seed data.")
    
    except Exception as e:
        print(f"Error initializing database: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    print("=== CRM Database Initialization ===\n")
    init_db()
    print("\n=== Initialization Complete ===")
