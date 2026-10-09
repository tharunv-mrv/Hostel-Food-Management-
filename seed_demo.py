"""
Helper script to populate realistic demo sample data for presentations and testing.
Run: python seed_demo.py
"""

import json
import numpy as np
from datetime import datetime
from app import app, db
from models import AdminUser, Student, FeePayment, MealMenu, FoodEntry

def seed():
    with app.app_context():
        # Ensure default admin exists
        admin = AdminUser.query.filter_by(username="admin").first()
        if not admin:
            admin = AdminUser(username="admin", email="admin@canteen.edu", role="admin")
            admin.set_password("Admin@123")
            db.session.add(admin)

        # Check if students already exist
        if Student.query.count() > 0:
            print("[Seed] Students already exist in database. Skipping student seed.")
            return

        print("[Seed] Populating demo sample students with room, fee, and biometric data...")

        # Synthetic 128-d vectors for demo students
        vec1 = np.random.randn(128).astype(np.float32)
        vec1 = (vec1 / np.linalg.norm(vec1)).tolist()

        vec2 = np.random.randn(128).astype(np.float32)
        vec2 = (vec2 / np.linalg.norm(vec2)).tolist()

        s1 = Student(
            student_id="1XX23AIML001",
            name="Tharun Kumar",
            srn="PES12023001",
            phone_number="9876543210",
            room_number="302",
            room_sharing_type="Double",
            room_occupants=2,
            branch="AIML",
            year="1st Year",
            hostel="Kaveri Hostel",
            total_hostel_fees=75000.0,
            total_fees_paid=75000.0,
            last_payment_date=datetime.now().strftime('%Y-%m-%d'),
            face_encoding=json.dumps(vec1),
            active=True,
            meal_access_enabled=True
        )
        s1.set_password("Student@123")

        s2 = Student(
            student_id="1XX23CSE042",
            name="Ananya Sharma",
            srn="PES12023042",
            phone_number="9876543211",
            room_number="204",
            room_sharing_type="Triple",
            room_occupants=3,
            branch="CSE",
            year="2nd Year",
            hostel="Ganga Hostel",
            total_hostel_fees=75000.0,
            total_fees_paid=50000.0,  # 25,000 pending
            last_payment_date=datetime.now().strftime('%Y-%m-%d'),
            face_encoding=json.dumps(vec2),
            active=True,
            meal_access_enabled=True
        )
        s2.set_password("Student@123")

        db.session.add_all([s1, s2])
        db.session.commit()

        # Add fee payment records
        p1 = FeePayment(
            student_id="1XX23AIML001",
            student_name="Tharun Kumar",
            amount=75000.0,
            payment_date=datetime.now().strftime('%Y-%m-%d'),
            payment_method="UPI",
            reference_no="UPI-THARUN-001",
            remarks="Full annual hostel fee clearance",
            created_by="Admin"
        )

        p2 = FeePayment(
            student_id="1XX23CSE042",
            student_name="Ananya Sharma",
            amount=50000.0,
            payment_date=datetime.now().strftime('%Y-%m-%d'),
            payment_method="Net Banking",
            reference_no="NEFT-ANANYA-002",
            remarks="Semester 1 installment",
            created_by="Admin"
        )
        db.session.add_all([p1, p2])
        db.session.commit()

        # Add sample past meal entry
        today_str = datetime.now().strftime('%Y-%m-%d')
        entry = FoodEntry(
            student_id="1XX23CSE042",
            student_name="Ananya Sharma",
            srn="PES12023042",
            room_number="204",
            meal="Breakfast",
            entry_date=today_str,
            entry_time="08:15:30 AM",
            timestamp=datetime.now(),
            verification_method="face",
            status="Approved"
        )
        db.session.add(entry)
        db.session.commit()

        print("[Seed] Successfully added demo residents, fee accounts, and meal history!")

if __name__ == '__main__':
    seed()
