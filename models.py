import json
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class AdminUser(db.Model):
    """Administrator user model for role-based authentication."""
    __tablename__ = 'admin_users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(100), nullable=True)
    role = db.Column(db.String(20), default='admin', nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'role': self.role,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }


class Student(db.Model):
    """Registered student model with comprehensive academic, fee, and biometric details."""
    __tablename__ = 'students'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    srn = db.Column(db.String(50), unique=True, nullable=True, index=True)
    phone_number = db.Column(db.String(20), nullable=True)
    room_number = db.Column(db.String(20), nullable=True)
    room_sharing_type = db.Column(db.String(30), default='Double')
    room_occupants = db.Column(db.Integer, default=2)
    admission_date = db.Column(db.String(15), nullable=True)

    branch = db.Column(db.String(50), nullable=False)
    year = db.Column(db.String(20), nullable=False)
    hostel = db.Column(db.String(50), nullable=False)

    # Fee Account Fields
    total_hostel_fees = db.Column(db.Float, default=75000.0, nullable=False)
    total_fees_paid = db.Column(db.Float, default=0.0, nullable=False)
    last_payment_date = db.Column(db.String(15), nullable=True)

    # Biometrics & Access Controls
    face_encoding = db.Column(db.Text, nullable=True)  # JSON-serialized 128-float list
    photo_preview = db.Column(db.Text, nullable=True)   # Base64 thumbnail
    active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    meal_access_enabled = db.Column(db.Boolean, default=True, nullable=False, index=True)
    meal_restriction_reason = db.Column(db.String(255), default='None')

    # Student portal credentials
    password_hash = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    @property
    def pending_fees(self):
        """Calculate pending hostel balance."""
        diff = self.total_hostel_fees - self.total_fees_paid
        return round(max(0.0, diff), 2)

    @property
    def fee_status(self):
        """Fee payment classification: PAID, PARTIALLY PAID, UNPAID, OVERPAID."""
        diff = self.total_hostel_fees - self.total_fees_paid
        if diff < 0:
            return 'OVERPAID'
        elif diff == 0:
            return 'PAID'
        elif self.total_fees_paid > 0:
            return 'PARTIALLY PAID'
        else:
            return 'UNPAID'

    @property
    def has_face_enrolled(self):
        return bool(self.face_encoding)

    def to_dict(self, include_encoding=False, mask_phone=False):
        """Serialize student data for JSON response, protecting sensitive credentials."""
        phone_display = self.phone_number
        if mask_phone and self.phone_number and len(self.phone_number) >= 4:
            phone_display = '*' * (len(self.phone_number) - 4) + self.phone_number[-4:]

        data = {
            'id': self.id,
            'student_id': self.student_id,
            'name': self.name,
            'srn': self.srn or self.student_id,
            'phone_number': phone_display,
            'room_number': self.room_number or '--',
            'room_sharing_type': self.room_sharing_type or 'Standard',
            'room_occupants': self.room_occupants or 1,
            'admission_date': self.admission_date or '--',
            'branch': self.branch,
            'year': self.year,
            'hostel': self.hostel,
            'total_hostel_fees': round(self.total_hostel_fees, 2),
            'total_fees_paid': round(self.total_fees_paid, 2),
            'pending_fees': self.pending_fees,
            'fee_status': self.fee_status,
            'last_payment_date': self.last_payment_date or '--',
            'active': self.active,
            'meal_access_enabled': self.meal_access_enabled,
            'meal_restriction_reason': self.meal_restriction_reason or 'None',
            'has_face_enrolled': self.has_face_enrolled,
            'photo_preview': self.photo_preview,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }
        if include_encoding:
            data['face_encoding'] = self.face_encoding
        return data


class FeePayment(db.Model):
    """Auditable fee payment transaction record."""
    __tablename__ = 'fee_payments'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(50), nullable=False, index=True)
    student_name = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.String(15), nullable=False, index=True)  # YYYY-MM-DD
    payment_method = db.Column(db.String(30), default='UPI') # UPI, Cash, Card, Net Banking
    reference_no = db.Column(db.String(100), nullable=True)  # Receipt or Bank Ref
    remarks = db.Column(db.String(255), nullable=True)
    created_by = db.Column(db.String(50), default='Admin')
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id,
            'student_name': self.student_name,
            'amount': round(self.amount, 2),
            'payment_date': self.payment_date,
            'payment_method': self.payment_method,
            'reference_no': self.reference_no or '--',
            'remarks': self.remarks or '',
            'created_by': self.created_by,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }


class MealMenu(db.Model):
    """Daily meal menu for breakfast and lunch."""
    __tablename__ = 'meal_menus'

    id = db.Column(db.Integer, primary_key=True)
    meal_type = db.Column(db.String(20), nullable=False)  # 'Breakfast' or 'Lunch'
    menu_date = db.Column(db.String(15), nullable=False)  # YYYY-MM-DD or 'Daily'
    items = db.Column(db.Text, nullable=False)            # e.g. "Idli, Vada, Sambhar, Chutney"
    is_published = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'meal_type': self.meal_type,
            'menu_date': self.menu_date,
            'items': self.items,
            'is_published': self.is_published,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }


class FoodEntry(db.Model):
    """
    Canteen meal attendance record.
    Enforces atomic uniqueness on (student_id, entry_date, meal) to prevent duplicate entries.
    """
    __tablename__ = 'food_entries'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(50), nullable=False, index=True)
    student_name = db.Column(db.String(100), nullable=False)
    srn = db.Column(db.String(50), nullable=True)
    room_number = db.Column(db.String(20), nullable=True)
    meal = db.Column(db.String(20), default='Lunch', nullable=False)
    entry_date = db.Column(db.String(10), nullable=False, index=True)  # Format: YYYY-MM-DD
    entry_time = db.Column(db.String(15), nullable=False)              # Format: HH:MM:SS AM/PM
    timestamp = db.Column(db.DateTime, default=datetime.now, index=True)
    verification_method = db.Column(db.String(20), default='face')     # 'face' or 'manual'
    status = db.Column(db.String(20), default='Approved', nullable=False)

    __table_args__ = (
        db.UniqueConstraint('student_id', 'entry_date', 'meal', name='uix_student_date_meal'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id,
            'student_name': self.student_name,
            'srn': self.srn or self.student_id,
            'room_number': self.room_number or '--',
            'meal': self.meal,
            'entry_date': self.entry_date,
            'entry_time': self.entry_time,
            'verification_method': self.verification_method,
            'status': self.status
        }


class RejectedAttempt(db.Model):
    """Log of rejected canteen meal access attempts for administrative inspection."""
    __tablename__ = 'rejected_attempts'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(50), nullable=True, index=True)
    student_name = db.Column(db.String(100), nullable=True)
    meal_type = db.Column(db.String(20), nullable=False)
    attempt_date = db.Column(db.String(10), nullable=False, index=True)
    attempt_time = db.Column(db.String(15), nullable=False)
    reason = db.Column(db.String(255), nullable=False)
    verification_method = db.Column(db.String(20), default='face')
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id or 'Unknown',
            'student_name': self.student_name or 'Unregistered Visitor',
            'meal_type': self.meal_type,
            'attempt_date': self.attempt_date,
            'attempt_time': self.attempt_time,
            'reason': self.reason,
            'verification_method': self.verification_method,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }


class SmsLog(db.Model):
    """Audit log of SMS notifications sent to students."""
    __tablename__ = 'sms_logs'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(50), nullable=False, index=True)
    student_name = db.Column(db.String(100), nullable=False)
    phone_number = db.Column(db.String(20), nullable=False)
    message = db.Column(db.Text, nullable=False)
    meal_type = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), default='queued')  # 'queued', 'sent', 'failed'
    provider_name = db.Column(db.String(50), default='mock')
    provider_ref = db.Column(db.String(100), nullable=True)
    error_message = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now, index=True)

    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id,
            'student_name': self.student_name,
            'phone_number': self.phone_number,
            'message': self.message,
            'meal_type': self.meal_type,
            'status': self.status,
            'provider_name': self.provider_name,
            'provider_ref': self.provider_ref or '--',
            'error_message': self.error_message or '',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }


class DailyReport(db.Model):
    """Daily generated Excel attendance report record."""
    __tablename__ = 'daily_reports'

    id = db.Column(db.Integer, primary_key=True)
    report_date = db.Column(db.String(10), unique=True, nullable=False, index=True)
    file_path = db.Column(db.String(255), nullable=False)
    total_students = db.Column(db.Integer, default=0)
    total_breakfast = db.Column(db.Integer, default=0)
    total_lunch = db.Column(db.Integer, default=0)
    total_meals_served = db.Column(db.Integer, default=0)
    generated_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'report_date': self.report_date,
            'file_path': self.file_path,
            'total_students': self.total_students,
            'total_breakfast': self.total_breakfast,
            'total_lunch': self.total_lunch,
            'total_meals_served': self.total_meals_served,
            'generated_at': self.generated_at.strftime('%Y-%m-%d %H:%M:%S') if self.generated_at else None
        }


class AuditLog(db.Model):
    """System-wide audit trail for administrative operations."""
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(100), nullable=False)
    actor_username = db.Column(db.String(50), default='admin')
    actor_role = db.Column(db.String(20), default='admin')
    target_type = db.Column(db.String(50), nullable=True)  # 'student', 'fee', 'menu', 'config'
    target_id = db.Column(db.String(50), nullable=True)
    details = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.now, index=True)

    def to_dict(self):
        return {
            'id': self.id,
            'action': self.action,
            'actor_username': self.actor_username,
            'actor_role': self.actor_role,
            'target_type': self.target_type or '--',
            'target_id': self.target_id or '--',
            'details': self.details or '',
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S') if self.timestamp else None
        }


class ArchivedFoodEntry(db.Model):
    """Restricted security archive for preserved attendance history."""
    __tablename__ = 'archived_food_entries'

    id = db.Column(db.Integer, primary_key=True)
    original_id = db.Column(db.Integer, nullable=True)
    student_id = db.Column(db.String(50), nullable=False, index=True)
    student_name = db.Column(db.String(100), nullable=False)
    srn = db.Column(db.String(50), nullable=True)
    room_number = db.Column(db.String(20), nullable=True)
    meal = db.Column(db.String(20), nullable=False)
    entry_date = db.Column(db.String(10), nullable=False, index=True)
    entry_time = db.Column(db.String(15), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=True)
    verification_method = db.Column(db.String(20), default='face')
    status = db.Column(db.String(20), default='Approved')
    archived_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    archived_by = db.Column(db.String(50), default='admin')
    archive_reason = db.Column(db.String(255), default='Administrative clear')

    def to_dict(self):
        return {
            'id': self.id,
            'original_id': self.original_id,
            'student_id': self.student_id,
            'student_name': self.student_name,
            'srn': self.srn or self.student_id,
            'room_number': self.room_number or '--',
            'meal': self.meal,
            'entry_date': self.entry_date,
            'entry_time': self.entry_time,
            'verification_method': self.verification_method,
            'status': self.status,
            'archived_at': self.archived_at.strftime('%Y-%m-%d %H:%M:%S') if self.archived_at else None,
            'archived_by': self.archived_by,
            'archive_reason': self.archive_reason
        }


class ArchivedRejectedAttempt(db.Model):
    """Restricted security archive for preserved rejected attempts."""
    __tablename__ = 'archived_rejected_attempts'

    id = db.Column(db.Integer, primary_key=True)
    original_id = db.Column(db.Integer, nullable=True)
    student_id = db.Column(db.String(50), nullable=True, index=True)
    student_name = db.Column(db.String(100), nullable=True)
    meal_type = db.Column(db.String(20), nullable=False)
    attempt_date = db.Column(db.String(10), nullable=False, index=True)
    attempt_time = db.Column(db.String(15), nullable=False)
    reason = db.Column(db.String(255), nullable=False)
    verification_method = db.Column(db.String(20), default='face')
    created_at = db.Column(db.DateTime, nullable=True)
    archived_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    archived_by = db.Column(db.String(50), default='admin')
    archive_reason = db.Column(db.String(255), default='Administrative clear')

    def to_dict(self):
        return {
            'id': self.id,
            'original_id': self.original_id,
            'student_id': self.student_id or 'Unknown',
            'student_name': self.student_name or 'Unregistered Visitor',
            'meal_type': self.meal_type,
            'attempt_date': self.attempt_date,
            'attempt_time': self.attempt_time,
            'reason': self.reason,
            'verification_method': self.verification_method,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'archived_at': self.archived_at.strftime('%Y-%m-%d %H:%M:%S') if self.archived_at else None,
            'archived_by': self.archived_by,
            'archive_reason': self.archive_reason
        }


class ArchivedSmsLog(db.Model):
    """Restricted security archive for preserved SMS logs."""
    __tablename__ = 'archived_sms_logs'

    id = db.Column(db.Integer, primary_key=True)
    original_id = db.Column(db.Integer, nullable=True)
    student_id = db.Column(db.String(50), nullable=False, index=True)
    student_name = db.Column(db.String(100), nullable=False)
    phone_number = db.Column(db.String(20), nullable=False)
    message = db.Column(db.Text, nullable=False)
    meal_type = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), default='sent')
    provider_name = db.Column(db.String(50), default='mock')
    provider_ref = db.Column(db.String(100), nullable=True)
    error_message = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=True)
    archived_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    archived_by = db.Column(db.String(50), default='admin')
    archive_reason = db.Column(db.String(255), default='Administrative clear')

    def to_dict(self):
        return {
            'id': self.id,
            'original_id': self.original_id,
            'student_id': self.student_id,
            'student_name': self.student_name,
            'phone_number': self.phone_number,
            'message': self.message,
            'meal_type': self.meal_type,
            'status': self.status,
            'provider_name': self.provider_name,
            'provider_ref': self.provider_ref or '--',
            'error_message': self.error_message or '',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'archived_at': self.archived_at.strftime('%Y-%m-%d %H:%M:%S') if self.archived_at else None,
            'archived_by': self.archived_by,
            'archive_reason': self.archive_reason
        }


class ArchivedAuditLog(db.Model):
    """Restricted security archive for preserved system audit trail."""
    __tablename__ = 'archived_audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    original_id = db.Column(db.Integer, nullable=True)
    action = db.Column(db.String(100), nullable=False)
    actor_username = db.Column(db.String(50), default='admin')
    actor_role = db.Column(db.String(20), default='admin')
    target_type = db.Column(db.String(50), nullable=True)
    target_id = db.Column(db.String(50), nullable=True)
    details = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, nullable=True)
    archived_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    archived_by = db.Column(db.String(50), default='admin')
    archive_reason = db.Column(db.String(255), default='Administrative clear')

    def to_dict(self):
        return {
            'id': self.id,
            'original_id': self.original_id,
            'action': self.action,
            'actor_username': self.actor_username,
            'actor_role': self.actor_role,
            'target_type': self.target_type or '--',
            'target_id': self.target_id or '--',
            'details': self.details or '',
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S') if self.timestamp else None,
            'archived_at': self.archived_at.strftime('%Y-%m-%d %H:%M:%S') if self.archived_at else None,
            'archived_by': self.archived_by,
            'archive_reason': self.archive_reason
        }


def migrate_database(app):
    """
    Ensure all tables, missing columns, and default administrator accounts
    are created without destroying any existing data.
    """
    with app.app_context():
        # 1. Create all missing tables
        db.create_all()

        # 2. Check and migrate columns on SQLite tables
        try:
            if db.engine.dialect.name == 'sqlite':
                conn = db.engine.raw_connection()
                cur = conn.cursor()

                # Check students columns
                cur.execute("PRAGMA table_info(students);")
                existing_student_cols = {row[1] for row in cur.fetchall()}

                student_migrations = [
                    ("srn", "VARCHAR(50)"),
                    ("phone_number", "VARCHAR(20)"),
                    ("room_number", "VARCHAR(20)"),
                    ("room_sharing_type", "VARCHAR(30) DEFAULT 'Double'"),
                    ("room_occupants", "INTEGER DEFAULT 2"),
                    ("admission_date", "VARCHAR(15)"),
                    ("total_hostel_fees", "FLOAT DEFAULT 75000.0"),
                    ("total_fees_paid", "FLOAT DEFAULT 0.0"),
                    ("last_payment_date", "VARCHAR(15)"),
                    ("meal_access_enabled", "BOOLEAN DEFAULT 1"),
                    ("meal_restriction_reason", "VARCHAR(255) DEFAULT 'None'"),
                    ("password_hash", "VARCHAR(255)")
                ]

                for col_name, col_def in student_migrations:
                    if col_name not in existing_student_cols:
                        cur.execute(f"ALTER TABLE students ADD COLUMN {col_name} {col_def};")

                # Check food_entries columns
                cur.execute("PRAGMA table_info(food_entries);")
                existing_food_cols = {row[1] for row in cur.fetchall()}

                food_migrations = [
                    ("srn", "VARCHAR(50)"),
                    ("room_number", "VARCHAR(20)"),
                    ("timestamp", "DATETIME"),
                    ("verification_method", "VARCHAR(20) DEFAULT 'face'")
                ]

                for col_name, col_def in food_migrations:
                    if col_name not in existing_food_cols:
                        cur.execute(f"ALTER TABLE food_entries ADD COLUMN {col_name} {col_def};")

                conn.commit()
                conn.close()
        except Exception as e:
            print(f"[Migration] Note during table column verification: {e}")

        # 3. Ensure Default Administrator Account exists
        default_admin = AdminUser.query.filter_by(username=app.config.get('DEFAULT_ADMIN_USERNAME', 'admin')).first()
        if not default_admin:
            admin = AdminUser(
                username=app.config.get('DEFAULT_ADMIN_USERNAME', 'admin'),
                email=app.config.get('DEFAULT_ADMIN_EMAIL', 'admin@canteen.edu'),
                role='admin'
            )
            admin.set_password(app.config.get('DEFAULT_ADMIN_PASSWORD', 'Admin@123'))
            db.session.add(admin)
            db.session.commit()
            print(f"[Migration] Initialized default administrator: {admin.username}")

        # 4. Ensure Default Daily Menus exist
        if MealMenu.query.count() == 0:
            m1 = MealMenu(
                meal_type='Breakfast',
                menu_date='Daily',
                items='Idli, Vada, Sambar, Coconut Chutney, Bread Butter, Tea / Coffee',
                is_published=True
            )
            m2 = MealMenu(
                meal_type='Lunch',
                menu_date='Daily',
                items='Steamed Rice, Dal Tadka, Paneer Butter Masala, Chapati, Mixed Veg Curry, Curd, Pickle',
                is_published=True
            )
            db.session.add_all([m1, m2])
            db.session.commit()
            print("[Migration] Initialized default canteen meal menus.")

