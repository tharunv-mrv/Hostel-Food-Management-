import base64
import os
import json
import cv2
import numpy as np

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
MODELS_DIR = os.path.join(BASE_DIR, 'models')
YUNET_PATH = os.path.join(MODELS_DIR, 'face_detection_yunet_2023mar.onnx')
SFACE_PATH = os.path.join(MODELS_DIR, 'face_recognition_sface_2021dec.onnx')

class FaceService:
    """Face detection and verification engine using OpenCV Deep Learning (YuNet + SFace)."""

    def __init__(self):
        self.yunet_path = YUNET_PATH
        self.sface_path = SFACE_PATH
        self.detector = None
        self.recognizer = None
        self.haar_cascade = None
        self._init_models()

    def _init_models(self):
        """Initialize YuNet and SFace neural networks."""
        try:
            if os.path.exists(self.yunet_path) and os.path.exists(self.sface_path):
                # YuNet detector: score_threshold=0.6, nms_threshold=0.3
                self.detector = cv2.FaceDetectorYN.create(
                    self.yunet_path, '', (320, 320), 0.6, 0.3, 5000
                )
                self.recognizer = cv2.FaceRecognizerSF.create(self.sface_path, '')
                print("[FaceService] OpenCV YuNet & SFace models loaded successfully.")
            else:
                print("[FaceService] Warning: Neural network model files not found.")
        except Exception as e:
            print(f"[FaceService] Error loading neural network models: {e}")

        # Fallback Haar Cascade
        try:
            haar_path = os.path.join(cv2.data.haarcascades, 'haarcascade_frontalface_default.xml')
            if os.path.exists(haar_path):
                self.haar_cascade = cv2.CascadeClassifier(haar_path)
        except Exception as e:
            print(f"[FaceService] Warning: Could not load Haar cascade: {e}")

    def decode_base64_image(self, data_url):
        """Decode base64 data URI into OpenCV BGR image array."""
        try:
            if ',' in data_url:
                header, encoded = data_url.split(',', 1)
            else:
                encoded = data_url
            img_bytes = base64.b64decode(encoded)
            np_arr = np.frombuffer(img_bytes, dtype=np.uint8)
            img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            return img, None
        except Exception as e:
            return None, f"Failed to decode image data: {str(e)}"

    def create_thumbnail(self, img_bgr, face_box=None, size=(120, 120)):
        """Generate a small base64 JPEG thumbnail of the cropped face or whole image."""
        try:
            h, w, _ = img_bgr.shape
            if face_box is not None:
                x, y, bw, bh = [int(v) for v in face_box[:4]]
                # Add 20% margin around face
                pad_x = int(bw * 0.2)
                pad_y = int(bh * 0.2)
                x1 = max(0, x - pad_x)
                y1 = max(0, y - pad_y)
                x2 = min(w, x + bw + pad_x)
                y2 = min(h, y + bh + pad_y)
                crop = img_bgr[y1:y2, x1:x2]
                if crop.size > 0:
                    thumb = cv2.resize(crop, size, interpolation=cv2.INTER_AREA)
                else:
                    thumb = cv2.resize(img_bgr, size, interpolation=cv2.INTER_AREA)
            else:
                thumb = cv2.resize(img_bgr, size, interpolation=cv2.INTER_AREA)

            _, buf = cv2.imencode('.jpg', thumb, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            b64_str = base64.b64encode(buf).decode('utf-8')
            return f"data:image/jpeg;base64,{b64_str}"
        except Exception:
            return None

    def extract_face_with_landmarks(self, img_bgr, check_quality=False):
        """
        Detect face, extract 128-d embedding, evaluate image quality, and extract 5 landmark coordinates.
        Returns: (encoding, thumbnail, error_message, meta_dict)
        """
        if img_bgr is None or img_bgr.size == 0:
            return None, None, "Invalid image data provided.", None

        h, w, _ = img_bgr.shape
        if h < 40 or w < 40:
            return None, None, "Image resolution too low.", None

        # Efficiency Optimization: Downscale high-resolution frames (e.g. 1080p/4K) to max 640px
        # This dramatically cuts YuNet DNN inference time by 80-90% without losing facial details.
        max_dim = 640
        if max(h, w) > max_dim:
            scale = max_dim / float(max(h, w))
            img_bgr = cv2.resize(img_bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
            h, w, _ = img_bgr.shape

        # Detect with YuNet
        faces = None
        if self.detector is not None:
            self.detector.setInputSize((w, h))
            _, faces = self.detector.detect(img_bgr)

        # Filter valid faces
        valid_faces = []
        if faces is not None and len(faces) > 0:
            for face in faces:
                score = float(face[14])
                if score >= 0.55:
                    valid_faces.append(face)

        if len(valid_faces) == 0:
            if self.haar_cascade is not None:
                gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
                haar_faces = self.haar_cascade.detectMultiScale(gray, 1.2, 5, minSize=(60, 60))
                if len(haar_faces) == 0:
                    return None, None, "No face detected. Please center your face in the camera frame.", None
                if len(haar_faces) > 1:
                    return None, None, f"Multiple faces detected ({len(haar_faces)}). Exactly one face must be visible.", None
                hx, hy, hw, hh = haar_faces[0]
                synth_face = np.array([
                    hx, hy, hw, hh,
                    hx + hw * 0.3, hy + hh * 0.35,  # right eye
                    hx + hw * 0.7, hy + hh * 0.35,  # left eye
                    hx + hw * 0.5, hy + hh * 0.55,  # nose
                    hx + hw * 0.35, hy + hh * 0.75, # right mouth
                    hx + hw * 0.65, hy + hh * 0.75, # left mouth
                    0.80
                ], dtype=np.float32)
                valid_faces = [synth_face]
            else:
                return None, None, "No face detected. Please center your face in the camera frame.", None

        if len(valid_faces) > 1:
            return None, None, f"Multiple faces detected ({len(valid_faces)}). Please ensure only one person is in front of the camera.", None

        target_face = valid_faces[0]
        box = [int(v) for v in target_face[:4]]
        bx, by, bw, bh = box

        # Optional quality checks
        if check_quality and bw > 0 and bh > 0:
            crop_y1 = max(0, by)
            crop_y2 = min(h, by + bh)
            crop_x1 = max(0, bx)
            crop_x2 = min(w, bx + bw)
            face_crop = img_bgr[crop_y1:crop_y2, crop_x1:crop_x2]
            if face_crop.size > 0:
                gray_crop = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
                brightness = float(np.mean(gray_crop))
                if brightness < 25.0:
                    return None, None, "Lighting too dark. Please ensure face is well illuminated.", None
                sharpness = float(cv2.Laplacian(gray_crop, cv2.CV_64F).var())
                if sharpness < 15.0 and bw > 60:
                    return None, None, "Image appears blurry. Please hold steady for scanning.", None

        # Extract landmarks: [[rx, ry], [lx, ly], [nx, ny], [rmx, rmy], [lmx, lmy]]
        landmarks = []
        for i in range(4, 14, 2):
            landmarks.append([float(target_face[i]), float(target_face[i+1])])

        # Extract deep 128-d feature representation
        try:
            aligned_face = self.recognizer.alignCrop(img_bgr, target_face)
            feature = self.recognizer.feature(aligned_face)
            encoding = feature.flatten().astype(float).tolist()
            thumbnail = self.create_thumbnail(img_bgr, target_face[:4])

            meta = {
                'box': box,
                'landmarks': landmarks,
                'confidence': round(float(target_face[14]), 3)
            }
            return encoding, thumbnail, None, meta
        except Exception as e:
            return None, None, f"Feature extraction failed: {str(e)}", None

    def extract_face_encoding(self, img_bgr):
        """
        Detect face and extract 128-dimensional embedding.
        Maintains backward compatibility with original signature: returns (encoding, thumbnail, error)
        """
        enc, thumb, err, _ = self.extract_face_with_landmarks(img_bgr, check_quality=False)
        return enc, thumb, err

    def verify_against_students(self, candidate_encoding, students, threshold=0.363):
        """
        Compare candidate encoding against registered active students.
        Returns: (best_student, best_score, error_message)
        """
        if not candidate_encoding:
            return None, 0.0, "Missing candidate face encoding."

        if not students:
            return None, 0.0, "No registered students in the database."

        cand_arr = np.array(candidate_encoding, dtype=np.float32).reshape(1, -1)
        best_student = None
        best_score = -1.0

        for student in students:
            if not getattr(student, 'face_encoding', None):
                continue
            try:
                known_encoding = json.loads(student.face_encoding)
                known_arr = np.array(known_encoding, dtype=np.float32).reshape(1, -1)

                # Compute cosine similarity using OpenCV SFace recognizer
                if self.recognizer is not None:
                    score = float(self.recognizer.match(cand_arr, known_arr, cv2.FaceRecognizerSF_FR_COSINE))
                else:
                    # Pure numpy cosine similarity fallback
                    dot = np.dot(cand_arr.flatten(), known_arr.flatten())
                    norm_a = np.linalg.norm(cand_arr)
                    norm_b = np.linalg.norm(known_arr)
                    score = float(dot / (norm_a * norm_b)) if (norm_a > 0 and norm_b > 0) else 0.0

                if score > best_score:
                    best_score = score
                    best_student = student
            except Exception as e:
                print(f"[FaceService] Error comparing student {student.student_id}: {e}")
                continue

        if best_student is not None and best_score >= threshold:
            return best_student, best_score, None
        else:
            return None, max(0.0, best_score), f"Face not recognized (confidence: {round(max(0.0, best_score)*100, 1)}%, required: {round(threshold*100, 1)}%)."

face_service = FaceService()
