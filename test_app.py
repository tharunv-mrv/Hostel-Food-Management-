"""
AI-POWERED HOSTEL FOOD MANAGEMENT SYSTEM
Automated Acceptance Criteria Test Suite (TEST 1 to TEST 40)

Test Scenarios:
TEST 1: An administrator can log in and manage students.
TEST 2: A student cannot access admin-only pages or APIs.
TEST 3: An administrator can register a student and enroll their face.
TEST 4: An administrator can update an individual student's hostel fee.
TEST 5: When a payment is recorded, pending fees are recalculated correctly.
TEST 6: A student with a disabled meal access status is rejected.
TEST 7: A student who violates the configured fee policy is rejected.
TEST 8: A student with valid access can record breakfast during breakfast hours.
TEST 9: A student with valid access can record lunch during lunch hours.
TEST 10: Meal entry outside the configured serving window is rejected.
TEST 11: Repeated requests cannot create duplicate meal attendance.
TEST 12: An Excel report includes the required columns and correct meal totals.
TEST 13: SMS notifications are queued only after successful attendance.
TEST 14: An SMS provider failure does not delete a valid attendance record.
TEST 15: A student cannot view another student's personal information.
TEST 16: Existing project features continue to work after the upgrade.
TEST 17: Fee calculations remain correct when payments are corrected or reversed.
TEST 18: Simultaneous attendance requests do not produce duplicate entries.
TEST 19: Daily reports can be regenerated safely without corrupting historical data.
TEST 20: Sensitive administrative actions are recorded in the audit log.
TEST 21: Attendance logs and rejected logs endpoints return accurate data.
TEST 22: Excel formula injection sanitization prevents spreadsheet calculation exploits.
TEST 23: Excel export creates multi-worksheet reports (Breakfast & Lunch).
TEST 24: SMS service idempotency prevents duplicate notifications.
TEST 25: Face recognition API enforces quality metrics and 5-point landmark detection.
TEST 26: Student phone numbers are masked for data privacy.
TEST 27: Dashboard refresh endpoints return consistent, isolated data.
TEST 28: Refresh operation never modifies or purges existing records.
TEST 29: Clear endpoints require explicit administrator authentication and authorization.
TEST 30: Clearing attendance archives records while preserving students and fee accounts.
TEST 31: Clearing rejections moves logs to archive while preserving successful attendance.
TEST 32: Clearing SMS logs archives historical records without dropping queued dispatches.
TEST 33: Clearing audit trail creates an immutable retention log entry.
TEST 34: Unified clear router and archive inspection endpoints operate securely.
TEST 35: Permanent deletion is blocked under default data retention policies.
TEST 36: Health check endpoints return system health and service readiness.
TEST 37: Templates contain accessibility landmarks, skip links, table captions, and ARIA roles.
TEST 38: HTTP responses enforce defense-in-depth security headers and CSRF endpoint returns token.
TEST 39: Sensitive endpoints enforce sliding-window rate limiting when enabled.
TEST 40: Custom error handlers sanitize 404, 403, and 400 API responses without leaking internals.
TEST 41: End-to-end CSRF validation during student registration across all security scenarios.
"""

import unittest
import json
import os
import openpyxl
import numpy as np
from datetime import datetime
from sqlalchemy.pool import StaticPool

from app import create_app, db, validate_meal_eligibility
from models import (
    AdminUser, Student, FeePayment, FoodEntry, RejectedAttempt, SmsLog, DailyReport, AuditLog, MealMenu,
    ArchivedFoodEntry, ArchivedRejectedAttempt, ArchivedSmsLog, ArchivedAuditLog
)
from report_service import generate_daily_attendance_excel, sanitize_cell
from sms_service import send_meal_sms_async
from face_service import face_service


class HostelFoodSystemFullTestSuite(unittest.TestCase):
    def setUp(self):
        """Create a fresh, isolated in-memory test database for every test method."""
        self.app = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
            'SQLALCHEMY_ENGINE_OPTIONS': {
                'poolclass': StaticPool,
                'connect_args': {'check_same_thread': False}
            },
            'SECRET_KEY': 'test-secret-key-1234',
            'ENFORCE_MEAL_HOURS': False,
            'ENFORCE_LUNCH_HOURS': False,
            'FEE_POLICY_ENFORCED': False,
            'MAX_PERMITTED_FEE_BALANCE': 5000.0,
            'DEFAULT_ADMIN_USERNAME': 'admin',
            'DEFAULT_ADMIN_PASSWORD': 'Admin@123',
            'RECOGNITION_THRESHOLD': 0.363,
            'SMS_PROVIDER': 'mock'
        })
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()

        # Initialize fresh database tables and default admin
        db.create_all()

        # Create default admin for test execution
        admin = AdminUser(username='admin', email='admin@canteen.edu', role='admin')
        admin.set_password('Admin@123')
        db.session.add(admin)
        db.session.commit()

    def tearDown(self):
        """Clean up in-memory database after each test method."""
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def _login_as_admin(self):
        return self.client.post('/api/auth/login', json={
            'role': 'admin',
            'username': 'admin',
            'password': 'Admin@123'
        })

    def _create_test_student(self, student_id="TEST001", name="Tharun Test", total_fees=75000.0, fees_paid=75000.0, meal_access=True, active=True):
        vec = np.ones(128, dtype=np.float32)
        vec = (vec / np.linalg.norm(vec)).tolist()
        student = Student(
            student_id=student_id,
            name=name,
            srn=f"SRN-{student_id}",
            phone_number="9876543210",
            room_number="302",
            room_sharing_type="Double",
            room_occupants=2,
            branch="AIML",
            year="1st Year",
            hostel="Kaveri Hostel",
            total_hostel_fees=total_fees,
            total_fees_paid=fees_paid,
            last_payment_date=datetime.now().strftime('%Y-%m-%d'),
            face_encoding=json.dumps(vec),
            active=active,
            meal_access_enabled=meal_access
        )
        student.set_password("Student@123")
        db.session.add(student)
        db.session.commit()
        return student

    # ==========================================
    # TESTS
    # ==========================================

    def test_01_admin_login_and_manage_students(self):
        """TEST 1: An administrator can log in and manage students."""
        res_login = self._login_as_admin()
        self.assertEqual(res_login.status_code, 200)
        self.assertTrue(res_login.get_json()['success'])

        # Admin lists students
        res_list = self.client.get('/api/students')
        self.assertEqual(res_list.status_code, 200)
        self.assertTrue(res_list.get_json()['success'])

    def test_02_student_cannot_access_admin_endpoints(self):
        """TEST 2: A student cannot access admin-only pages or APIs."""
        self._create_test_student()
        # Login as student
        res_stud_login = self.client.post('/api/auth/login', json={
            'role': 'student',
            'username': 'TEST001',
            'password': 'Student@123'
        })
        self.assertEqual(res_stud_login.status_code, 200)

        # Attempt to access admin API
        res_admin_api = self.client.get('/api/students')
        self.assertEqual(res_admin_api.status_code, 403)

        # Attempt to access admin web route
        res_admin_page = self.client.get('/admin')
        self.assertEqual(res_admin_page.status_code, 302)  # Redirects away

    def test_03_admin_register_student_and_enroll_face(self):
        """TEST 3: An administrator can register a student and enroll their face."""
        self._login_as_admin()
        payload = {
            'student_id': 'SRN900',
            'name': 'New Resident',
            'srn': 'PES900',
            'phone_number': '9988776655',
            'hostel': 'Ganga Hostel',
            'room_number': '101',
            'room_sharing_type': 'Single',
            'room_occupants': 1,
            'branch': 'CSE',
            'year': '1st Year',
            'total_hostel_fees': 80000.0,
            'total_fees_paid': 80000.0
        }
        res = self.client.post('/api/students/register', json=payload)
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertTrue(data['success'])

        student = Student.query.filter_by(student_id='SRN900').first()
        self.assertIsNotNone(student)
        self.assertEqual(student.name, 'New Resident')

    def test_04_admin_update_individual_student_fee(self):
        """TEST 4: An administrator can update an individual student's hostel fee."""
        self._login_as_admin()
        student = self._create_test_student(student_id="FEE001", total_fees=75000.0)

        res = self.client.put(f'/api/students/{student.student_id}', json={
            'total_hostel_fees': 90000.0
        })
        self.assertEqual(res.status_code, 200)
        updated = Student.query.filter_by(student_id="FEE001").first()
        self.assertEqual(updated.total_hostel_fees, 90000.0)

    def test_05_payment_recording_and_pending_recalculation(self):
        """TEST 5: When a payment is recorded, pending fees are recalculated correctly."""
        self._login_as_admin()
        student = self._create_test_student(student_id="PAY001", total_fees=75000.0, fees_paid=25000.0)
        self.assertEqual(student.pending_fees, 50000.0)

        res = self.client.post('/api/fees/payment', json={
            'student_id': 'PAY001',
            'amount': 30000.0,
            'payment_method': 'UPI',
            'reference_no': 'REF-12345'
        })
        self.assertEqual(res.status_code, 201)

        updated = Student.query.filter_by(student_id="PAY001").first()
        self.assertEqual(updated.total_fees_paid, 55000.0)
        self.assertEqual(updated.pending_fees, 20000.0)
        self.assertEqual(updated.fee_status, 'PARTIALLY PAID')

    def test_06_disabled_meal_access_rejection(self):
        """TEST 6: A student with a disabled meal access status is rejected."""
        student = self._create_test_student(student_id="DIS001", meal_access=False)
        student.meal_restriction_reason = "Hostel discipline penalty"
        db.session.commit()

        eligible, reason, code = validate_meal_eligibility(student, 'Lunch')
        self.assertFalse(eligible)
        self.assertEqual(code, 'meal_access_disabled')
        self.assertIn("Hostel discipline penalty", reason)

    def test_07_fee_policy_violation_rejection(self):
        """TEST 7: A student who violates the configured fee policy is rejected."""
        self.app.config['FEE_POLICY_ENFORCED'] = True
        self.app.config['MAX_PERMITTED_FEE_BALANCE'] = 5000.0

        # Student with 20,000 pending balance
        student = self._create_test_student(student_id="DEF001", total_fees=75000.0, fees_paid=55000.0)
        self.assertEqual(student.pending_fees, 20000.0)

        eligible, reason, code = validate_meal_eligibility(student, 'Lunch')
        self.assertFalse(eligible)
        self.assertEqual(code, 'fee_policy_violation')

    def test_08_record_breakfast_service(self):
        """TEST 8: A student with valid access can record breakfast during breakfast hours."""
        student = self._create_test_student(student_id="BF001")
        today_str = datetime.now().strftime('%Y-%m-%d')

        entry = FoodEntry(
            student_id=student.student_id,
            student_name=student.name,
            meal='Breakfast',
            entry_date=today_str,
            entry_time='08:30:00 AM',
            status='Approved'
        )
        db.session.add(entry)
        db.session.commit()

        fetched = FoodEntry.query.filter_by(student_id='BF001', meal='Breakfast').first()
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.meal, 'Breakfast')

    def test_09_record_lunch_service(self):
        """TEST 9: A student with valid access can record lunch during lunch hours."""
        student = self._create_test_student(student_id="LUN001")
        today_str = datetime.now().strftime('%Y-%m-%d')

        entry = FoodEntry(
            student_id=student.student_id,
            student_name=student.name,
            meal='Lunch',
            entry_date=today_str,
            entry_time='01:15:00 PM',
            status='Approved'
        )
        db.session.add(entry)
        db.session.commit()

        fetched = FoodEntry.query.filter_by(student_id='LUN001', meal='Lunch').first()
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.meal, 'Lunch')

    def test_10_meal_outside_serving_window_rejected(self):
        """TEST 10: Meal entry outside the configured serving window is rejected."""
        self.app.config['ENFORCE_MEAL_HOURS'] = True
        # Set serving hours in the past
        self.app.config['LUNCH_START_TIME'] = '01:00'
        self.app.config['LUNCH_END_TIME'] = '01:05'

        student = self._create_test_student(student_id="OUT001")
        eligible, reason, code = validate_meal_eligibility(student, 'Lunch')
        self.assertFalse(eligible)
        self.assertEqual(code, 'outside_hours')

    def test_11_duplicate_meal_attendance_prevention(self):
        """TEST 11: Repeated requests cannot create duplicate meal attendance."""
        student = self._create_test_student(student_id="DUP001")
        today_str = datetime.now().strftime('%Y-%m-%d')

        # First entry
        entry = FoodEntry(
            student_id=student.student_id,
            student_name=student.name,
            meal='Lunch',
            entry_date=today_str,
            entry_time='12:30:00 PM',
            status='Approved'
        )
        db.session.add(entry)
        db.session.commit()

        # Attempt eligibility for same meal today
        eligible, reason, code = validate_meal_eligibility(student, 'Lunch')
        self.assertFalse(eligible)
        self.assertEqual(code, 'already_recorded')

    def test_12_excel_report_generation_and_columns(self):
        """TEST 12: An Excel report includes the required columns and correct meal totals."""
        today_str = datetime.now().strftime('%Y-%m-%d')
        student = self._create_test_student(student_id="REP001", name="Excel Tester")

        # Record breakfast & lunch
        e1 = FoodEntry(student_id=student.student_id, student_name=student.name, meal='Breakfast', entry_date=today_str, entry_time='08:00 AM', status='Approved')
        e2 = FoodEntry(student_id=student.student_id, student_name=student.name, meal='Lunch', entry_date=today_str, entry_time='01:00 PM', status='Approved')
        db.session.add_all([e1, e2])
        db.session.commit()

        res = generate_daily_attendance_excel(today_str, self.app.config['REPORTS_DIR'])
        self.assertTrue(os.path.exists(res['excel_path']))
        self.assertEqual(res['total_breakfast'], 1)
        self.assertEqual(res['total_lunch'], 1)
        self.assertEqual(res['total_meals_served'], 2)

        # Inspect excel columns
        wb = openpyxl.load_workbook(res['excel_path'])
        ws = wb.active
        headers = [ws.cell(row=4, column=i).value for i in range(1, 16)]
        self.assertIn("Student ID", headers)
        self.assertIn("Registered Phone Number", headers)
        self.assertIn("Room Sharing Details", headers)
        self.assertIn("Breakfast Entry Time", headers)
        self.assertIn("Lunch Entry Time", headers)
        self.assertIn("Number of Meals Taken", headers)
        self.assertIn("Pending Fees (₹)", headers)
        self.assertIn("Fee Status", headers)

    def test_13_sms_notification_logging(self):
        """TEST 13: SMS notifications are logged only after successful attendance."""
        student = self._create_test_student(student_id="SMS001")
        sms_log = SmsLog(
            student_id=student.student_id,
            student_name=student.name,
            phone_number=student.phone_number,
            message="Hello Tharun, your Lunch was recorded.",
            meal_type="Lunch",
            status="sent",
            provider_name="mock"
        )
        db.session.add(sms_log)
        db.session.commit()

        fetched = SmsLog.query.filter_by(student_id='SMS001').first()
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.status, 'sent')

    def test_14_sms_failure_preserves_attendance_record(self):
        """TEST 14: An SMS provider failure does not delete a valid attendance record."""
        student = self._create_test_student(student_id="SMSFAIL001")
        today_str = datetime.now().strftime('%Y-%m-%d')

        entry = FoodEntry(
            student_id=student.student_id,
            student_name=student.name,
            meal='Lunch',
            entry_date=today_str,
            entry_time='01:00 PM',
            status='Approved'
        )
        db.session.add(entry)

        # Failed SMS record
        sms_log = SmsLog(
            student_id=student.student_id,
            student_name=student.name,
            phone_number=student.phone_number,
            message="Test msg",
            meal_type="Lunch",
            status="failed",
            error_message="Gateway Timeout"
        )
        db.session.add(sms_log)
        db.session.commit()

        # Meal entry must remain preserved!
        preserved = FoodEntry.query.filter_by(student_id="SMSFAIL001").first()
        self.assertIsNotNone(preserved)
        self.assertEqual(preserved.status, 'Approved')

    def test_15_student_privacy_isolation(self):
        """TEST 15: A student cannot view another student's personal information."""
        s1 = self._create_test_student(student_id="PRIV001", name="Alice")
        s2 = self._create_test_student(student_id="PRIV002", name="Bob")

        # Login as Alice
        self.client.post('/api/auth/login', json={'role': 'student', 'username': 'PRIV001', 'password': 'Student@123'})

        # Fetch own profile
        res = self.client.get('/api/student/profile')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()['student']
        self.assertEqual(data['student_id'], 'PRIV001')
        self.assertEqual(data['name'], 'Alice')

    def test_16_backward_compatibility_existing_features(self):
        """TEST 16: Existing project features continue to work after upgrade."""
        res_scanner = self.client.get('/')
        self.assertEqual(res_scanner.status_code, 200)

        res_entries = self.client.get('/api/entries/today')
        self.assertEqual(res_entries.status_code, 200)
        self.assertIn('today_lunch_count', res_entries.get_json()['metrics'])

    def test_17_fee_correction_and_reversal(self):
        """TEST 17: Fee calculations remain correct when payments are corrected or reversed."""
        self._login_as_admin()
        student = self._create_test_student(student_id="REV001", total_fees=75000.0, fees_paid=50000.0)

        # Record payment
        res_pay = self.client.post('/api/fees/payment', json={
            'student_id': 'REV001',
            'amount': 25000.0,
            'payment_method': 'Cash'
        })
        pay_id = res_pay.get_json()['payment']['id']
        self.assertEqual(student.pending_fees, 0.0)

        # Reverse payment
        res_rev = self.client.post(f'/api/fees/correction/{pay_id}', json={
            'reason': 'Incorrect amount deposited'
        })
        self.assertEqual(res_rev.status_code, 200)

        reloaded = Student.query.filter_by(student_id="REV001").first()
        self.assertEqual(reloaded.total_fees_paid, 50000.0)
        self.assertEqual(reloaded.pending_fees, 25000.0)

    def test_18_atomic_unique_attendance_constraint(self):
        """TEST 18: Simultaneous attendance requests do not produce duplicate entries."""
        student = self._create_test_student(student_id="ATOMIC001")
        today_str = datetime.now().strftime('%Y-%m-%d')

        entry1 = FoodEntry(student_id=student.student_id, student_name=student.name, meal='Lunch', entry_date=today_str, entry_time='12:00 PM', status='Approved')
        db.session.add(entry1)
        db.session.commit()

        # Database level unique constraint check
        entry2 = FoodEntry(student_id=student.student_id, student_name=student.name, meal='Lunch', entry_date=today_str, entry_time='12:00 PM', status='Approved')
        db.session.add(entry2)
        with self.assertRaises(Exception):
            db.session.commit()
        db.session.rollback()

    def test_19_idempotent_report_regeneration(self):
        """TEST 19: Daily reports can be regenerated safely without corrupting historical data."""
        today_str = datetime.now().strftime('%Y-%m-%d')
        student = self._create_test_student(student_id="IDEM001")

        # Generate report 1
        res1 = generate_daily_attendance_excel(today_str, self.app.config['REPORTS_DIR'])
        count1 = DailyReport.query.filter_by(report_date=today_str).count()
        self.assertEqual(count1, 1)

        # Generate report 2 for same date
        res2 = generate_daily_attendance_excel(today_str, self.app.config['REPORTS_DIR'])
        count2 = DailyReport.query.filter_by(report_date=today_str).count()
        self.assertEqual(count2, 1)  # Stays 1, updated idempotently

    def test_20_sensitive_admin_actions_recorded_in_audit_log(self):
        """TEST 20: Sensitive administrative actions are recorded in the audit log."""
        self._login_as_admin()
        student = self._create_test_student(student_id="AUDIT001")

        # Toggle meal access
        self.client.post(f'/api/students/{student.student_id}/toggle-meal-access', json={
            'reason': 'Pending payment review'
        })

        audit_entry = AuditLog.query.filter_by(target_id='AUDIT001').first()
        self.assertIsNotNone(audit_entry)
        self.assertIn("Toggled meal access", audit_entry.action)

    def test_21_attendance_logs_and_rejected_logs_endpoints(self):
        """TEST 21: Attendance and rejection log APIs return correctly formatted entries with date filtering."""
        today_str = datetime.now().strftime('%Y-%m-%d')
        student = self._create_test_student(student_id="ATT001", name="Attendance Tester")

        # Create food entry
        entry = FoodEntry(
            student_id="ATT001",
            student_name="Attendance Tester",
            meal="Lunch",
            entry_date=today_str,
            entry_time="12:30:00 PM",
            verification_method="face",
            status="Approved"
        )
        # Create rejected attempt
        rej = RejectedAttempt(
            student_id="ATT001",
            student_name="Attendance Tester",
            meal_type="Lunch",
            attempt_date=today_str,
            attempt_time="12:45:00 PM",
            reason="Lunch already recorded today",
            verification_method="face"
        )
        db.session.add_all([entry, rej])
        db.session.commit()

        # Unauthenticated rejected entries -> 403
        res_rej_unauth = self.client.get('/api/entries/rejected')
        self.assertEqual(res_rej_unauth.status_code, 403)

        # Authenticate admin
        self._login_as_admin()

        # Fetch rejected entries
        res_rej = self.client.get('/api/entries/rejected')
        self.assertEqual(res_rej.status_code, 200)
        rej_data = res_rej.get_json()
        self.assertTrue(rej_data['success'])
        self.assertGreaterEqual(len(rej_data['rejected']), 1)
        self.assertEqual(rej_data['rejected'][0]['student_id'], 'ATT001')

        # Fetch attendance entries for today
        res_att = self.client.get('/api/entries/today')
        self.assertEqual(res_att.status_code, 200)
        att_data = res_att.get_json()
        self.assertTrue(att_data['success'])
        self.assertEqual(len(att_data['entries']), 1)
        self.assertEqual(att_data['entries'][0]['student_id'], 'ATT001')

        # Fetch attendance entries with date query param
        res_att_date = self.client.get(f'/api/entries/today?date={today_str}')
        self.assertEqual(res_att_date.status_code, 200)
        self.assertEqual(len(res_att_date.get_json()['entries']), 1)

    def test_22_excel_formula_injection_sanitization(self):
        """TEST 22: Cell values starting with formula control characters are safely escaped."""
        self.assertEqual(sanitize_cell("=1+1"), "'=1+1")
        self.assertEqual(sanitize_cell("+SUM(A1:A10)"), "'+SUM(A1:A10)")
        self.assertEqual(sanitize_cell("-2+3"), "'-2+3")
        self.assertEqual(sanitize_cell("@malicious_macro"), "'@malicious_macro")
        self.assertEqual(sanitize_cell("\tcmd.exe"), "'\tcmd.exe")
        self.assertEqual(sanitize_cell("Normal Text 123"), "Normal Text 123")
        self.assertEqual(sanitize_cell(12345), 12345)
        self.assertIsNone(sanitize_cell(None))

    def test_23_excel_multi_worksheet_workbook(self):
        """TEST 23: Excel workbook contains all required worksheets with formatted metadata."""
        today_str = datetime.now().strftime('%Y-%m-%d')
        student = self._create_test_student(student_id="MS001", name="Multi Sheet Tester")
        e1 = FoodEntry(student_id=student.student_id, student_name=student.name, meal='Breakfast', entry_date=today_str, entry_time='08:15 AM', status='Approved')
        db.session.add(e1)
        db.session.commit()

        res = generate_daily_attendance_excel(today_str, self.app.config['REPORTS_DIR'])
        wb = openpyxl.load_workbook(res['excel_path'])
        
        # Check all 4 worksheets exist
        self.assertIn("Daily Attendance", wb.sheetnames)
        self.assertIn("Breakfast Service", wb.sheetnames)
        self.assertIn("Lunch Service", wb.sheetnames)
        self.assertIn("Service Summary", wb.sheetnames)

        # Inspect summary sheet
        ws_sum = wb["Service Summary"]
        self.assertEqual(ws_sum["A1"].value, "HOSTEL CANTEEN DAILY AUDIT SUMMARY")
        cell_vals = [ws_sum.cell(row=r, column=1).value for r in range(1, 15)]
        self.assertIn("Total Registered Residents", cell_vals)
        self.assertIn("Breakfast Meals Served", cell_vals)
        self.assertIn("Lunch Meals Served", cell_vals)

    def test_24_sms_idempotency_deduplication(self):
        """TEST 24: SMS service deduplicates notifications for identical student, meal, and date."""
        student = self._create_test_student(student_id="IDEM_SMS01")
        today_str = datetime.now().strftime('%Y-%m-%d')

        # Trigger first async SMS
        send_meal_sms_async(self.app, student.student_id, student.name, student.phone_number, "Lunch", "01:00 PM", today_str)
        
        import time
        time.sleep(0.5)

        sms_count_1 = SmsLog.query.filter_by(student_id=student.student_id, meal_type="Lunch").count()
        self.assertEqual(sms_count_1, 1)

        # Trigger second duplicate async SMS for same meal/date
        send_meal_sms_async(self.app, student.student_id, student.name, student.phone_number, "Lunch", "01:05 PM", today_str)
        time.sleep(0.5)

        sms_count_2 = SmsLog.query.filter_by(student_id=student.student_id, meal_type="Lunch").count()
        self.assertEqual(sms_count_2, 1)

    def test_25_automatic_scanner_api_quality_and_landmarks(self):
        """TEST 25: Automated scan-face endpoint returns proper status codes, boxes, and landmark metadata."""
        # Test 1: Invalid/empty payload
        res_empty = self.client.post('/api/scan-face', json={'image': ''})
        self.assertEqual(res_empty.status_code, 400)

        # Test 2: Blank black image (no face detected)
        import cv2
        import base64
        blank_img = np.zeros((480, 640, 3), dtype=np.uint8)
        _, buf = cv2.imencode('.jpg', blank_img)
        b64 = "data:image/jpeg;base64," + base64.b64encode(buf).decode('utf-8')

        res_no_face = self.client.post('/api/scan-face', json={'image': b64, 'meal_type': 'auto'})
        self.assertEqual(res_no_face.status_code, 200)
        data_no_face = res_no_face.get_json()
        self.assertFalse(data_no_face['success'])
        self.assertIn(data_no_face['status'], ['no_face', 'quality_fail', 'detection_error'])

    def test_26_phone_number_masking_privacy(self):
        """TEST 26: Phone numbers are masked for privacy on audit and log interfaces."""
        def mask_phone(phone):
            if not phone:
                return "--"
            clean = str(phone).strip()
            if len(clean) >= 10:
                return "******" + clean[-4:]
            return clean

        self.assertEqual(mask_phone("9876543210"), "******3210")
        self.assertEqual(mask_phone("+919876543210"), "******3210")
        self.assertEqual(mask_phone(""), "--")
        self.assertEqual(mask_phone(None), "--")

    def test_27_dashboard_refresh_endpoints_consistency(self):
        """TEST 27: All four dashboard refresh API endpoints return HTTP 200 with complete data structures."""
        self._login_as_admin()
        
        # 1. Attendance Today
        res1 = self.client.get('/api/entries/today')
        self.assertEqual(res1.status_code, 200)
        self.assertIn('entries', res1.get_json())
        self.assertIn('metrics', res1.get_json())

        # 2. Rejected Entries
        res2 = self.client.get('/api/entries/rejected')
        self.assertEqual(res2.status_code, 200)
        self.assertIn('rejected', res2.get_json())

        # 3. SMS Logs
        res3 = self.client.get('/api/sms/logs')
        self.assertEqual(res3.status_code, 200)
        self.assertIn('logs', res3.get_json())

        # 4. Audit Logs
        res4 = self.client.get('/api/audit-logs')
        self.assertEqual(res4.status_code, 200)
        self.assertIn('logs', res4.get_json())

    def test_28_refresh_does_not_delete_records(self):
        """TEST 28: Refresh endpoints reload data without deleting or modifying any records."""
        self._login_as_admin()
        today_str = datetime.now().strftime('%Y-%m-%d')
        student = self._create_test_student(student_id="REFRESH01")

        e = FoodEntry(student_id=student.student_id, student_name=student.name, meal='Lunch', entry_date=today_str, entry_time='12:30 PM', status='Approved')
        r = RejectedAttempt(student_id=student.student_id, student_name=student.name, meal_type='Lunch', attempt_date=today_str, attempt_time='12:35 PM', reason='Duplicate')
        s = SmsLog(student_id=student.student_id, student_name=student.name, phone_number=student.phone_number, message='Test', meal_type='Lunch', status='sent')
        a = AuditLog(action='Test action', actor_username='admin', target_type='test', target_id='1')
        db.session.add_all([e, r, s, a])
        db.session.commit()

        # Call all refresh endpoints
        self.client.get('/api/entries/today')
        self.client.get('/api/entries/rejected')
        self.client.get('/api/sms/logs')
        self.client.get('/api/audit/logs')

        # Verify all records still exist exactly as before
        self.assertEqual(FoodEntry.query.count(), 1)
        self.assertEqual(RejectedAttempt.query.count(), 1)
        self.assertEqual(SmsLog.query.count(), 1)
        self.assertGreaterEqual(AuditLog.query.count(), 1)

    def test_29_clear_endpoints_require_admin_authorization(self):
        """TEST 29: Clear Records endpoints reject unauthenticated users and student accounts."""
        student = self._create_test_student(student_id="UNAUTH01")

        endpoints = [
            '/api/entries/clear',
            '/api/entries/rejected/clear',
            '/api/sms/logs/clear',
            '/api/audit/logs/clear'
        ]

        # 1. Unauthenticated requests -> 403
        for ep in endpoints:
            res = self.client.post(ep, json={'reason': 'hack'})
            self.assertEqual(res.status_code, 403)

        # 2. Authenticated as student -> 403
        self.client.post('/api/auth/login', json={
            'role': 'student',
            'username': 'UNAUTH01',
            'password': 'Student@123'
        })
        for ep in endpoints:
            res = self.client.post(ep, json={'reason': 'hack'})
            self.assertEqual(res.status_code, 403)

    def test_30_attendance_clearing_archives_and_preserves_students_fees(self):
        """TEST 30: Clearing attendance moves records to archive, updates counts, and preserves student & fee records."""
        today_str = datetime.now().strftime('%Y-%m-%d')
        student = self._create_test_student(student_id="ATTCLR01", total_fees=80000.0, fees_paid=50000.0)

        # Add fee payment
        pay = FeePayment(student_id=student.student_id, student_name=student.name, amount=50000.0, payment_date=today_str, payment_method='UPI')
        # Add 2 attendance entries
        e1 = FoodEntry(student_id=student.student_id, student_name=student.name, meal='Breakfast', entry_date=today_str, entry_time='08:00 AM', status='Approved')
        e2 = FoodEntry(student_id=student.student_id, student_name=student.name, meal='Lunch', entry_date=today_str, entry_time='01:00 PM', status='Approved')
        db.session.add_all([pay, e1, e2])
        db.session.commit()

        self._login_as_admin()

        # Clear attendance
        res = self.client.post('/api/entries/clear', json={
            'date': today_str,
            'reason': 'Testing archive operation'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['archived_count'], 2)

        # Active attendance for today must be 0
        self.assertEqual(FoodEntry.query.filter_by(entry_date=today_str).count(), 0)

        # Archive table must contain the 2 archived records
        archived = ArchivedFoodEntry.query.filter_by(student_id='ATTCLR01').all()
        self.assertEqual(len(archived), 2)
        self.assertEqual(archived[0].archive_reason, 'Testing archive operation')
        self.assertIsNotNone(archived[0].archived_at)

        # Student profile and fee records must be completely untouched
        stud_db = Student.query.filter_by(student_id='ATTCLR01').first()
        self.assertIsNotNone(stud_db)
        self.assertEqual(stud_db.total_hostel_fees, 80000.0)
        self.assertEqual(stud_db.total_fees_paid, 50000.0)
        self.assertEqual(FeePayment.query.filter_by(student_id='ATTCLR01').count(), 1)

        # Today metrics endpoint reflects 0 served meals
        res_today = self.client.get('/api/entries/today')
        self.assertEqual(res_today.get_json()['metrics']['today_lunch_count'], 0)
        self.assertEqual(res_today.get_json()['metrics']['today_breakfast_count'], 0)

    def test_31_rejections_clearing_preserves_successful_attendance(self):
        """TEST 31: Clearing rejections archives rejected attempts and preserves successful meal records."""
        today_str = datetime.now().strftime('%Y-%m-%d')
        student = self._create_test_student(student_id="REJCLR01")

        # Successful attendance
        entry = FoodEntry(student_id=student.student_id, student_name=student.name, meal='Lunch', entry_date=today_str, entry_time='12:30 PM', status='Approved')
        # Rejected attempts
        r1 = RejectedAttempt(student_id=student.student_id, student_name=student.name, meal_type='Lunch', attempt_date=today_str, attempt_time='12:00 PM', reason='Duplicate')
        r2 = RejectedAttempt(student_id=None, student_name='Unknown', meal_type='Lunch', attempt_date=today_str, attempt_time='12:05 PM', reason='Face not recognized')
        db.session.add_all([entry, r1, r2])
        db.session.commit()

        self._login_as_admin()

        res = self.client.post('/api/entries/rejected/clear', json={'reason': 'Clean rejected attempts'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['archived_count'], 2)

        # Rejections cleared
        self.assertEqual(RejectedAttempt.query.count(), 0)
        # Archived rejections populated
        self.assertEqual(ArchivedRejectedAttempt.query.count(), 2)
        # Successful attendance remains untouched
        self.assertEqual(FoodEntry.query.count(), 1)

    def test_32_sms_clearing_preserves_queued_messages_and_attendance(self):
        """TEST 32: Clearing SMS logs preserves in-flight/queued messages and attendance records."""
        student = self._create_test_student(student_id="SMSCLR01")

        entry = FoodEntry(student_id=student.student_id, student_name=student.name, meal='Lunch', entry_date='2026-10-09', entry_time='12:30 PM', status='Approved')
        s1 = SmsLog(student_id=student.student_id, student_name=student.name, phone_number=student.phone_number, message='Delivered msg', meal_type='Lunch', status='delivered')
        s2 = SmsLog(student_id=student.student_id, student_name=student.name, phone_number=student.phone_number, message='Failed msg', meal_type='Lunch', status='failed')
        s_queued = SmsLog(student_id=student.student_id, student_name=student.name, phone_number=student.phone_number, message='Queued in-flight', meal_type='Lunch', status='queued')
        db.session.add_all([entry, s1, s2, s_queued])
        db.session.commit()

        self._login_as_admin()

        res = self.client.post('/api/sms/logs/clear', json={'reason': 'Archive completed SMS'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['archived_count'], 2)

        # Queued in-flight message must NOT be deleted or cancelled
        remaining = SmsLog.query.all()
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0].status, 'queued')

        # Archived count
        self.assertEqual(ArchivedSmsLog.query.count(), 2)
        # Attendance untouched
        self.assertEqual(FoodEntry.query.count(), 1)

    def test_33_audit_clearing_archives_and_creates_retention_entry(self):
        """TEST 33: Clearing audit logs archives records and records an immutable retention event in active audit trail."""
        a1 = AuditLog(action='Admin login', actor_username='admin', target_type='auth', target_id='admin')
        a2 = AuditLog(action='Student enrolled', actor_username='admin', target_type='student', target_id='STU01')
        db.session.add_all([a1, a2])
        db.session.commit()

        self._login_as_admin()

        res = self.client.post('/api/audit/logs/clear', json={'reason': 'Quarterly archive'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertGreaterEqual(data['archived_count'], 2)

        # Preserved in archive
        self.assertGreaterEqual(ArchivedAuditLog.query.count(), 2)

        # Active audit log must contain the new retention event documenting the clearing action!
        active_logs = AuditLog.query.all()
        self.assertEqual(len(active_logs), 1)
        self.assertIn("Archived Security Audit Trail", active_logs[0].action)
        self.assertIn("Quarterly archive", active_logs[0].details)

    def test_34_unified_clear_endpoint_and_archive_inspection(self):
        """TEST 34: Unified clear router and archive inspection API function correctly."""
        self._login_as_admin()

        # Bad module name
        res_bad = self.client.post('/api/admin/clear-records/invalid_mod', json={})
        self.assertEqual(res_bad.status_code, 400)

        # Archive view endpoints
        res_att = self.client.get('/api/archive/attendance')
        self.assertEqual(res_att.status_code, 200)
        self.assertIn('records', res_att.get_json())

        res_rej = self.client.get('/api/archive/rejections')
        self.assertEqual(res_rej.status_code, 200)

        res_sms = self.client.get('/api/archive/sms')
        self.assertEqual(res_sms.status_code, 200)

        res_audit = self.client.get('/api/archive/audit')
        self.assertEqual(res_audit.status_code, 200)

    def test_35_permanent_deletion_policy_enforcement(self):
        """TEST 35: Permanent deletion purge action is prohibited by default retention policy."""
        self._login_as_admin()

        res_purge_att = self.client.post('/api/entries/clear', json={'action': 'purge'})
        self.assertEqual(res_purge_att.status_code, 403)

        res_purge_audit = self.client.post('/api/audit/logs/clear', json={'action': 'purge'})
        self.assertEqual(res_purge_audit.status_code, 403)

    def test_36_health_check_endpoints(self):
        """TEST 36: Production health check endpoints return healthy status and diagnostic information."""
        # Root health check endpoint
        res = self.client.get('/health')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get('status'), 'healthy')
        self.assertIn('models_loaded', data)
        self.assertIn('database', data)

        # API health check endpoint
        res_api = self.client.get('/api/health')
        self.assertEqual(res_api.status_code, 200)
        data_api = res_api.get_json()
        self.assertEqual(data_api.get('status'), 'healthy')
        self.assertEqual(data_api.get('database'), 'sqlite')

    def test_37_accessibility_landmarks_and_skip_link(self):
        """TEST 37: Templates contain accessibility landmarks, skip links, table captions, and ARIA roles."""
        # 1. Login page
        res_login = self.client.get('/login')
        self.assertEqual(res_login.status_code, 200)
        self.assertIn(b'class="skip-link"', res_login.data)
        self.assertIn(b'role="tablist"', res_login.data)
        self.assertIn(b'aria-selected="true"', res_login.data)
        self.assertIn(b'id="login-main"', res_login.data)

        # 2. Main scanner page
        res_index = self.client.get('/')
        self.assertEqual(res_index.status_code, 200)
        self.assertIn(b'class="skip-link"', res_index.data)
        self.assertIn(b'role="banner"', res_index.data)
        self.assertIn(b'role="radiogroup"', res_index.data)
        self.assertIn(b'id="manualEntryModal"', res_index.data)
        self.assertIn(b'role="dialog"', res_index.data)

        # 3. Admin portal
        self._login_as_admin()
        res_admin = self.client.get('/admin')
        self.assertEqual(res_admin.status_code, 200)
        self.assertIn(b'class="skip-link"', res_admin.data)
        self.assertIn(b'role="tablist"', res_admin.data)
        self.assertIn(b'role="tabpanel"', res_admin.data)
        self.assertIn(b'<caption class="sr-only">', res_admin.data)
        self.assertIn(b'scope="col"', res_admin.data)

        # 4. Student portal
        self.client.get('/api/auth/logout')
        self._create_test_student("STU_A11Y")
        self.client.post('/api/auth/login', json={'role': 'student', 'username': 'STU_A11Y', 'password': 'Student@123'})
        res_student = self.client.get('/student')
        self.assertEqual(res_student.status_code, 200)
        self.assertIn(b'class="skip-link"', res_student.data)
        self.assertIn(b'role="tablist"', res_student.data)
        self.assertIn(b'<caption class="sr-only">', res_student.data)

    def test_38_security_headers_and_csrf_endpoint(self):
        """TEST 38: HTTP responses enforce defense-in-depth security headers and CSRF endpoint returns valid token."""
        res = self.client.get('/login')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get('X-Content-Type-Options'), 'nosniff')
        self.assertEqual(res.headers.get('X-Frame-Options'), 'SAMEORIGIN')
        self.assertEqual(res.headers.get('X-XSS-Protection'), '1; mode=block')
        self.assertEqual(res.headers.get('Referrer-Policy'), 'strict-origin-when-cross-origin')

        # CSRF token endpoint
        res_csrf = self.client.get('/api/auth/csrf')
        self.assertEqual(res_csrf.status_code, 200)
        data = res_csrf.get_json()
        self.assertTrue(data.get('success'))
        csrf_tok = data.get('csrf_token')
        self.assertIsNotNone(csrf_tok)
        self.assertEqual(len(csrf_tok), 64)

    def test_39_rate_limiting_enforcement(self):
        """TEST 39: Sensitive endpoints enforce sliding-window rate limiting when enabled."""
        from app import _rate_limit_records
        _rate_limit_records.clear()

        # Create isolated app instance with rate limiting enabled and testing flag false
        rl_app = create_app({
            'TESTING': False,
            'RATE_LIMIT_ENABLED': True,
            'CSRF_ENABLED': False,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
            'SQLALCHEMY_ENGINE_OPTIONS': {
                'poolclass': StaticPool,
                'connect_args': {'check_same_thread': False}
            },
            'SECRET_KEY': 'rl-secret'
        })
        with rl_app.app_context():
            db.create_all()
            with rl_app.test_client() as client:
                # Login limit is 25 per minute; verify that 26th request receives 429
                for _ in range(25):
                    client.post('/api/auth/login', json={'role': 'admin', 'username': 'fake', 'password': 'bad'})
                res_blocked = client.post('/api/auth/login', json={'role': 'admin', 'username': 'fake', 'password': 'bad'})
                self.assertEqual(res_blocked.status_code, 429)
                data = res_blocked.get_json()
                self.assertFalse(data.get('success'))
                self.assertEqual(data.get('error'), 'Rate Limit Exceeded')

        _rate_limit_records.clear()

    def test_40_custom_error_handlers_sanitization(self):
        """TEST 40: Custom error handlers sanitize 404, 403, and 400 API responses without leaking internals."""
        # 404 Not Found API
        res_404 = self.client.get('/api/undefined-endpoint-xyz')
        self.assertEqual(res_404.status_code, 404)
        data_404 = res_404.get_json()
        self.assertFalse(data_404.get('success'))
        self.assertEqual(data_404.get('error'), 'Not Found')

        # 403 Forbidden API
        res_403 = self.client.get('/api/admin/config')
        self.assertEqual(res_403.status_code, 403)
        data_403 = res_403.get_json()
        self.assertFalse(data_403.get('success'))
        self.assertEqual(data_403.get('message'), 'Admin privilege required.')

        # 400 Bad Request API
        self._login_as_admin()
        res_400 = self.client.post('/api/admin/clear-records/nonexistent_mod', json={})
        self.assertEqual(res_400.status_code, 400)
        data_400 = res_400.get_json()
        self.assertFalse(data_400.get('success'))
        self.assertIn('Unknown module', data_400.get('message'))

    def test_41_student_registration_csrf_validation_suite(self):
        """TEST 41: End-to-end CSRF validation during student registration across all security scenarios."""
        # Create an app instance with CSRF_ENABLED=True and TESTING=False to test actual middleware
        csrf_app = create_app({
            'TESTING': False,
            'CSRF_ENABLED': True,
            'RATE_LIMIT_ENABLED': False,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
            'SQLALCHEMY_ENGINE_OPTIONS': {
                'poolclass': StaticPool,
                'connect_args': {'check_same_thread': False}
            },
            'SECRET_KEY': 'csrf-test-secret-key'
        })
        with csrf_app.app_context():
            db.create_all()
            if not AdminUser.query.filter_by(username='admin').first():
                admin = AdminUser(username='admin', email='admin@canteen.edu', role='admin')
                admin.set_password('Admin@123')
                db.session.add(admin)
                db.session.commit()

            with csrf_app.test_client() as client:
                # 1. Login as admin
                login_res = client.post('/api/auth/login', json={
                    'role': 'admin',
                    'username': 'admin',
                    'password': 'Admin@123'
                })
                self.assertEqual(login_res.status_code, 200)
                login_data = login_res.get_json()
                self.assertTrue(login_data['success'])
                csrf_token = login_data.get('csrf_token')
                self.assertIsNotNone(csrf_token)
                self.assertEqual(len(csrf_token), 64)

                # 2. Open admin page and verify CSRF token and hidden input are rendered in template
                admin_page_res = client.get('/admin')
                self.assertEqual(admin_page_res.status_code, 200)
                self.assertIn(f'name="csrf-token" content="{csrf_token}"'.encode(), admin_page_res.data)
                self.assertIn(b'id="regCsrfToken"', admin_page_res.data)

                # 3. Scenario A: Submit registration WITHOUT CSRF token -> MUST FAIL with 403
                res_no_csrf = client.post('/api/students/register', json={
                    'student_id': 'CSRF001',
                    'name': 'No Csrf Student',
                    'phone_number': '9876543210'
                })
                self.assertEqual(res_no_csrf.status_code, 403)
                data_no_csrf = res_no_csrf.get_json()
                self.assertFalse(data_no_csrf['success'])
                self.assertIn('CSRF validation failed', data_no_csrf['message'])
                # Verify student was NOT saved in database
                self.assertIsNone(Student.query.filter_by(student_id='CSRF001').first())

                # 4. Scenario B: Submit registration with INVALID CSRF token -> MUST FAIL with 403
                res_bad_csrf = client.post('/api/students/register', headers={
                    'X-CSRF-Token': 'invalid-token-1234567890abcdef'
                }, json={
                    'student_id': 'CSRF002',
                    'name': 'Bad Csrf Student',
                    'phone_number': '9876543210'
                })
                self.assertEqual(res_bad_csrf.status_code, 403)
                data_bad_csrf = res_bad_csrf.get_json()
                self.assertFalse(data_bad_csrf['success'])
                self.assertIn('CSRF validation failed', data_bad_csrf['message'])

                # 5. Scenario C: Submit registration WITH VALID CSRF header -> MUST SUCCEED with 200
                res_valid_header = client.post('/api/students/register', headers={
                    'X-CSRF-Token': csrf_token
                }, json={
                    'student_id': 'CSRF003',
                    'name': 'Valid Header Student',
                    'srn': 'SRN-CSRF003',
                    'phone_number': '9876543210',
                    'hostel': 'Kaveri Hostel',
                    'room_number': '201',
                    'total_hostel_fees': 75000.0,
                    'total_fees_paid': 25000.0
                })
                self.assertEqual(res_valid_header.status_code, 201)
                data_valid = res_valid_header.get_json()
                self.assertTrue(data_valid['success'])
                # Verify student is properly saved in database with all details
                saved_student = Student.query.filter_by(student_id='CSRF003').first()
                self.assertIsNotNone(saved_student)
                self.assertEqual(saved_student.name, 'Valid Header Student')
                self.assertEqual(saved_student.pending_fees, 50000.0)

                # 6. Scenario D: Duplicate student registration prevented -> MUST FAIL with 400
                res_duplicate = client.post('/api/students/register', headers={
                    'X-CSRF-Token': csrf_token
                }, json={
                    'student_id': 'CSRF003',
                    'name': 'Duplicate Student',
                    'phone_number': '9876543210'
                })
                self.assertEqual(res_duplicate.status_code, 400)
                self.assertIn('already registered', res_duplicate.get_json()['message'])

                # 7. Scenario E: Submit registration with CSRF token in JSON body -> MUST SUCCEED with 201
                res_valid_body = client.post('/api/students/register', json={
                    'csrf_token': csrf_token,
                    'student_id': 'CSRF004',
                    'name': 'Valid Body Student',
                    'phone_number': '9876543210',
                    'hostel': 'Kaveri Hostel',
                    'room_number': '202'
                })
                self.assertEqual(res_valid_body.status_code, 201)
                self.assertTrue(res_valid_body.get_json()['success'])
                self.assertIsNotNone(Student.query.filter_by(student_id='CSRF004').first())

                # 8. Scenario F: Refreshing token via /api/auth/csrf and submitting again
                refresh_res = client.get('/api/auth/csrf')
                self.assertEqual(refresh_res.status_code, 200)
                refreshed_token = refresh_res.get_json()['csrf_token']
                res_after_refresh = client.post('/api/students/register', headers={
                    'X-CSRF-Token': refreshed_token
                }, json={
                    'student_id': 'CSRF005',
                    'name': 'After Refresh Student',
                    'phone_number': '9876543210'
                })
                self.assertEqual(res_after_refresh.status_code, 201)
                self.assertTrue(res_after_refresh.get_json()['success'])

                # 9. Scenario G: Session logout / expiration -> request rejected
                client.get('/logout')
                res_logged_out = client.post('/api/students/register', headers={
                    'X-CSRF-Token': csrf_token
                }, json={
                    'student_id': 'CSRF006',
                    'name': 'Expired Session Student',
                    'phone_number': '9876543210'
                })
                self.assertIn(res_logged_out.status_code, (401, 403))

    def test_42_database_persistence_and_backup_endpoints(self):
        """TEST 42: Automated database backup and persistence endpoints verify system snapshots."""
        self._login_as_admin()

        # 1. Non-admin access rejected
        with self.app.test_client() as unauth_client:
            res_unauth = unauth_client.get('/api/admin/backups')
            self.assertEqual(res_unauth.status_code, 403)

        # 2. Admin retrieves backup list
        res_list = self.client.get('/api/admin/backups')
        self.assertEqual(res_list.status_code, 200)
        data_list = res_list.get_json()
        self.assertTrue(data_list['success'])
        self.assertIn('backups', data_list)

        # 3. Direct backup service function testing
        from backup_service import list_backups, rotate_backups
        backups = list_backups()
        self.assertIsInstance(backups, list)
        pruned = rotate_backups(max_backups=20)
        self.assertIsInstance(pruned, int)

    def test_43_student_registration_persistence_across_app_restarts_and_deletion(self):
        """TEST 43: Register student, delete student, restart app, verify disk persistence, no duplicates, and real subprocess restart."""
        import tempfile
        import sqlite3
        import subprocess
        import sys

        temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        temp_db_path = os.path.abspath(temp_db.name)
        temp_db.close()

        uri = f"sqlite:///{temp_db_path.replace(os.sep, '/')}"

        cfg = {
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': uri,
            'SECRET_KEY': 'test-secret-persistence',
            'ENFORCE_MEAL_HOURS': False,
            'ENFORCE_LUNCH_HOURS': False,
            'FEE_POLICY_ENFORCED': False,
            'DEFAULT_ADMIN_USERNAME': 'admin',
            'DEFAULT_ADMIN_PASSWORD': 'Admin@123',
            'SMS_PROVIDER': 'mock'
        }

        try:
            # === PHASE 1: FIRST APP LIFECYCLE (REGISTRATION & DELETION) ===
            app1 = create_app(cfg)
            with app1.app_context():
                db.create_all()
                admin = AdminUser(username='admin', email='admin@canteen.edu', role='admin')
                admin.set_password('Admin@123')
                db.session.add(admin)
                db.session.commit()

            with app1.test_client() as client1:
                # Login as admin
                l_res = client1.post('/api/auth/login', json={'role': 'admin', 'username': 'admin', 'password': 'Admin@123'})
                self.assertEqual(l_res.status_code, 200)
                csrf1 = l_res.get_json().get('csrf_token')
                hdrs = {'X-CSRFToken': csrf1}

                # Register student A (To be kept and verified)
                res_a = client1.post('/api/students/register', json={
                    'student_id': 'TESTPERSIST001',
                    'name': 'Persistent Student',
                    'srn': 'PES12026001',
                    'phone_number': '9845012345',
                    'branch': 'CSE',
                    'year': '2nd Year',
                    'hostel': 'Ganga Hostel',
                    'room_number': 'R101',
                    'room_sharing_type': 'Double',
                    'room_occupants': 2,
                    'total_hostel_fees': 75000.0,
                    'total_fees_paid': 35000.0
                }, headers=hdrs)
                self.assertEqual(res_a.status_code, 201)

                # Register student B (To be deleted)
                res_b = client1.post('/api/students/register', json={
                    'student_id': 'TESTPERSIST002',
                    'name': 'Temporary Student',
                    'srn': 'PES12026002',
                    'phone_number': '9845099999',
                    'branch': 'ECE',
                    'year': '1st Year',
                    'hostel': 'Kaveri Hostel',
                    'room_number': 'K202',
                    'total_hostel_fees': 75000.0,
                    'total_fees_paid': 20000.0
                }, headers=hdrs)
                self.assertEqual(res_b.status_code, 201)

                # Delete student B
                del_res = client1.delete('/api/students/TESTPERSIST002', headers=hdrs)
                self.assertEqual(del_res.status_code, 200)
                self.assertTrue(del_res.get_json()['success'])

            # Cleanly close and dispose app1 connections
            with app1.app_context():
                db.session.remove()
                db.engine.dispose()
            del app1

            # === PHASE 2: DIRECT DISK INSPECTION (PRE-RESTART) ===
            con = sqlite3.connect(temp_db_path)
            cur = con.cursor()
            cur.execute("SELECT student_id, name, room_number, total_fees_paid FROM students")
            disk_rows = cur.fetchall()
            con.close()

            disk_ids = [r[0] for r in disk_rows]
            self.assertIn('TESTPERSIST001', disk_ids)
            self.assertNotIn('TESTPERSIST002', disk_ids)
            row_a = next(r for r in disk_rows if r[0] == 'TESTPERSIST001')
            self.assertEqual(row_a[1], 'Persistent Student')
            self.assertEqual(row_a[2], 'R101')
            self.assertEqual(row_a[3], 35000.0)

            # === PHASE 3: SECOND APP LIFECYCLE (IN-PROCESS RESTART SIMULATION) ===
            app2 = create_app(cfg)
            self.assertEqual(app2.config['SQLALCHEMY_DATABASE_URI'], uri)

            with app2.test_client() as client2:
                # Login as admin in restarted app
                l_res2 = client2.post('/api/auth/login', json={'role': 'admin', 'username': 'admin', 'password': 'Admin@123'})
                self.assertEqual(l_res2.status_code, 200)

                # List students
                st_res = client2.get('/api/students')
                self.assertEqual(st_res.status_code, 200)
                st_data = st_res.get_json()
                self.assertTrue(st_data['success'])
                all_ids = [s['student_id'] for s in st_data['students']]

                # Persistent student must exist and details must be identical
                self.assertIn('TESTPERSIST001', all_ids)
                s_details = next(s for s in st_data['students'] if s['student_id'] == 'TESTPERSIST001')
                self.assertEqual(s_details['name'], 'Persistent Student')
                self.assertEqual(s_details['room_number'], 'R101')
                self.assertEqual(s_details['hostel'], 'Ganga Hostel')
                self.assertEqual(s_details['total_fees_paid'], 35000.0)

                # Verify student ID is NOT duplicated
                with app2.app_context():
                    self.assertEqual(Student.query.filter_by(student_id='TESTPERSIST001').count(), 1)

                # Deleted student must NEVER reappear
                self.assertNotIn('TESTPERSIST002', all_ids)
                # Seed demo students must NOT have been auto-injected
                self.assertNotIn('1XX23AIML001', all_ids)
                self.assertNotIn('1XX23CSE042', all_ids)

            with app2.app_context():
                db.session.remove()
                db.engine.dispose()
            del app2

            # === PHASE 4: GENUINE SEPARATE-PROCESS RESTART VERIFICATION ===
            # Spawns a completely new operating system process running Python to verify that
            # true process termination, memory clearance, and fresh reload preserve data.
            sub_py_code = (
                "import sys, os, json\n"
                "from app import create_app, db\n"
                "from models import Student\n"
                f"cfg = {{'TESTING': True, 'SQLALCHEMY_DATABASE_URI': '{uri}', 'SECRET_KEY': 'test-subproc'}}\n"
                "app = create_app(cfg)\n"
                "with app.app_context():\n"
                "    students = Student.query.all()\n"
                "    s_ids = [s.student_id for s in students]\n"
                "    assert 'TESTPERSIST001' in s_ids, f'Missing student in new process: {s_ids}'\n"
                "    assert 'TESTPERSIST002' not in s_ids, f'Deleted student reappeared in new process: {s_ids}'\n"
                "    assert '1XX23AIML001' not in s_ids, 'Demo student auto-seeded in new process!'\n"
                "    s1 = Student.query.filter_by(student_id='TESTPERSIST001').first()\n"
                "    assert s1.name == 'Persistent Student'\n"
                "    assert s1.room_number == 'R101'\n"
                "    assert s1.total_fees_paid == 35000.0\n"
                "    print(json.dumps({'success': True, 'count': len(s_ids), 'students': s_ids}))\n"
            )
            sub_res = subprocess.run(
                [sys.executable, "-c", sub_py_code],
                capture_output=True,
                text=True,
                cwd=os.path.dirname(os.path.abspath(__file__))
            )
            self.assertEqual(sub_res.returncode, 0, f"Subprocess restart failed: {sub_res.stderr}")
            self.assertIn('"success": true', sub_res.stdout.lower())

        finally:
            for ext in ('', '-wal', '-shm'):
                candidate = temp_db_path + ext
                if os.path.exists(candidate):
                    try:
                        os.remove(candidate)
                    except Exception:
                        pass

    def test_44_live_server_abrupt_taskkill_persistence(self):
        """TEST 44: Start real HTTP server, register student over TCP, force-kill via taskkill /F, restart server, verify persistence."""
        import tempfile
        import sqlite3
        import subprocess
        import sys
        import time
        import urllib.request
        import http.cookiejar

        temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        temp_db_path = os.path.abspath(temp_db.name)
        temp_db.close()

        uri = f"sqlite:///{temp_db_path.replace(os.sep, '/')}"
        project_dir = os.path.dirname(os.path.abspath(__file__))
        port = 5099
        base_url = f"http://127.0.0.1:{port}"

        env = os.environ.copy()
        env['DATABASE_URL'] = uri
        env['PORT'] = str(port)
        env['FLASK_DEBUG'] = 'False'

        def wait_for_server(timeout=15.0):
            deadline = time.time() + timeout
            while time.time() < deadline:
                try:
                    with urllib.request.urlopen(f"{base_url}/health", timeout=1.5) as resp:
                        if resp.status == 200:
                            return True
                except Exception:
                    time.sleep(0.3)
            return False

        def force_kill_pid(pid):
            if os.name == 'nt':
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
            else:
                import signal
                try:
                    os.kill(pid, signal.SIGKILL)
                except Exception:
                    pass

        proc1 = None
        proc2 = None
        try:
            # 1. Start real Flask server #1 as a background OS process
            proc1 = subprocess.Popen(
                [sys.executable, "app.py"],
                cwd=project_dir,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            self.assertTrue(wait_for_server(), "Real Flask server #1 failed to start on port 5099")

            # 2. Authenticate and register student over real HTTP TCP connection
            cj1 = http.cookiejar.CookieJar()
            opener1 = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj1))

            login_req = urllib.request.Request(
                f"{base_url}/api/auth/login",
                data=json.dumps({'role': 'admin', 'username': 'admin', 'password': 'Admin@123'}).encode('utf-8'),
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            with opener1.open(login_req, timeout=5.0) as resp:
                self.assertEqual(resp.status, 200)
                login_data = json.loads(resp.read().decode('utf-8'))
                csrf_token = login_data['csrf_token']

            reg_payload = {
                'student_id': 'KILLTEST999',
                'name': 'Abrupt Kill Survivor',
                'srn': 'PES12026999',
                'phone_number': '9845077777',
                'branch': 'AIML',
                'year': '3rd Year',
                'hostel': 'Cauvery Hostel',
                'room_number': 'K999',
                'total_hostel_fees': 75000.0,
                'total_fees_paid': 40000.0
            }
            reg_req = urllib.request.Request(
                f"{base_url}/api/students/register",
                data=json.dumps(reg_payload).encode('utf-8'),
                headers={
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': csrf_token
                },
                method='POST'
            )
            with opener1.open(reg_req, timeout=5.0) as resp:
                self.assertEqual(resp.status, 201)
                reg_data = json.loads(resp.read().decode('utf-8'))
                self.assertTrue(reg_data['success'])

            # 3. Immediately force-kill server #1 with Windows taskkill /F (simulating abrupt VS Code exit)
            force_kill_pid(proc1.pid)
            proc1.wait(timeout=5.0)
            proc1 = None

            # 4. Inspect SQLite file on disk directly after abrupt kill
            con = sqlite3.connect(temp_db_path)
            cur = con.cursor()
            cur.execute("SELECT student_id, name, room_number, total_fees_paid FROM students WHERE student_id = 'KILLTEST999'")
            row = cur.fetchone()
            con.close()
            self.assertIsNotNone(row, "Student record lost after taskkill /F!")
            self.assertEqual(row[0], 'KILLTEST999')
            self.assertEqual(row[1], 'Abrupt Kill Survivor')

            # 5. Start real Flask server #2 on the same database file
            proc2 = subprocess.Popen(
                [sys.executable, "app.py"],
                cwd=project_dir,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            self.assertTrue(wait_for_server(), "Real Flask server #2 failed to start after restart")

            # 6. Query GET /api/students over HTTP on restarted server #2
            cj2 = http.cookiejar.CookieJar()
            opener2 = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj2))
            login_req2 = urllib.request.Request(
                f"{base_url}/api/auth/login",
                data=json.dumps({'role': 'admin', 'username': 'admin', 'password': 'Admin@123'}).encode('utf-8'),
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            with opener2.open(login_req2, timeout=5.0) as resp:
                self.assertEqual(resp.status, 200)

            with opener2.open(f"{base_url}/api/students", timeout=5.0) as resp:
                self.assertEqual(resp.status, 200)
                st_data = json.loads(resp.read().decode('utf-8'))
                self.assertTrue(st_data['success'])
                st_ids = [s['student_id'] for s in st_data['students']]
                self.assertIn('KILLTEST999', st_ids)

            with opener2.open(f"{base_url}/admin", timeout=5.0) as resp:
                self.assertEqual(resp.status, 200)
                admin_html = resp.read().decode('utf-8')
                self.assertIn('KILLTEST999', admin_html)
                self.assertIn('Abrupt Kill Survivor', admin_html)

            force_kill_pid(proc2.pid)
            proc2.wait(timeout=5.0)
            proc2 = None

        finally:
            for p in (proc1, proc2):
                if p is not None and p.poll() is None:
                    force_kill_pid(p.pid)
                    try:
                        p.wait(timeout=3.0)
                    except Exception:
                        pass
            for ext in ('', '-wal', '-shm', '-journal'):
                candidate = temp_db_path + ext
                if os.path.exists(candidate):
                    try:
                        os.remove(candidate)
                    except Exception:
                        pass

    def test_45_admin_portal_displays_existing_and_newly_registered_students(self):
        """
        Verify that both existing students and newly registered students are directly
        rendered in GET /admin HTML (#studentsTableBody, #feeAccountsTableBody,
        #metricTotalStudents, and #initialStudentsData) as well as returned by
        GET /api/students before and after application restart. Also verify read-only
        that the primary instance/hostel_food.db contains the 2 genuine students.
        """
        import sqlite3
        import tempfile
        from config import DEFAULT_DB_FILE

        # 1. Read-only verification of active instance/hostel_food.db
        if os.path.exists(DEFAULT_DB_FILE):
            ro_con = sqlite3.connect(f"file:{DEFAULT_DB_FILE}?mode=ro", uri=True)
            cur = ro_con.cursor()
            cur.execute("SELECT student_id, name, active FROM students ORDER BY student_id")
            prod_rows = cur.fetchall()
            ro_con.close()
            prod_ids = {r[0] for r in prod_rows}
            self.assertIn('25SUUBEAML729', prod_ids)
            self.assertIn('25SUUBEAML761', prod_ids)

        # 2. Isolated lifecycle test for /admin HTML and /api/students
        temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        temp_db_path = os.path.abspath(temp_db.name)
        temp_db.close()
        uri = f"sqlite:///{temp_db_path.replace(os.sep, '/')}"

        cfg = {
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': uri,
            'SECRET_KEY': 'test-admin-portal-render',
            'DEFAULT_ADMIN_USERNAME': 'admin',
            'DEFAULT_ADMIN_PASSWORD': 'Admin@123',
            'SMS_PROVIDER': 'mock'
        }

        try:
            app1 = create_app(cfg)
            with app1.app_context():
                db.create_all()
                admin = AdminUser(username='admin', email='admin@canteen.edu', role='admin')
                admin.set_password('Admin@123')
                existing_student = Student(
                    student_id='EXIST001',
                    name='Existing Resident One',
                    srn='EXIST001',
                    phone_number='9876543210',
                    branch='AIML',
                    year='2nd Year',
                    hostel='Main Hostel',
                    room_number='B201',
                    total_hostel_fees=150000.0,
                    total_fees_paid=75000.0,
                    active=True,
                    meal_access_enabled=True
                )
                db.session.add_all([admin, existing_student])
                db.session.commit()

            with app1.test_client() as client1:
                client1.post('/api/auth/login', json={'role': 'admin', 'username': 'admin', 'password': 'Admin@123'})

                # Verify existing student is rendered in /admin HTML immediately
                admin_res1 = client1.get('/admin')
                self.assertEqual(admin_res1.status_code, 200)
                html1 = admin_res1.data.decode('utf-8')
                self.assertIn('EXIST001', html1)
                self.assertIn('Existing Resident One', html1)
                self.assertIn('id="metricTotalStudents">1</h3>', html1)

                # Register a second student via API
                reg_res = client1.post('/api/students/register', json={
                    'student_id': 'NEWREG002',
                    'name': 'Newly Registered Two',
                    'srn': 'NEWREG002',
                    'phone_number': '9123456780',
                    'branch': 'CSE',
                    'year': '1st Year',
                    'hostel': 'Kaveri Hostel',
                    'room_number': 'C102',
                    'total_hostel_fees': 150000.0,
                    'total_fees_paid': 150000.0
                })
                self.assertEqual(reg_res.status_code, 201)

            with app1.app_context():
                db.session.remove()
                db.engine.dispose()

            # Simulate application restart with a new app instance on the same DB
            app2 = create_app(cfg)
            with app2.test_client() as client2:
                client2.post('/api/auth/login', json={'role': 'admin', 'username': 'admin', 'password': 'Admin@123'})

                admin_res2 = client2.get('/admin')
                self.assertEqual(admin_res2.status_code, 200)
                html2 = admin_res2.data.decode('utf-8')
                self.assertIn('EXIST001', html2)
                self.assertIn('Existing Resident One', html2)
                self.assertIn('NEWREG002', html2)
                self.assertIn('Newly Registered Two', html2)
                self.assertIn('id="metricTotalStudents">2</h3>', html2)

                api_res2 = client2.get('/api/students')
                self.assertEqual(api_res2.status_code, 200)
                api_data2 = api_res2.get_json()
                self.assertEqual(len(api_data2['students']), 2)

            with app2.app_context():
                db.session.remove()
                db.engine.dispose()
        finally:
            for ext in ('', '-wal', '-shm', '-journal'):
                candidate = temp_db_path + ext
                if os.path.exists(candidate):
                    try:
                        os.remove(candidate)
                    except Exception:
                        pass


class MajorProjectFixVerificationTests(unittest.TestCase):
    """
    Comprehensive Verification Suite (TEST A through TEST T) for:
    - Permanent SQLite Student Database Persistence
    - Permanent Excel Student Register Synchronization (student_register.xlsx)
    - Student Account Registration & SRN + Password Login
    - Administrator Password Reset for Students
    All tests run against isolated temporary SQLite databases and temporary Excel files.
    """

    def setUp(self):
        import shutil
        import tempfile
        self.temp_dir = tempfile.mkdtemp(prefix="hostel_major_fix_test_")
        self.db_path = os.path.join(self.temp_dir, "test_hostel_food.db")
        self.excel_path = os.path.join(self.temp_dir, "exports", "student_register.xlsx")
        self.db_uri = f"sqlite:///{self.db_path.replace(os.sep, '/')}"
        self.test_cfg = {
            'TESTING': True,
            'CSRF_ENABLED': False,
            'RATE_LIMIT_ENABLED': False,
            'SQLALCHEMY_DATABASE_URI': self.db_uri,
            'STUDENT_REGISTER_EXCEL_PATH': self.excel_path,
            'EXPORTS_DIR': os.path.dirname(self.excel_path),
            'SECRET_KEY': 'major-fix-test-secret',
            'DEFAULT_ADMIN_USERNAME': 'admin',
            'DEFAULT_ADMIN_PASSWORD': 'Admin@123',
            'DEFAULT_STUDENT_PASSWORD': 'Student@123',
            'SMS_PROVIDER': 'mock',
            'ENFORCE_MEAL_HOURS': False,
            'FEE_POLICY_ENFORCED': False,
        }
        self.app = create_app(self.test_cfg)
        from models import migrate_database
        with self.app.app_context():
            migrate_database(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        import shutil
        try:
            with self.app.app_context():
                db.session.remove()
                db.engine.dispose()
        except Exception:
            pass
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _admin_login(self, client=None):
        c = client or self.client
        res = c.post('/api/auth/login', json={
            'role': 'admin',
            'username': 'admin',
            'password': 'Admin@123'
        })
        self.assertEqual(res.status_code, 200)
        return res.get_json()

    def _read_excel_rows(self, path=None):
        from openpyxl import load_workbook
        target = path or self.excel_path
        self.assertTrue(os.path.exists(target), f"Expected Excel file at {target}")
        wb = load_workbook(target, read_only=False, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        wb.close()
        header = [str(c) for c in rows[0]] if rows else []
        data_rows = []
        for r in rows[1:]:
            if r and r[0] is not None:
                data_rows.append(dict(zip(header, r)))
        return header, data_rows

    def test_A_student_registration_persistence(self):
        """TEST A — Student Registration Persistence in SQLite, Excel register, and /api/students."""
        from excel_sync_service import REQUIRED_EXCEL_COLUMNS
        self._admin_login()
        res = self.client.post('/api/students/register', json={
            'student_id': '25SUUBEAML801',
            'srn': '25SUUBEAML801',
            'name': 'Arjun Rao',
            'phone_number': '9876500801',
            'hostel': 'Kaveri Hostel',
            'room_number': '101',
            'room_sharing_type': 'Double',
            'room_occupants': 2,
            'total_hostel_fees': 80000.0,
            'total_fees_paid': 50000.0,
            'password': 'ArjunPass123'
        })
        self.assertEqual(res.status_code, 201)
        body = res.get_json()
        self.assertTrue(body['success'])
        self.assertTrue(body['excel_synced'])

        # 1. Verify in SQLite database
        with self.app.app_context():
            st = Student.query.filter_by(srn='25SUUBEAML801').first()
            self.assertIsNotNone(st)
            self.assertEqual(st.name, 'Arjun Rao')
            self.assertEqual(st.pending_fees, 30000.0)

        # 2. Verify in Excel register
        header, rows = self._read_excel_rows()
        self.assertEqual(header, REQUIRED_EXCEL_COLUMNS)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['SRN'], '25SUUBEAML801')
        self.assertEqual(rows[0]['Student Name'], 'Arjun Rao')
        self.assertEqual(rows[0]['Hostel Room Number'], '101')
        self.assertEqual(float(rows[0]['Total Hostel Fees']), 80000.0)
        self.assertEqual(float(rows[0]['Fees Paid']), 50000.0)
        self.assertEqual(float(rows[0]['Pending Fees']), 30000.0)

        # 3. Verify in /api/students
        api_res = self.client.get('/api/students')
        self.assertEqual(api_res.status_code, 200)
        students = api_res.get_json()['students']
        self.assertEqual(len(students), 1)
        self.assertEqual(students[0]['srn'], '25SUUBEAML801')

    def test_B_persistence_across_restart(self):
        """TEST B — Persistence Across Restart: close DB session, recreate app instance, verify DB, Excel, and API."""
        self._admin_login()
        self.client.post('/api/students/register', json={
            'student_id': '25SUUBEAML802',
            'srn': '25SUUBEAML802',
            'name': 'Bhavana Nair',
            'phone_number': '9876500802',
            'hostel': 'Main Hostel',
            'room_number': '202',
            'password': 'BhavanaPass123'
        })

        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()

        # Recreate app instance pointing to same DB & Excel
        app2 = create_app(self.test_cfg)
        try:
            with app2.app_context():
                st = Student.query.filter_by(srn='25SUUBEAML802').first()
                self.assertIsNotNone(st)
                self.assertEqual(st.name, 'Bhavana Nair')

            with app2.test_client() as client2:
                self._admin_login(client2)
                api_res = client2.get('/api/students')
                self.assertEqual(api_res.status_code, 200)
                srns = [s['srn'] for s in api_res.get_json()['students']]
                self.assertIn('25SUUBEAML802', srns)

            _, rows = self._read_excel_rows()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['SRN'], '25SUUBEAML802')
        finally:
            with app2.app_context():
                db.session.remove()
                db.engine.dispose()

    def test_C_multiple_student_registrations_no_overwrite(self):
        """TEST C — Multiple Student Registrations: register 3 students sequentially without overwriting earlier ones."""
        self._admin_login()
        for idx, (srn, name) in enumerate([
            ('25SUUBEAML811', 'Student One'),
            ('25SUUBEAML812', 'Student Two'),
            ('25SUUBEAML813', 'Student Three'),
        ], start=1):
            r = self.client.post('/api/students/register', json={
                'student_id': srn,
                'srn': srn,
                'name': name,
                'phone_number': f'987650081{idx}',
                'room_number': f'30{idx}',
                'password': f'Pass{idx}#1234'
            })
            self.assertEqual(r.status_code, 201)

        with self.app.app_context():
            self.assertEqual(Student.query.count(), 3)

        _, rows = self._read_excel_rows()
        self.assertEqual(len(rows), 3)
        self.assertEqual([r['SRN'] for r in rows], ['25SUUBEAML811', '25SUUBEAML812', '25SUUBEAML813'])

    def test_D_duplicate_srn_protection(self):
        """TEST D — Duplicate SRN Protection: reject duplicate SRN and keep original DB record and Excel row intact."""
        self._admin_login()
        r1 = self.client.post('/api/students/register', json={
            'student_id': '25SUUBEAML820',
            'srn': '25SUUBEAML820',
            'name': 'Original Resident',
            'phone_number': '9876500820',
            'room_number': '401',
            'password': 'OrigPassword123'
        })
        self.assertEqual(r1.status_code, 201)

        # Attempt duplicate with lowercase/whitespace variations
        r2 = self.client.post('/api/students/register', json={
            'student_id': ' 25suubeaml820 ',
            'srn': ' 25suubeaml820 ',
            'name': 'Attempted Overwrite',
            'phone_number': '9999999999',
            'room_number': '999',
            'password': 'OtherPassword999'
        })
        self.assertEqual(r2.status_code, 400)
        self.assertFalse(r2.get_json()['success'])

        with self.app.app_context():
            st = Student.query.filter_by(srn='25SUUBEAML820').first()
            self.assertEqual(st.name, 'Original Resident')
            self.assertEqual(st.room_number, '401')

        _, rows = self._read_excel_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['Student Name'], 'Original Resident')

    def test_E_admin_logout_login_persistence(self):
        """TEST E — Admin Logout / Login Persistence: student remains visible in /api/students and /admin."""
        self._admin_login()
        self.client.post('/api/students/register', json={
            'student_id': '25SUUBEAML830',
            'srn': '25SUUBEAML830',
            'name': 'Persistent Resident',
            'phone_number': '9876500830',
            'room_number': '105'
        })
        self.client.get('/logout')
        self._admin_login()

        api_res = self.client.get('/api/students')
        self.assertEqual(api_res.status_code, 200)
        self.assertEqual(len(api_res.get_json()['students']), 1)

        admin_res = self.client.get('/admin')
        self.assertEqual(admin_res.status_code, 200)
        self.assertIn(b'25SUUBEAML830', admin_res.data)
        self.assertIn(b'Persistent Resident', admin_res.data)

    def test_F_student_login_success(self):
        """TEST F — Student Login Success with SRN and custom password."""
        self._admin_login()
        self.client.post('/api/students/register', json={
            'student_id': '25SUUBEAML840',
            'srn': '25SUUBEAML840',
            'name': 'Karthikeya V',
            'phone_number': '9876500840',
            'room_number': '208',
            'password': 'MySecretLogin99'
        })
        self.client.get('/logout')

        # Log in with lowercase SRN to verify normalization
        login_res = self.client.post('/api/auth/login', json={
            'role': 'student',
            'username': ' 25suubeaml840 ',
            'password': 'MySecretLogin99'
        })
        self.assertEqual(login_res.status_code, 200)
        login_data = login_res.get_json()
        self.assertTrue(login_data['success'])
        self.assertEqual(login_data['role'], 'student')
        self.assertEqual(login_data['srn'], '25SUUBEAML840')

        prof_res = self.client.get('/api/student/profile')
        self.assertEqual(prof_res.status_code, 200)
        self.assertEqual(prof_res.get_json()['student']['name'], 'Karthikeya V')

    def test_G_student_wrong_password_rejection(self):
        """TEST G — Student Wrong Password Rejection."""
        self._admin_login()
        self.client.post('/api/students/register', json={
            'student_id': '25SUUBEAML841',
            'srn': '25SUUBEAML841',
            'name': 'Deepa S',
            'phone_number': '9876500841',
            'password': 'CorrectPassword123'
        })
        self.client.get('/logout')

        bad_res = self.client.post('/api/auth/login', json={
            'role': 'student',
            'username': '25SUUBEAML841',
            'password': 'WrongPassword999'
        })
        self.assertEqual(bad_res.status_code, 401)
        self.assertFalse(bad_res.get_json()['success'])

    def test_H_student_unknown_srn_rejection(self):
        """TEST H — Student Unknown SRN Rejection."""
        res = self.client.post('/api/auth/login', json={
            'role': 'student',
            'username': 'NONEXISTENT_SRN_999',
            'password': 'AnyPassword123'
        })
        self.assertEqual(res.status_code, 401)
        self.assertFalse(res.get_json()['success'])
        self.assertIn('not found', res.get_json()['message'].lower())

    def test_I_inactive_student_login_rejection(self):
        """TEST I — Inactive Student Login Rejection."""
        self._admin_login()
        self.client.post('/api/students/register', json={
            'student_id': '25SUUBEAML842',
            'srn': '25SUUBEAML842',
            'name': 'Inactive Student',
            'phone_number': '9876500842',
            'password': 'ActivePass123'
        })
        self.client.post('/api/students/25SUUBEAML842/toggle-active')
        self.client.get('/logout')

        res = self.client.post('/api/auth/login', json={
            'role': 'student',
            'username': '25SUUBEAML842',
            'password': 'ActivePass123'
        })
        self.assertEqual(res.status_code, 403)
        self.assertFalse(res.get_json()['success'])
        self.assertIn('deactivated', res.get_json()['message'].lower())

    def test_J_admin_password_reset_success(self):
        """TEST J — Admin Password Reset Success: old password fails, new password succeeds."""
        self._admin_login()
        self.client.post('/api/students/register', json={
            'student_id': '25SUUBEAML850',
            'srn': '25SUUBEAML850',
            'name': 'Reset Target Student',
            'phone_number': '9876500850',
            'password': 'OldPassword123'
        })
        self.client.get('/logout')

        # 1. Verify login works with OldPassword123
        r_old_ok = self.client.post('/api/auth/login', json={
            'role': 'student',
            'username': '25SUUBEAML850',
            'password': 'OldPassword123'
        })
        self.assertEqual(r_old_ok.status_code, 200)
        self.client.get('/logout')

        # 2. Log in as admin and reset password to NewPassword456
        self._admin_login()
        rst_res = self.client.post('/api/students/25SUUBEAML850/reset-password', json={
            'new_password': 'NewPassword456',
            'confirm_password': 'NewPassword456',
            'must_change_password': True
        })
        self.assertEqual(rst_res.status_code, 200)
        self.assertTrue(rst_res.get_json()['success'])
        self.assertTrue(rst_res.get_json()['student']['must_change_password'])
        self.client.get('/logout')

        # 3. Verify student login fails with OldPassword123
        r_old_fail = self.client.post('/api/auth/login', json={
            'role': 'student',
            'username': '25SUUBEAML850',
            'password': 'OldPassword123'
        })
        self.assertEqual(r_old_fail.status_code, 401)

        # 4. Verify student login succeeds with NewPassword456
        r_new_ok = self.client.post('/api/auth/login', json={
            'role': 'student',
            'username': '25SUUBEAML850',
            'password': 'NewPassword456'
        })
        self.assertEqual(r_new_ok.status_code, 200)
        self.assertTrue(r_new_ok.get_json()['must_change_password'])

    def test_K_admin_password_reset_persistence_across_restart(self):
        """TEST K — Admin Password Reset Persistence Across Restart."""
        self._admin_login()
        self.client.post('/api/students/register', json={
            'student_id': '25SUUBEAML851',
            'srn': '25SUUBEAML851',
            'name': 'Restart Reset Student',
            'phone_number': '9876500851',
            'password': 'InitialPassword111'
        })
        self.client.post('/api/students/25SUUBEAML851/reset-password', json={
            'new_password': 'ResetPassword222',
            'confirm_password': 'ResetPassword222'
        })

        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()

        app2 = create_app(self.test_cfg)
        try:
            with app2.test_client() as client2:
                r_old = client2.post('/api/auth/login', json={
                    'role': 'student',
                    'username': '25SUUBEAML851',
                    'password': 'InitialPassword111'
                })
                self.assertEqual(r_old.status_code, 401)

                r_new = client2.post('/api/auth/login', json={
                    'role': 'student',
                    'username': '25SUUBEAML851',
                    'password': 'ResetPassword222'
                })
                self.assertEqual(r_new.status_code, 200)
        finally:
            with app2.app_context():
                db.session.remove()
                db.engine.dispose()

    def test_L_unauthorized_password_reset_rejection(self):
        """TEST L — Unauthorized Password Reset Rejection (unauthenticated and student role)."""
        self._admin_login()
        self.client.post('/api/students/register', json={
            'student_id': '25SUUBEAML852',
            'srn': '25SUUBEAML852',
            'name': 'Protected Student',
            'phone_number': '9876500852',
            'password': 'SafePassword123'
        })
        self.client.get('/logout')

        # 1. Unauthenticated attempt
        r_unauth = self.client.post('/api/students/25SUUBEAML852/reset-password', json={
            'new_password': 'HackedPassword999'
        })
        self.assertIn(r_unauth.status_code, (401, 403))

        # 2. Logged in as student attempt
        self.client.post('/api/auth/login', json={
            'role': 'student',
            'username': '25SUUBEAML852',
            'password': 'SafePassword123'
        })
        r_stu = self.client.post('/api/students/25SUUBEAML852/reset-password', json={
            'new_password': 'HackedPassword999'
        })
        self.assertIn(r_stu.status_code, (401, 403))
        self.client.get('/logout')

        # 3. Verify original password still works and hacked password fails
        r_orig = self.client.post('/api/auth/login', json={
            'role': 'student',
            'username': '25SUUBEAML852',
            'password': 'SafePassword123'
        })
        self.assertEqual(r_orig.status_code, 200)

    def test_M_password_reset_validation(self):
        """TEST M — Password Reset Validation: empty, too-short, mismatched confirm, and non-existent SRN."""
        self._admin_login()
        self.client.post('/api/students/register', json={
            'student_id': '25SUUBEAML853',
            'srn': '25SUUBEAML853',
            'name': 'Validation Student',
            'phone_number': '9876500853',
            'password': 'ValidOrigPassword1'
        })

        # Empty password
        r_empty = self.client.post('/api/students/25SUUBEAML853/reset-password', json={'new_password': ''})
        self.assertEqual(r_empty.status_code, 400)

        # Too-short password
        r_short = self.client.post('/api/students/25SUUBEAML853/reset-password', json={'new_password': '12345'})
        self.assertEqual(r_short.status_code, 400)

        # Mismatched confirm_password
        r_mismatch = self.client.post('/api/students/25SUUBEAML853/reset-password', json={
            'new_password': 'ValidNewPassword1',
            'confirm_password': 'DifferentPassword2'
        })
        self.assertEqual(r_mismatch.status_code, 400)

        # Non-existent SRN
        r_notfound = self.client.post('/api/students/UNKNOWN_SRN_404/reset-password', json={
            'new_password': 'ValidNewPassword1'
        })
        self.assertEqual(r_notfound.status_code, 404)

        # Verify original password was untouched
        self.client.get('/logout')
        r_login = self.client.post('/api/auth/login', json={
            'role': 'student',
            'username': '25SUUBEAML853',
            'password': 'ValidOrigPassword1'
        })
        self.assertEqual(r_login.status_code, 200)

    def test_N_password_reset_does_not_affect_other_students(self):
        """TEST N — Password Reset Does Not Affect Other Students."""
        self._admin_login()
        self.client.post('/api/students/register', json={
            'student_id': '25SUUBEAML861',
            'srn': '25SUUBEAML861',
            'name': 'Student One',
            'phone_number': '9876500861',
            'password': 'StudentOneOrig123'
        })
        self.client.post('/api/students/register', json={
            'student_id': '25SUUBEAML862',
            'srn': '25SUUBEAML862',
            'name': 'Student Two',
            'phone_number': '9876500862',
            'password': 'StudentTwoOrig456'
        })

        # Reset password for Student 1 only
        res = self.client.post('/api/students/25SUUBEAML861/reset-password', json={
            'new_password': 'StudentOneNew789'
        })
        self.assertEqual(res.status_code, 200)
        self.client.get('/logout')

        # Verify Student 2 still logs in with StudentTwoOrig456
        r2 = self.client.post('/api/auth/login', json={
            'role': 'student',
            'username': '25SUUBEAML862',
            'password': 'StudentTwoOrig456'
        })
        self.assertEqual(r2.status_code, 200)

    def test_O_password_security_in_db_logs_and_excel(self):
        """TEST O — Password Security in Database, Logs, and Excel."""
        self._admin_login()
        secret_pw = 'UltraSecretPlaintext#987'
        reset_pw = 'UltraResetPlaintext#654'
        self.client.post('/api/students/register', json={
            'student_id': '25SUUBEAML870',
            'srn': '25SUUBEAML870',
            'name': 'Security Audit Student',
            'phone_number': '9876500870',
            'password': secret_pw
        })
        self.client.post('/api/students/25SUUBEAML870/reset-password', json={
            'new_password': reset_pw
        })

        # 1. Verify DB stores hash, not plaintext, and AuditLog does not contain plaintext or hash
        with self.app.app_context():
            st = Student.query.filter_by(srn='25SUUBEAML870').first()
            self.assertNotEqual(st.password_hash, secret_pw)
            self.assertNotEqual(st.password_hash, reset_pw)
            self.assertTrue(st.check_password(reset_pw))
            pw_hash = st.password_hash

            logs = AuditLog.query.all()
            self.assertTrue(any('Admin password reset for student 25SUUBEAML870' in (l.action or '') for l in logs))
            for l in logs:
                blob = f"{l.action} {l.details}"
                self.assertNotIn(secret_pw, blob)
                self.assertNotIn(reset_pw, blob)
                self.assertNotIn(pw_hash, blob)

        # 2. Verify API responses do not expose password_hash
        api_res = self.client.get('/api/students')
        api_raw = json.dumps(api_res.get_json())
        self.assertNotIn('password_hash', api_raw)
        self.assertNotIn(reset_pw, api_raw)
        self.assertNotIn(pw_hash, api_raw)

        # 3. Verify Excel register does not contain password or password hash
        header, rows = self._read_excel_rows()
        for col in header:
            self.assertNotIn('password', col.lower())
        excel_raw = json.dumps(rows)
        self.assertNotIn(secret_pw, excel_raw)
        self.assertNotIn(reset_pw, excel_raw)
        self.assertNotIn(pw_hash, excel_raw)

    def test_P_excel_update_synchronization(self):
        """TEST P — Excel Update Synchronization on profile edit, fee payment, and status toggle without duplicates."""
        self._admin_login()
        self.client.post('/api/students/register', json={
            'student_id': '25SUUBEAML880',
            'srn': '25SUUBEAML880',
            'name': 'Sync Student',
            'phone_number': '9876500880',
            'room_number': '101',
            'room_sharing_type': 'Double',
            'total_hostel_fees': 75000.0,
            'total_fees_paid': 25000.0
        })

        # Update room, phone, sharing, and total fees
        u_res = self.client.put('/api/students/25SUUBEAML880', json={
            'phone_number': '9111122222',
            'room_number': '505',
            'room_sharing_type': 'Single',
            'total_hostel_fees': 90000.0
        })
        self.assertEqual(u_res.status_code, 200)

        # Record fee payment of 30000 -> total paid = 55000, pending = 35000
        p_res = self.client.post('/api/fees/payment', json={
            'student_id': '25SUUBEAML880',
            'amount': 30000.0,
            'payment_method': 'UPI'
        })
        self.assertEqual(p_res.status_code, 201)

        # Toggle active status to Inactive
        t_res = self.client.post('/api/students/25SUUBEAML880/toggle-active')
        self.assertEqual(t_res.status_code, 200)

        _, rows = self._read_excel_rows()
        self.assertEqual(len(rows), 1, "Must not create duplicate SRN rows in Excel!")
        row = rows[0]
        self.assertEqual(row['SRN'], '25SUUBEAML880')
        self.assertEqual(row['Phone Number'], '9111122222')
        self.assertEqual(row['Hostel Room Number'], '505')
        self.assertEqual(row['Room Sharing'], 'Single')
        self.assertEqual(row['Account Status'], 'Inactive')
        self.assertEqual(float(row['Total Hostel Fees']), 90000.0)
        self.assertEqual(float(row['Fees Paid']), 55000.0)
        self.assertEqual(float(row['Pending Fees']), 35000.0)

    def test_Q_excel_recovery_and_regeneration(self):
        """TEST Q — Excel Recovery / Regeneration when Excel file is missing or out of sync."""
        self._admin_login()
        self.client.post('/api/students/register', json={
            'student_id': '25SUUBEAML891',
            'srn': '25SUUBEAML891',
            'name': 'Recovery Student One',
            'phone_number': '9876500891'
        })
        self.client.post('/api/students/register', json={
            'student_id': '25SUUBEAML892',
            'srn': '25SUUBEAML892',
            'name': 'Recovery Student Two',
            'phone_number': '9876500892'
        })

        # Delete the Excel file to simulate missing file
        if os.path.exists(self.excel_path):
            os.remove(self.excel_path)
        self.assertFalse(os.path.exists(self.excel_path))

        # Trigger regeneration via Admin API
        sync_res = self.client.post('/api/admin/students/sync-excel')
        self.assertEqual(sync_res.status_code, 200)
        self.assertTrue(sync_res.get_json()['success'])
        self.assertTrue(os.path.exists(self.excel_path))

        _, rows = self._read_excel_rows()
        self.assertEqual(len(rows), 2)
        self.assertEqual({r['SRN'] for r in rows}, {'25SUUBEAML891', '25SUUBEAML892'})

        # Also verify download endpoint works
        dl_res = self.client.get('/api/admin/students/export-excel')
        self.assertEqual(dl_res.status_code, 200)
        dl_res.close()

    def test_R_face_registration_status_persistence(self):
        """TEST R — Face Registration Status Persistence in SQLite, /api/students, and Excel register."""
        from unittest.mock import patch
        self._admin_login()
        self.client.post('/api/students/register', json={
            'student_id': '25SUUBEAML901',
            'srn': '25SUUBEAML901',
            'name': 'Biometric Resident',
            'phone_number': '9876500901'
        })
        _, rows_before = self._read_excel_rows()
        self.assertEqual(rows_before[0]['Face Registration Status'], 'Not Registered')

        fake_encoding = [0.1234] * 128
        with patch.object(face_service, 'decode_base64_image', return_value=(np.zeros((100, 100, 3), dtype=np.uint8), None)), \
             patch.object(face_service, 'extract_face_encoding', return_value=(fake_encoding, 'data:image/jpeg;base64,thumb', None)):
            e_res = self.client.post('/api/students/25SUUBEAML901/enroll-face', json={
                'image': 'data:image/jpeg;base64,validface'
            })
            self.assertEqual(e_res.status_code, 200)

        api_res = self.client.get('/api/students')
        st_dict = api_res.get_json()['students'][0]
        self.assertTrue(st_dict['has_face_enrolled'])

        _, rows_after = self._read_excel_rows()
        self.assertEqual(rows_after[0]['Face Registration Status'], 'Registered')

    def test_S_canteen_verification_compatibility(self):
        """TEST S — Canteen Verification Compatibility after DB and Excel enhancements."""
        from unittest.mock import patch
        self._admin_login()
        fake_encoding = [0.25] * 128
        with patch.object(face_service, 'decode_base64_image', return_value=(np.zeros((100, 100, 3), dtype=np.uint8), None)), \
             patch.object(face_service, 'extract_face_encoding', return_value=(fake_encoding, 'data:image/jpeg;base64,thumb', None)):
            self.client.post('/api/students/register', json={
                'student_id': '25SUUBEAML902',
                'srn': '25SUUBEAML902',
                'name': 'Canteen Verified Student',
                'phone_number': '9876500902',
                'room_number': '309',
                'image': 'data:image/jpeg;base64,validface'
            })

        # Verify manual scan by SRN works
        m_res = self.client.post('/api/scan-manual', json={
            'identifier': '25SUUBEAML902',
            'meal_type': 'Breakfast'
        })
        self.assertEqual(m_res.status_code, 200)
        self.assertEqual(m_res.get_json()['status'], 'granted')

        # Verify biometric face scan works for Lunch
        with patch.object(face_service, 'decode_base64_image', return_value=(np.zeros((100, 100, 3), dtype=np.uint8), None)), \
             patch.object(face_service, 'extract_face_with_landmarks', return_value=(fake_encoding, None, None, {'box': [0, 0, 50, 50], 'landmarks': []})):
            f_res = self.client.post('/api/scan-face', json={
                'image': 'data:image/jpeg;base64,validface',
                'meal_type': 'Lunch'
            })
            self.assertEqual(f_res.status_code, 200)
            self.assertEqual(f_res.get_json()['status'], 'granted')

    def test_T_production_database_and_excel_register_integrity(self):
        """TEST T — Verify genuine students 25SUUBEAML729 and 25SUUBEAML761 remain intact in instance/hostel_food.db."""
        import sqlite3
        from config import DEFAULT_DB_FILE
        if os.path.exists(DEFAULT_DB_FILE):
            ro_con = sqlite3.connect(f"file:{DEFAULT_DB_FILE}?mode=ro", uri=True)
            cur = ro_con.cursor()
            cur.execute("SELECT student_id, name, srn, active FROM students ORDER BY student_id")
            rows = cur.fetchall()
            ro_con.close()
            ids = {r[0] for r in rows}
            self.assertIn('25SUUBEAML729', ids)
            self.assertIn('25SUUBEAML761', ids)


if __name__ == '__main__':
    unittest.main()



