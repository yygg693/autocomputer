#!/usr/bin/env python3
"""Windows built-in OCR (Windows.Media.Ocr via PowerShell) — zero extra downloads.

Usage:
  python ocr.py read <image_path> [--region x,y,w,h] [--lines]
      OCR an image; print JSON: {"status":"ok","lang":..., "results":[{text,confidence,box,center}], "text": "..."}
"""
import sys, io, os, json, subprocess, argparse
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_PS = Path(__file__).parent / "ocr.ps1"


def ocr_image(image_path: str, region: str = None, timeout: float = 120.0) -> dict:
    """Run OCR on an image (optionally cropped to region). Returns normalized dict."""
    target = image_path
    tmp_crop = None
    if region:
        try:
            from PIL import Image
            x, y, w, h = map(int, region.split(","))
            im = Image.open(image_path).crop((x, y, x + w, y + h))
            tmp_crop = str(Path(image_path).with_name("_ocr_crop.png"))
            im.save(tmp_crop)
            target = tmp_crop
        except Exception:
            pass
    try:
        p = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-File", str(_PS), "-Path", os.path.abspath(target)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    finally:
        if tmp_crop and os.path.exists(tmp_crop):
            try: os.remove(tmp_crop)
            except Exception: pass

    raw = (p.stdout or "").strip()
    data = None
    for line in raw.splitlines():
        try:
            data = json.loads(line)
            break
        except Exception:
            continue
    if not data:
        return {"status": "error", "message": (p.stderr or raw)[:300], "rc": p.returncode}

    words = data.get("words", [])
    results = []
    for wd in words:
        x, y, w, h = wd.get("x", 0), wd.get("y", 0), wd.get("w", 0), wd.get("h", 0)
        results.append({
            "text": wd.get("text", ""),
            "confidence": 1.0,
            "box": {"left": x, "top": y, "width": w, "height": h},
            "center": {"x": x + w // 2, "y": y + h // 2},
        })
    return {"status": "ok", "lang": data.get("lang"), "results": results, "text": data.get("text", "")}


def ocr_lines(image_path: str, region: str = None) -> list:
    """Group OCR words into reading lines (left-to-right). Returns [{text, box, center}]."""
    data = ocr_image(image_path, region)
    if data.get("status") != "ok":
        return []
    words = sorted(data["results"], key=lambda r: (r["box"]["top"] // 20, r["box"]["left"]))
    lines = []
    for wd in words:
        b = wd["box"]
        placed = False
        for ln in lines:
            lb = ln["box"]
            if abs(b["top"] - lb["top"]) < max(12, b["height"] * 0.5) and abs(b["left"] - lb["left"]) < 1200:
                ln["text"] += (" " if b["left"] > lb["left"] + lb["width"] - 4 else "") + wd["text"]
                ln["box"] = {"left": min(lb["left"], b["left"]), "top": min(lb["top"], b["top"]),
                             "width": max(lb["left"] + lb["width"], b["left"] + b["width"]) - min(lb["left"], b["left"]),
                             "height": max(lb["top"] + lb["height"], b["top"] + b["height"]) - min(lb["top"], b["top"])}
                placed = True
                break
        if not placed:
            lines.append({"text": wd["text"], "box": dict(b), "center": dict(wd["center"])})
    for ln in lines:
        ln["center"] = {"x": ln["box"]["left"] + ln["box"]["width"] // 2,
                        "y": ln["box"]["top"] + ln["box"]["height"] // 2}
    return lines


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Windows built-in OCR")
    ap.add_argument("cmd", choices=["read"])
    ap.add_argument("image")
    ap.add_argument("--region", help="x,y,w,h")
    ap.add_argument("--lines", action="store_true", help="group into lines")
    args = ap.parse_args()
    if args.cmd == "read":
        if args.lines:
            out = {"status": "ok", "lines": ocr_lines(args.image, args.region)}
        else:
            out = ocr_image(args.image, args.region)
        print(json.dumps(out, ensure_ascii=False))
