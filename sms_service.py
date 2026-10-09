import os
import time
import random
import threading
from datetime import datetime
from flask import current_app

class SmsProvider:
    """Base interface for SMS Gateway providers."""
    def send_sms(self, phone_number, message):
        raise NotImplementedError

class MockSmsProvider(SmsProvider):
    """
    Console and audit-based SMS simulator for testing and development in India.
    Does not incur telecom charges and avoids unconfigured DLT template rejections.
    """
    def send_sms(self, phone_number, message):
        ref_id = f"MOCK-IND-{int(time.time())}-{random.randint(1000, 9999)}"
        print(f"\n[SMS MOCK GATEWAY] =========================================")
        print(f"To: {phone_number}")
        print(f"Sender ID: HSTLFD")
        print(f"Message: {message}")
        print(f"Provider Ref: {ref_id}")
        print(f"Status: DELIVERED (Simulated)")
        print(f"===========================================================\n")
        return {
            'success': True,
            'provider': 'mock',
            'ref_id': ref_id,
            'status': 'delivered',
            'error': None
        }

class Fast2SmsProvider(SmsProvider):
    """Integration for Fast2SMS Indian SMS Gateway (Quick SMS / DLT)."""
    def __init__(self, api_key, sender_id="HSTLFD"):
        self.api_key = api_key
        self.sender_id = sender_id

    def send_sms(self, phone_number, message):
        import urllib.request
        import json

        # Normalize 10-digit Indian mobile number
        clean_phone = phone_number.replace('+91', '').replace('-', '').replace(' ', '').strip()
        if len(clean_phone) > 10:
            clean_phone = clean_phone[-10:]

        url = "https://www.fast2sms.com/dev/bulkV2"
        headers = {
            "authorization": self.api_key,
            "Content-Type": "application/json"
        }
        payload = {
            "route": "q",
            "message": message,
            "language": "english",
            "flash": 0,
            "numbers": clean_phone
        }

        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                res_body = json.loads(response.read().decode('utf-8'))
                if res_body.get('return'):
                    return {
                        'success': True,
                        'provider': 'fast2sms',
                        'ref_id': str(res_body.get('request_id', '')),
                        'status': 'sent',
                        'error': None
                    }
                else:
                    return {
                        'success': False,
                        'provider': 'fast2sms',
                        'ref_id': None,
                        'status': 'failed',
                        'error': str(res_body.get('message', 'Fast2SMS error'))
                    }
        except Exception as e:
            return {
                'success': False,
                'provider': 'fast2sms',
                'ref_id': None,
                'status': 'failed',
                'error': str(e)
            }

class TwilioSmsProvider(SmsProvider):
    """Twilio SMS Gateway implementation."""
    def __init__(self, account_sid, auth_token, from_number):
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_number = from_number

    def send_sms(self, phone_number, message):
        import urllib.request
        import urllib.parse
        import base64
        import json

        # Ensure E.164 format for international delivery
        clean_phone = phone_number.strip()
        if not clean_phone.startswith('+'):
            clean_phone = '+91' + clean_phone[-10:]

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
        data = urllib.parse.urlencode({
            'To': clean_phone,
            'From': self.from_number,
            'Body': message
        }).encode('utf-8')

        auth_header = base64.b64encode(f"{self.account_sid}:{self.auth_token}".encode('utf-8')).decode('utf-8')
        headers = {
            'Authorization': f'Basic {auth_header}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                res_body = json.loads(response.read().decode('utf-8'))
                return {
                    'success': True,
                    'provider': 'twilio',
                    'ref_id': res_body.get('sid', ''),
                    'status': 'sent',
                    'error': None
                }
        except Exception as e:
            return {
                'success': False,
                'provider': 'twilio',
                'ref_id': None,
                'status': 'failed',
                'error': str(e)
            }

def get_sms_provider(config=None):
    """Instantiate the active SMS provider according to runtime settings."""
    cfg = config or (current_app.config if current_app else {})
    provider_name = (cfg.get('SMS_PROVIDER') or 'mock').lower()

    if provider_name == 'fast2sms' and cfg.get('SMS_API_KEY'):
        return Fast2SmsProvider(
            api_key=cfg['SMS_API_KEY'],
            sender_id=cfg.get('SMS_SENDER_ID', 'HSTLFD')
        )
    elif provider_name == 'twilio' and cfg.get('TWILIO_ACCOUNT_SID') and cfg.get('TWILIO_AUTH_TOKEN'):
        return TwilioSmsProvider(
            account_sid=cfg['TWILIO_ACCOUNT_SID'],
            auth_token=cfg['TWILIO_AUTH_TOKEN'],
            from_number=cfg.get('TWILIO_PHONE_NUMBER', '')
        )
    else:
        return MockSmsProvider()

def send_meal_sms_async(app, student_id, student_name, phone_number, meal_type, entry_time, entry_date):
    """
    Non-blocking background worker to deliver SMS without delaying scanner UI.
    Includes idempotency deduplication to prevent duplicate messages for the same meal attendance.
    """
    if not phone_number:
        return

    def _worker():
        with app.app_context():
            from models import db, SmsLog
            
            # Idempotency check: verify an SMS was not already queued/sent for this student & meal today
            try:
                date_obj = datetime.strptime(entry_date, '%Y-%m-%d').date()
            except Exception:
                date_obj = datetime.now().date()

            existing = SmsLog.query.filter(
                SmsLog.student_id == student_id,
                SmsLog.meal_type == meal_type,
                SmsLog.created_at >= date_obj
            ).first()
            if existing and existing.status in ('queued', 'sending', 'sent', 'delivered'):
                return

            msg = f"Hello {student_name}, your {meal_type} entry was recorded successfully at {entry_time} on {entry_date}. Hostel Food Management System."
            provider = get_sms_provider(app.config)

            # 1. State: QUEUED
            log_entry = SmsLog(
                student_id=student_id,
                student_name=student_name,
                phone_number=phone_number,
                message=msg,
                meal_type=meal_type,
                status='queued',
                provider_name=app.config.get('SMS_PROVIDER', 'mock')
            )
            db.session.add(log_entry)
            db.session.commit()

            # 2. State: SENDING
            log_entry.status = 'sending'
            db.session.commit()

            # 3. Dispatch to provider with retry on temporary error
            res = provider.send_sms(phone_number, msg)
            if not res.get('success'):
                # Quick retry once
                time.sleep(1)
                res = provider.send_sms(phone_number, msg)

            # 4. Final state update
            log_entry.status = res.get('status', 'failed')
            log_entry.provider_ref = res.get('ref_id')
            log_entry.error_message = res.get('error')
            db.session.commit()

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
