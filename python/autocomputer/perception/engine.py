"""
Perception layer — multi-backend OCR + LLM Vision.

Architecture:
    PerceptionManager
    ├── PaddleOCRBackend  (default, Chinese-optimized)
    ├── EasyOCRBackend    (multi-language fallback)
    ├── TesseractBackend  (lightweight, no GPU)
    └── LLMVisionBackend  (GPT-4V / Claude Vision)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TextRegion:
    """Detected text with bounding box and confidence."""
    text: str
    x: int
    y: int
    width: int
    height: int
    confidence: float = 0.0
    language: str = ""

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.x + self.width, self.y + self.height)

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)


@dataclass
class PerceptionResult:
    """Complete perception result."""
    regions: list[TextRegion] = field(default_factory=list)
    full_text: str = ""
    backend: str = ""
    elapsed_ms: float = 0.0


class PerceptionBackend(ABC):
    """Abstract OCR/perception backend interface."""

    name: str = "base"

    @abstractmethod
    def recognize(self, image_data: bytes, languages: Optional[list[str]] = None) -> PerceptionResult:
        """Recognize text from image bytes (PNG or raw RGBA)."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this backend's dependencies are installed."""
        ...


class EasyOCRBackend(PerceptionBackend):
    """EasyOCR — good multi-language support, CPU-friendly."""

    name = "easyocr"

    def __init__(self) -> None:
        self._reader = None
        self._available: Optional[bool] = None

    def is_available(self) -> bool:
        if self._available is None:
            try:
                import easyocr  # noqa: F401
                self._available = True
            except ImportError:
                self._available = False
        return self._available

    def recognize(self, image_data: bytes, languages: Optional[list[str]] = None) -> PerceptionResult:
        import time
        import io
        from PIL import Image
        import numpy as np
        import easyocr

        t0 = time.time()

        if self._reader is None:
            langs = languages or ["ch_sim", "en"]
            self._reader = easyocr.Reader(langs, gpu=False)

        img = Image.open(io.BytesIO(image_data)).convert("RGB")
        arr = np.array(img)
        results = self._reader.readtext(arr)

        regions = [
            TextRegion(
                text=r[1],
                x=int(r[0][0][0]), y=int(r[0][0][1]),
                width=int(r[0][2][0] - r[0][0][0]),
                height=int(r[0][2][1] - r[0][0][1]),
                confidence=float(r[2]),
            )
            for r in results
        ]

        return PerceptionResult(
            regions=regions,
            full_text=" ".join(r.text for r in regions),
            backend=self.name,
            elapsed_ms=(time.time() - t0) * 1000,
        )


class PaddleOCRBackend(PerceptionBackend):
    """PaddleOCR — fast, Chinese-optimized (PP-OCRv5)."""

    name = "paddleocr"

    def __init__(self) -> None:
        self._ocr = None
        self._available: Optional[bool] = None

    def is_available(self) -> bool:
        if self._available is None:
            try:
                import paddleocr  # noqa: F401
                self._available = True
            except ImportError:
                self._available = False
        return self._available

    def recognize(self, image_data: bytes, languages: Optional[list[str]] = None) -> PerceptionResult:
        import time
        import io
        import numpy as np

        t0 = time.time()

        if self._ocr is None:
            from paddleocr import PaddleOCR
            self._ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)

        img = _bytes_to_numpy(image_data)
        raw = self._ocr.ocr(img, cls=True)

        regions = []
        if raw and raw[0]:
            for line in raw[0]:
                box = line[0]
                text = line[1][0]
                conf = line[1][1]
                regions.append(TextRegion(
                    text=text,
                    x=int(box[0][0]), y=int(box[0][1]),
                    width=int(box[2][0] - box[0][0]),
                    height=int(box[2][1] - box[0][1]),
                    confidence=float(conf),
                ))

        return PerceptionResult(
            regions=regions,
            full_text=" ".join(r.text for r in regions),
            backend=self.name,
            elapsed_ms=(time.time() - t0) * 1000,
        )


class TesseractBackend(PerceptionBackend):
    """Tesseract — lightweight, no GPU, good for simple text."""

    name = "tesseract"

    def is_available(self) -> bool:
        try:
            import pytesseract  # noqa: F401
            return True
        except ImportError:
            return False

    def recognize(self, image_data: bytes, languages: Optional[list[str]] = None) -> PerceptionResult:
        import time
        import io
        import pytesseract
        from PIL import Image

        t0 = time.time()
        img = Image.open(io.BytesIO(image_data)).convert("RGB")
        lang = "+".join(languages) if languages else "chi_sim+eng"

        data = pytesseract.image_to_data(img, lang=lang, output_type=pytesseract.Output.DICT)
        regions = [
            TextRegion(
                text=data["text"][i],
                x=data["left"][i], y=data["top"][i],
                width=data["width"][i], height=data["height"][i],
                confidence=int(data["conf"][i]) / 100.0 if data["conf"][i] > 0 else 0.0,
            )
            for i in range(len(data["text"]))
            if data["text"][i].strip()
        ]

        return PerceptionResult(
            regions=regions,
            full_text=" ".join(r.text for r in regions),
            backend=self.name,
            elapsed_ms=(time.time() - t0) * 1000,
        )


class LLMVisionBackend(PerceptionBackend):
    """LLM Vision — send screenshot to GPT-4V/Claude for analysis."""

    name = "llm_vision"

    def __init__(self, model: str = "gpt-4o", api_key: Optional[str] = None) -> None:
        self.model = model
        self.api_key = api_key

    def is_available(self) -> bool:
        try:
            import openai  # noqa: F401
            return True
        except ImportError:
            return False

    def recognize(self, image_data: bytes, languages: Optional[list[str]] = None) -> PerceptionResult:
        import time
        import base64

        t0 = time.time()

        try:
            import openai

            client = openai.OpenAI(api_key=self.api_key) if self.api_key else openai.OpenAI()
            b64 = base64.b64encode(image_data).decode()

            response = client.chat.completions.create(
                model=self.model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "List ALL visible text on this screen. For each text element, provide: text content, approximate position (x,y,width,height in pixels). Format as JSON array."},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    ],
                }],
                max_tokens=1000,
            )

            result_text = response.choices[0].message.content or "[]"

            # Parse JSON from response
            import json
            try:
                items = json.loads(result_text)
                regions = [
                    TextRegion(
                        text=item.get("text", ""),
                        x=item.get("x", 0), y=item.get("y", 0),
                        width=item.get("width", 0), height=item.get("height", 0),
                        confidence=0.9,
                        language=item.get("language", ""),
                    )
                    for item in items
                ]
            except json.JSONDecodeError:
                regions = [TextRegion(text=result_text, x=0, y=0, width=0, height=0)]

            return PerceptionResult(
                regions=regions,
                full_text=result_text,
                backend=f"{self.name}({self.model})",
                elapsed_ms=(time.time() - t0) * 1000,
            )

        except Exception as e:
            return PerceptionResult(
                regions=[],
                full_text=f"LLM Vision error: {e}",
                backend=self.name,
                elapsed_ms=(time.time() - t0) * 1000,
            )


# ── Manager ──

class PerceptionManager:
    """Auto-selects the best available OCR backend."""

    _instance: Optional["PerceptionManager"] = None

    def __init__(self) -> None:
        self._backends: dict[str, PerceptionBackend] = {
            "paddleocr": PaddleOCRBackend(),
            "easyocr": EasyOCRBackend(),
            "tesseract": TesseractBackend(),
            "llm_vision": LLMVisionBackend(),
        }
        self._default: Optional[str] = None

    @classmethod
    def get_instance(cls) -> "PerceptionManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def list_available(self) -> list[str]:
        return [name for name, b in self._backends.items() if b.is_available()]

    def get_backend(self, name: Optional[str] = None) -> PerceptionBackend:
        """Get a specific backend, or auto-select the best available."""
        if name:
            backend = self._backends.get(name)
            if backend and backend.is_available():
                return backend
            raise ValueError(f"Backend '{name}' not available. Available: {self.list_available()}")

        # Auto-select: PaddleOCR > EasyOCR > Tesseract > LLM Vision
        for name in ["paddleocr", "easyocr", "tesseract", "llm_vision"]:
            backend = self._backends[name]
            if backend.is_available():
                return backend

        raise RuntimeError("No OCR backend available. Install one: pip install paddleocr easyocr pytesseract")

    def recognize(self, image_data: bytes, backend: Optional[str] = None, languages: Optional[list[str]] = None) -> PerceptionResult:
        return self.get_backend(backend).recognize(image_data, languages)


# ── Helpers ──

def _bytes_to_numpy(data: bytes) -> "numpy.ndarray":
    import io
    import numpy as np
    from PIL import Image
    img = Image.open(io.BytesIO(data)).convert("RGB")
    return np.array(img)
