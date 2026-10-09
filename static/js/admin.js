// AI Hostel Food Management System - Admin Dashboard Client

let allStudentsList = [];
let adminStream = null;
let capturedPhotoData = null;

function switchAdminSection(sectionName) {
    document.querySelectorAll('.admin-section').forEach(sec => sec.style.display = 'none');
    document.querySelectorAll('.nav-tab-btn').forEach(btn => btn.classList.remove('active'));

    const activeSec = document.getElementById(`section-${sectionName}`);
    if (activeSec) activeSec.style.display = 'block';

    const tabBtn = Array.from(document.querySelectorAll('.nav-tab-btn')).find(b => b.getAttribute('onclick')?.includes(sectionName));
    if (tabBtn) tabBtn.classList.add('active');

    // Trigger tab-specific refresh safely
    if (sectionName === 'fees' && window.loadFeeLedger) window.loadFeeLedger();
    else if (sectionName === 'attendance') {
        if (window.loadAttendanceLogs) window.loadAttendanceLogs();
        if (window.loadRejectedLogs) window.loadRejectedLogs();
    }
    else if (sectionName === 'sms' && window.loadSmsLogs) window.loadSmsLogs();
    else if (sectionName === 'audit' && window.loadAuditLogs) window.loadAuditLogs();
    else if (sectionName === 'config' && window.loadConfig) window.loadConfig();
}

// Monotonic request sequence counters to prevent stale responses overwriting newer data
let attendanceReqSeq = 0;
let rejectionsReqSeq = 0;
let smsReqSeq = 0;
let auditReqSeq = 0;

function maskPhoneNumber(phone) {
    if (!phone || typeof phone !== 'string') return '--';
    const clean = phone.trim();
    if (clean.length >= 10) {
        return clean.substring(0, 2) + '••••' + clean.substring(clean.length - 4);
    }
    return clean;
}

// ==========================================
// 1. ATTENDANCE LOGS REFRESH
// ==========================================
window.loadAttendanceLogs = async function() {
    const seq = ++attendanceReqSeq;
    const btn = document.getElementById('refreshAttendanceBtn');
    const originalHtml = btn ? btn.innerHTML : '🔄 Refresh Attendance';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '⏳ Refreshing...';
    }

    const dateFilterEl = document.getElementById('attendanceDateFilter');
    const selectedDate = dateFilterEl ? dateFilterEl.value.trim() : '';
    const url = selectedDate ? `/api/entries/today?date=${encodeURIComponent(selectedDate)}` : '/api/entries/today';

    const body = document.getElementById('entriesTableBody');

    try {
        const res = await fetch(url);
        if (seq !== attendanceReqSeq) return;
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.message || `Server returned ${res.status}`);
        }
        const data = await res.json();
        if (seq !== attendanceReqSeq) return;

        if (body) {
            if (data.success && data.entries && data.entries.length > 0) {
                body.innerHTML = data.entries.map(e => `
                    <tr>
                        <td style="font-family:var(--font-mono);color:var(--text-muted);">#${e.id}</td>
                        <td style="font-family:var(--font-mono);">${e.entry_time || '--'}</td>
                        <td><strong style="font-family:var(--font-mono);color:var(--color-primary);">${e.student_id}</strong></td>
                        <td>${e.student_name || 'Unknown'}</td>
                        <td>${e.room_number || '--'}</td>
                        <td><span class="badge ${e.meal === 'Breakfast' ? 'badge-neutral' : 'badge-warning'}">${e.meal || 'Lunch'}</span></td>
                        <td><span class="badge badge-neutral">${(e.verification_method || 'face').toUpperCase()}</span></td>
                        <td><span class="badge badge-success">✅ ${e.status || 'Approved'}</span></td>
                    </tr>
                `).join('');
            } else {
                const dateLabel = selectedDate ? `for ${selectedDate}` : 'today';
                body.innerHTML = `<tr><td colspan="8" class="text-center" style="color:var(--text-muted);padding:1.5rem;">No meal entries recorded ${dateLabel}.</td></tr>`;
            }
        }

        if (btn) {
            btn.innerHTML = '✅ Refreshed!';
            setTimeout(() => {
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = originalHtml;
                }
            }, 1000);
        }
    } catch (err) {
        console.error('Error in loadAttendanceLogs:', err);
        if (body && seq === attendanceReqSeq) {
            body.innerHTML = `<tr><td colspan="8" class="text-center" style="color:var(--color-danger);padding:1.2rem;">⚠️ Failed to refresh attendance entries: ${err.message}. Please click Refresh again.</td></tr>`;
        }
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = originalHtml;
        }
    }
};

// ==========================================
// 2. REJECTIONS LOGS REFRESH
// ==========================================
window.loadRejectedLogs = async function() {
    const seq = ++rejectionsReqSeq;
    const btn = document.getElementById('refreshRejectedBtn');
    const originalHtml = btn ? btn.innerHTML : '🔄 Refresh Rejections';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '⏳ Refreshing...';
    }

    const body = document.getElementById('rejectedTableBody');

    try {
        const res = await fetch('/api/entries/rejected');
        if (seq !== rejectionsReqSeq) return;
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.message || `Server returned ${res.status}`);
        }
        const data = await res.json();
        if (seq !== rejectionsReqSeq) return;

        if (body) {
            if (data.success && data.rejected && data.rejected.length > 0) {
                body.innerHTML = data.rejected.map(r => `
                    <tr>
                        <td style="font-family:var(--font-mono);">${r.attempt_date || ''} ${r.attempt_time || ''}</td>
                        <td><strong style="font-family:var(--font-mono);">${r.student_id || 'Unknown'}</strong></td>
                        <td>${r.student_name || 'Unregistered Visitor'}</td>
                        <td><span class="badge badge-neutral">${r.meal_type || 'Lunch'}</span></td>
                        <td style="color:var(--color-danger);font-weight:600;">⛔ ${r.reason || 'Denied'}</td>
                        <td><span class="badge badge-neutral">${(r.verification_method || 'face').toUpperCase()}</span></td>
                    </tr>
                `).join('');
            } else {
                body.innerHTML = '<tr><td colspan="6" class="text-center" style="color:var(--text-muted);padding:1.5rem;">No rejected attempts recorded.</td></tr>';
            }
        }

        if (btn) {
            btn.innerHTML = '✅ Refreshed!';
            setTimeout(() => {
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = originalHtml;
                }
            }, 1000);
        }
    } catch (err) {
        console.error('Error in loadRejectedLogs:', err);
        if (body && seq === rejectionsReqSeq) {
            body.innerHTML = `<tr><td colspan="6" class="text-center" style="color:var(--color-danger);padding:1.2rem;">⚠️ Failed to refresh rejected attempts: ${err.message}. Please click Refresh again.</td></tr>`;
        }
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = originalHtml;
        }
    }
};

// ==========================================
// 3. SMS NOTIFICATION LOGS REFRESH
// ==========================================
window.loadSmsLogs = async function() {
    const seq = ++smsReqSeq;
    const btn = document.getElementById('refreshSmsBtn');
    const originalHtml = btn ? btn.innerHTML : '🔄 Refresh SMS Logs';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '⏳ Refreshing...';
    }

    const body = document.getElementById('smsTableBody');

    try {
        const res = await fetch('/api/sms/logs');
        if (seq !== smsReqSeq) return;
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.message || `Server returned ${res.status}`);
        }
        const data = await res.json();
        if (seq !== smsReqSeq) return;

        if (body) {
            if (data.success && data.logs && data.logs.length > 0) {
                body.innerHTML = data.logs.map(l => `
                    <tr>
                        <td style="font-family:var(--font-mono);font-size:0.75rem;">${l.created_at || '--'}</td>
                        <td><strong style="font-family:var(--font-mono);color:var(--color-primary);">${l.student_id || '--'}</strong></td>
                        <td>${l.student_name || 'Resident'}</td>
                        <td style="font-family:var(--font-mono);">${maskPhoneNumber(l.phone_number)}</td>
                        <td><span class="badge badge-neutral">${l.meal_type || 'Meal'}</span></td>
                        <td><span class="badge ${l.status === 'sent' || l.status === 'delivered' ? 'badge-success' : (l.status === 'queued' || l.status === 'sending' ? 'badge-warning' : 'badge-danger')}">${(l.status || 'UNKNOWN').toUpperCase()}</span></td>
                        <td><span class="badge badge-neutral">${(l.provider_name || 'mock').toUpperCase()}</span></td>
                        <td style="font-family:var(--font-mono);font-size:0.75rem;">${l.provider_ref || '--'}</td>
                    </tr>
                `).join('');
            } else {
                body.innerHTML = '<tr><td colspan="8" class="text-center" style="color:var(--text-muted);padding:1.5rem;">No SMS dispatch records found.</td></tr>';
            }
        }

        if (btn) {
            btn.innerHTML = '✅ Refreshed!';
            setTimeout(() => {
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = originalHtml;
                }
            }, 1000);
        }
    } catch (err) {
        console.error('Error in loadSmsLogs:', err);
        if (body && seq === smsReqSeq) {
            body.innerHTML = `<tr><td colspan="8" class="text-center" style="color:var(--color-danger);padding:1.2rem;">⚠️ Failed to refresh SMS logs: ${err.message}. Please click Refresh again.</td></tr>`;
        }
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = originalHtml;
        }
    }
};

// ==========================================
// 4. AUDIT LOGS REFRESH
// ==========================================
window.loadAuditLogs = async function() {
    const seq = ++auditReqSeq;
    const btn = document.getElementById('refreshAuditBtn');
    const originalHtml = btn ? btn.innerHTML : '🔄 Refresh Audit Trail';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '⏳ Refreshing...';
    }

    const body = document.getElementById('auditTableBody');

    try {
        const res = await fetch('/api/audit/logs');
        if (seq !== auditReqSeq) return;
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.message || `Server returned ${res.status}`);
        }
        const data = await res.json();
        if (seq !== auditReqSeq) return;

        if (body) {
            if (data.success && data.logs && data.logs.length > 0) {
                body.innerHTML = data.logs.map(a => `
                    <tr>
                        <td style="font-family:var(--font-mono);font-size:0.75rem;">${a.timestamp || '--'}</td>
                        <td><strong>${a.action || '--'}</strong></td>
                        <td><span class="badge badge-neutral">${a.actor_username || 'Admin'} (${a.actor_role || 'admin'})</span></td>
                        <td>${a.target_type || '--'}</td>
                        <td style="font-family:var(--font-mono);">${a.target_id || '--'}</td>
                        <td style="color:var(--text-secondary);font-size:0.8rem;">${a.details || ''}</td>
                    </tr>
                `).join('');
            } else {
                body.innerHTML = '<tr><td colspan="6" class="text-center" style="color:var(--text-muted);padding:1.5rem;">No audit records found.</td></tr>';
            }
        }

        if (btn) {
            btn.innerHTML = '✅ Refreshed!';
            setTimeout(() => {
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = originalHtml;
                }
            }, 1000);
        }
    } catch (err) {
        console.error('Error in loadAuditLogs:', err);
        if (body && seq === auditReqSeq) {
            body.innerHTML = `<tr><td colspan="6" class="text-center" style="color:var(--color-danger);padding:1.2rem;">⚠️ Failed to refresh audit logs: ${err.message}. Please click Refresh again.</td></tr>`;
        }
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = originalHtml;
        }
    }
};

document.addEventListener('DOMContentLoaded', () => {
    // Elements
    const adminWebcam = document.getElementById('adminWebcam');
    const adminCanvas = document.getElementById('adminCanvas');
    const captureFaceBtn = document.getElementById('captureFaceBtn');
    const retakeFaceBtn = document.getElementById('retakeFaceBtn');
    const capturedImagePreview = document.getElementById('capturedImagePreview');
    const snapshotDisplay = document.getElementById('snapshotDisplay');
    const registerForm = document.getElementById('registerForm');
    const regStatusAlert = document.getElementById('regStatusAlert');

    // Top Metrics
    const metricTotalStudents = document.getElementById('metricTotalStudents');
    const metricTodayBreakfast = document.getElementById('metricTodayBreakfast');
    const metricTodayLunch = document.getElementById('metricTodayLunch');
    const metricFeesCollected = document.getElementById('metricFeesCollected');
    const metricFeesPending = document.getElementById('metricFeesPending');
    const metricSmsCount = document.getElementById('metricSmsCount');

    // Date inputs default to today
    const todayStr = new Date().toISOString().split('T')[0];
    if (document.getElementById('reportDateInput')) document.getElementById('reportDateInput').value = todayStr;
    if (document.getElementById('payDate')) document.getElementById('payDate').value = todayStr;
    if (document.getElementById('admissionDate')) document.getElementById('admissionDate').value = todayStr;
    if (document.getElementById('attendanceDateFilter')) document.getElementById('attendanceDateFilter').value = todayStr;

    // ==========================================
    // CAMERA ENROLLMENT
    // ==========================================
    async function initAdminCamera() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({
                video: { width: { ideal: 480 }, height: { ideal: 360 }, facingMode: 'user' },
                audio: false
            });
            adminStream = stream;
            adminWebcam.srcObject = stream;
        } catch (err) {
            console.warn('Admin camera warning:', err);
        }
    }

    function captureFacePhoto() {
        const w = adminWebcam.videoWidth || 480;
        const h = adminWebcam.videoHeight || 360;

        adminCanvas.width = w;
        adminCanvas.height = h;
        const ctx = adminCanvas.getContext('2d');
        ctx.drawImage(adminWebcam, 0, 0, w, h);

        capturedPhotoData = adminCanvas.toDataURL('image/jpeg', 0.9);
        capturedImagePreview.src = capturedPhotoData;
        capturedImagePreview.style.display = 'block';

        const hint = snapshotDisplay.querySelector('.no-snap-hint');
        if (hint) hint.style.display = 'none';

        captureFaceBtn.style.display = 'none';
        retakeFaceBtn.style.display = 'inline-flex';
    }

    function retakeFacePhoto() {
        capturedPhotoData = null;
        capturedImagePreview.src = '';
        capturedImagePreview.style.display = 'none';

        const hint = snapshotDisplay.querySelector('.no-snap-hint');
        if (hint) hint.style.display = 'block';

        captureFaceBtn.style.display = 'inline-flex';
        retakeFaceBtn.style.display = 'none';
    }

    if (captureFaceBtn) captureFaceBtn.addEventListener('click', captureFacePhoto);
    if (retakeFaceBtn) retakeFaceBtn.addEventListener('click', retakeFacePhoto);

    // ==========================================
    // STUDENT REGISTRATION
    // ==========================================
    if (registerForm) registerForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const submitBtn = document.getElementById('submitRegisterBtn');
        submitBtn.disabled = true;
        submitBtn.textContent = 'Enrolling Student...';

        const payload = {
            student_id: document.getElementById('studentId').value.trim().toUpperCase(),
            name: document.getElementById('studentName').value.trim(),
            srn: document.getElementById('studentSrn').value.trim().toUpperCase(),
            phone_number: document.getElementById('studentPhone').value.trim(),
            hostel: document.getElementById('studentHostel').value.trim(),
            room_number: document.getElementById('studentRoom').value.trim(),
            room_sharing_type: document.getElementById('roomSharingType').value,
            room_occupants: parseInt(document.getElementById('roomOccupants').value || 2),
            branch: document.getElementById('studentBranch').value,
            year: document.getElementById('studentYear').value,
            admission_date: document.getElementById('admissionDate').value,
            total_hostel_fees: parseFloat(document.getElementById('totalHostelFees').value || 75000),
            total_fees_paid: parseFloat(document.getElementById('initialFeesPaid').value || 0),
            image: capturedPhotoData
        };

        try {
            const res = await fetch('/api/students/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (res.ok && data.success) {
                regStatusAlert.className = 'alert-box alert-success';
                regStatusAlert.textContent = `✅ ${data.message}`;
                regStatusAlert.style.display = 'block';
                registerForm.reset();
                retakeFacePhoto();
                loadStudents();
                loadMetrics();
            } else {
                regStatusAlert.className = 'alert-box alert-danger';
                regStatusAlert.textContent = `❌ ${data.message || 'Registration failed'}`;
                regStatusAlert.style.display = 'block';
            }
        } catch (err) {
            regStatusAlert.className = 'alert-box alert-danger';
            regStatusAlert.textContent = '❌ Network error during registration.';
            regStatusAlert.style.display = 'block';
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = '✅ Register Student in System';
        }
    });

    // ==========================================
    // MANUAL VERIFICATION
    // ==========================================
    document.getElementById('manualVerifyForm')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const alertBox = document.getElementById('manualVerifyAlert');
        if (alertBox) alertBox.style.display = 'none';

        const identifier = document.getElementById('manualStudentId')?.value.trim();
        const meal_type = document.getElementById('manualMealType')?.value;

        try {
            const res = await fetch('/api/scan-manual', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ identifier, meal_type })
            });
            const data = await res.json();
            if (alertBox) {
                alertBox.style.display = 'block';
                if (data.status === 'granted') {
                    alertBox.className = 'alert-box alert-success';
                    alertBox.textContent = `✅ ${data.message} (${data.student.name})`;
                    document.getElementById('manualVerifyForm')?.reset();
                    window.loadAttendanceLogs();
                    loadMetrics();
                } else {
                    alertBox.className = 'alert-box alert-danger';
                    alertBox.textContent = `❌ Rejected: ${data.message}`;
                }
            }
        } catch (err) {
            if (alertBox) {
                alertBox.className = 'alert-box alert-danger';
                alertBox.textContent = '❌ Error performing manual verification.';
                alertBox.style.display = 'block';
            }
        }
    });

    // ==========================================
    // RECORD FEE PAYMENT
    // ==========================================
    document.getElementById('paymentRecordForm')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const alertBox = document.getElementById('paymentAlert');
        if (alertBox) alertBox.style.display = 'none';

        const payload = {
            student_id: document.getElementById('payStudentId')?.value.trim().toUpperCase(),
            amount: parseFloat(document.getElementById('payAmount')?.value || 0),
            payment_method: document.getElementById('payMethod')?.value,
            reference_no: document.getElementById('payRef')?.value.trim(),
            payment_date: document.getElementById('payDate')?.value,
            remarks: document.getElementById('payRemarks')?.value.trim()
        };

        try {
            const res = await fetch('/api/fees/payment', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (alertBox) alertBox.style.display = 'block';
            if (res.ok && data.success) {
                if (alertBox) {
                    alertBox.className = 'alert-box alert-success';
                    alertBox.textContent = `✅ ${data.message}`;
                }
                document.getElementById('paymentRecordForm')?.reset();
                if (document.getElementById('payDate')) document.getElementById('payDate').value = todayStr;
                loadFeeLedger();
                loadMetrics();
            } else {
                if (alertBox) {
                    alertBox.className = 'alert-box alert-danger';
                    alertBox.textContent = `❌ ${data.message || 'Failed to record payment'}`;
                }
            }
        } catch (err) {
            if (alertBox) {
                alertBox.className = 'alert-box alert-danger';
                alertBox.textContent = '❌ Network error recording payment.';
                alertBox.style.display = 'block';
            }
        }
    });

    // ==========================================
    // MENUS
    // ==========================================
    document.getElementById('bfMenuForm')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const items = document.getElementById('bfMenuItems')?.value.trim();
        await saveMenu('Breakfast', items);
    });

    document.getElementById('lunchMenuForm')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const items = document.getElementById('lunchMenuItems')?.value.trim();
        await saveMenu('Lunch', items);
    });

    async function saveMenu(meal_type, items) {
        try {
            const res = await fetch('/api/menus', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ meal_type, items, menu_date: 'Daily' })
            });
            const data = await res.json();
            if (data.success) alert(`${meal_type} menu published successfully!`);
        } catch (err) {
            alert('Failed to save menu.');
        }
    }

    // ==========================================
    // LOADERS & TABLE RENDERERS
    // ==========================================
    window.loadMetrics = async () => {
        try {
            const res = await fetch('/api/entries/today');
            const data = await res.json();
            if (data.success && data.metrics) {
                metricTotalStudents.textContent = data.metrics.total_students;
                metricTodayBreakfast.textContent = data.metrics.today_breakfast_count;
                metricTodayLunch.textContent = data.metrics.today_lunch_count;
                metricFeesCollected.textContent = `₹${data.metrics.total_fees_collected.toLocaleString('en-IN')}`;
                metricFeesPending.textContent = `₹${data.metrics.total_fees_pending.toLocaleString('en-IN')}`;
                metricSmsCount.textContent = data.metrics.sms_delivered_count || 0;
            }
        } catch (e) {}
    };

    window.loadStudents = async () => {
        try {
            const res = await fetch('/api/students');
            const data = await res.json();
            if (data.success) {
                allStudentsList = data.students || [];
                renderStudentsTable(allStudentsList);
            }
        } catch (e) {}
    };

    function renderStudentsTable(students) {
        const body = document.getElementById('studentsTableBody');
        if (!students || students.length === 0) {
            body.innerHTML = '<tr><td colspan="10" class="text-center">No students registered yet.</td></tr>';
            return;
        }

        body.innerHTML = students.map(s => `
            <tr>
                <td>
                    ${s.photo_preview 
                        ? `<img src="${s.photo_preview}" class="table-avatar" alt="${s.name}">`
                        : `<div class="avatar-wrapper" style="width:36px;height:36px;font-size:0.75rem;">${s.name.substring(0,2).toUpperCase()}</div>`
                    }
                </td>
                <td>
                    <strong style="font-family:var(--font-mono);color:var(--color-primary);">${s.student_id}</strong>
                    <br><small style="color:var(--text-muted);">${s.srn || ''}</small>
                </td>
                <td>${s.name}<br><small style="color:var(--text-secondary);">${s.branch} • ${s.year}</small></td>
                <td>${s.hostel} - R${s.room_number || '--'}</td>
                <td style="font-family:var(--font-mono);font-size:0.8rem;">${s.phone_number || '--'}</td>
                <td>
                    <span class="badge ${s.fee_status === 'PAID' ? 'badge-success' : (s.fee_status === 'PARTIALLY PAID' ? 'badge-warning' : 'badge-danger')}">
                        ${s.fee_status}
                    </span>
                </td>
                <td style="font-family:var(--font-mono);">₹${s.pending_fees.toFixed(2)}</td>
                <td>
                    <button class="btn btn-small ${s.meal_access_enabled ? 'badge-success' : 'badge-danger'}" onclick="toggleMealAccess('${s.student_id}', ${s.meal_access_enabled})">
                        ${s.meal_access_enabled ? 'Enabled ✅' : 'Disabled ⛔'}
                    </button>
                </td>
                <td>
                    <span class="badge ${s.has_face_enrolled ? 'badge-success' : 'badge-neutral'}">
                        ${s.has_face_enrolled ? 'Enrolled' : 'None'}
                    </span>
                </td>
                <td>
                    <button class="btn btn-small btn-secondary" onclick="openStudentPay('${s.student_id}')" title="Record payment">💳</button>
                    <button class="btn btn-small ${s.active ? 'btn-outline' : 'badge-danger'}" onclick="toggleActive('${s.student_id}')" title="Toggle active status">
                        ${s.active ? 'Active' : 'Inactive'}
                    </button>
                    <button class="btn btn-small btn-outline-danger" onclick="deleteStudent('${s.student_id}')" title="Delete">🗑️</button>
                </td>
            </tr>
        `).join('');
    }

    // Search and filter listeners
    document.getElementById('studentSearchInput')?.addEventListener('input', applyFilters);
    document.getElementById('filterFeeStatus')?.addEventListener('change', applyFilters);
    document.getElementById('filterActiveStatus')?.addEventListener('change', applyFilters);

    function applyFilters() {
        const query = (document.getElementById('studentSearchInput')?.value || '').toLowerCase().trim();
        const feeStatus = document.getElementById('filterFeeStatus')?.value || '';
        const activeStatus = document.getElementById('filterActiveStatus')?.value || '';

        const filtered = allStudentsList.filter(s => {
            const matchesQuery = !query || s.name.toLowerCase().includes(query) || s.student_id.toLowerCase().includes(query) || (s.srn && s.srn.toLowerCase().includes(query)) || (s.room_number && s.room_number.includes(query));
            const matchesFee = !feeStatus || s.fee_status === feeStatus;
            const matchesActive = !activeStatus || String(s.active) === activeStatus;
            return matchesQuery && matchesFee && matchesActive;
        });
        renderStudentsTable(filtered);
    }

    // Toggle Student Actions
    window.toggleMealAccess = async (studentId, currentStatus) => {
        let reason = 'Admin toggle';
        if (currentStatus) {
            reason = prompt('Enter restriction reason (e.g. Outstanding dues / Disciplinary):', 'Pending fees overdue');
            if (reason === null) return;
        }
        try {
            const res = await fetch(`/api/students/${studentId}/toggle-meal-access`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ reason })
            });
            const data = await res.json();
            if (data.success) { loadStudents(); loadMetrics(); }
        } catch (e) { alert('Failed to update meal access.'); }
    };

    window.toggleActive = async (studentId) => {
        try {
            const res = await fetch(`/api/students/${studentId}/toggle-active`, { method: 'POST' });
            const data = await res.json();
            if (data.success) { loadStudents(); loadMetrics(); }
        } catch (e) { alert('Failed to toggle status.'); }
    };

    window.deleteStudent = async (studentId) => {
        if (!confirm(`Are you sure you want to delete student ${studentId}? Biometrics will be removed.`)) return;
        try {
            const res = await fetch(`/api/students/${studentId}`, { method: 'DELETE' });
            const data = await res.json();
            if (data.success) { loadStudents(); loadMetrics(); }
        } catch (e) { alert('Failed to delete student.'); }
    };

    window.openStudentPay = (studentId) => {
        switchAdminSection('fees');
        document.getElementById('payStudentId').value = studentId;
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    // ==========================================
    // FEE LEDGER
    // ==========================================
    window.loadFeeLedger = async () => {
        try {
            const [sumRes, studRes] = await Promise.all([
                fetch('/api/fees/summary'),
                fetch('/api/students')
            ]);
            const sumData = await sumRes.json();
            const studData = await studRes.json();

            if (sumData.success && sumData.counts) {
                document.getElementById('feeCountPaid').textContent = sumData.counts.paid;
                document.getElementById('feeCountPartial').textContent = sumData.counts.partially_paid;
                document.getElementById('feeCountUnpaid').textContent = sumData.counts.unpaid;
            }

            if (studData.success) {
                const body = document.getElementById('feeAccountsTableBody');
                body.innerHTML = studData.students.map(s => `
                    <tr>
                        <td><strong style="font-family:var(--font-mono);color:var(--color-primary);">${s.student_id}</strong></td>
                        <td>${s.name}</td>
                        <td style="font-family:var(--font-mono);">₹${s.total_hostel_fees.toFixed(2)}</td>
                        <td style="font-family:var(--font-mono);color:var(--color-success);">₹${s.total_fees_paid.toFixed(2)}</td>
                        <td style="font-family:var(--font-mono);color:var(--color-danger);font-weight:700;">₹${s.pending_fees.toFixed(2)}</td>
                        <td><span class="badge ${s.fee_status === 'PAID' ? 'badge-success' : (s.fee_status === 'PARTIALLY PAID' ? 'badge-warning' : 'badge-danger')}">${s.fee_status}</span></td>
                        <td>${s.last_payment_date || '--'}</td>
                        <td>
                            <button class="btn btn-small btn-secondary" onclick="viewPaymentHistory('${s.student_id}', '${s.name}')">History 📄</button>
                            <button class="btn btn-small btn-primary" onclick="openStudentPay('${s.student_id}')">+ Pay</button>
                        </td>
                    </tr>
                `).join('');
            }
        } catch (e) {}
    };

    window.viewPaymentHistory = async (studentId, studentName) => {
        document.getElementById('modalStudentTitle').textContent = `Payment History: ${studentName} (${studentId})`;
        document.getElementById('paymentHistoryModal').style.display = 'flex';
        const body = document.getElementById('modalPaymentsBody');
        body.innerHTML = '<tr><td colspan="7" class="text-center">Loading receipts...</td></tr>';

        try {
            const res = await fetch(`/api/fees/history/${studentId}`);
            const data = await res.json();
            if (data.success && data.payments.length > 0) {
                body.innerHTML = data.payments.map(p => `
                    <tr>
                        <td>#${p.id}</td>
                        <td>${p.payment_date}</td>
                        <td>${p.payment_method}</td>
                        <td style="font-family:var(--font-mono);">${p.reference_no}</td>
                        <td><strong>₹${p.amount.toFixed(2)}</strong></td>
                        <td>${p.remarks}</td>
                        <td>
                            <button class="btn btn-small btn-outline-danger" onclick="reversePayment(${p.id}, '${studentId}')">Reverse</button>
                        </td>
                    </tr>
                `).join('');
            } else {
                body.innerHTML = '<tr><td colspan="7" class="text-center">No payment history on record.</td></tr>';
            }
        } catch (e) {
            body.innerHTML = '<tr><td colspan="7" class="text-center">Error loading receipts.</td></tr>';
        }
    };

    window.closePaymentModal = () => {
        document.getElementById('paymentHistoryModal').style.display = 'none';
    };

    window.reversePayment = async (paymentId, studentId) => {
        const reason = prompt('Enter justification reason for payment reversal / correction:', 'Duplicate payment entry correction');
        if (!reason) return;

        try {
            const res = await fetch(`/api/fees/correction/${paymentId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ reason })
            });
            const data = await res.json();
            if (data.success) {
                alert('Payment reversed successfully.');
                closePaymentModal();
                loadFeeLedger();
                loadStudents();
                loadMetrics();
            }
        } catch (e) { alert('Reversal failed.'); }
    };

    // ==========================================
    // ATTENDANCE & REJECTIONS EVENT LISTENERS
    // ==========================================
    const attFilter = document.getElementById('attendanceDateFilter');
    if (attFilter) {
        attFilter.addEventListener('change', () => window.loadAttendanceLogs());
    }
    const refAttBtn = document.getElementById('refreshAttendanceBtn');
    if (refAttBtn) {
        refAttBtn.addEventListener('click', () => window.loadAttendanceLogs());
    }
    const refRejBtn = document.getElementById('refreshRejectedBtn');
    if (refRejBtn) {
        refRejBtn.addEventListener('click', () => window.loadRejectedLogs());
    }

    // ==========================================
    // REPORTS GENERATION
    // ==========================================
    window.generateDailyReport = async () => {
        const dateVal = document.getElementById('reportDateInput').value || todayStr;
        const alertBox = document.getElementById('reportGenAlert');
        alertBox.style.display = 'block';
        alertBox.className = 'alert-box';
        alertBox.textContent = `Generating attendance workbook for ${dateVal}...`;

        try {
            const res = await fetch('/api/reports/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ date: dateVal })
            });
            const data = await res.json();
            if (data.success) {
                alertBox.className = 'alert-box alert-success';
                alertBox.textContent = `✅ Workbook for ${dateVal} successfully generated! (${data.details.total_meals_served} meals calculated across ${data.details.total_students} students)`;
            } else {
                alertBox.className = 'alert-box alert-danger';
                alertBox.textContent = '❌ Failed to generate report.';
            }
        } catch (e) {
            alertBox.className = 'alert-box alert-danger';
            alertBox.textContent = '❌ Network error during report generation.';
        }
    };

    window.downloadReport = (format) => {
        const dateVal = document.getElementById('reportDateInput').value || todayStr;
        window.location.href = `/api/reports/download?date=${dateVal}&format=${format}`;
    };

    // ==========================================
    // SMS & AUDIT REFRESH EVENT LISTENERS
    // ==========================================
    const refSmsBtn = document.getElementById('refreshSmsBtn');
    if (refSmsBtn) {
        refSmsBtn.addEventListener('click', () => window.loadSmsLogs());
    }
    const refAuditBtn = document.getElementById('refreshAuditBtn');
    if (refAuditBtn) {
        refAuditBtn.addEventListener('click', () => window.loadAuditLogs());
    }

    // ==========================================
    // CONFIGURATION
    // ==========================================
    const thresholdSlider = document.getElementById('thresholdSlider');
    const thresholdVal = document.getElementById('thresholdVal');
    if (thresholdSlider && thresholdVal) {
        thresholdSlider.addEventListener('input', (e) => thresholdVal.textContent = parseFloat(e.target.value).toFixed(2));
    }

    window.loadConfig = async () => {
        try {
            const res = await fetch('/api/admin/config');
            const data = await res.json();
            thresholdSlider.value = data.threshold;
            thresholdVal.textContent = parseFloat(data.threshold).toFixed(2);
            document.getElementById('enforceMealHoursToggle').checked = data.enforce_meal_hours;
            document.getElementById('enforceFeePolicyToggle').checked = data.fee_policy_enforced;
            document.getElementById('maxPermittedDues').value = data.max_permitted_fee_balance;
            document.getElementById('bfStartTime').value = data.breakfast_start;
            document.getElementById('bfEndTime').value = data.breakfast_end;
            document.getElementById('lunchStartTime').value = data.lunch_start;
            document.getElementById('lunchEndTime').value = data.lunch_end;
            if (document.getElementById('smsProviderSelect')) document.getElementById('smsProviderSelect').value = data.sms_provider || 'mock';
            if (document.getElementById('smsSenderIdInput')) document.getElementById('smsSenderIdInput').value = data.sms_sender_id || 'HSTLFD';
            if (document.getElementById('smsSenderPhoneInput')) document.getElementById('smsSenderPhoneInput').value = data.twilio_phone_number || '';
        } catch (e) {}
    };

    window.saveSystemConfig = async () => {
        try {
            const res = await fetch('/api/admin/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    threshold: parseFloat(thresholdSlider.value),
                    enforce_meal_hours: document.getElementById('enforceMealHoursToggle').checked,
                    fee_policy_enforced: document.getElementById('enforceFeePolicyToggle').checked,
                    max_permitted_fee_balance: parseFloat(document.getElementById('maxPermittedDues').value),
                    breakfast_start: document.getElementById('bfStartTime').value,
                    breakfast_end: document.getElementById('bfEndTime').value,
                    lunch_start: document.getElementById('lunchStartTime').value,
                    lunch_end: document.getElementById('lunchEndTime').value,
                    sms_provider: document.getElementById('smsProviderSelect')?.value || 'mock',
                    sms_sender_id: document.getElementById('smsSenderIdInput')?.value || 'HSTLFD',
                    twilio_phone_number: document.getElementById('smsSenderPhoneInput')?.value || ''
                })
            });
            const data = await res.json();
            if (data.success) alert('Policy & SMS configuration saved successfully!');
        } catch (e) { alert('Failed to save configuration.'); }
    };

    window.resetTodayEntries = async () => {
        if (!confirm("Are you sure you want to clear today's attendance entries for testing?")) return;
        try {
            const res = await fetch('/api/admin/reset-db', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ target: 'entries' })
            });
            const data = await res.json();
            if (data.success) {
                alert(data.message);
                loadAttendanceLogs();
                loadMetrics();
            }
        } catch (e) { alert('Failed to reset.'); }
    };

    // ==========================================
    // RECORD CLEARING & RETENTION CONTROLLER
    // ==========================================
    let activeClearModule = null;

    const clearModal = document.getElementById('clearRecordsModal');
    const clearTitle = document.getElementById('clearModalTitle');
    const clearNotice = document.getElementById('clearModalNotice');
    const clearDateGroup = document.getElementById('clearDateGroup');
    const clearDateScope = document.getElementById('clearDateScope');
    const clearReasonInput = document.getElementById('clearReasonInput');
    const clearConfirmCheckbox = document.getElementById('clearConfirmCheckbox');
    const confirmClearBtn = document.getElementById('confirmClearBtn');
    const clearModalAlert = document.getElementById('clearModalAlert');

    window.openClearRecordsModal = (module) => {
        activeClearModule = module;
        if (!clearModal) return;

        if (module === 'attendance') {
            clearTitle.textContent = '🗑️ Clear Attendance Records';
            clearNotice.innerHTML = '⚠️ <strong>Attendance Module:</strong> Active meal attendance records will be transferred to the restricted archive. <strong>Student profiles, biometric face encodings, and fee payment accounts are strictly protected and will NOT be modified.</strong>';
            if (clearDateGroup) clearDateGroup.style.display = 'block';
        } else if (module === 'rejections') {
            clearTitle.textContent = '🗑️ Clear Rejected Attempts';
            clearNotice.innerHTML = '⚠️ <strong>Rejections Module:</strong> Active rejected meal attempt logs will be moved to the restricted archive. <strong>Approved attendance records will NOT be deleted or altered.</strong>';
            if (clearDateGroup) clearDateGroup.style.display = 'none';
        } else if (module === 'sms') {
            clearTitle.textContent = '🗑️ Clear SMS Delivery Logs';
            clearNotice.innerHTML = '⚠️ <strong>SMS Delivery Logs:</strong> Historical completed and failed SMS records will be archived. <strong>Any queued or in-flight SMS messages will continue delivering normally. Attendance records will NOT be deleted.</strong>';
            if (clearDateGroup) clearDateGroup.style.display = 'none';
        } else if (module === 'audit') {
            clearTitle.textContent = '🗑️ Clear Audit Trail';
            clearNotice.innerHTML = '⚠️ <strong>Security Audit Trail:</strong> Active audit records will be transferred to the restricted security archive. <strong>An immutable retention log entry will immediately be recorded documenting this archiving action, your admin identity, and the timestamp.</strong> Ordinary administrators cannot permanently destroy security history.';
            if (clearDateGroup) clearDateGroup.style.display = 'none';
        }

        if (clearReasonInput) clearReasonInput.value = '';
        if (clearConfirmCheckbox) clearConfirmCheckbox.checked = false;
        if (confirmClearBtn) {
            confirmClearBtn.disabled = true;
            confirmClearBtn.innerHTML = 'Confirm & Archive';
        }
        if (clearModalAlert) clearModalAlert.style.display = 'none';

        clearModal.style.display = 'flex';
    };

    window.closeClearRecordsModal = () => {
        if (clearModal) clearModal.style.display = 'none';
        activeClearModule = null;
    };

    if (clearConfirmCheckbox && confirmClearBtn) {
        clearConfirmCheckbox.addEventListener('change', () => {
            confirmClearBtn.disabled = !clearConfirmCheckbox.checked;
        });
    }

    window.submitClearRecords = async () => {
        if (!activeClearModule || !confirmClearBtn) return;

        const reason = (clearReasonInput ? clearReasonInput.value.trim() : '') || 'Administrative clear';
        const dateScope = clearDateScope ? clearDateScope.value : 'today';
        const targetDate = dateScope === 'all' ? 'all' : (document.getElementById('attendanceDateFilter')?.value || todayStr);

        confirmClearBtn.disabled = true;
        confirmClearBtn.innerHTML = '⏳ Archiving records...';
        if (clearModalAlert) clearModalAlert.style.display = 'none';

        try {
            const payload = {
                reason: reason,
                action: 'archive',
                date: activeClearModule === 'attendance' ? targetDate : undefined
            };

            const res = await fetch(`/api/admin/clear-records/${activeClearModule}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const data = await res.json();

            if (!res.ok || !data.success) {
                throw new Error(data.message || `Server returned ${res.status}`);
            }

            if (clearModalAlert) {
                clearModalAlert.className = 'alert-box alert-success';
                clearModalAlert.style.display = 'block';
                clearModalAlert.textContent = `✅ ${data.message}`;
            }

            if (activeClearModule === 'attendance') {
                window.loadAttendanceLogs();
                loadMetrics();
            } else if (activeClearModule === 'rejections') {
                window.loadRejectedLogs();
            } else if (activeClearModule === 'sms') {
                window.loadSmsLogs();
            } else if (activeClearModule === 'audit') {
                window.loadAuditLogs();
            }

            setTimeout(() => {
                window.closeClearRecordsModal();
            }, 750);

        } catch (err) {
            console.error('Clear records error:', err);
            if (clearModalAlert) {
                clearModalAlert.className = 'alert-box alert-danger';
                clearModalAlert.style.display = 'block';
                clearModalAlert.textContent = `❌ ${err.message || 'Operation failed'}`;
            }
            confirmClearBtn.disabled = false;
            confirmClearBtn.innerHTML = 'Confirm & Archive';
        }
    };

    // Initial boot
    initAdminCamera();
    loadStudents();
    loadMetrics();
    window.loadAttendanceLogs();
    window.loadRejectedLogs();
});
