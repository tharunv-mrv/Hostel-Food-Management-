/**
 * AI-POWERED HOSTEL FOOD MANAGEMENT SYSTEM
 * Live 3D Holographic Biometric Scanner & Automated Detection Controller
 *
 * Features:
 * - Three.js WebGL 3D rotating humanoid head topography with biometric wireframe & landmark nodes
 * - Automatic frame sampling cadence (~700ms) with concurrency locking
 * - Landmark & bounding box overlay projection
 * - Post-scan cooldown countdown timer (3.5s)
 * - State machine: Searching -> Verifying -> Granted / Rejected / Cooldown
 * - Web Audio API synthesized feedback tones
 * - Fallback 2D biometric wireframe renderer if WebGL is unavailable
 * - Full WCAG accessibility and prefers-reduced-motion compliance
 */

// Global Meal Selection State
let currentScanMeal = 'auto';

function setScanMeal(meal) {
    currentScanMeal = meal;
    document.querySelectorAll('.meal-toggle-btn').forEach(b => b.classList.remove('active'));
    const pill = document.getElementById('activeMealPill');
    if (meal === 'Breakfast') {
        const btn = document.getElementById('btnBreakfastMeal');
        if (btn) btn.classList.add('active');
        if (pill) pill.textContent = 'Active Service: 🌅 Breakfast';
    } else if (meal === 'Lunch') {
        const btn = document.getElementById('btnLunchMeal');
        if (btn) btn.classList.add('active');
        if (pill) pill.textContent = 'Active Service: ☀️ Lunch';
    } else {
        const btn = document.getElementById('btnAutoMeal');
        if (btn) btn.classList.add('active');
        if (pill) pill.textContent = 'Active Service: ⚡ Auto-Detect';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    // -------------------------------------------------------------
    // DOM ELEMENTS
    // -------------------------------------------------------------
    const video = document.getElementById('webcam');
    const snapshotCanvas = document.getElementById('snapshotCanvas');
    const landmarkCanvas = document.getElementById('landmarkCanvas');
    const canvas3d = document.getElementById('canvas3d');
    const model3dContainer = document.getElementById('model3dContainer');

    const toggleAutoScanBtn = document.getElementById('toggleAutoScanBtn');
    const retryCamBtn = document.getElementById('retryCamBtn');
    const resetScannerBtn = document.getElementById('resetScannerBtn');
    const cameraStatus = document.getElementById('cameraStatus');
    const cooldownIndicator = document.getElementById('cooldownIndicator');
    const cooldownTimer = document.getElementById('cooldownTimer');
    const liveClock = document.getElementById('liveClock');

    // Scanner State Bar Elements
    const scannerStateBar = document.getElementById('scannerStateBar');
    const stateIconBubble = document.getElementById('stateIconBubble');
    const stateHeadline = document.getElementById('stateHeadline');
    const stateDescription = document.getElementById('stateDescription');
    const stateProgressFill = document.getElementById('stateProgressFill');
    const hudMeshStatus = document.getElementById('hudMeshStatus');
    const hudLandmarksCount = document.getElementById('hudLandmarksCount');

    // Result Presentation Elements
    const standbyView = document.getElementById('standbyView');
    const resultContent = document.getElementById('resultContent');
    const resultPill = document.getElementById('resultPill');
    const statusBanner = document.getElementById('statusBanner');
    const bannerIcon = document.getElementById('bannerIcon');
    const bannerTitle = document.getElementById('bannerTitle');
    const bannerMessage = document.getElementById('bannerMessage');

    // Student Info Elements
    const studentProfile = document.getElementById('studentProfile');
    const studentPhoto = document.getElementById('studentPhoto');
    const studentAvatarFallback = document.getElementById('studentAvatarFallback');
    const studentName = document.getElementById('studentName');
    const studentId = document.getElementById('studentId');
    const studentRoom = document.getElementById('studentRoom');
    const studentBranch = document.getElementById('studentBranch');
    const mealTypeBadge = document.getElementById('mealType');
    const lunchStatusBadge = document.getElementById('lunchStatusBadge');
    const entryTime = document.getElementById('entryTime');
    const smsStatusBadge = document.getElementById('smsStatusBadge');

    // Stats Counters
    const todayServedCount = document.getElementById('todayServedCount');
    const todayBreakfastCount = document.getElementById('todayBreakfastCount');
    const totalActiveStudents = document.getElementById('totalActiveStudents');

    // -------------------------------------------------------------
    // STATE VARIABLES
    // -------------------------------------------------------------
    let streamRef = null;
    let isProcessingFrame = false;
    let isScannerPaused = false;
    let isInCooldown = false;
    let cooldownIntervalId = null;
    let scanLoopIntervalId = null;
    const SCAN_CADENCE_MS = 700;
    const COOLDOWN_DURATION_SEC = 3.5;

    // Check user's OS preference for reduced motion
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    // -------------------------------------------------------------
    // AUDIO SYNTHESIZER (Pure Web Audio API)
    // -------------------------------------------------------------
    function playAudioTone(type) {
        try {
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            if (!AudioContext) return;
            const ctx = new AudioContext();
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.connect(gain);
            gain.connect(ctx.destination);

            if (type === 'success') {
                // Two-tone rising major third (C5 to E5)
                osc.type = 'triangle';
                osc.frequency.setValueAtTime(523.25, ctx.currentTime);
                osc.frequency.exponentialRampToValueAtTime(659.25, ctx.currentTime + 0.15);
                gain.gain.setValueAtTime(0.25, ctx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.35);
                osc.start();
                osc.stop(ctx.currentTime + 0.35);
            } else if (type === 'warning') {
                // Alert harmonic tone
                osc.type = 'sawtooth';
                osc.frequency.setValueAtTime(440, ctx.currentTime);
                osc.frequency.setValueAtTime(392, ctx.currentTime + 0.15);
                gain.gain.setValueAtTime(0.18, ctx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.32);
                osc.start();
                osc.stop(ctx.currentTime + 0.32);
            } else if (type === 'error') {
                // Dissonant descending alert
                osc.type = 'sawtooth';
                osc.frequency.setValueAtTime(240, ctx.currentTime);
                osc.frequency.exponentialRampToValueAtTime(140, ctx.currentTime + 0.28);
                gain.gain.setValueAtTime(0.25, ctx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.4);
                osc.start();
                osc.stop(ctx.currentTime + 0.4);
            }
        } catch (e) {
            // Audio context restricted by autoplay policies until user gesture
        }
    }

    // -------------------------------------------------------------
    // LIVE CLOCK
    // -------------------------------------------------------------
    function updateClock() {
        if (liveClock) {
            const now = new Date();
            liveClock.textContent = now.toLocaleTimeString([], { hour12: true });
        }
    }
    setInterval(updateClock, 1000);
    updateClock();

    // =============================================================
    // THREE.JS 3D HOLOGRAPHIC HEAD VISUALIZER
    // =============================================================
    class BiometricHeadVisualizer {
        constructor(canvas, container) {
            this.canvas = canvas;
            this.container = container;
            this.scene = null;
            this.camera = null;
            this.renderer = null;
            this.headGroup = null;
            this.wireMesh = null;
            this.solidMesh = null;
            this.laserPlane = null;
            this.landmarksPoints = null;
            this.landmarkNodes = [];
            this.animationFrameId = null;

            // Palette definitions
            this.colors = {
                searching: { main: 0x00e5ff, wire: 0x00b0ff, emissive: 0x004d73 },
                verifying: { main: 0xfbbc04, wire: 0xffa000, emissive: 0x664400 },
                granted:   { main: 0x00e676, wire: 0x00c853, emissive: 0x005924 },
                rejected:  { main: 0xff5252, wire: 0xd50000, emissive: 0x5a0000 }
            };

            this.currentState = 'searching';
            this.targetYaw = 0;
            this.currentYaw = 0;
            this.isFallback = false;

            this.init();
        }

        init() {
            if (typeof THREE === 'undefined') {
                console.warn('Three.js library not loaded. Falling back to 2D biometric projector.');
                this.initFallback();
                return;
            }

            try {
                const width = this.container.clientWidth || 300;
                const height = this.container.clientHeight || 280;

                // 1. Scene & Camera
                this.scene = new THREE.Scene();
                this.camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 100);
                this.camera.position.set(0, 0, 5.2);

                // 2. WebGL Renderer
                this.renderer = new THREE.WebGLRenderer({
                    canvas: this.canvas,
                    alpha: true,
                    antialias: true
                });
                this.renderer.setSize(width, height);
                this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

                // 3. Lighting
                const ambientLight = new THREE.AmbientLight(0xffffff, 0.7);
                this.scene.add(ambientLight);

                const dirLight = new THREE.DirectionalLight(0x00e5ff, 1.2);
                dirLight.position.set(2, 4, 3);
                this.scene.add(dirLight);

                // 4. Build Procedural Realistic Head Topography
                this.buildHeadModel();

                // 5. Build Biometric Laser Scanning Plane
                this.buildScannerLaser();

                // 6. Handle Resizing
                window.addEventListener('resize', () => this.onResize());

                // 7. Start Render Loop
                this.animate = this.animate.bind(this);
                this.animate();

            } catch (err) {
                console.warn('WebGL initialization failed, falling back to 2D canvas:', err);
                this.initFallback();
            }
        }

        buildHeadModel() {
            this.headGroup = new THREE.Group();

            // Create procedural anatomical head using modified SphereGeometry
            const headGeom = new THREE.SphereGeometry(1.4, 26, 22);
            const posAttr = headGeom.attributes.position;
            const vertex = new THREE.Vector3();

            // Sculpt the sphere into realistic cranium and facial topography
            for (let i = 0; i < posAttr.count; i++) {
                vertex.fromBufferAttribute(posAttr, i);

                // Taper cranium into jawline and chin
                if (vertex.y < 0) {
                    const factor = 1.0 + vertex.y * 0.35;
                    vertex.x *= Math.max(0.62, factor);
                    vertex.z *= Math.max(0.70, factor);
                }

                // Sculpt nose ridge protrusion at front center
                if (vertex.z > 0.4 && vertex.y > -0.25 && vertex.y < 0.45 && Math.abs(vertex.x) < 0.35) {
                    vertex.z += 0.28 * (1.0 - Math.abs(vertex.x) / 0.35);
                }

                // Sculpt eye hollow indentations
                if (vertex.z > 0.4 && vertex.y > 0.2 && vertex.y < 0.55 && Math.abs(vertex.x) > 0.25 && Math.abs(vertex.x) < 0.7) {
                    vertex.z -= 0.16;
                }

                // Sculpt chin protrusion
                if (vertex.y < -1.0 && vertex.z > 0.1 && Math.abs(vertex.x) < 0.4) {
                    vertex.z += 0.22;
                }

                posAttr.setXYZ(i, vertex.x, vertex.y, vertex.z);
            }
            headGeom.computeVertexNormals();

            // Solid semi-translucent inner core
            const solidMat = new THREE.MeshPhongMaterial({
                color: 0x051a2e,
                emissive: this.colors.searching.emissive,
                specular: this.colors.searching.main,
                shininess: 60,
                transparent: true,
                opacity: 0.5,
                wireframe: false
            });
            this.solidMesh = new THREE.Mesh(headGeom, solidMat);
            this.headGroup.add(this.solidMesh);

            // Exterior biometric holographic wireframe
            const wireMat = new THREE.MeshBasicMaterial({
                color: this.colors.searching.wire,
                wireframe: true,
                transparent: true,
                opacity: 0.38
            });
            this.wireMesh = new THREE.Mesh(headGeom, wireMat);
            this.headGroup.add(this.wireMesh);

            // Biometric Facial Landmark Nodes (Eyes, Nose, Mouth, Jaw, Brow)
            const landmarkCoords = [
                { x: -0.42, y: 0.35, z: 1.15, label: 'L_EYE' },
                { x:  0.42, y: 0.35, z: 1.15, label: 'R_EYE' },
                { x:  0.0,  y: 0.05, z: 1.48, label: 'NOSE' },
                { x: -0.28, y: -0.42, z: 1.08, label: 'L_MOUTH' },
                { x:  0.28, y: -0.42, z: 1.08, label: 'R_MOUTH' },
                { x:  0.0,  y: -1.05, z: 1.02, label: 'CHIN' },
                { x:  0.0,  y:  0.72, z: 1.15, label: 'BROW' }
            ];

            const nodeGeom = new THREE.SphereGeometry(0.045, 12, 12);
            this.landmarkNodes = [];

            landmarkCoords.forEach(c => {
                const nodeMat = new THREE.MeshBasicMaterial({
                    color: this.colors.searching.main,
                    transparent: true,
                    opacity: 0.95
                });
                const node = new THREE.Mesh(nodeGeom, nodeMat);
                node.position.set(c.x, c.y, c.z);
                this.headGroup.add(node);
                this.landmarkNodes.push(node);
            });

            // Connect landmark nodes with subtle vector filaments
            const linePoints = [
                new THREE.Vector3(-0.42, 0.35, 1.15), new THREE.Vector3(0.0, 0.05, 1.48),
                new THREE.Vector3(0.42, 0.35, 1.15),  new THREE.Vector3(0.0, 0.05, 1.48),
                new THREE.Vector3(-0.42, 0.35, 1.15), new THREE.Vector3(0.42, 0.35, 1.15),
                new THREE.Vector3(0.0, 0.05, 1.48),   new THREE.Vector3(-0.28, -0.42, 1.08),
                new THREE.Vector3(0.0, 0.05, 1.48),   new THREE.Vector3(0.28, -0.42, 1.08),
                new THREE.Vector3(-0.28, -0.42, 1.08), new THREE.Vector3(0.28, -0.42, 1.08),
                new THREE.Vector3(0.0, -1.05, 1.02),  new THREE.Vector3(0.0, -0.42, 1.08)
            ];
            const filamentGeom = new THREE.BufferGeometry().setFromPoints(linePoints);
            const filamentMat = new THREE.LineBasicMaterial({
                color: this.colors.searching.main,
                transparent: true,
                opacity: 0.4
            });
            this.filamentLines = new THREE.LineSegments(filamentGeom, filamentMat);
            this.headGroup.add(this.filamentLines);

            this.scene.add(this.headGroup);
        }

        buildScannerLaser() {
            // Horizontal laser sweep plane slicing through head
            const laserGeom = new THREE.PlaneGeometry(3.2, 0.04);
            const laserMat = new THREE.MeshBasicMaterial({
                color: this.colors.searching.main,
                transparent: true,
                opacity: 0.75,
                side: THREE.DoubleSide
            });
            this.laserPlane = new THREE.Mesh(laserGeom, laserMat);
            this.laserPlane.rotation.x = Math.PI / 2;
            this.scene.add(this.laserPlane);
        }

        setState(state) {
            this.currentState = state;
            const theme = this.colors[state] || this.colors.searching;

            if (this.isFallback) return;

            if (this.wireMesh) {
                this.wireMesh.material.color.setHex(theme.wire);
            }
            if (this.solidMesh) {
                this.solidMesh.material.emissive.setHex(theme.emissive);
                this.solidMesh.material.specular.setHex(theme.main);
            }
            if (this.laserPlane) {
                this.laserPlane.material.color.setHex(theme.main);
            }
            if (this.filamentLines) {
                this.filamentLines.material.color.setHex(theme.main);
            }
            if (this.landmarkNodes) {
                this.landmarkNodes.forEach(node => {
                    node.material.color.setHex(theme.main);
                });
            }
        }

        onResize() {
            if (!this.container || !this.renderer || !this.camera) return;
            const width = this.container.clientWidth;
            const height = this.container.clientHeight;
            if (width > 0 && height > 0) {
                this.camera.aspect = width / height;
                this.camera.updateProjectionMatrix();
                this.renderer.setSize(width, height);
            }
        }

        animate() {
            this.animationFrameId = requestAnimationFrame(this.animate);

            const time = performance.now() * 0.001;

            if (this.headGroup) {
                // Determine target yaw rotation based on operational state
                if (prefersReducedMotion) {
                    this.targetYaw = 0;
                } else if (this.currentState === 'searching') {
                    // Gentle periodic oscillation around vertical axis (+/- 22 degrees)
                    this.targetYaw = Math.sin(time * 0.9) * 0.38;
                } else {
                    // When verifying, granted, or rejected, lock to front-facing view
                    this.targetYaw = 0;
                }

                // Smooth critically-damped lerp to target angle
                this.currentYaw += (this.targetYaw - this.currentYaw) * 0.08;
                this.headGroup.rotation.y = this.currentYaw;

                // Subtle organic pitch oscillation
                if (!prefersReducedMotion && this.currentState === 'searching') {
                    this.headGroup.rotation.x = Math.sin(time * 0.6) * 0.06;
                } else {
                    this.headGroup.rotation.x = 0;
                }

                // Pulse landmark nodes
                const pulseScale = 1.0 + Math.sin(time * 4) * 0.18;
                this.landmarkNodes.forEach(n => n.scale.set(pulseScale, pulseScale, pulseScale));
            }

            // Animate scanning laser up and down the cranium
            if (this.laserPlane) {
                const laserSpeed = this.currentState === 'verifying' ? 4.5 : 2.2;
                this.laserPlane.position.y = Math.sin(time * laserSpeed) * 1.35;
                this.laserPlane.position.z = Math.cos(this.currentYaw) * 0.3;
            }

            if (this.renderer && this.scene && this.camera) {
                this.renderer.render(this.scene, this.camera);
            }
        }

        initFallback() {
            this.isFallback = true;
            const ctx = this.canvas.getContext('2d');
            const renderFallback = () => {
                if (!this.canvas) return;
                const w = this.canvas.width = this.container.clientWidth || 300;
                const h = this.canvas.height = this.container.clientHeight || 280;
                const time = performance.now() * 0.001;

                ctx.clearRect(0, 0, w, h);

                const cx = w / 2;
                const cy = h / 2;
                const rx = 65;
                const ry = 85;

                let strokeColor = '#00e5ff';
                if (this.currentState === 'verifying') strokeColor = '#fbbc04';
                else if (this.currentState === 'granted') strokeColor = '#00e676';
                else if (this.currentState === 'rejected') strokeColor = '#ff5252';

                // Face oval wireframe
                ctx.save();
                ctx.strokeStyle = strokeColor;
                ctx.lineWidth = 2;
                ctx.beginPath();
                ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
                ctx.stroke();

                // Facial grid crosshairs
                ctx.strokeStyle = `${strokeColor}44`;
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.moveTo(cx, cy - ry);
                ctx.lineTo(cx, cy + ry);
                ctx.moveTo(cx - rx, cy);
                ctx.lineTo(cx + rx, cy);
                ctx.stroke();

                // Biometric Landmark Points
                const landmarks = [
                    { x: cx - 24, y: cy - 18 },
                    { x: cx + 24, y: cy - 18 },
                    { x: cx,      y: cy + 4 },
                    { x: cx - 18, y: cy + 32 },
                    { x: cx + 18, y: cy + 32 }
                ];

                ctx.fillStyle = strokeColor;
                landmarks.forEach(pt => {
                    ctx.beginPath();
                    ctx.arc(pt.x, pt.y, 4, 0, Math.PI * 2);
                    ctx.fill();
                });

                // Laser scan line
                const laserY = cy + Math.sin(time * 3) * (ry * 0.9);
                ctx.strokeStyle = strokeColor;
                ctx.lineWidth = 2;
                ctx.beginPath();
                ctx.moveTo(cx - rx, laserY);
                ctx.lineTo(cx + rx, laserY);
                ctx.stroke();

                ctx.restore();
                this.animationFrameId = requestAnimationFrame(renderFallback);
            };
            renderFallback();
        }

        destroy() {
            if (this.animationFrameId) cancelAnimationFrame(this.animationFrameId);
            if (this.renderer) this.renderer.dispose();
        }
    }

    // Initialize 3D visualizer
    const headVisualizer = new BiometricHeadVisualizer(canvas3d, model3dContainer);

    // =============================================================
    // 2D BIOMETRIC LANDMARK & BOX OVERLAY
    // =============================================================
    function drawLandmarksOverlay(box, landmarks, statusType) {
        if (!landmarkCanvas || !video) return;

        const displayWidth = video.clientWidth;
        const displayHeight = video.clientHeight;

        landmarkCanvas.width = displayWidth;
        landmarkCanvas.height = displayHeight;

        const ctx = landmarkCanvas.getContext('2d');
        ctx.clearRect(0, 0, displayWidth, displayHeight);

        if (!box) return;

        const videoW = video.videoWidth || 640;
        const videoH = video.videoHeight || 480;

        const scaleX = displayWidth / videoW;
        const scaleY = displayHeight / videoH;

        const bx = box[0] * scaleX;
        const by = box[1] * scaleY;
        const bw = box[2] * scaleX;
        const bh = box[3] * scaleY;

        let strokeStyle = '#00e5ff';
        if (statusType === 'granted') strokeStyle = '#00e676';
        else if (statusType === 'rejected' || statusType === 'already_recorded') strokeStyle = '#ff5252';

        // Draw Google-style high-tech corner brackets
        ctx.save();
        ctx.strokeStyle = strokeStyle;
        ctx.lineWidth = 3;
        ctx.shadowColor = strokeStyle;
        ctx.shadowBlur = 8;

        const cornerLen = Math.min(bw, bh) * 0.22;

        // Top-left
        ctx.beginPath();
        ctx.moveTo(bx, by + cornerLen);
        ctx.lineTo(bx, by);
        ctx.lineTo(bx + cornerLen, by);
        ctx.stroke();

        // Top-right
        ctx.beginPath();
        ctx.moveTo(bx + bw - cornerLen, by);
        ctx.lineTo(bx + bw, by);
        ctx.lineTo(bx + bw, by + cornerLen);
        ctx.stroke();

        // Bottom-left
        ctx.beginPath();
        ctx.moveTo(bx, by + bh - cornerLen);
        ctx.lineTo(bx, by + bh);
        ctx.lineTo(bx + cornerLen, by + bh);
        ctx.stroke();

        // Bottom-right
        ctx.beginPath();
        ctx.moveTo(bx + bw - cornerLen, by + bh);
        ctx.lineTo(bx + bw, by + bh);
        ctx.lineTo(bx + bw, by + bh - cornerLen);
        ctx.stroke();

        // Draw landmark nodes if provided
        if (landmarks && landmarks.length > 0) {
            ctx.fillStyle = strokeStyle;
            landmarks.forEach(pt => {
                const px = pt[0] * scaleX;
                const py = pt[1] * scaleY;
                ctx.beginPath();
                ctx.arc(px, py, 4, 0, Math.PI * 2);
                ctx.fill();
            });
        }

        ctx.restore();
    }

    function clearLandmarksOverlay() {
        if (!landmarkCanvas) return;
        const ctx = landmarkCanvas.getContext('2d');
        ctx.clearRect(0, 0, landmarkCanvas.width, landmarkCanvas.height);
    }

    // =============================================================
    // STATE MACHINE CONTROLLER
    // =============================================================
    function updateScannerState(state, headline, description) {
        if (!scannerStateBar) return;

        // Reset classes
        scannerStateBar.className = 'scanner-state-bar';

        if (state === 'searching') {
            scannerStateBar.classList.add('state-searching');
            if (stateIconBubble) stateIconBubble.textContent = '🔍';
            if (stateHeadline) stateHeadline.textContent = headline || 'Searching for a face...';
            if (stateDescription) stateDescription.textContent = description || 'Center your face in the camera viewport for automatic scan.';
            if (stateProgressFill) stateProgressFill.style.width = '35%';
            headVisualizer.setState('searching');
            if (hudMeshStatus) hudMeshStatus.textContent = 'ACTIVE';

        } else if (state === 'verifying') {
            scannerStateBar.classList.add('state-verifying');
            if (stateIconBubble) stateIconBubble.textContent = '⚡';
            if (stateHeadline) stateHeadline.textContent = headline || 'Verifying face biometrics...';
            if (stateDescription) stateDescription.textContent = description || 'Extracting topographical features and matching enrolled profile.';
            if (stateProgressFill) stateProgressFill.style.width = '75%';
            headVisualizer.setState('verifying');
            if (hudMeshStatus) hudMeshStatus.textContent = 'MATCHING';

        } else if (state === 'granted') {
            scannerStateBar.classList.add('state-granted');
            if (stateIconBubble) stateIconBubble.textContent = '✅';
            if (stateHeadline) stateHeadline.textContent = headline || 'Access Granted!';
            if (stateDescription) stateDescription.textContent = description || 'Meal attendance confirmed and registered in database.';
            if (stateProgressFill) stateProgressFill.style.width = '100%';
            headVisualizer.setState('granted');
            if (hudMeshStatus) hudMeshStatus.textContent = 'VERIFIED';

        } else if (state === 'rejected') {
            scannerStateBar.classList.add('state-rejected');
            if (stateIconBubble) stateIconBubble.textContent = '⛔';
            if (stateHeadline) stateHeadline.textContent = headline || 'Verification Alert';
            if (stateDescription) stateDescription.textContent = description || 'Identity unconfirmed or meal policy restriction.';
            if (stateProgressFill) stateProgressFill.style.width = '100%';
            headVisualizer.setState('rejected');
            if (hudMeshStatus) hudMeshStatus.textContent = 'RESTRICTED';

        } else if (state === 'paused') {
            scannerStateBar.classList.add('state-searching');
            if (stateIconBubble) stateIconBubble.textContent = '⏸️';
            if (stateHeadline) stateHeadline.textContent = 'Automatic Scanning Paused';
            if (stateDescription) stateDescription.textContent = 'Click Resume Auto-Scan to re-enable continuous facial detection.';
            if (stateProgressFill) stateProgressFill.style.width = '0%';
            headVisualizer.setState('searching');
            if (hudMeshStatus) hudMeshStatus.textContent = 'PAUSED';
        }
    }

    // =============================================================
    // COOLDOWN COUNTDOWN TIMER
    // =============================================================
    function startCooldownTimer(seconds = COOLDOWN_DURATION_SEC) {
        isInCooldown = true;
        let remaining = seconds;

        if (cooldownIndicator) cooldownIndicator.style.display = 'inline-flex';
        if (cooldownTimer) cooldownTimer.textContent = Math.ceil(remaining);

        if (cooldownIntervalId) clearInterval(cooldownIntervalId);

        cooldownIntervalId = setInterval(() => {
            remaining -= 0.5;
            if (cooldownTimer) cooldownTimer.textContent = Math.max(1, Math.ceil(remaining));

            if (remaining <= 0) {
                clearInterval(cooldownIntervalId);
                cooldownIntervalId = null;
                isInCooldown = false;
                if (cooldownIndicator) cooldownIndicator.style.display = 'none';

                // Revert to searching state
                clearLandmarksOverlay();
                updateScannerState('searching');
            }
        }, 500);
    }

    function cancelCooldown() {
        if (cooldownIntervalId) {
            clearInterval(cooldownIntervalId);
            cooldownIntervalId = null;
        }
        isInCooldown = false;
        if (cooldownIndicator) cooldownIndicator.style.display = 'none';
        clearLandmarksOverlay();
        resetScannerView();
        updateScannerState('searching');
    }

    // =============================================================
    // WEBCAM STREAM CONTROLLER
    // =============================================================
    async function initCamera() {
        if (streamRef) {
            streamRef.getTracks().forEach(track => track.stop());
            streamRef = null;
        }

        if (cameraStatus) cameraStatus.textContent = 'Connecting Camera...';

        try {
            const constraints = {
                video: {
                    width: { ideal: 640 },
                    height: { ideal: 480 },
                    facingMode: 'user'
                },
                audio: false
            };

            const stream = await navigator.mediaDevices.getUserMedia(constraints);
            streamRef = stream;
            video.srcObject = stream;

            video.onloadedmetadata = () => {
                video.play();
                if (cameraStatus) {
                    cameraStatus.textContent = 'Live Feed Active';
                    cameraStatus.style.color = '#34a853';
                }
                updateScannerState('searching');
            };
        } catch (err) {
            console.error('Camera access error:', err);
            if (cameraStatus) {
                cameraStatus.textContent = 'Camera Unavailable';
                cameraStatus.style.color = '#ea4335';
            }
            updateScannerState('rejected', 'Camera Inaccessible', 'Please allow camera permission in your browser.');
        }
    }

    function captureSnapshot() {
        const width = video.videoWidth || 640;
        const height = video.videoHeight || 480;

        snapshotCanvas.width = width;
        snapshotCanvas.height = height;
        const ctx = snapshotCanvas.getContext('2d');
        ctx.drawImage(video, 0, 0, width, height);

        return snapshotCanvas.toDataURL('image/jpeg', 0.85);
    }

    // =============================================================
    // AUTOMATIC FACE DETECTION & SCAN CYCLE
    // =============================================================
    async function processVideoFrame() {
        // Prevent overlapping requests or scanning during pauses / cooldowns
        if (isProcessingFrame || isScannerPaused || isInCooldown) return;
        if (!video || video.readyState < 2 || video.videoWidth === 0) return;

        isProcessingFrame = true;

        const imageData = captureSnapshot();
        const payload = {
            image: imageData,
            meal_type: currentScanMeal === 'auto' ? null : currentScanMeal
        };

        try {
            const response = await fetch('/api/scan-face', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const data = await response.json();
            handleScanResponse(data);
        } catch (err) {
            console.warn('Scan frame request error:', err);
        } finally {
            isProcessingFrame = false;
        }
    }

    // Main continuous scanning timer
    function startAutoScanLoop() {
        if (scanLoopIntervalId) clearInterval(scanLoopIntervalId);
        scanLoopIntervalId = setInterval(processVideoFrame, SCAN_CADENCE_MS);
    }

    // =============================================================
    // SCAN RESULT HANDLER & STUDENT PROFILE PRESENTATION
    // =============================================================
    function handleScanResponse(data) {
        // Case: No face detected in frame
        if (data.status === 'no_face') {
            clearLandmarksOverlay();
            if (!isInCooldown) {
                updateScannerState('searching');
            }
            return;
        }

        // Case: Quality check failure (too dark / blurry)
        if (data.status === 'quality_fail') {
            if (!isInCooldown) {
                updateScannerState('searching', 'Adjust Position or Lighting', data.message);
            }
            return;
        }

        // Project bounding box and landmarks onto overlay
        if (data.box) {
            drawLandmarksOverlay(data.box, data.landmarks, data.status);
        }

        if (standbyView) standbyView.style.display = 'none';
        if (resultContent) resultContent.style.display = 'block';
        if (statusBanner) statusBanner.className = 'status-banner';

        if (data.status === 'granted') {
            // SUCCESS - ACCESS GRANTED
            playAudioTone('success');
            if (statusBanner) statusBanner.classList.add('banner-success');
            if (bannerIcon) bannerIcon.textContent = '✅';
            if (bannerTitle) bannerTitle.textContent = 'ACCESS GRANTED';
            if (bannerMessage) bannerMessage.textContent = data.message || 'Meal entry recorded successfully!';
            if (resultPill) {
                resultPill.className = 'badge badge-success';
                resultPill.textContent = 'VERIFIED';
            }

            renderStudentDetails(data.student, data.entry);
            if (studentProfile) studentProfile.style.display = 'block';

            updateScannerState('granted', 'Access Granted ✅', `${data.student.name} (${data.entry.meal}) recorded.`);
            refreshStats();
            startCooldownTimer(3.5);

        } else if (data.status === 'already_recorded') {
            // DUPLICATE MEAL
            playAudioTone('warning');
            if (statusBanner) statusBanner.classList.add('banner-warning');
            if (bannerIcon) bannerIcon.textContent = '⚠️';
            if (bannerTitle) bannerTitle.textContent = 'MEAL ALREADY RECORDED';
            if (bannerMessage) bannerMessage.textContent = data.message || 'Student has already claimed this meal today.';
            if (resultPill) {
                resultPill.className = 'badge badge-warning';
                resultPill.textContent = 'ALREADY CLAIMED';
            }

            if (data.student) {
                renderStudentDetails(data.student, null, 'Already Recorded');
                if (studentProfile) studentProfile.style.display = 'block';
            }

            updateScannerState('rejected', 'Meal Already Recorded ⚠️', data.message);
            startCooldownTimer(3.5);

        } else if (data.status === 'meal_access_disabled') {
            // MEAL PRIVILEGES DISABLED
            playAudioTone('error');
            if (statusBanner) statusBanner.classList.add('banner-danger');
            if (bannerIcon) bannerIcon.textContent = '⛔';
            if (bannerTitle) bannerTitle.textContent = 'MEAL ACCESS RESTRICTED';
            if (bannerMessage) bannerMessage.textContent = data.message || 'Canteen meal access disabled by hostel warden.';
            if (resultPill) {
                resultPill.className = 'badge badge-danger';
                resultPill.textContent = 'DISABLED';
            }

            if (data.student) {
                renderStudentDetails(data.student, null, 'Restricted');
                if (studentProfile) studentProfile.style.display = 'block';
            }

            updateScannerState('rejected', 'Access Restricted ⛔', data.message);
            startCooldownTimer(3.5);

        } else if (data.status === 'fee_policy_violation') {
            // FEE DUES VIOLATION
            playAudioTone('error');
            if (statusBanner) statusBanner.classList.add('banner-danger');
            if (bannerIcon) bannerIcon.textContent = '⚠️';
            if (bannerTitle) bannerTitle.textContent = 'FEE DUES RESTRICTION';
            if (bannerMessage) bannerMessage.textContent = data.message || 'Outstanding dues exceed allowed policy.';
            if (resultPill) {
                resultPill.className = 'badge badge-danger';
                resultPill.textContent = 'FEE DUES';
            }

            if (data.student) {
                renderStudentDetails(data.student, null, 'Fee Blocked');
                if (studentProfile) studentProfile.style.display = 'block';
            }

            updateScannerState('rejected', 'Fee Policy Block ⚠️', data.message);
            startCooldownTimer(3.5);

        } else if (data.status === 'outside_hours') {
            // OUTSIDE SERVING WINDOW
            playAudioTone('warning');
            if (statusBanner) statusBanner.classList.add('banner-warning');
            if (bannerIcon) bannerIcon.textContent = '⏰';
            if (bannerTitle) bannerTitle.textContent = 'SERVICE CLOSED';
            if (bannerMessage) bannerMessage.textContent = data.message || 'Meal is only served during official schedule hours.';
            if (resultPill) {
                resultPill.className = 'badge badge-warning';
                resultPill.textContent = 'CLOSED';
            }

            if (data.student) {
                renderStudentDetails(data.student, null, 'Closed');
                if (studentProfile) studentProfile.style.display = 'block';
            }

            updateScannerState('rejected', 'Outside Service Hours ⏰', data.message);
            startCooldownTimer(3.5);

        } else if (data.status === 'not_recognized') {
            // UNKNOWN FACE
            playAudioTone('error');
            if (statusBanner) statusBanner.classList.add('banner-danger');
            if (bannerIcon) bannerIcon.textContent = '❌';
            if (bannerTitle) bannerTitle.textContent = 'FACE NOT RECOGNIZED';
            if (bannerMessage) bannerMessage.textContent = 'No matching enrolled resident found. Please contact canteen admin.';
            if (resultPill) {
                resultPill.className = 'badge badge-danger';
                resultPill.textContent = 'REJECTED';
            }
            if (studentProfile) studentProfile.style.display = 'none';

            updateScannerState('rejected', 'Face Not Recognized ❌', 'No matching student record in database.');
            startCooldownTimer(3.5);

        } else {
            // OTHER DETECTION ERRORS
            playAudioTone('error');
            if (statusBanner) statusBanner.classList.add('banner-danger');
            if (bannerIcon) bannerIcon.textContent = '⚠️';
            if (bannerTitle) bannerTitle.textContent = 'VERIFICATION FAILED';
            if (bannerMessage) bannerMessage.textContent = data.message || 'Biometric check failed.';
            if (resultPill) {
                resultPill.className = 'badge badge-danger';
                resultPill.textContent = 'FAILED';
            }
            if (studentProfile) studentProfile.style.display = 'none';

            updateScannerState('rejected', 'Verification Failed', data.message || 'Check failed.');
            startCooldownTimer(3.5);
        }
    }

    function renderStudentDetails(student, entry, customStatus) {
        if (!student) return;

        if (studentName) studentName.textContent = student.name;
        if (studentId) studentId.textContent = `${student.student_id} (${student.srn || student.student_id})`;
        if (studentRoom) studentRoom.textContent = `${student.hostel} • Room ${student.room_number || '--'}`;
        if (studentBranch) studentBranch.textContent = `${student.branch} • ${student.year}`;

        if (entry) {
            if (mealTypeBadge) mealTypeBadge.textContent = entry.meal;
            if (entryTime) entryTime.textContent = entry.entry_time;
            if (lunchStatusBadge) lunchStatusBadge.innerHTML = '<span class="badge badge-success">Approved ✅</span>';
            if (smsStatusBadge) smsStatusBadge.innerHTML = '<span class="badge badge-success">SMS Dispatched 📱</span>';
        } else {
            if (mealTypeBadge) mealTypeBadge.textContent = currentScanMeal === 'auto' ? 'Meal' : currentScanMeal;
            if (entryTime) entryTime.textContent = '--';
            if (lunchStatusBadge) lunchStatusBadge.innerHTML = `<span class="badge badge-warning">${customStatus || 'Denied'}</span>`;
            if (smsStatusBadge) smsStatusBadge.innerHTML = '<span class="badge badge-neutral">No SMS Sent</span>';
        }

        if (student.photo_preview) {
            if (studentPhoto) {
                studentPhoto.src = student.photo_preview;
                studentPhoto.style.display = 'block';
            }
            if (studentAvatarFallback) studentAvatarFallback.style.display = 'none';
        } else {
            if (studentPhoto) studentPhoto.style.display = 'none';
            if (studentAvatarFallback) {
                studentAvatarFallback.style.display = 'flex';
                studentAvatarFallback.textContent = student.name.substring(0, 2).toUpperCase();
            }
        }
    }

    function resetScannerView() {
        if (standbyView) standbyView.style.display = 'block';
        if (resultContent) resultContent.style.display = 'none';
        if (resultPill) {
            resultPill.className = 'badge badge-neutral';
            resultPill.textContent = 'Standby';
        }
    }

    async function refreshStats() {
        try {
            const res = await fetch('/api/entries/today');
            const data = await res.json();
            if (data.success && data.metrics) {
                if (todayServedCount) todayServedCount.textContent = data.metrics.today_lunch_count;
                if (todayBreakfastCount) todayBreakfastCount.textContent = data.metrics.today_breakfast_count;
                if (totalActiveStudents) totalActiveStudents.textContent = data.metrics.active_students;
            }
        } catch (e) {}
    }

    // =============================================================
    // UI BUTTON CONTROLS & KEYBOARD SHORTCUTS
    // =============================================================
    if (toggleAutoScanBtn) {
        toggleAutoScanBtn.addEventListener('click', () => {
            isScannerPaused = !isScannerPaused;
            if (isScannerPaused) {
                toggleAutoScanBtn.innerHTML = '▶️ Resume Auto-Scan';
                toggleAutoScanBtn.classList.replace('btn-secondary', 'btn-primary');
                updateScannerState('paused');
            } else {
                toggleAutoScanBtn.innerHTML = '⏸️ Pause Auto-Scan';
                toggleAutoScanBtn.classList.replace('btn-primary', 'btn-secondary');
                updateScannerState('searching');
            }
        });
    }

    if (retryCamBtn) {
        retryCamBtn.addEventListener('click', () => {
            initCamera();
        });
    }

    if (resetScannerBtn) {
        resetScannerBtn.addEventListener('click', () => {
            cancelCooldown();
        });
    }

    window.addEventListener('keydown', (e) => {
        if (e.code === 'Space' && document.activeElement.tagName !== 'INPUT') {
            e.preventDefault();
            if (toggleAutoScanBtn) toggleAutoScanBtn.click();
        } else if (e.code === 'Escape') {
            cancelCooldown();
        }
    });

    // Initialize camera, continuous scanning loop, and statistics
    initCamera();
    startAutoScanLoop();
    refreshStats();
});
