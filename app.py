import os
import json
import secrets
import time
from collections import defaultdict
from datetime import datetime, time as dtime
from functools import wraps
from flask import Flask, render_template, request, jsonify, current_app, session, redirect, url_for, send_file
from werkzeug.security import generate_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config
from models import (
    db, AdminUser, Student, FeePayment, MealMenu, FoodEntry, RejectedAttempt, SmsLog, DailyReport, AuditLog,
    ArchivedFoodEntry, ArchivedRejectedAttempt, ArchivedSmsLog, ArchivedAuditLog, migrate_database, flush_sqlite_to_disk
)
from face_service import face_service
from sms_service import send_meal_sms_async
from report_service import generate_daily_attendance_excel
from excel_sync_service import (
    sync_student_register_excel,
    get_excel_register_status,
    resolve_excel_register_path,
)


# In-memory sliding window rate-limiting store
_rate_limit_records = defaultdict(list)


def get_client_ip():
    """Extract client IP address accounting for reverse proxy headers."""
    forwarded = request.headers.get('X-Forwarded-For')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or '127.0.0.1'


def check_rate_limit(key: str, max_requests: int = 30, window_seconds: int = 60) -> bool:
    """Sliding-window in-memory rate limiter per client IP or action."""
    if current_app.config.get('TESTING', False) or not current_app.config.get('RATE_LIMIT_ENABLED', True):
        return True
    now = time.time()
    history = _rate_limit_records[key]
    _rate_limit_records[key] = [t for t in history if now - t < window_seconds]
    if len(_rate_limit_records[key]) >= max_requests:
        return False
    _rate_limit_records[key].append(now)
    return True


def get_csrf_token() -> str:
    """Retrieve or generate cryptographically secure CSRF token bound to current session."""
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return session['_csrf_token']


# ==========================================
# AUTHENTICATION & ACCESS CONTROL DECORATORS
# ==========================================

def admin_required(f):
    """Ensure endpoint is accessed only by authorized administrators."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'admin':
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'success': False, 'message': 'Admin privilege required.'}), 403
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function


def student_required(f):
    """Ensure endpoint is accessed only by authenticated students."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'student':
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'success': False, 'message': 'Student authentication required.'}), 403
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function


def login_required(f):
    """Ensure user is logged in (admin or student)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('role'):
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'success': False, 'message': 'Authentication required.'}), 401
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function


def log_audit(action, target_type=None, target_id=None, details=None):
    """Helper to record administrative actions into AuditLog."""
    try:
        actor_username = session.get('username') or 'system'
        actor_role = session.get('role') or 'admin'
        entry = AuditLog(
            action=action,
            actor_username=actor_username,
            actor_role=actor_role,
            target_type=target_type,
            target_id=str(target_id) if target_id else None,
            details=details
        )
        db.session.add(entry)
        db.session.commit()
    except Exception as e:
        print(f"[Audit] Failed to record log: {e}")


def get_current_meal_type():
    """Determine the active meal type based on server time and configured windows."""
    now_time = datetime.now().time()
    bf_start = dtime(*map(int, current_app.config.get('BREAKFAST_START_TIME', '07:30').split(':')))
    bf_end = dtime(*map(int, current_app.config.get('BREAKFAST_END_TIME', '10:30').split(':')))
    lunch_start = dtime(*map(int, current_app.config.get('LUNCH_START_TIME', '11:30').split(':')))
    lunch_end = dtime(*map(int, current_app.config.get('LUNCH_END_TIME', '15:30').split(':')))

    if bf_start <= now_time <= bf_end:
        return 'Breakfast', True
    elif lunch_start <= now_time <= lunch_end:
        return 'Lunch', True
    else:
        # Default fallback to Lunch if outside hours (when hours enforcement is toggled off)
        return 'Lunch', False


def validate_meal_eligibility(student, meal_type):
    """
    Validate all hostel eligibility rules:
    1. Account active
    2. Meal access enabled
    3. Fee policy compliance
    4. Meal serving window
    5. Duplicate prevention for same meal & date
    """
    today_str = datetime.now().strftime('%Y-%m-%d')
    now_time = datetime.now().time()

    # Rule 1: Student account active
    if not student.active:
        return False, "Student account is deactivated. Contact hostel office.", "inactive"

    # Rule 2: Meal access enabled
    if not student.meal_access_enabled:
        reason = student.meal_restriction_reason or "Meal access disabled by administrator"
        return False, f"Meal access restricted: {reason}", "meal_access_disabled"

    # Rule 3: Fee policy enforcement
    if current_app.config.get('FEE_POLICY_ENFORCED', False):
        max_allowed = current_app.config.get('MAX_PERMITTED_FEE_BALANCE', 5000.0)
        if student.pending_fees > max_allowed:
            return False, f"Fee policy violation: Outstanding dues of ₹{student.pending_fees:.2f} exceed permitted ₹{max_allowed:.2f}.", "fee_policy_violation"

    # Rule 4: Serving window enforcement
    if current_app.config.get('ENFORCE_MEAL_HOURS', False):
        if meal_type == 'Breakfast':
            start = dtime(*map(int, current_app.config.get('BREAKFAST_START_TIME', '07:30').split(':')))
            end = dtime(*map(int, current_app.config.get('BREAKFAST_END_TIME', '10:30').split(':')))
        else:
            start = dtime(*map(int, current_app.config.get('LUNCH_START_TIME', '11:30').split(':')))
            end = dtime(*map(int, current_app.config.get('LUNCH_END_TIME', '15:30').split(':')))

        if not (start <= now_time <= end):
            return False, f"Serving window for {meal_type} is closed ({start.strftime('%I:%M %p')} - {end.strftime('%I:%M %p')}).", "outside_hours"

    # Rule 5: Duplicate check for today
    existing = FoodEntry.query.filter_by(
        student_id=student.student_id,
        entry_date=today_str,
        meal=meal_type
    ).first()

    if existing:
        return False, f"{meal_type} already recorded today at {existing.entry_time}.", "already_recorded"

    return True, "Eligible", "ok"


# ==========================================
# ROUTE REGISTRATION FACTORY
# ==========================================

def register_routes(app):
    """Register all web routes, APIs, and view endpoints."""

    # ------------------------------------------
    # SECURITY MIDDLEWARE & DEFENSE-IN-DEPTH
    # ------------------------------------------

    @app.context_processor
    def inject_csrf_token():
        return dict(csrf_token=get_csrf_token)

    @app.before_request
    def validate_csrf():
        """Validate CSRF token for state-changing requests when session is active."""
        if current_app.config.get('TESTING', False) or not current_app.config.get('CSRF_ENABLED', True):
            return None
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return None
        # Exempt biometric camera stream and initial login
        if request.path in ('/api/scan-face', '/api/auth/login', '/health', '/api/health'):
            return None

        if session.get('role'):
            token = request.headers.get('X-CSRF-Token') or request.headers.get('X-CSRFToken')
            if not token and request.is_json:
                token = (request.get_json(silent=True) or {}).get('csrf_token')
            if not token and request.form:
                token = request.form.get('csrf_token')
            expected = session.get('_csrf_token')
            if not expected or not token or not secrets.compare_digest(str(token), str(expected)):
                return jsonify({'success': False, 'message': 'CSRF validation failed: missing or invalid token.'}), 403
        return None

    @app.after_request
    def add_security_headers(response):
        """Inject defense-in-depth HTTP security headers and prevent stale API caching."""
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        if request.path.startswith('/api/') or request.path.startswith('/static/') or request.path in ('/', '/admin', '/student', '/login'):
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        return response

    @app.errorhandler(400)
    def handle_bad_request(e):
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'error': 'Bad Request', 'message': str(e)}), 400
        return render_template('login.html'), 400

    @app.errorhandler(403)
    def handle_forbidden(e):
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'error': 'Forbidden', 'message': 'Access forbidden.'}), 403
        return render_template('login.html'), 403

    @app.errorhandler(404)
    def handle_not_found(e):
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'error': 'Not Found', 'message': 'Resource not found.'}), 404
        return render_template('login.html'), 404

    @app.errorhandler(429)
    def handle_rate_limited(e):
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'error': 'Rate Limit Exceeded', 'message': 'Too many requests. Please wait a moment.'}), 429
        return render_template('login.html'), 429

    @app.errorhandler(500)
    def handle_server_error(e):
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'error': 'Server Error', 'message': 'An internal server error occurred.'}), 500
        return render_template('login.html'), 500

    @app.route('/api/auth/csrf', methods=['GET'])
    def api_csrf():
        """Retrieve current session CSRF token."""
        return jsonify({'success': True, 'csrf_token': get_csrf_token()}), 200

    # ------------------------------------------
    # HEALTH CHECK & SYSTEM MONITORING
    # ------------------------------------------

    @app.route('/health', methods=['GET'])
    @app.route('/api/health', methods=['GET'])
    def health_check():
        """Service health-check endpoint for cloud load balancers and deployment probes."""
        models_loaded = bool(face_service.detector is not None and face_service.recognizer is not None)
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'service': 'Hostel Food Management System',
            'models_loaded': models_loaded,
            'database': db.engine.dialect.name
        }), 200

    # ------------------------------------------
    # PAGE ROUTES
    # ------------------------------------------

    @app.route('/')
    def canteen_scanner():
        """Main canteen scanner kiosk route."""
        return render_template('index.html')

    @app.route('/login')
    def login_page():
        """User login page (both admin and student)."""
        get_csrf_token()
        if session.get('role') == 'admin':
            return redirect(url_for('admin_dashboard'))
        elif session.get('role') == 'student':
            return redirect(url_for('student_dashboard'))
        return render_template('login.html')

    @app.route('/logout')
    def logout():
        """Log out user and clear session."""
        username = session.get('username') or session.get('student_id')
        role = session.get('role')
        session.clear()
        if username:
            log_audit(f"Logout successful for {username} ({role})", target_type="auth", target_id=username)
        return redirect(url_for('login_page'))

    def _find_student_by_identifier(identifier: str):
        """Locate a student record by normalized Student ID or SRN."""
        ident = (identifier or '').strip().upper()
        if not ident:
            return None
        return Student.query.filter(
            (Student.student_id == ident) | (Student.srn == ident)
        ).first()

    @app.route('/admin')
    @admin_required
    def admin_dashboard():
        """Admin management dashboard with server-rendered initial students and metrics."""
        get_csrf_token()
        db_error = None
        try:
            students = Student.query.order_by(Student.created_at.desc()).all()
            initial_students = [s.to_dict() for s in students]

            today_str = datetime.now().strftime('%Y-%m-%d')
            today_entries = FoodEntry.query.filter_by(entry_date=today_str).all()
            bf_count = sum(1 for e in today_entries if e.meal == 'Breakfast')
            lunch_count = sum(1 for e in today_entries if e.meal == 'Lunch')
            total_collected = round(sum(s.total_fees_paid for s in students), 2)
            total_pending = round(sum(s.pending_fees for s in students), 2)
            sms_count = SmsLog.query.filter(SmsLog.created_at >= datetime.now().date()).count()

            initial_metrics = {
                'total_students': len(students),
                'today_breakfast_count': bf_count,
                'today_lunch_count': lunch_count,
                'total_fees_collected': total_collected,
                'total_fees_pending': total_pending,
                'sms_delivered_count': sms_count,
                'paid_count': sum(1 for s in students if s.fee_status == 'PAID'),
                'partial_count': sum(1 for s in students if s.fee_status == 'PARTIALLY PAID'),
                'unpaid_count': sum(1 for s in students if s.fee_status == 'UNPAID')
            }
        except Exception as exc:
            print(f"[Database Error] Failed to load admin dashboard data: {exc}")
            db_error = "Database error: unable to retrieve student records."
            initial_students = []
            initial_metrics = {
                'total_students': 0,
                'today_breakfast_count': 0,
                'today_lunch_count': 0,
                'total_fees_collected': 0.0,
                'total_fees_pending': 0.0,
                'sms_delivered_count': 0,
                'paid_count': 0,
                'partial_count': 0,
                'unpaid_count': 0
            }

        return render_template(
            'admin.html',
            initial_students=initial_students,
            initial_metrics=initial_metrics,
            db_error=db_error
        )

    @app.route('/student')
    @student_required
    def student_dashboard():
        """Student private self-service dashboard."""
        get_csrf_token()
        return render_template('student.html')

    # ------------------------------------------
    # AUTHENTICATION APIS
    # ------------------------------------------

    @app.route('/api/auth/login', methods=['POST'])
    def api_login():
        """Authenticate administrator or student."""
        client_ip = get_client_ip()
        if not check_rate_limit(f"login_{client_ip}", max_requests=25, window_seconds=60):
            return jsonify({'success': False, 'error': 'Rate Limit Exceeded', 'message': 'Too many login attempts. Please wait 1 minute.'}), 429

        data = request.get_json() or {}
        role = (data.get('role') or 'student').strip().lower()
        username = (data.get('username') or data.get('srn') or data.get('student_id') or '').strip()
        password = (data.get('password') or '').strip()

        if not username or not password:
            return jsonify({'success': False, 'message': 'Username and password are required.'}), 400

        if role == 'admin':
            admin = AdminUser.query.filter_by(username=username).first()
            if not admin or not admin.check_password(password):
                return jsonify({'success': False, 'message': 'Invalid administrator credentials.'}), 401

            session['role'] = 'admin'
            session['username'] = admin.username
            session['user_id'] = admin.id
            csrf_token = get_csrf_token()
            log_audit(f"Admin login: {admin.username}", target_type="auth", target_id=admin.username)
            return jsonify({'success': True, 'role': 'admin', 'redirect': '/admin', 'csrf_token': csrf_token})

        elif role == 'student':
            normalized_ident = username.upper()
            student = _find_student_by_identifier(normalized_ident)

            if not student:
                return jsonify({'success': False, 'message': 'Student record not found.'}), 401

            # Check password; if not set yet, compare against default student password
            valid_pw = False
            if student.password_hash:
                valid_pw = student.check_password(password)
            else:
                default_pw = current_app.config.get('DEFAULT_STUDENT_PASSWORD', 'Student@123')
                if password == default_pw:
                    student.set_password(default_pw)
                    db.session.commit()
                    flush_sqlite_to_disk()
                    valid_pw = True

            if not valid_pw:
                return jsonify({'success': False, 'message': 'Invalid student password.'}), 401

            if not student.active:
                return jsonify({'success': False, 'message': 'Student account is deactivated. Contact warden.'}), 403

            session['role'] = 'student'
            session['student_id'] = student.student_id
            session['srn'] = student.srn or student.student_id
            session['username'] = student.name
            session['user_id'] = student.id
            csrf_token = get_csrf_token()
            return jsonify({
                'success': True,
                'role': 'student',
                'redirect': '/student',
                'csrf_token': csrf_token,
                'srn': student.srn or student.student_id,
                'student_id': student.student_id,
                'must_change_password': bool(student.must_change_password)
            })

        return jsonify({'success': False, 'message': 'Invalid role specified.'}), 400

    @app.route('/api/auth/me', methods=['GET'])
    def api_me():
        """Retrieve current logged-in identity."""
        if not session.get('role'):
            return jsonify({'logged_in': False}), 200

        return jsonify({
            'logged_in': True,
            'role': session.get('role'),
            'username': session.get('username'),
            'student_id': session.get('student_id'),
            'srn': session.get('srn') or session.get('student_id')
        })

    # ------------------------------------------
    # CANTEEN SCANNER APIS
    # ------------------------------------------

    @app.route('/api/scan-face', methods=['POST'])
    def scan_face():
        """
        Canteen Biometric Verification endpoint.
        Receives webcam frame, verifies face, records meal if eligible, sends SMS.
        """
        client_ip = get_client_ip()
        if not check_rate_limit(f"scan_{client_ip}", max_requests=120, window_seconds=60):
            return jsonify({'success': False, 'status': 'rate_limited', 'message': 'Too many face scan requests. Please wait a moment.'}), 429

        data = request.get_json() or {}
        image_data = data.get('image')
        requested_meal = data.get('meal_type')  # 'Breakfast', 'Lunch', or None (auto)

        if not image_data:
            return jsonify({'success': False, 'status': 'error', 'message': 'No camera image received.'}), 400

        # Determine meal type
        auto_meal, in_window = get_current_meal_type()
        meal_type = requested_meal if requested_meal in ('Breakfast', 'Lunch') else auto_meal

        # 1. Decode image
        img_bgr, decode_err = face_service.decode_base64_image(image_data)
        if decode_err:
            return jsonify({'success': False, 'status': 'error', 'message': decode_err}), 400

        # 2. Extract face encoding, landmarks, and enforce quality
        candidate_encoding, _, extract_err, meta = face_service.extract_face_with_landmarks(img_bgr, check_quality=True)
        if extract_err:
            status_tag = 'no_face' if ('No face' in extract_err) else ('quality_fail' if ('dark' in extract_err or 'blurry' in extract_err) else 'detection_error')
            return jsonify({
                'success': False,
                'status': status_tag,
                'message': extract_err
            }), 200

        # 3. Retrieve registered active students
        active_students = Student.query.filter_by(active=True).all()
        if not active_students:
            return jsonify({
                'success': False,
                'status': 'no_students',
                'message': 'No active students registered in database.'
            }), 200

        # 4. Compare with enrolled students
        threshold = current_app.config.get('RECOGNITION_THRESHOLD', 0.363)
        matched_student, score, verify_err = face_service.verify_against_students(
            candidate_encoding, active_students, threshold=threshold
        )

        today_str = datetime.now().strftime('%Y-%m-%d')
        now_time_str = datetime.now().strftime('%I:%M:%S %p')

        if not matched_student:
            # Log rejected attempt
            rej = RejectedAttempt(
                student_id=None,
                student_name='Unknown Face',
                meal_type=meal_type,
                attempt_date=today_str,
                attempt_time=now_time_str,
                reason="Face not recognized or match score below threshold",
                verification_method='face'
            )
            db.session.add(rej)
            db.session.commit()

            return jsonify({
                'success': False,
                'status': 'not_recognized',
                'message': 'Face Not Recognized. Please contact the canteen administrator.',
                'confidence': round(max(0.0, score) * 100, 1),
                'landmarks': meta.get('landmarks') if meta else None,
                'box': meta.get('box') if meta else None
            }), 200

        # 5. Validate meal access and fee policy
        is_eligible, reason_msg, status_code = validate_meal_eligibility(matched_student, meal_type)

        if not is_eligible:
            # Log rejected attempt
            rej = RejectedAttempt(
                student_id=matched_student.student_id,
                student_name=matched_student.name,
                meal_type=meal_type,
                attempt_date=today_str,
                attempt_time=now_time_str,
                reason=reason_msg,
                verification_method='face'
            )
            db.session.add(rej)
            db.session.commit()

            return jsonify({
                'success': False,
                'status': status_code,
                'message': reason_msg,
                'student': matched_student.to_dict(),
                'landmarks': meta.get('landmarks') if meta else None,
                'box': meta.get('box') if meta else None
            }), 200

        # 6. Record successful attendance (atomic handling)
        now = datetime.now()
        entry = FoodEntry(
            student_id=matched_student.student_id,
            student_name=matched_student.name,
            srn=matched_student.srn or matched_student.student_id,
            room_number=matched_student.room_number or '--',
            meal=meal_type,
            entry_date=today_str,
            entry_time=now.strftime('%I:%M:%S %p'),
            timestamp=now,
            verification_method='face',
            status='Approved'
        )
        try:
            db.session.add(entry)
            db.session.commit()
            flush_sqlite_to_disk()
        except Exception as e:
            db.session.rollback()
            return jsonify({
                'success': False,
                'status': 'already_recorded',
                'message': f"{meal_type} already recorded today.",
                'student': matched_student.to_dict()
            }), 200

        # 7. Asynchronous SMS Notification
        send_meal_sms_async(
            current_app._get_current_object(),
            matched_student.student_id,
            matched_student.name,
            matched_student.phone_number,
            meal_type,
            entry.entry_time,
            today_str
        )

        return jsonify({
            'success': True,
            'status': 'granted',
            'message': f"Access Granted! {meal_type} entry recorded successfully.",
            'confidence': round(score * 100, 1),
            'student': matched_student.to_dict(),
            'entry': entry.to_dict(),
            'landmarks': meta.get('landmarks') if meta else None,
            'box': meta.get('box') if meta else None
        }), 200

    @app.route('/api/scan-manual', methods=['POST'])
    @admin_required
    def scan_manual():
        """Alternative manual verification workflow for canteen staff."""
        data = request.get_json() or {}
        identifier = (data.get('identifier') or '').strip().upper()
        requested_meal = data.get('meal_type')

        if not identifier:
            return jsonify({'success': False, 'message': 'Student ID or SRN is required.'}), 400

        student = Student.query.filter(
            (Student.student_id == identifier) | (Student.srn == identifier)
        ).first()

        if not student:
            return jsonify({'success': False, 'message': 'Student not found in database.'}), 404

        auto_meal, _ = get_current_meal_type()
        meal_type = requested_meal if requested_meal in ('Breakfast', 'Lunch') else auto_meal

        today_str = datetime.now().strftime('%Y-%m-%d')
        now_time_str = datetime.now().strftime('%I:%M:%S %p')

        # Eligibility check
        is_eligible, reason_msg, status_code = validate_meal_eligibility(student, meal_type)
        if not is_eligible:
            rej = RejectedAttempt(
                student_id=student.student_id,
                student_name=student.name,
                meal_type=meal_type,
                attempt_date=today_str,
                attempt_time=now_time_str,
                reason=f"Manual scan rejected: {reason_msg}",
                verification_method='manual'
            )
            db.session.add(rej)
            db.session.commit()
            flush_sqlite_to_disk()
            return jsonify({'success': False, 'status': status_code, 'message': reason_msg, 'student': student.to_dict()}), 200

        now = datetime.now()
        entry = FoodEntry(
            student_id=student.student_id,
            student_name=student.name,
            srn=student.srn or student.student_id,
            room_number=student.room_number or '--',
            meal=meal_type,
            entry_date=today_str,
            entry_time=now_time_str,
            timestamp=now,
            verification_method='manual',
            status='Approved'
        )
        try:
            db.session.add(entry)
            db.session.commit()
            flush_sqlite_to_disk()
        except Exception:
            db.session.rollback()
            return jsonify({'success': False, 'status': 'already_recorded', 'message': f"{meal_type} already recorded today."}), 200

        log_audit(f"Manual meal verified for {student.student_id} ({meal_type})", target_type="attendance", target_id=student.student_id)

        # Asynchronous SMS
        send_meal_sms_async(
            current_app._get_current_object(),
            student.student_id,
            student.name,
            student.phone_number,
            meal_type,
            entry.entry_time,
            today_str
        )

        return jsonify({
            'success': True,
            'status': 'granted',
            'message': f"Manual Verification Granted! {meal_type} recorded.",
            'student': student.to_dict(),
            'entry': entry.to_dict()
        })

    # ------------------------------------------
    # STUDENT PORTAL APIS
    # ------------------------------------------

    @app.route('/api/student/profile', methods=['GET'])
    @student_required
    def student_profile():
        """Retrieve logged-in student's private profile and fee details."""
        student_id = session.get('student_id') or session.get('srn')
        student = _find_student_by_identifier(student_id)
        if not student:
            return jsonify({'success': False, 'message': 'Student profile not found.'}), 404

        payments = FeePayment.query.filter_by(student_id=student.student_id).order_by(FeePayment.id.desc()).all()
        return jsonify({
            'success': True,
            'student': student.to_dict(mask_phone=True),
            'payments': [p.to_dict() for p in payments]
        })

    @app.route('/api/student/meals', methods=['GET'])
    @student_required
    def student_meals():
        """Retrieve logged-in student's personal meal attendance history."""
        student_id = session.get('student_id') or session.get('srn')
        student = _find_student_by_identifier(student_id)
        target_sid = student.student_id if student else student_id
        entries = FoodEntry.query.filter_by(student_id=target_sid).order_by(FoodEntry.id.desc()).all()
        return jsonify({
            'success': True,
            'entries': [e.to_dict() for e in entries]
        })

    @app.route('/api/student/change-password', methods=['POST'])
    @student_required
    def student_change_password():
        """Allow an authenticated student to change their own password."""
        student_id = session.get('student_id') or session.get('srn')
        student = _find_student_by_identifier(student_id)
        if not student:
            return jsonify({'success': False, 'message': 'Student profile not found.'}), 404

        data = request.get_json() or {}
        current_password = (data.get('current_password') or '').strip()
        new_password = (data.get('new_password') or '').strip()
        confirm_password = (data.get('confirm_password') or '').strip()

        if not new_password or len(new_password) < 6:
            return jsonify({'success': False, 'message': 'New password must be at least 6 characters long.'}), 400

        if confirm_password and new_password != confirm_password:
            return jsonify({'success': False, 'message': 'New password and confirmation do not match.'}), 400

        if current_password and student.password_hash and not student.check_password(current_password):
            return jsonify({'success': False, 'message': 'Current password is incorrect.'}), 401

        student.set_password(new_password)
        student.must_change_password = False
        student.updated_at = datetime.now()
        db.session.commit()
        flush_sqlite_to_disk()
        sync_student_register_excel()

        log_audit(
            f"Student changed own password: {student.srn or student.student_id}",
            target_type="student_auth",
            target_id=student.srn or student.student_id
        )
        return jsonify({
            'success': True,
            'message': 'Password updated successfully.',
            'must_change_password': False
        })

    @app.route('/api/student/menus', methods=['GET'])
    @login_required
    def get_public_menus():
        """Retrieve published menus for students and canteen display."""
        menus = MealMenu.query.filter_by(is_published=True).all()
        return jsonify({
            'success': True,
            'menus': [m.to_dict() for m in menus],
            'timings': {
                'breakfast': f"{current_app.config.get('BREAKFAST_START_TIME', '07:30')} - {current_app.config.get('BREAKFAST_END_TIME', '10:30')}",
                'lunch': f"{current_app.config.get('LUNCH_START_TIME', '11:30')} - {current_app.config.get('LUNCH_END_TIME', '15:30')}"
            }
        })

    # ------------------------------------------
    # ADMIN STUDENT MANAGEMENT APIS
    # ------------------------------------------

    @app.route('/api/students', methods=['GET'])
    @admin_required
    def get_students():
        """List and filter registered students."""
        try:
            query = Student.query
            room = request.args.get('room')
            fee_status = request.args.get('fee_status')
            active = request.args.get('active')
            search = (request.args.get('search') or '').strip().lower()

            if room:
                query = query.filter_by(room_number=room)
            if active in ('true', 'false'):
                query = query.filter_by(active=(active == 'true'))

            students = query.order_by(Student.created_at.desc()).all()

            if fee_status:
                students = [s for s in students if s.fee_status.lower() == fee_status.lower()]

            if search:
                students = [
                    s for s in students if
                    search in s.name.lower() or
                    search in s.student_id.lower() or
                    (s.srn and search in s.srn.lower()) or
                    (s.room_number and search in s.room_number.lower())
                ]

            return jsonify({
                'success': True,
                'students': [s.to_dict() for s in students]
            })
        except Exception as exc:
            print(f"[Database Error] Failed to fetch students in GET /api/students: {exc}")
            return jsonify({
                'success': False,
                'error': 'Database Error',
                'message': 'Database error: unable to retrieve student records.'
            }), 500

    @app.route('/api/students/register', methods=['POST'])
    @admin_required
    def register_student():
        """Register a new student with fees, room, password hash, biometric face enrollment, and Excel sync."""
        data = request.get_json() or {}
        raw_srn = (data.get('srn') or data.get('student_id') or '').strip().upper()
        raw_student_id = (data.get('student_id') or raw_srn).strip().upper()
        student_id = raw_student_id
        srn = raw_srn or student_id

        name = (data.get('name') or '').strip()
        phone_number = (data.get('phone_number') or '').strip()
        branch = (data.get('branch') or '').strip()
        year = (data.get('year') or '').strip()
        hostel = (data.get('hostel') or '').strip()
        room_number = (data.get('room_number') or '').strip()
        room_sharing_type = (data.get('room_sharing_type') or 'Double').strip()
        room_occupants = int(data.get('room_occupants') or 2)
        admission_date = data.get('admission_date') or datetime.now().strftime('%Y-%m-%d')
        total_hostel_fees = float(data.get('total_hostel_fees') if data.get('total_hostel_fees') is not None and data.get('total_hostel_fees') != '' else current_app.config.get('DEFAULT_HOSTEL_FEE', 75000.0))
        initial_fees_paid = float(data.get('total_fees_paid') or 0.0)
        image_data = data.get('image')

        # Password handling: accept explicit initial password or fallback to default student password
        raw_password = data.get('password') if 'password' in data else data.get('student_password')
        if raw_password is not None and str(raw_password).strip() != '':
            password_to_set = str(raw_password).strip()
            if len(password_to_set) < 6:
                return jsonify({'success': False, 'message': 'Student password must be at least 6 characters long.'}), 400
        else:
            password_to_set = current_app.config.get('DEFAULT_STUDENT_PASSWORD', 'Student@123')

        # Required fields check
        if not student_id or not name:
            return jsonify({'success': False, 'message': 'Student ID / SRN and Full Name are mandatory.'}), 400

        # Unique validation across both student_id and srn without overwriting existing records
        existing_by_id = Student.query.filter(
            (Student.student_id == student_id) | (Student.srn == student_id)
        ).first()
        if existing_by_id:
            return jsonify({'success': False, 'message': f'Student ID / SRN "{student_id}" is already registered.'}), 400

        if srn and srn != student_id:
            existing_by_srn = Student.query.filter(
                (Student.srn == srn) | (Student.student_id == srn)
            ).first()
            if existing_by_srn:
                return jsonify({'success': False, 'message': f'SRN "{srn}" is already registered.'}), 400

        # Optional Face extraction
        encoding = None
        thumbnail = None
        if image_data:
            img_bgr, decode_err = face_service.decode_base64_image(image_data)
            if decode_err:
                return jsonify({'success': False, 'message': decode_err}), 400
            enc, thumb, ext_err = face_service.extract_face_encoding(img_bgr)
            if ext_err:
                return jsonify({'success': False, 'message': ext_err}), 400
            encoding = enc
            thumbnail = thumb

        now_dt = datetime.now()
        student = Student(
            student_id=student_id,
            name=name,
            srn=srn,
            phone_number=phone_number,
            branch=branch or 'General',
            year=year or '1st Year',
            hostel=hostel or 'Main Hostel',
            room_number=room_number,
            room_sharing_type=room_sharing_type,
            room_occupants=room_occupants,
            admission_date=admission_date,
            total_hostel_fees=total_hostel_fees,
            total_fees_paid=initial_fees_paid,
            last_payment_date=now_dt.strftime('%Y-%m-%d') if initial_fees_paid > 0 else None,
            face_encoding=json.dumps(encoding) if encoding else "",
            photo_preview=thumbnail or "",
            active=True,
            meal_access_enabled=True,
            must_change_password=False,
            created_at=now_dt,
            updated_at=now_dt
        )
        student.set_password(password_to_set)
        try:
            db.session.add(student)
            # Record initial payment record if amount > 0
            if initial_fees_paid > 0:
                pay_rec = FeePayment(
                    student_id=student_id,
                    student_name=name,
                    amount=initial_fees_paid,
                    payment_date=now_dt.strftime('%Y-%m-%d'),
                    payment_method='Initial Registration',
                    reference_no='REG-PAY-001',
                    remarks='Initial payment at registration',
                    created_by=session.get('username') or 'Admin'
                )
                db.session.add(pay_rec)
            db.session.commit()
            flush_sqlite_to_disk()
            db_target = current_app.config.get('SQLALCHEMY_DATABASE_URI', current_app.config.get('DB_FILE_PATH'))
            total_students = Student.query.count()
            print(f"[Persistence] Registered student {student_id} in {db_target} | Total students on disk: {total_students}")
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Database error while saving student: {str(e)}'}), 500

        # Synchronize permanent Excel student register (never rolls back committed DB record)
        excel_res = sync_student_register_excel()

        log_audit(f"Student enrolled: {name} ({student_id})", target_type="student", target_id=student_id)
        return jsonify({
            'success': True,
            'message': f"Student {name} ({student_id}) enrolled successfully!",
            'student': student.to_dict(),
            'excel_synced': excel_res.get('success', False)
        }), 201

    @app.route('/api/students/<student_id>', methods=['PUT'])
    @admin_required
    def update_student(student_id):
        """Update student profile details, fees, and room information."""
        student = _find_student_by_identifier(student_id)
        if not student:
            return jsonify({'success': False, 'message': 'Student not found.'}), 404

        data = request.get_json() or {}
        if 'name' in data and data['name'] is not None:
            new_name = str(data['name']).strip()
            if not new_name:
                return jsonify({'success': False, 'message': 'Student name cannot be empty.'}), 400
            student.name = new_name
        if 'phone_number' in data and data['phone_number'] is not None:
            student.phone_number = str(data['phone_number']).strip()
        if 'room_number' in data and data['room_number'] is not None:
            student.room_number = str(data['room_number']).strip()
        if 'room_sharing_type' in data and data['room_sharing_type']:
            student.room_sharing_type = str(data['room_sharing_type']).strip()
        if 'room_occupants' in data and data['room_occupants'] is not None:
            student.room_occupants = int(data['room_occupants'])
        if 'total_hostel_fees' in data and data['total_hostel_fees'] is not None:
            old_fee = student.total_hostel_fees
            student.total_hostel_fees = float(data['total_hostel_fees'])
            log_audit(
                f"Hostel fee updated for {student.student_id}: ₹{old_fee} -> ₹{student.total_hostel_fees}",
                target_type="fee",
                target_id=student.student_id
            )
        if 'branch' in data and data['branch'] is not None:
            student.branch = str(data['branch']).strip()
        if 'year' in data and data['year'] is not None:
            student.year = str(data['year']).strip()
        if 'hostel' in data and data['hostel'] is not None:
            student.hostel = str(data['hostel']).strip()
        if 'active' in data and isinstance(data['active'], bool):
            student.active = data['active']
        if 'meal_access_enabled' in data and isinstance(data['meal_access_enabled'], bool):
            student.meal_access_enabled = data['meal_access_enabled']

        student.updated_at = datetime.now()
        db.session.commit()
        flush_sqlite_to_disk()
        excel_res = sync_student_register_excel()
        log_audit(f"Updated profile for student {student.student_id}", target_type="student", target_id=student.student_id)
        return jsonify({
            'success': True,
            'message': 'Student profile updated.',
            'student': student.to_dict(),
            'excel_synced': excel_res.get('success', False)
        })

    @app.route('/api/students/<identifier>/reset-password', methods=['POST'])
    @app.route('/api/admin/students/reset-password', methods=['POST'])
    @admin_required
    def admin_reset_student_password(identifier=None):
        """
        Administrator Password Reset for a specific student by SRN or Student ID.
        Updates only the targeted student's password_hash, sets must_change_password,
        flushes to SQLite, syncs Excel timestamp, and records a sanitized AuditLog entry.
        """
        data = request.get_json() or {}
        target_ident = (identifier or data.get('srn') or data.get('student_id') or '').strip().upper()
        if not target_ident:
            return jsonify({'success': False, 'message': 'Student SRN or ID is required.'}), 400

        student = _find_student_by_identifier(target_ident)
        if not student:
            return jsonify({'success': False, 'message': f'Student "{target_ident}" not found.'}), 404

        new_password = (data.get('new_password') or data.get('password') or '').strip()
        confirm_password = data.get('confirm_password')

        if not new_password or len(new_password) < 6:
            return jsonify({
                'success': False,
                'message': 'New password must be at least 6 characters long.'
            }), 400

        if confirm_password is not None and new_password != str(confirm_password).strip():
            return jsonify({
                'success': False,
                'message': 'New password and confirm password do not match.'
            }), 400

        must_change = bool(data.get('must_change_password', True))
        student.set_password(new_password)
        student.must_change_password = must_change
        student.updated_at = datetime.now()

        try:
            db.session.commit()
            flush_sqlite_to_disk()
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Database error while resetting password: {str(e)}'}), 500

        sync_student_register_excel()

        admin_actor = session.get('username') or 'admin'
        target_srn = student.srn or student.student_id
        log_audit(
            action=f"Admin password reset for student {target_srn}",
            target_type="student_auth",
            target_id=target_srn,
            details=f"Password reset by admin '{admin_actor}' for SRN {target_srn} (must_change_password={must_change})"
        )

        return jsonify({
            'success': True,
            'message': f"Password reset successfully for {student.name} ({target_srn}).",
            'student': student.to_dict()
        }), 200

    @app.route('/api/admin/students/export-excel', methods=['GET'])
    @admin_required
    def export_student_register_excel():
        """Download the permanent Excel student register (`instance/exports/student_register.xlsx`)."""
        excel_path = resolve_excel_register_path()
        if not os.path.exists(excel_path):
            sync_res = sync_student_register_excel()
            if not sync_res.get('success') or not os.path.exists(excel_path):
                return jsonify({
                    'success': False,
                    'message': f"Unable to generate Excel student register: {sync_res.get('error', 'unknown error')}"
                }), 500

        log_audit("Downloaded student_register.xlsx", target_type="excel_register", target_id="student_register.xlsx")
        return send_file(
            excel_path,
            as_attachment=True,
            download_name='student_register.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    @app.route('/api/admin/students/sync-excel', methods=['POST'])
    @admin_required
    def regenerate_student_register_excel():
        """Regenerate and synchronize `student_register.xlsx` from the authoritative SQLite database."""
        res = sync_student_register_excel(force_rebuild=True)
        if res.get('success'):
            log_audit(
                f"Synchronized student_register.xlsx ({res.get('row_count', 0)} students)",
                target_type="excel_register",
                target_id="student_register.xlsx"
            )
            return jsonify({
                'success': True,
                'message': f"Excel student register synchronized ({res.get('row_count', 0)} students).",
                **res
            }), 200
        return jsonify({
            'success': False,
            'message': f"Excel synchronization failed: {res.get('error', 'Unknown error')}",
            **res
        }), 500

    @app.route('/api/admin/students/excel-status', methods=['GET'])
    @admin_required
    def student_register_excel_status():
        """Return health and metadata for `instance/exports/student_register.xlsx`."""
        status = get_excel_register_status()
        return jsonify({'success': True, **status}), 200

    @app.route('/api/students/<student_id>/toggle-active', methods=['POST'])
    @admin_required
    def toggle_student_active(student_id):
        """Toggle active/inactive status of student."""
        student = _find_student_by_identifier(student_id)
        if not student:
            return jsonify({'success': False, 'message': 'Student not found.'}), 404

        student.active = not student.active
        student.updated_at = datetime.now()
        db.session.commit()
        flush_sqlite_to_disk()
        sync_student_register_excel()
        log_audit(f"Toggled active status for {student.student_id} to {student.active}", target_type="student", target_id=student.student_id)
        return jsonify({
            'success': True,
            'active': student.active,
            'message': f"Student status updated to {'Active' if student.active else 'Inactive'}."
        })

    @app.route('/api/students/<student_id>/toggle-meal-access', methods=['POST'])
    @admin_required
    def toggle_meal_access(student_id):
        """Enable or disable student canteen meal access with a recorded reason."""
        student = _find_student_by_identifier(student_id)
        if not student:
            return jsonify({'success': False, 'message': 'Student not found.'}), 404

        data = request.get_json() or {}
        reason = data.get('reason') or ('Admin restriction' if student.meal_access_enabled else 'Restored by admin')
        student.meal_access_enabled = not student.meal_access_enabled
        student.meal_restriction_reason = reason if not student.meal_access_enabled else 'None'
        student.updated_at = datetime.now()

        db.session.commit()
        flush_sqlite_to_disk()
        sync_student_register_excel()
        log_audit(f"Toggled meal access for {student.student_id} to {student.meal_access_enabled}. Reason: {reason}", target_type="access", target_id=student.student_id)
        return jsonify({
            'success': True,
            'meal_access_enabled': student.meal_access_enabled,
            'message': f"Meal access {'enabled' if student.meal_access_enabled else 'disabled'} successfully."
        })

    @app.route('/api/students/<student_id>/enroll-face', methods=['POST'])
    @admin_required
    def enroll_face(student_id):
        """Enroll or replace student face biometrics."""
        student = _find_student_by_identifier(student_id)
        if not student:
            return jsonify({'success': False, 'message': 'Student not found.'}), 404

        data = request.get_json() or {}
        image_data = data.get('image')
        if not image_data:
            return jsonify({'success': False, 'message': 'Face snapshot image required.'}), 400

        img_bgr, decode_err = face_service.decode_base64_image(image_data)
        if decode_err:
            return jsonify({'success': False, 'message': decode_err}), 400

        encoding, thumbnail, ext_err = face_service.extract_face_encoding(img_bgr)
        if ext_err:
            return jsonify({'success': False, 'message': ext_err}), 400

        student.face_encoding = json.dumps(encoding)
        student.photo_preview = thumbnail
        student.updated_at = datetime.now()
        db.session.commit()
        flush_sqlite_to_disk()
        sync_student_register_excel()

        log_audit(f"Face biometrics enrolled/updated for student {student.student_id}", target_type="biometrics", target_id=student.student_id)
        return jsonify({'success': True, 'message': f"Face enrolled successfully for {student.name}."})

    @app.route('/api/students/<student_id>/face', methods=['DELETE'])
    @admin_required
    def remove_face(student_id):
        """Remove enrolled face reference for a student."""
        student = _find_student_by_identifier(student_id)
        if not student:
            return jsonify({'success': False, 'message': 'Student not found.'}), 404

        student.face_encoding = ""
        student.photo_preview = ""
        student.updated_at = datetime.now()
        db.session.commit()
        flush_sqlite_to_disk()
        sync_student_register_excel()

        log_audit(f"Face biometrics removed for student {student.student_id}", target_type="biometrics", target_id=student.student_id)
        return jsonify({'success': True, 'message': f"Face enrollment cleared for {student.student_id}."})

    @app.route('/api/students/<student_id>', methods=['DELETE'])
    @admin_required
    def delete_student(student_id):
        """Delete student record and clean up associated records within a single transaction."""
        student = _find_student_by_identifier(student_id)
        if not student:
            return jsonify({'success': False, 'message': 'Student not found.'}), 404

        target_sid = student.student_id
        deleted_srn = student.srn or student.student_id
        try:
            # Delete associated records to prevent orphaned entries in fees, meals, and logs
            FeePayment.query.filter_by(student_id=target_sid).delete()
            FoodEntry.query.filter_by(student_id=target_sid).delete()
            RejectedAttempt.query.filter_by(student_id=target_sid).delete()
            SmsLog.query.filter_by(student_id=target_sid).delete()

            db.session.delete(student)
            db.session.commit()
            flush_sqlite_to_disk()
            sync_student_register_excel(deleted_srn=deleted_srn)
            db_target = current_app.config.get('SQLALCHEMY_DATABASE_URI', current_app.config.get('DB_FILE_PATH'))
            total_students = Student.query.count()
            print(f"[Persistence] Deleted student {target_sid} from {db_target} | Total students on disk: {total_students}")
            log_audit(f"Deleted student {target_sid}", target_type="student", target_id=target_sid)
            return jsonify({'success': True, 'message': f'Student {target_sid} deleted successfully.'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Failed to delete student: {str(e)}'}), 500

    # ------------------------------------------
    # FEE MANAGEMENT APIS
    # ------------------------------------------

    @app.route('/api/fees/payment', methods=['POST'])
    @admin_required
    def record_fee_payment():
        """Record an auditable fee payment and recalculate pending balance."""
        data = request.get_json() or {}
        student_id = (data.get('student_id') or data.get('srn') or '').strip().upper()
        amount = float(data.get('amount') or 0.0)
        payment_date = data.get('payment_date') or datetime.now().strftime('%Y-%m-%d')
        payment_method = data.get('payment_method') or 'UPI'
        reference_no = (data.get('reference_no') or '').strip()
        remarks = (data.get('remarks') or '').strip()

        if not student_id or amount <= 0:
            return jsonify({'success': False, 'message': 'Valid Student ID and positive payment amount required.'}), 400

        student = _find_student_by_identifier(student_id)
        if not student:
            return jsonify({'success': False, 'message': 'Student record not found.'}), 404

        # Record payment transaction
        payment = FeePayment(
            student_id=student.student_id,
            student_name=student.name,
            amount=amount,
            payment_date=payment_date,
            payment_method=payment_method,
            reference_no=reference_no,
            remarks=remarks,
            created_by=session.get('username') or 'Admin'
        )
        db.session.add(payment)

        # Update student totals atomically
        student.total_fees_paid += amount
        student.last_payment_date = payment_date
        student.updated_at = datetime.now()
        db.session.commit()
        flush_sqlite_to_disk()
        sync_student_register_excel()

        log_audit(f"Recorded fee payment of ₹{amount:.2f} for {student.student_id} ({payment_method})", target_type="fee", target_id=student.student_id)

        return jsonify({
            'success': True,
            'message': f"Payment of ₹{amount:.2f} recorded successfully for {student.name}.",
            'payment': payment.to_dict(),
            'student': student.to_dict()
        }), 201

    @app.route('/api/fees/history/<student_id>', methods=['GET'])
    @admin_required
    def get_fee_history(student_id):
        """Retrieve complete payment history for a student."""
        student = _find_student_by_identifier(student_id)
        target_sid = student.student_id if student else student_id
        payments = FeePayment.query.filter_by(student_id=target_sid).order_by(FeePayment.id.desc()).all()
        return jsonify({'success': True, 'payments': [p.to_dict() for p in payments]})

    @app.route('/api/fees/correction/<int:payment_id>', methods=['POST'])
    @admin_required
    def correct_fee_payment(payment_id):
        """Correct or reverse an errant fee payment entry with audit logging."""
        payment = db.session.get(FeePayment, payment_id)
        if not payment:
            return jsonify({'success': False, 'message': 'Payment record not found.'}), 404

        data = request.get_json() or {}
        reason = data.get('reason') or 'Administrative correction'

        student = Student.query.filter_by(student_id=payment.student_id).first()
        if student:
            # Reversal
            student.total_fees_paid = max(0.0, student.total_fees_paid - payment.amount)
            student.updated_at = datetime.now()

        old_amount = payment.amount
        db.session.delete(payment)
        db.session.commit()
        flush_sqlite_to_disk()
        sync_student_register_excel()

        log_audit(f"Reversed payment #{payment_id} of ₹{old_amount:.2f} for {student.student_id if student else 'Unknown'}. Reason: {reason}", target_type="fee", target_id=payment_id)

        return jsonify({
            'success': True,
            'message': f"Payment #{payment_id} reversed successfully.",
            'student': student.to_dict() if student else None
        })

    @app.route('/api/fees/summary', methods=['GET'])
    @admin_required
    def get_fee_summary():
        """Retrieve college-wide fee metrics."""
        students = Student.query.all()
        total_hostel_fees = sum(s.total_hostel_fees for s in students)
        total_collected = sum(s.total_fees_paid for s in students)
        total_pending = sum(s.pending_fees for s in students)

        paid_count = sum(1 for s in students if s.fee_status == 'PAID')
        partial_count = sum(1 for s in students if s.fee_status == 'PARTIALLY PAID')
        unpaid_count = sum(1 for s in students if s.fee_status == 'UNPAID')

        return jsonify({
            'success': True,
            'total_hostel_fees': round(total_hostel_fees, 2),
            'total_collected': round(total_collected, 2),
            'total_pending': round(total_pending, 2),
            'counts': {
                'paid': paid_count,
                'partially_paid': partial_count,
                'unpaid': unpaid_count
            }
        })

    # ------------------------------------------
    # MENU MANAGEMENT APIS
    # ------------------------------------------

    @app.route('/api/menus', methods=['GET'])
    @admin_required
    def admin_get_menus():
        """List all breakfast and lunch menus."""
        menus = MealMenu.query.order_by(MealMenu.id.desc()).all()
        return jsonify({'success': True, 'menus': [m.to_dict() for m in menus]})

    @app.route('/api/menus', methods=['POST'])
    @admin_required
    def admin_save_menu():
        """Create or update meal menus."""
        data = request.get_json() or {}
        meal_type = data.get('meal_type')
        items = (data.get('items') or '').strip()
        menu_date = data.get('menu_date') or 'Daily'

        if not meal_type or not items:
            return jsonify({'success': False, 'message': 'Meal type and items are required.'}), 400

        # Update existing menu if found for date & type
        menu = MealMenu.query.filter_by(meal_type=meal_type, menu_date=menu_date).first()
        if not menu:
            menu = MealMenu(meal_type=meal_type, menu_date=menu_date, items=items, is_published=True)
            db.session.add(menu)
        else:
            menu.items = items
            menu.is_published = True

        db.session.commit()
        log_audit(f"Published {meal_type} menu for {menu_date}", target_type="menu", target_id=menu.id)
        return jsonify({'success': True, 'message': f'{meal_type} menu saved successfully.', 'menu': menu.to_dict()})

    # ------------------------------------------
    # ATTENDANCE & REPORT APIS
    # ------------------------------------------

    @app.route('/api/entries/today', methods=['GET'])
    def get_today_entries():
        """Retrieve today's attendance summary and meal breakdown, with optional date filtering."""
        today_str = datetime.now().strftime('%Y-%m-%d')
        date_param = request.args.get('date', '').strip()
        query_date = date_param if date_param else today_str

        # Filtered entries for requested date
        entries = FoodEntry.query.filter_by(entry_date=query_date).order_by(FoodEntry.id.desc()).all()

        # If filtered by another date, fetch today's entries for the dashboard top metrics
        today_entries = entries if query_date == today_str else FoodEntry.query.filter_by(entry_date=today_str).all()

        total_students = Student.query.count()
        active_students = Student.query.filter_by(active=True).count()
        disabled_meal_students = Student.query.filter_by(meal_access_enabled=False).count()

        bf_count = sum(1 for e in today_entries if e.meal == 'Breakfast')
        lunch_count = sum(1 for e in today_entries if e.meal == 'Lunch')
        unique_students = len({e.student_id for e in today_entries})

        # Fee metrics
        students = Student.query.all()
        total_collected = sum(s.total_fees_paid for s in students)
        total_pending = sum(s.pending_fees for s in students)
        defaulters_count = sum(1 for s in students if s.pending_fees > 0)

        # SMS count
        sms_count = SmsLog.query.filter(SmsLog.created_at >= datetime.now().date()).count()

        return jsonify({
            'success': True,
            'today_date': today_str,
            'query_date': query_date,
            'metrics': {
                'total_students': total_students,
                'active_students': active_students,
                'disabled_meal_students': disabled_meal_students,
                'today_lunch_count': lunch_count,
                'today_breakfast_count': bf_count,
                'today_unique_students': unique_students,
                'total_fees_collected': round(total_collected, 2),
                'total_fees_pending': round(total_pending, 2),
                'defaulters_count': defaulters_count,
                'sms_delivered_count': sms_count
            },
            'entries': [e.to_dict() for e in entries]
        })

    @app.route('/api/entries/rejected', methods=['GET'])
    @admin_required
    def get_rejected_entries():
        """Retrieve canteen rejected attempts log."""
        entries = RejectedAttempt.query.order_by(RejectedAttempt.id.desc()).limit(100).all()
        return jsonify({'success': True, 'rejected': [e.to_dict() for e in entries]})

    @app.route('/api/reports/generate', methods=['POST'])
    @admin_required
    def trigger_report_generation():
        """Manually generate daily Excel & CSV attendance report."""
        data = request.get_json() or {}
        report_date = data.get('date') or datetime.now().strftime('%Y-%m-%d')

        res = generate_daily_attendance_excel(report_date, current_app.config.get('REPORTS_DIR'))
        log_audit(f"Generated attendance report for {report_date}", target_type="report", target_id=report_date)
        return jsonify({
            'success': True,
            'message': f"Report for {report_date} generated successfully.",
            'details': res
        })

    @app.route('/api/reports/download', methods=['GET'])
    @admin_required
    def download_report():
        """Download generated Excel or CSV attendance sheet."""
        report_date = request.args.get('date') or datetime.now().strftime('%Y-%m-%d')
        fmt = request.args.get('format', 'xlsx').lower()

        reports_dir = current_app.config.get('REPORTS_DIR')
        filename = f"attendance_{report_date}.{fmt}"
        filepath = os.path.join(reports_dir, filename)

        if not os.path.exists(filepath):
            # Generate on the fly
            generate_daily_attendance_excel(report_date, reports_dir)

        if os.path.exists(filepath):
            return send_file(filepath, as_attachment=True, download_name=filename)
        return jsonify({'success': False, 'message': 'Report could not be found.'}), 404

    @app.route('/api/sms/logs', methods=['GET'])
    @admin_required
    def get_sms_logs():
        """Retrieve recent SMS notification dispatch records."""
        logs = SmsLog.query.order_by(SmsLog.id.desc()).limit(100).all()
        return jsonify({'success': True, 'logs': [l.to_dict() for l in logs]})

    @app.route('/api/audit/logs', methods=['GET'])
    @app.route('/api/audit-logs', methods=['GET'])
    @admin_required
    def get_audit_logs():
        """Retrieve system audit trail records."""
        logs = AuditLog.query.order_by(AuditLog.id.desc()).limit(100).all()
        return jsonify({'success': True, 'logs': [l.to_dict() for l in logs]})

    # ------------------------------------------
    # RECORD RETENTION & ARCHIVE APIS
    # ------------------------------------------

    def _clear_attendance_impl(data):
        date_param = data.get('date') or datetime.now().strftime('%Y-%m-%d')
        reason = data.get('reason') or 'Administrative attendance clearing'
        action = data.get('action', 'archive').lower()
        actor = session.get('username', 'admin')

        if action == 'purge' and not current_app.config.get('ALLOW_PERMANENT_DELETION', False):
            return jsonify({
                'success': False,
                'message': 'Permanent deletion is prohibited by system retention policy. Records must be archived.'
            }), 403

        query = FoodEntry.query
        if date_param != 'all':
            query = query.filter_by(entry_date=date_param)
        entries = query.all()
        count = len(entries)

        if count == 0:
            return jsonify({
                'success': True,
                'module': 'attendance',
                'archived_count': 0,
                'message': f"No attendance records found for date '{date_param}'."
            }), 200

        try:
            if action == 'archive':
                archived_objs = []
                for e in entries:
                    archived_objs.append(ArchivedFoodEntry(
                        original_id=e.id,
                        student_id=e.student_id,
                        student_name=e.student_name,
                        srn=e.srn,
                        room_number=e.room_number,
                        meal=e.meal,
                        entry_date=e.entry_date,
                        entry_time=e.entry_time,
                        timestamp=e.timestamp,
                        verification_method=e.verification_method,
                        status=e.status,
                        archived_at=datetime.now(),
                        archived_by=actor,
                        archive_reason=reason
                    ))
                db.session.add_all(archived_objs)

            for e in entries:
                db.session.delete(e)

            log_audit(f"Cleared {count} attendance records ({action}) for {date_param}", target_type="attendance", target_id=str(count), details=reason)
            db.session.commit()

            return jsonify({
                'success': True,
                'module': 'attendance',
                'archived_count': count,
                'action_taken': action,
                'message': f"Successfully {action}d {count} attendance record(s)."
            }), 200
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f"Failed to clear attendance: {str(e)}"}), 500

    def _clear_rejections_impl(data):
        reason = data.get('reason') or 'Administrative rejections clearing'
        action = data.get('action', 'archive').lower()
        actor = session.get('username', 'admin')

        if action == 'purge' and not current_app.config.get('ALLOW_PERMANENT_DELETION', False):
            return jsonify({
                'success': False,
                'message': 'Permanent deletion is prohibited by system retention policy. Records must be archived.'
            }), 403

        entries = RejectedAttempt.query.all()
        count = len(entries)

        if count == 0:
            return jsonify({
                'success': True,
                'module': 'rejections',
                'archived_count': 0,
                'message': "No rejected attempts found to clear."
            }), 200

        try:
            if action == 'archive':
                archived_objs = []
                for r in entries:
                    archived_objs.append(ArchivedRejectedAttempt(
                        original_id=r.id,
                        student_id=r.student_id,
                        student_name=r.student_name,
                        meal_type=r.meal_type,
                        attempt_date=r.attempt_date,
                        attempt_time=r.attempt_time,
                        reason=r.reason,
                        verification_method=r.verification_method,
                        created_at=r.created_at,
                        archived_at=datetime.now(),
                        archived_by=actor,
                        archive_reason=reason
                    ))
                db.session.add_all(archived_objs)

            for r in entries:
                db.session.delete(r)

            log_audit(f"Cleared {count} rejected meal attempts ({action})", target_type="rejection", target_id=str(count), details=reason)
            db.session.commit()

            return jsonify({
                'success': True,
                'module': 'rejections',
                'archived_count': count,
                'action_taken': action,
                'message': f"Successfully {action}d {count} rejected attempt(s)."
            }), 200
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f"Failed to clear rejections: {str(e)}"}), 500

    def _clear_sms_impl(data):
        reason = data.get('reason') or 'Administrative SMS logs clearing'
        action = data.get('action', 'archive').lower()
        actor = session.get('username', 'admin')

        if action == 'purge' and not current_app.config.get('ALLOW_PERMANENT_DELETION', False):
            return jsonify({
                'success': False,
                'message': 'Permanent deletion is prohibited by system retention policy. Records must be archived.'
            }), 403

        completed_logs = SmsLog.query.filter(SmsLog.status.notin_(['queued', 'sending'])).all()
        count = len(completed_logs)

        if count == 0:
            return jsonify({
                'success': True,
                'module': 'sms',
                'archived_count': 0,
                'message': "No completed SMS logs found to clear (in-flight messages were preserved)."
            }), 200

        try:
            if action == 'archive':
                archived_objs = []
                for s in completed_logs:
                    archived_objs.append(ArchivedSmsLog(
                        original_id=s.id,
                        student_id=s.student_id,
                        student_name=s.student_name,
                        phone_number=s.phone_number,
                        message=s.message,
                        meal_type=s.meal_type,
                        status=s.status,
                        provider_name=s.provider_name,
                        provider_ref=s.provider_ref,
                        error_message=s.error_message,
                        created_at=s.created_at,
                        archived_at=datetime.now(),
                        archived_by=actor,
                        archive_reason=reason
                    ))
                db.session.add_all(archived_objs)

            for s in completed_logs:
                db.session.delete(s)

            log_audit(f"Cleared {count} SMS dispatch logs ({action})", target_type="sms", target_id=str(count), details=reason)
            db.session.commit()

            return jsonify({
                'success': True,
                'module': 'sms',
                'archived_count': count,
                'action_taken': action,
                'message': f"Successfully {action}d {count} SMS log(s)."
            }), 200
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f"Failed to clear SMS logs: {str(e)}"}), 500

    def _clear_audit_impl(data):
        reason = data.get('reason') or 'Administrative audit trail clearing'
        action = data.get('action', 'archive').lower()
        actor = session.get('username', 'admin')
        actor_role = session.get('role', 'admin')

        if action == 'purge':
            return jsonify({
                'success': False,
                'message': 'Permanent deletion of security audit history is strictly prohibited by security policy. Audit records must be transferred to the restricted security archive.'
            }), 403

        entries = AuditLog.query.all()
        count = len(entries)

        try:
            if count > 0:
                archived_objs = []
                for a in entries:
                    archived_objs.append(ArchivedAuditLog(
                        original_id=a.id,
                        action=a.action,
                        actor_username=a.actor_username,
                        actor_role=a.actor_role,
                        target_type=a.target_type,
                        target_id=a.target_id,
                        details=a.details,
                        timestamp=a.timestamp,
                        archived_at=datetime.now(),
                        archived_by=actor,
                        archive_reason=reason
                    ))
                db.session.add_all(archived_objs)

                for a in entries:
                    db.session.delete(a)

            now_dt = datetime.now()
            retention_entry = AuditLog(
                action="Archived Security Audit Trail",
                actor_username=actor,
                actor_role=actor_role,
                target_type="audit",
                target_id=f"{count}_records",
                details=f"Admin '{actor}' transferred {count} audit records into restricted security archive on {now_dt.strftime('%Y-%m-%d %H:%M:%S')}. Reason: {reason}",
                timestamp=now_dt
            )
            db.session.add(retention_entry)
            db.session.commit()

            return jsonify({
                'success': True,
                'module': 'audit',
                'archived_count': count,
                'action_taken': 'archive',
                'message': f"Successfully archived {count} audit record(s) to security archive. Retention event recorded."
            }), 200
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f"Failed to archive audit trail: {str(e)}"}), 500

    # Route Endpoints
    @app.route('/api/entries/clear', methods=['POST'])
    @app.route('/api/attendance/clear', methods=['POST'])
    @admin_required
    def api_clear_attendance():
        data = request.get_json() or {}
        return _clear_attendance_impl(data)

    @app.route('/api/entries/rejected/clear', methods=['POST'])
    @app.route('/api/rejections/clear', methods=['POST'])
    @admin_required
    def api_clear_rejections():
        data = request.get_json() or {}
        return _clear_rejections_impl(data)

    @app.route('/api/sms/logs/clear', methods=['POST'])
    @app.route('/api/sms/clear', methods=['POST'])
    @admin_required
    def api_clear_sms():
        data = request.get_json() or {}
        return _clear_sms_impl(data)

    @app.route('/api/audit/logs/clear', methods=['POST'])
    @app.route('/api/audit-logs/clear', methods=['POST'])
    @app.route('/api/audit/clear', methods=['POST'])
    @admin_required
    def api_clear_audit():
        data = request.get_json() or {}
        return _clear_audit_impl(data)

    @app.route('/api/admin/clear-records/<module>', methods=['POST'])
    @admin_required
    def api_unified_clear(module):
        data = request.get_json() or {}
        mod = (module or '').lower()
        if mod in ('attendance', 'entries'):
            return _clear_attendance_impl(data)
        elif mod in ('rejections', 'rejected'):
            return _clear_rejections_impl(data)
        elif mod in ('sms', 'sms_logs'):
            return _clear_sms_impl(data)
        elif mod in ('audit', 'audit_logs'):
            return _clear_audit_impl(data)
        return jsonify({'success': False, 'message': f"Unknown module '{module}'. Valid modules: attendance, rejections, sms, audit."}), 400

    @app.route('/api/archive/<module>', methods=['GET'])
    @admin_required
    def api_view_archive(module):
        mod = (module or '').lower()
        limit = min(int(request.args.get('limit', 100)), 500)
        if mod in ('attendance', 'entries'):
            records = ArchivedFoodEntry.query.order_by(ArchivedFoodEntry.id.desc()).limit(limit).all()
        elif mod in ('rejections', 'rejected'):
            records = ArchivedRejectedAttempt.query.order_by(ArchivedRejectedAttempt.id.desc()).limit(limit).all()
        elif mod in ('sms', 'sms_logs'):
            records = ArchivedSmsLog.query.order_by(ArchivedSmsLog.id.desc()).limit(limit).all()
        elif mod in ('audit', 'audit_logs'):
            records = ArchivedAuditLog.query.order_by(ArchivedAuditLog.id.desc()).limit(limit).all()
        else:
            return jsonify({'success': False, 'message': f"Unknown archive module '{module}'."}), 400

        return jsonify({
            'success': True,
            'module': mod,
            'count': len(records),
            'records': [r.to_dict() for r in records]
        })

    # ------------------------------------------
    # CONFIGURATION & DEV APIS
    # ------------------------------------------

    @app.route('/api/admin/config', methods=['GET', 'POST'])
    @admin_required
    def handle_config():
        """Manage runtime application and policy configurations."""
        if request.method == 'POST':
            data = request.get_json() or {}
            if 'threshold' in data:
                current_app.config['RECOGNITION_THRESHOLD'] = float(data['threshold'])
            if 'enforce_meal_hours' in data:
                current_app.config['ENFORCE_MEAL_HOURS'] = bool(data['enforce_meal_hours'])
                current_app.config['ENFORCE_LUNCH_HOURS'] = current_app.config['ENFORCE_MEAL_HOURS']
            if 'fee_policy_enforced' in data:
                current_app.config['FEE_POLICY_ENFORCED'] = bool(data['fee_policy_enforced'])
            if 'max_permitted_fee_balance' in data:
                current_app.config['MAX_PERMITTED_FEE_BALANCE'] = float(data['max_permitted_fee_balance'])
            if 'breakfast_start' in data:
                current_app.config['BREAKFAST_START_TIME'] = str(data['breakfast_start'])
            if 'breakfast_end' in data:
                current_app.config['BREAKFAST_END_TIME'] = str(data['breakfast_end'])
            if 'lunch_start' in data:
                current_app.config['LUNCH_START_TIME'] = str(data['lunch_start'])
            if 'lunch_end' in data:
                current_app.config['LUNCH_END_TIME'] = str(data['lunch_end'])

            if 'sms_sender_id' in data:
                current_app.config['SMS_SENDER_ID'] = str(data['sms_sender_id']).strip()
            if 'twilio_phone_number' in data:
                current_app.config['TWILIO_PHONE_NUMBER'] = str(data['twilio_phone_number']).strip()
            if 'sms_provider' in data:
                current_app.config['SMS_PROVIDER'] = str(data['sms_provider']).strip()

            log_audit("Updated system configuration", target_type="config")
            return jsonify({
                'success': True,
                'message': 'Configuration updated successfully.',
                'config': {
                    'threshold': current_app.config['RECOGNITION_THRESHOLD'],
                    'enforce_meal_hours': current_app.config['ENFORCE_MEAL_HOURS'],
                    'fee_policy_enforced': current_app.config['FEE_POLICY_ENFORCED'],
                    'max_permitted_fee_balance': current_app.config['MAX_PERMITTED_FEE_BALANCE'],
                    'breakfast_start': current_app.config['BREAKFAST_START_TIME'],
                    'breakfast_end': current_app.config['BREAKFAST_END_TIME'],
                    'lunch_start': current_app.config['LUNCH_START_TIME'],
                    'lunch_end': current_app.config['LUNCH_END_TIME'],
                    'sms_sender_id': current_app.config.get('SMS_SENDER_ID', 'HSTLFD'),
                    'twilio_phone_number': current_app.config.get('TWILIO_PHONE_NUMBER', ''),
                    'sms_provider': current_app.config.get('SMS_PROVIDER', 'mock')
                }
            })

        return jsonify({
            'threshold': current_app.config.get('RECOGNITION_THRESHOLD', 0.363),
            'enforce_meal_hours': current_app.config.get('ENFORCE_MEAL_HOURS', False),
            'fee_policy_enforced': current_app.config.get('FEE_POLICY_ENFORCED', False),
            'max_permitted_fee_balance': current_app.config.get('MAX_PERMITTED_FEE_BALANCE', 5000.0),
            'breakfast_start': current_app.config.get('BREAKFAST_START_TIME', '07:30'),
            'breakfast_end': current_app.config.get('BREAKFAST_END_TIME', '10:30'),
            'lunch_start': current_app.config.get('LUNCH_START_TIME', '11:30'),
            'lunch_end': current_app.config.get('LUNCH_END_TIME', '15:30'),
            'sms_sender_id': current_app.config.get('SMS_SENDER_ID', 'HSTLFD'),
            'twilio_phone_number': current_app.config.get('TWILIO_PHONE_NUMBER', ''),
            'sms_provider': current_app.config.get('SMS_PROVIDER', 'mock')
        })

    @app.route('/api/admin/reset-db', methods=['POST'])
    @admin_required
    def reset_database():
        """Development helper to clear entries or whole database."""
        data = request.get_json() or {}
        target = data.get('target', 'entries')

        if target == 'all':
            from backup_service import create_database_backup
            create_database_backup(label="pre_reset_safety", app=current_app)
            FoodEntry.query.delete()
            FeePayment.query.delete()
            RejectedAttempt.query.delete()
            SmsLog.query.delete()
            Student.query.delete()
        else:
            FoodEntry.query.delete()
            RejectedAttempt.query.delete()

        db.session.commit()
        log_audit(f"Reset database target={target}", target_type="system")
        return jsonify({
            'success': True,
            'message': f"Database ({'all records' if target == 'all' else 'food entries'}) reset successfully."
        })

    # ------------------------------------------
    # DATABASE BACKUP & PERSISTENCE APIS
    # ------------------------------------------

    @app.route('/api/admin/backups', methods=['GET'])
    @admin_required
    def get_database_backups():
        """List all available database snapshots and storage statistics."""
        from backup_service import list_backups
        backups = list_backups()
        return jsonify({'success': True, 'backups': backups, 'count': len(backups)})

    @app.route('/api/admin/backups/create', methods=['POST'])
    @admin_required
    def trigger_database_backup():
        """Create an on-demand, transactional database snapshot."""
        from backup_service import create_database_backup
        data = request.get_json() or {}
        label = data.get('label', 'manual')
        res = create_database_backup(label=label, app=current_app)
        if res.get('success'):
            log_audit(f"Created manual database backup: {res.get('backup_file')}", target_type="backup")
            return jsonify(res), 200
        return jsonify(res), 500

    @app.route('/api/admin/backups/restore', methods=['POST'])
    @admin_required
    def restore_database_backup():
        """Restore database from a selected backup snapshot."""
        from backup_service import restore_database_from_backup
        data = request.get_json() or {}
        backup_file = data.get('backup_file')
        if not backup_file:
            return jsonify({'success': False, 'message': 'Backup filename required.'}), 400
        res = restore_database_from_backup(backup_file, app=current_app)
        if res.get('success'):
            sync_student_register_excel(app=current_app, force_rebuild=True)
            log_audit(f"Restored database from snapshot: {backup_file}", target_type="backup")
            return jsonify(res), 200
        return jsonify(res), 500


_startup_initialized = False


def create_app(test_config=None):
    """Application factory for Hostel Food Management System."""
    global _startup_initialized
    app = Flask(__name__)
    app.config.from_object(Config)

    if test_config:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config.get('BACKUP_DIR', os.path.join(app.instance_path, 'backups')), exist_ok=True)
    os.makedirs(app.config.get('EXPORTS_DIR', os.path.join(app.instance_path, 'exports')), exist_ok=True)
    os.makedirs(app.config.get('REPORTS_DIR', 'reports'), exist_ok=True)
    db.init_app(app)

    register_routes(app)

    # Automatic schema migration, startup backup & persistence check
    if not app.config.get('TESTING') and not _startup_initialized:
        _startup_initialized = True
        try:
            from backup_service import create_database_backup
            b_res = create_database_backup(label="startup", app=app)
            if b_res.get('success'):
                print(f"[Backup] Startup snapshot preserved: {b_res['backup_file']}")
        except Exception as e:
            print(f"[Backup] Startup note: {e}")

        migrate_database(app)
        try:
            ex_res = sync_student_register_excel(app=app)
            if ex_res.get('success'):
                print(f"[ExcelSync] Permanent student register verified: {ex_res['excel_path']} ({ex_res['row_count']} students)")
        except Exception as e:
            print(f"[ExcelSync] Startup sync note: {e}")

    app.config['TEMPLATES_AUTO_RELOAD'] = True
    return app


# Default application instance for standard execution (e.g. Gunicorn: app:app)
app = create_app()

# Enable reverse-proxy header support for Render/cloud deployments
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)


def _cleanup_stale_port_listeners(port: int):
    """On Windows, SO_REUSEADDR allows multiple processes to bind to the same port.
    Ensure any stale previous instance on this port is terminated before binding."""
    if os.name != 'nt':
        return
    try:
        import subprocess
        my_pids = {str(os.getpid()), str(os.getppid())}
        out = subprocess.check_output(['netstat', '-ano'], text=True, stderr=subprocess.DEVNULL)
        stale_pids = set()
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[0].upper() == 'TCP' and parts[3].upper() == 'LISTENING':
                local_addr = parts[1]
                pid = parts[4]
                if local_addr.endswith(f':{port}') and pid not in my_pids and pid != '0':
                    stale_pids.add(pid)
        for pid in stale_pids:
            subprocess.run(['taskkill', '/F', '/PID', pid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"[Server] Terminated stale process (PID {pid}) previously holding port {port}.")
    except Exception:
        pass


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() in ('true', '1', 'yes')
    _cleanup_stale_port_listeners(port)
    print(f"AI-Powered Hostel Food Management System running on http://0.0.0.0:{port}")
    print(f"Admin portal available at http://0.0.0.0:{port}/admin")
    print(f"Student portal available at http://0.0.0.0:{port}/student")
    app.run(host='0.0.0.0', port=port, debug=debug)
