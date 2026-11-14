"""Drive the actual Tk app and capture only its own window on Windows.

Run: py -X utf8 verify_local_gui.py
Writes inspection screenshots/reports under verification/gui/. No desktop-wide
capture, no browser substitute, no third-party screenshot dependency.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import struct
import time
from unittest.mock import patch
import zlib

import numpy as np
import calc_rating_gui as gui


def save_window_png(app, path):
    if not hasattr(ctypes, "windll"):
        raise RuntimeError("Native-window capture requires Windows.")
    user, gdi = ctypes.windll.user32, ctypes.windll.gdi32
    user.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user.GetAncestor.restype = wintypes.HWND
    user.GetWindowDC.argtypes = [wintypes.HWND]
    user.GetWindowDC.restype = wintypes.HDC
    user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
    user.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi.CreateCompatibleDC.restype = wintypes.HDC
    gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
    gdi.SelectObject.restype = wintypes.HANDLE
    gdi.DeleteObject.argtypes = [wintypes.HANDLE]
    gdi.DeleteDC.argtypes = [wintypes.HDC]

    class Header(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("width", wintypes.LONG), ("height", wintypes.LONG),
                    ("planes", wintypes.WORD), ("bit_count", wintypes.WORD), ("compression", wintypes.DWORD),
                    ("size_image", wintypes.DWORD), ("xppm", wintypes.LONG), ("yppm", wintypes.LONG),
                    ("colors", wintypes.DWORD), ("important", wintypes.DWORD)]
    gdi.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.POINTER(Header), wintypes.UINT,
                                    ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
    gdi.CreateDIBSection.restype = wintypes.HANDLE
    app.update()
    hwnd = user.GetAncestor(app.winfo_id(), 2)
    # Force a complete repaint before WM_PRINT; otherwise native themed
    # controls can leave stale text after overview panels change height.
    user.RedrawWindow.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.HANDLE, wintypes.UINT]
    user.RedrawWindow(hwnd, None, None, 0x185)
    app.update()
    rect = wintypes.RECT()
    if not user.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise RuntimeError("Cannot read this Tk window's bounds.")
    width, height = rect.right - rect.left, rect.bottom - rect.top
    source_dc = user.GetWindowDC(hwnd)
    memory_dc = gdi.CreateCompatibleDC(source_dc)
    header = Header(ctypes.sizeof(Header), width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
    bits = ctypes.c_void_p()
    bitmap = gdi.CreateDIBSection(source_dc, ctypes.byref(header), 0, ctypes.byref(bits), None, 0)
    old = gdi.SelectObject(memory_dc, bitmap)
    try:
        if not user.PrintWindow(hwnd, memory_dc, 2):
            raise RuntimeError("PrintWindow failed; not falling back to a desktop screenshot.")
        data = ctypes.string_at(bits, width * height * 4)
        rgb = np.frombuffer(data, np.uint8).reshape(height, width, 4)[:, :, [2, 1, 0]].copy()
        if float(np.std(rgb)) < 5:
            raise RuntimeError("Captured window looks blank.")
        raw = b"".join(b"\x00" + row.tobytes() for row in rgb)
        def chunk(kind, value):
            return struct.pack(">I", len(value)) + kind + value + struct.pack(">I", zlib.crc32(kind + value) & 0xffffffff)
        png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
               + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(png)
    finally:
        gdi.SelectObject(memory_dc, old)
        gdi.DeleteObject(bitmap)
        gdi.DeleteDC(memory_dc)
        user.ReleaseDC(hwnd, source_dc)


def read_unicode_clipboard(app):
    """Tk 8.6's STRING readback can corrupt multibyte text at buffer boundaries.
    Verify what other Windows apps actually paste: CF_UNICODETEXT.
    """
    app.update_idletasks()
    user, kernel = ctypes.windll.user32, ctypes.windll.kernel32
    user.GetClipboardData.argtypes = [wintypes.UINT]
    user.GetClipboardData.restype = wintypes.HANDLE
    kernel.GlobalLock.argtypes = [wintypes.HANDLE]
    kernel.GlobalLock.restype = ctypes.c_void_p
    kernel.GlobalUnlock.argtypes = [wintypes.HANDLE]
    if not user.OpenClipboard(None):
        raise RuntimeError("Cannot open Unicode clipboard for verification.")
    try:
        handle = user.GetClipboardData(13)
        if not handle:
            raise RuntimeError("Unicode clipboard is empty.")
        pointer = kernel.GlobalLock(handle)
        if not pointer:
            raise RuntimeError("Cannot lock Unicode clipboard data.")
        try:
            return ctypes.wstring_at(pointer).replace("\r\n", "\n")
        finally:
            kernel.GlobalUnlock(handle)
    finally:
        user.CloseClipboard()


def run(output, bootstrap):
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    app = gui.MatchedRatingApp()
    app.geometry("1180x840+30+30")
    state = {"errors": [], "result": None}
    started = time.monotonic()
    output.mkdir(parents=True, exist_ok=True)

    def callback_error(kind, value, traceback):
        import traceback as traceback_module
        detail = "".join(traceback_module.format_exception(kind, value, traceback))
        state["errors"].append(detail)
        app._on_close()
    app.report_callback_exception = callback_error

    def begin():
        app.qs6_var.set("15")
        app.qs7_var.set("7.5")
        app.bootstrap_var.set(str(bootstrap))
        app.calculate_button.invoke()
        app.after(100, finished)

    def finished():
        if time.monotonic() - started > 240:
            state["errors"].append("GUI calculation timed out")
            app._on_close()
            return
        if app._worker is not None:
            app.after(100, finished)
            return
        if app._report is None:
            state["errors"].append("No report after clicking the calculation button")
            app._on_close()
            return
        state["result"] = app._report
        assert len(app.notebook.tabs()) == 6, "six report tabs must be present"
        assert "截断校正候选" in app._full_report_text, "candidate section missing"
        app.copy_button.invoke()
        assert read_unicode_clipboard(app) == app._full_report_text, "Unicode clipboard contents differ"
        with patch.object(gui.filedialog, "asksaveasfilename", return_value=str(output / "exported_report.json")):
            app.export_button.invoke()
        saved = json.loads((output / "exported_report.json").read_text(encoding="utf-8"))
        assert saved["year"] == 2025
        assert saved["levels"]["6"]["baseline"] is not None
        app.notebook.select(0)
        app.update_idletasks()
        save_window_png(app, output / "overview.png")
        app.notebook.select(5)
        app.chart_level_var.set("6级")
        app.chart_mode_var.set("边界成绩配对")
        app.update_idletasks(); app._draw_chart(); app.update_idletasks()
        save_window_png(app, output / "boundary.png")
        app.chart_mode_var.set("缺失比例假设情景")
        app._draw_chart(); app.update_idletasks()
        save_window_png(app, output / "missing_scenarios.png")
        if app._hover_points:
            x, y, _ = app._hover_points[0]
            app.canvas.event_generate("<Motion>", x=int(x), y=int(y))
            app.update_idletasks()
            assert app.canvas.find_withtag("hover")
        app.reset_button.invoke()
        assert app._report is None and app.qs6_var.get() == "20"
        app._on_close()

    with patch.object(gui.messagebox, "showerror", side_effect=lambda *a, **kw: state["errors"].append(str(a))):
        app.after(80, begin)
        app.mainloop()
    if state["errors"] or state["result"] is None:
        raise RuntimeError(str(state["errors"]))
    report = state["result"]
    print(json.dumps({"gui": "PASS", "seconds": round(time.monotonic() - started, 1),
                      "actions": ["calculate", "tabs", "copy", "export", "hover", "reset"],
                      "methods": {k: v.selected_method for k, v in report.levels.items()},
                      "screenshots": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent / "verification" / "gui")
    parser.add_argument("--bootstrap", type=int, default=0)
    options = parser.parse_args()
    run(options.output_dir, options.bootstrap)
