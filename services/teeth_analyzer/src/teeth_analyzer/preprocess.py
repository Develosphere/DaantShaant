"""Image decode, quality assessment, and normalization before vision inference."""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from teeth_analyzer.config import settings

if TYPE_CHECKING:
    import numpy as np

_np: Any = None
_cv2: Any = None
_cv2_available: bool | None = None
_pil_available: bool | None = None


def _get_numpy():
    global _np
    if _np is None:
        import numpy as np_mod

        _np = np_mod
    return _np


def _cv2_ready() -> bool:
    global _cv2, _cv2_available
    if _cv2_available is not None:
        return _cv2_available
    try:
        import cv2 as cv2_mod

        _cv2 = cv2_mod
        _cv2_available = True
    except ImportError:
        _cv2_available = False
    return _cv2_available


def _pil_ready() -> bool:
    global _pil_available
    if _pil_available is None:
        try:
            from PIL import Image  # noqa: F401

            _pil_available = True
        except ImportError:
            _pil_available = False
    return _pil_available


@dataclass
class PreprocessResult:
    jpeg_bytes: bytes
    quality_score: float
    passed_gate: bool
    hint: str | None
    blur_variance: float
    brightness: float


def _decode_base64_image(image_base64: str) -> Any:
    np = _get_numpy()
    raw = base64.b64decode(image_base64, validate=True)
    if _cv2_ready():
        arr = np.frombuffer(raw, dtype=np.uint8)
        image = _cv2.imdecode(arr, _cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Could not decode image — use JPEG or PNG")
        return image
    if _pil_ready():
        from PIL import Image

        img = Image.open(io.BytesIO(raw)).convert("RGB")
        return np.array(img)[:, :, ::-1]
    raise ValueError(
        "Install opencv-python-headless (with numpy<2): pip install -c constraints.txt "
        "opencv-python-headless==4.9.0.80 'numpy>=1.26,<2'"
    )


def _preprocess_passthrough(image_base64: str) -> PreprocessResult:
    raw = base64.b64decode(image_base64, validate=True)
    if len(raw) < 100:
        raise ValueError("image_base64 is too small")
    return PreprocessResult(
        jpeg_bytes=raw,
        quality_score=0.75,
        passed_gate=True,
        hint=None,
        blur_variance=100.0,
        brightness=130.0,
    )


def assess_quality(image: Any) -> tuple[float, float, float]:
    np = _get_numpy()
    if _cv2_ready():
        gray = _cv2.cvtColor(image, _cv2.COLOR_BGR2GRAY)
        blur_variance = float(_cv2.Laplacian(gray, _cv2.CV_64F).var())
        brightness = float(np.mean(gray))
        h, w = gray.shape[:2]
    else:
        from PIL import Image, ImageFilter

        gray = np.mean(image, axis=2)
        blurred = np.array(Image.fromarray(gray.astype(np.uint8)).filter(ImageFilter.BLUR))
        blur_variance = float(np.var(gray.astype(float) - blurred.astype(float)) * 10)
        brightness = float(np.mean(gray))
        h, w = gray.shape[:2]

    blur_score = min(1.0, blur_variance / settings.min_blur_variance)
    brightness_score = 1.0 - min(abs(brightness - 130) / 130, 1.0)
    size_score = min(1.0, min(h, w) / settings.min_edge_px)
    quality = 0.5 * blur_score + 0.3 * brightness_score + 0.2 * size_score
    return quality, blur_variance, brightness


def _quality_hint(blur_variance: float, brightness: float, quality: float) -> str | None:
    if quality >= settings.quality_gate_threshold:
        return None
    if blur_variance < settings.min_blur_variance * 0.5:
        return "Image is blurry — hold the camera steady and move closer."
    if brightness < 60:
        return "Too dark — turn on a light or face a window."
    if brightness > 210:
        return "Too bright — reduce glare or move away from direct light."
    return "Hold still and center your teeth in the frame."


def normalize_image(image: Any) -> Any:
    np = _get_numpy()
    h, w = image.shape[:2]
    max_edge = settings.max_edge_px
    if _cv2_ready():
        if max(h, w) > max_edge:
            scale = max_edge / max(h, w)
            image = _cv2.resize(
                image, (int(w * scale), int(h * scale)), interpolation=_cv2.INTER_AREA
            )
        lab = _cv2.cvtColor(image, _cv2.COLOR_BGR2LAB)
        l, a, b = _cv2.split(lab)
        clahe = _cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l = clahe.apply(l)
        return _cv2.cvtColor(_cv2.merge([l, a, b]), _cv2.COLOR_LAB2BGR)
    from PIL import Image

    img = Image.fromarray(image[:, :, ::-1])
    if max(img.size) > max_edge:
        img.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    return np.array(img)[:, :, ::-1]


def _encode_jpeg(image: Any) -> bytes:
    if _cv2_ready():
        ok, buf = _cv2.imencode(".jpg", image, [int(_cv2.IMWRITE_JPEG_QUALITY), 85])
        if not ok:
            raise ValueError("Failed to encode processed image")
        return buf.tobytes()
    from PIL import Image

    img = Image.fromarray(image[:, :, ::-1])
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85)
    return out.getvalue()


def preprocess_frame(image_base64: str) -> PreprocessResult:
    if not _cv2_ready() and not _pil_ready():
        return _preprocess_passthrough(image_base64)
    image = _decode_base64_image(image_base64)
    image = normalize_image(image)
    quality, blur_var, brightness = assess_quality(image)
    hint = _quality_hint(blur_var, brightness, quality)
    passed = quality >= settings.quality_gate_threshold
    return PreprocessResult(
        jpeg_bytes=_encode_jpeg(image),
        quality_score=round(quality, 3),
        passed_gate=passed,
        hint=hint,
        blur_variance=blur_var,
        brightness=brightness,
    )


def frame_motion_score(prev_bgr: Any, curr_bgr: Any) -> float:
    np = _get_numpy()
    if _cv2_ready():
        p = _cv2.resize(prev_bgr, (160, 120))
        c = _cv2.resize(curr_bgr, (160, 120))
        diff = _cv2.absdiff(p, c)
        return float(np.mean(diff))
    p = np.mean(prev_bgr, axis=(0, 1))
    c = np.mean(curr_bgr, axis=(0, 1))
    return float(np.mean(np.abs(p - c)))
