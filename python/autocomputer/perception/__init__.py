"""Perception layer — multi-backend OCR + LLM Vision."""

from autocomputer.perception.engine import (
    EasyOCRBackend,
    LLMVisionBackend,
    PaddleOCRBackend,
    PerceptionBackend,
    PerceptionManager,
    PerceptionResult,
    TesseractBackend,
    TextRegion,
)

__all__ = [
    "PerceptionBackend",
    "PerceptionResult",
    "TextRegion",
    "EasyOCRBackend",
    "PaddleOCRBackend",
    "TesseractBackend",
    "LLMVisionBackend",
    "PerceptionManager",
]
