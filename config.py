import os

basedir = os.path.abspath(os.path.dirname(__file__))
DEFAULT_DB_FILE = os.path.abspath(os.path.join(basedir, 'instance', 'hostel_food.db'))


def resolve_database_uri(environ=None) -> str:
    """
    Resolve and canonicalize the database URI.
    1. In production (Render), uses DATABASE_URL (or INTERNAL_DATABASE_URL / POSTGRES_URL)
       to connect to persistent Render PostgreSQL, automatically normalizing 'postgres://'
       to 'postgresql://'.
    2. Never silently falls back to SQLite if DATABASE_URL is malformed or if
       REQUIRE_POSTGRESQL=true is set.
    3. For local development, ensures SQLite uses a strict absolute path anchored to basedir.
    """
    env = environ if environ is not None else os.environ

    raw_db_url = None
    used_var = None
    for var_name in ('DATABASE_URL', 'INTERNAL_DATABASE_URL', 'POSTGRES_URL', 'POSTGRESQL_URL'):
        if var_name in env and env.get(var_name) is not None:
            raw_db_url = str(env.get(var_name)).strip().strip('"').strip("'")
            used_var = var_name
            break

    require_pg = str(env.get('REQUIRE_POSTGRESQL', 'false')).strip().lower() in ('true', '1', 'yes')
    is_render = (
        str(env.get('RENDER', '')).strip().lower() in ('true', '1', 'yes')
        or bool(env.get('RENDER_SERVICE_ID'))
    )

    if raw_db_url is not None:
        if not raw_db_url:
            msg = (
                f"[CRITICAL][Database] Environment variable {used_var} is set to an empty string! "
                "Refusing to silently fall back to an empty local SQLite database. "
                "Provide a valid PostgreSQL DATABASE_URL or unset the empty variable for local dev."
            )
            print(msg)
            raise ValueError(msg)

        # Render/SQLAlchemy 2.1+ compatibility: explicitly target psycopg2-binary driver
        if raw_db_url.startswith('postgres://'):
            raw_db_url = raw_db_url.replace('postgres://', 'postgresql+psycopg2://', 1)
        elif raw_db_url.startswith('postgresql://'):
            raw_db_url = raw_db_url.replace('postgresql://', 'postgresql+psycopg2://', 1)
        elif raw_db_url.startswith('postgresql+psycopg://'):
            raw_db_url = raw_db_url.replace('postgresql+psycopg://', 'postgresql+psycopg2://', 1)

        if raw_db_url.startswith('postgresql+psycopg2://'):
            return raw_db_url

        # SQLite URI normalization
        if raw_db_url.startswith('sqlite:///'):
            if require_pg:
                msg = (
                    f"[CRITICAL][Database] {used_var} is configured for SQLite, "
                    "but REQUIRE_POSTGRESQL=true is enabled. PostgreSQL is required."
                )
                print(msg)
                raise RuntimeError(msg)

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

        msg = (
            f"[CRITICAL][Database] Unsupported or malformed {used_var} scheme in '{raw_db_url.split(':', 1)[0]}'. "
            "Expected 'postgresql://', 'postgres://', or 'sqlite:///'. "
            "Refusing to silently fall back to an empty local SQLite database."
        )
        print(msg)
        raise ValueError(msg)

    if require_pg:
        msg = (
            "[CRITICAL][Database] REQUIRE_POSTGRESQL=true is set, but DATABASE_URL is missing! "
            "Refusing to fall back to ephemeral local SQLite. Configure DATABASE_URL in Render Environment."
        )
        print(msg)
        raise RuntimeError(msg)

    if is_render:
        print(
            "[CRITICAL][Persistence] WARNING: Application is running on Render WITHOUT 'DATABASE_URL' configured! "
            "Render Web Services have an EPHEMERAL filesystem — any student registered in local SQLite "
            "(/opt/render/project/src/instance/hostel_food.db) WILL DISAPPEAR after 15 minutes of inactivity "
            "(when you close your laptop) or on the next deploy. "
            "Fix: Set DATABASE_URL to your Render PostgreSQL Internal Database URL in the Render Dashboard -> Environment."
        )

    # Default persistent SQLite file inside instance directory (for local development)
    os.makedirs(os.path.dirname(DEFAULT_DB_FILE), exist_ok=True)
    normalized_default = DEFAULT_DB_FILE.replace(os.sep, '/')
    return f"sqlite:///{normalized_default}"


def get_engine_options(db_uri: str, environ=None) -> dict:
    """
    Build SQLAlchemy engine options for reliable cloud PostgreSQL and local SQLite persistence.
    Enables pool_pre_ping=True and pool_recycle=280 so idle cloud PostgreSQL connections
    never fail after laptop sleep or mobile reconnection.
    """
    env = environ if environ is not None else os.environ
    uri = (db_uri or '').strip()

    if uri.startswith('postgresql'):
        return {
            'pool_pre_ping': True,
            'pool_recycle': int(env.get('DB_POOL_RECYCLE', 280)),
            'pool_size': int(env.get('DB_POOL_SIZE', 5)),
            'max_overflow': int(env.get('DB_MAX_OVERFLOW', 10)),
            'connect_args': {
                'connect_timeout': int(env.get('DB_CONNECT_TIMEOUT', 10)),
            },
        }

    if uri == 'sqlite:///:memory:':
        return {'pool_pre_ping': True}

    return {
        'pool_pre_ping': True,
        'connect_args': {'timeout': 15},
    }


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
    SQLALCHEMY_ENGINE_OPTIONS = get_engine_options(SQLALCHEMY_DATABASE_URI)

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
