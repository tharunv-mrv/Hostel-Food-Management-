import os

basedir = os.path.abspath(os.path.dirname(__file__))
DEFAULT_DB_FILE = os.path.abspath(os.path.join(basedir, 'instance', 'hostel_food.db'))


def resolve_database_uri() -> str:
    """
    Resolve and canonicalize the database URI.
    Ensures that SQLite databases always use strict, absolute file paths anchored
    to the project root directory (basedir), converting relative paths and normalizing
    Windows backslashes into RFC-compliant forward slashes. This prevents data loss
    when VS Code or terminals are launched from different working directories.
    """
    raw_db_url = os.environ.get('DATABASE_URL')
    if raw_db_url:
        raw_db_url = raw_db_url.strip()
        # Render/Heroku compatibility: postgres:// -> postgresql://
        if raw_db_url.startswith('postgres://'):
            return raw_db_url.replace('postgres://', 'postgresql://', 1)

        # SQLite URI normalization
        if raw_db_url.startswith('sqlite:///'):
            sqlite_target = raw_db_url.replace('sqlite:///', '', 1)
            if sqlite_target == ':memory:':
                return 'sqlite:///:memory:'

            # If target is a relative path, anchor strictly to basedir
            if not os.path.isabs(sqlite_target):
                resolved_abs = os.path.abspath(os.path.join(basedir, sqlite_target))
            else:
                resolved_abs = os.path.abspath(sqlite_target)

            os.makedirs(os.path.dirname(resolved_abs), exist_ok=True)
            normalized_path = resolved_abs.replace(os.sep, '/')
            return f"sqlite:///{normalized_path}"

        return raw_db_url

    # Default persistent SQLite file inside instance directory
    os.makedirs(os.path.dirname(DEFAULT_DB_FILE), exist_ok=True)
    normalized_default = DEFAULT_DB_FILE.replace(os.sep, '/')
    return f"sqlite:///{normalized_default}"


class Config:
    """Application configuration with environment variable support."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'hostel-canteen-super-secret-key-2026')

    # Primary Database, Backup & Excel Register Storage Paths
    DB_FILE_PATH = DEFAULT_DB_FILE
    BACKUP_DIR = os.path.abspath(os.path.join(basedir, 'instance', 'backups'))
    BACKUP_RETENTION_COUNT = int(os.environ.get('BACKUP_RETENTION_COUNT', 10))
    EXPORTS_DIR = os.path.abspath(os.path.join(basedir, 'instance', 'exports'))
    STUDENT_REGISTER_EXCEL_PATH = os.path.abspath(os.path.join(basedir, 'instance', 'exports', 'student_register.xlsx'))

    SQLALCHEMY_DATABASE_URI = resolve_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Production Session Cookie Security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() in ('true', '1', 'yes')
    
    # Initial Admin Credentials
    DEFAULT_ADMIN_USERNAME = os.environ.get('DEFAULT_ADMIN_USERNAME', 'admin')
    DEFAULT_ADMIN_PASSWORD = os.environ.get('DEFAULT_ADMIN_PASSWORD', 'Admin@123')
    DEFAULT_ADMIN_EMAIL = os.environ.get('DEFAULT_ADMIN_EMAIL', 'admin@canteen.edu')
    DEFAULT_STUDENT_PASSWORD = os.environ.get('DEFAULT_STUDENT_PASSWORD', 'Student@123')

    # Face Recognition Threshold (Cosine similarity for SFace)
    # Cosine score ranges from -1.0 to 1.0; 0.363 is OpenCV's recommended threshold for SFace
    RECOGNITION_THRESHOLD = float(os.environ.get('RECOGNITION_THRESHOLD', 0.363))
    
    # Timezone
    TIMEZONE = os.environ.get('TIMEZONE', 'Asia/Kolkata')

    # Meal timings (24-hour HH:MM)
    BREAKFAST_START_TIME = os.environ.get('BREAKFAST_START_TIME', '07:30')
    BREAKFAST_END_TIME = os.environ.get('BREAKFAST_END_TIME', '10:30')
    BREAKFAST_ENABLED = os.environ.get('BREAKFAST_ENABLED', 'True').lower() in ('true', '1', 'yes')

    LUNCH_START_TIME = os.environ.get('LUNCH_START_TIME', '11:30')
    LUNCH_END_TIME = os.environ.get('LUNCH_END_TIME', '15:30')
    LUNCH_ENABLED = os.environ.get('LUNCH_ENABLED', 'True').lower() in ('true', '1', 'yes')

    # Enforcement toggles
    ENFORCE_MEAL_HOURS = os.environ.get('ENFORCE_MEAL_HOURS', 'False').lower() in ('true', '1', 'yes')
    # Backward compatibility alias
    ENFORCE_LUNCH_HOURS = ENFORCE_MEAL_HOURS

    # Fee Policy
    FEE_POLICY_ENFORCED = os.environ.get('FEE_POLICY_ENFORCED', 'False').lower() in ('true', '1', 'yes')
    MAX_PERMITTED_FEE_BALANCE = float(os.environ.get('MAX_PERMITTED_FEE_BALANCE', 5000.0))
    DEFAULT_HOSTEL_FEE = float(os.environ.get('DEFAULT_HOSTEL_FEE', 75000.0))

    # SMS Configuration
    SMS_PROVIDER = os.environ.get('SMS_PROVIDER', 'mock')
    SMS_API_KEY = os.environ.get('SMS_API_KEY', '')
    SMS_API_SECRET = os.environ.get('SMS_API_SECRET', '')
    SMS_SENDER_ID = os.environ.get('SMS_SENDER_ID', 'HSTLFD')
    TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', '')
    TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', '')
    TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER', '')

    # Reports & Retention Policy
    REPORTS_DIR = os.path.join(basedir, 'reports')
    DATA_RETENTION_POLICY = os.environ.get('DATA_RETENTION_POLICY', 'archive')
    ALLOW_PERMANENT_DELETION = os.environ.get('ALLOW_PERMANENT_DELETION', 'False').lower() in ('true', '1', 'yes')

    # Security & Defense-in-Depth Policies
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 16 * 1024 * 1024))  # 16 MB max payload limit
    CSRF_ENABLED = os.environ.get('CSRF_ENABLED', 'True').lower() in ('true', '1', 'yes')
    RATE_LIMIT_ENABLED = os.environ.get('RATE_LIMIT_ENABLED', 'True').lower() in ('true', '1', 'yes')
