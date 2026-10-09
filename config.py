import os

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    """Application configuration with environment variable support."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'hostel-canteen-super-secret-key-2026')
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL', 
        f"sqlite:///{os.path.join(basedir, 'instance', 'hostel_food.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
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
