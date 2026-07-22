"""Tests for perception module."""


class TestTextRegion:
    def test_bbox(self) -> None:
        from autocomputer.perception import TextRegion

        r = TextRegion(text="test", x=10, y=20, width=100, height=30)
        assert r.bbox == (10, 20, 110, 50)
        assert r.center == (60, 35)


class TestPerceptionResult:
    def test_defaults(self) -> None:
        from autocomputer.perception import PerceptionResult

        r = PerceptionResult()
        assert r.regions == []
        assert r.full_text == ""


class TestPerceptionManager:
    def test_list_available(self) -> None:
        from autocomputer.perception import PerceptionManager

        mgr = PerceptionManager()
        available = mgr.list_available()
        # At least tesseract or easyocr might be available
        assert isinstance(available, list)

    def test_get_backend_auto(self) -> None:
        from autocomputer.perception import PerceptionManager

        mgr = PerceptionManager()
        # Should auto-select or raise if nothing available
        try:
            backend = mgr.get_backend()
            assert backend is not None
            assert backend.name in ("paddleocr", "easyocr", "tesseract", "llm_vision")
        except RuntimeError:
            pass  # No backend installed — acceptable

    def test_backend_not_available(self) -> None:
        from autocomputer.perception import PerceptionManager

        mgr = PerceptionManager()
        try:
            mgr.get_backend("nonexistent_backend_xyz")
            assert False, "Should have raised"
        except ValueError:
            pass


class TestEasyOCRBackend:
    def test_is_available(self) -> None:
        from autocomputer.perception import EasyOCRBackend

        b = EasyOCRBackend()
        avail = b.is_available()
        assert isinstance(avail, bool)


class TestTextRegionSearch:
    def test_find_by_text(self) -> None:
        from autocomputer.perception import TextRegion

        regions = [
            TextRegion("Login", 100, 200, 80, 40, 0.95),
            TextRegion("Sign Up", 300, 200, 100, 40, 0.90),
            TextRegion("Cancel", 500, 200, 80, 40, 0.85),
        ]

        # Find exact match
        matches = [r for r in regions if r.text.lower() == "login"]
        assert len(matches) == 1
        assert matches[0].center == (140, 220)

        # Find by substring
        matches = [r for r in regions if "sign" in r.text.lower()]
        assert len(matches) == 1

        # Find by confidence threshold
        high_conf = [r for r in regions if r.confidence >= 0.90]
        assert len(high_conf) == 2
