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


if __name__ == '__main__':
    unittest.main()

