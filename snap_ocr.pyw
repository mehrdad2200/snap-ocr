# -*- coding: utf-8 -*-
"""
Snap OCR  —  تبدیل هر بخش از صفحه به متن (تشخیص خودکار زبان)
================================================================
• همیشه در سینی ویندوز (کنار ساعت) فعال می‌ماند
• میانبر سراسری قابل تنظیم (کلیک راست روی آیکون -> تنظیمات)
• حالت پنجره: نمایش متن + انتخاب زبان   |   حالت سریع: فقط کپی در کلیپ‌بورد
• تشخیص خودکار زبان / خط (فارسی، عربی، لاتین، سیریلیک، چینی، ژاپنی، کره‌ای، ...)
  هر زبانی که Tesseract برایش traineddata داشته باشد پشتیبانی می‌شود.

نیازمندی:  pip install PyQt6 pillow   +   Tesseract-OCR   (pytesseract لازم نیست)
ساخت exe :  build_exe.bat
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

os.environ.setdefault("OMP_THREAD_LIMIT", "1")   # برای اجرای موازی سریع‌تر

from PyQt6.QtCore import (QAbstractNativeEventFilter, QBuffer, QIODevice, QRect,
                          QRectF, Qt, QThread, QTimer, pyqtSignal)
from PyQt6.QtGui import (QAction, QBrush, QColor, QFont, QGuiApplication, QIcon,
                         QKeySequence, QLinearGradient, QPainter, QPen, QPixmap,
                         QTextOption)
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import (QApplication, QCheckBox, QDialog, QFrame,
                             QGraphicsDropShadowEffect, QGridLayout, QHBoxLayout,
                             QKeySequenceEdit, QLabel, QMenu, QMessageBox,
                             QPushButton, QSystemTrayIcon, QTextEdit, QVBoxLayout,
                             QWidget)

APP_NAME = "SnapOCR"
SERVER_NAME = "SnapOCR_single_instance"
ACCENT = "#7C5CFF"
IS_WIN = sys.platform.startswith("win")
CFG_PATH = Path.home() / ".snap_ocr.json"

DEFAULT_CFG = {
    "auto": True,                 # تشخیص خودکار زبان
    "langs": ["fa", "ar", "en"],  # حالت دستی
    "hk_window": "Ctrl+Alt+O",    # میانبر: انتخاب + نمایش پنجره
    "hk_quick": "Ctrl+Alt+Q",     # میانبر: انتخاب + فقط کپی
    "autocopy": True,
}

# چیپ‌های حالت دستی: کد, نام نمایشی, کد Tesseract
LANGS = [
    ("fa", "فارسی", "fas"), ("ar", "العربية", "ara"), ("en", "English", "eng"),
    ("tr", "Türkçe", "tur"), ("ru", "Русский", "rus"), ("fr", "Français", "fra"),
    ("de", "Deutsch", "deu"), ("zh", "中文", "chi_sim"), ("ja", "日本語", "jpn"),
    ("ko", "한국어", "kor"),
]
TESS = {c: t for c, _, t in LANGS}

NAMES = {
    "fas": "فارسی", "ara": "عربی", "eng": "English", "tur": "ترکی", "fra": "فرانسوی",
    "deu": "آلمانی", "spa": "اسپانیایی", "ita": "ایتالیایی", "por": "پرتغالی",
    "nld": "هلندی", "pol": "لهستانی", "swe": "سوئدی", "ces": "چکی", "ron": "رومانیایی",
    "vie": "ویتنامی", "ind": "اندونزیایی", "rus": "روسی", "ukr": "اوکراینی",
    "bul": "بلغاری", "chi_sim": "چینی", "chi_tra": "چینی سنتی", "jpn": "ژاپنی",
    "kor": "کره‌ای", "ell": "یونانی", "heb": "عبری", "hin": "هندی", "tha": "تایلندی",
}

# گروه‌های خط برای تشخیص خودکار (هر گروه با زبان‌های نصب‌شده‌اش امتحان می‌شود)
SCRIPT_GROUPS = [
    ("arabic", ["fas", "ara"]),
    ("latin", ["eng"]),
    ("cyrillic", ["rus", "ukr", "bul"]),
    ("han-s", ["chi_sim"]), ("han-t", ["chi_tra"]),
    ("jpn", ["jpn"]), ("kor", ["kor"]),
    ("greek", ["ell"]), ("hebrew", ["heb"]), ("hindi", ["hin"]), ("thai", ["tha"]),
]
LATIN_EXTRA = ["tur", "fra", "deu", "spa", "ita", "por", "nld", "pol",
               "swe", "ces", "ron", "vie", "ind"]


def load_cfg():
    cfg = dict(DEFAULT_CFG)
    try:
        cfg.update(json.loads(CFG_PATH.read_text(encoding="utf-8")))
    except Exception:
        pass
    return cfg


def save_cfg(cfg):
    try:
        CFG_PATH.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def app_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


# ───────────────────────── OCR ─────────────────────────
def preprocess(img):
    from PIL import Image, ImageOps, ImageStat
    img = img.convert("L")
    w, h = img.size
    k = 3 if h < 50 else 2 if h < 200 else 1
    if k > 1:
        img = img.resize((w * k, h * k), Image.LANCZOS)
    if ImageStat.Stat(img).mean[0] < 115:          # پس‌زمینه تیره -> معکوس
        img = ImageOps.invert(img)
    img = ImageOps.autocontrast(img)
    return ImageOps.expand(img, border=12, fill=255)


def find_tesseract():
    exe = "tesseract.exe" if IS_WIN else "tesseract"
    for sub in ("tesseract", "Tesseract-OCR"):             # نسخه همراه برنامه
        p = app_dir() / sub / exe
        if p.exists():
            return str(p)
    cands = [shutil.which("tesseract"),
             r"C:\Program Files\Tesseract-OCR\tesseract.exe",
             r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
             os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe")]
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


_tess = {"have": None}
_NOWIN = 0x08000000 if IS_WIN else 0                     # CREATE_NO_WINDOW


def _env(exe):
    env = os.environ.copy()
    td = Path(exe).parent / "tessdata"
    try:
        if td.is_dir() and Path(exe).resolve().is_relative_to(app_dir().resolve()):
            env["TESSDATA_PREFIX"] = str(td)             # نسخه همراه
    except Exception:
        pass
    return env


def get_have(exe):
    if _tess["have"] is None:
        r = subprocess.run([exe, "--list-langs"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30,
                           creationflags=_NOWIN, env=_env(exe))
        have = set()
        for line in (r.stdout + "\n" + r.stderr).splitlines():
            line = line.strip()
            if re.fullmatch(r"[A-Za-z][A-Za-z_]*", line) and line not in ("osd", "equ"):
                have.add(line)
        _tess["have"] = have
    return _tess["have"]


def warm_up():
    try:
        exe = find_tesseract()
        if exe:
            get_have(exe)
    except Exception:
        pass


def tess_run(exe, img, lang, psm=6):
    """یک بار اجرای Tesseract؛ هم متن و هم میزان اطمینان را برمی‌گرداند"""
    with tempfile.TemporaryDirectory() as d:
        ip, base = os.path.join(d, "i.png"), os.path.join(d, "o")
        img.save(ip)
        cmd = [exe, ip, base, "-l", lang, "--oem", "1", "--psm", str(psm), "txt", "tsv"]
        r = subprocess.run(cmd, capture_output=True, creationflags=_NOWIN,
                           env=_env(exe), timeout=90)
        if not os.path.exists(base + ".txt"):
            err = r.stderr.decode("utf-8", "replace").strip()
            raise RuntimeError("خطای Tesseract:\n" + err[:300])
        text = open(base + ".txt", encoding="utf-8", errors="replace").read().strip()
        tot = n = 0
        try:
            lines = open(base + ".tsv", encoding="utf-8", errors="replace").read().splitlines()
        except OSError:
            lines = []
        for line in lines[1:]:
            p = line.split("\t")
            if len(p) < 12:
                continue
            try:
                c = float(p[10])
            except ValueError:
                continue
            t = p[11].strip()
            if t and c >= 0:
                tot += c * len(t)
                n += len(t)
        return text, (tot / n if n else 0.0)


def langs_label(codes):
    return "، ".join(NAMES.get(c, c) for c in codes)


def auto_ocr(exe, img, have):
    # مسیر سریع: یک بار اجرا با فارسی+عربی+انگلیسی؛ اگر مطمئن بود همان‌جا تمام می‌شود
    primary = [l for l in ("fas", "ara", "eng") if l in have]
    results = []
    if primary:
        text, conf = tess_run(exe, img, "+".join(primary))
        if not text.strip():
            return "", "متنی پیدا نشد"
        if conf >= 60:
            return text, "🌐 " + langs_label(primary)
        results.append((conf, text, primary))

    # مسیر کند (فقط وقتی اطمینان کم بود): بقیه‌ی خط‌ها و زبان‌ها به‌صورت موازی
    cands = []
    for name, langs in SCRIPT_GROUPS:
        if primary and name in ("arabic", "latin"):
            continue
        use = [l for l in langs if l in have]
        if use:
            cands.append(use)
    for l in [x for x in LATIN_EXTRA if x in have][:6]:
        cands.append([l, "eng"] if "eng" in have else [l])
    for i, use in enumerate(cands):
        if "eng" in have and "eng" not in use:
            cands[i] = use + ["eng"]

    def job(use):
        try:
            t, c = tess_run(exe, img, "+".join(use))
            return c, t, use
        except Exception:
            return 0.0, "", use

    if cands:
        with ThreadPoolExecutor(max_workers=4) as ex:
            results += list(ex.map(job, cands))
    if not results:
        raise RuntimeError("هیچ بسته‌ی زبانی در Tesseract نصب نیست.")
    conf, text, use = max(results, key=lambda r: r[0])
    if conf < 12 or not text.strip():
        return "", "متنی پیدا نشد"
    return text, "🌐 " + langs_label(use)


def manual_ocr(exe, img, have, codes):
    use = [TESS[c] for c in codes if TESS[c] in have]
    missing = [TESS[c] for c in codes if TESS[c] not in have]
    if not use:
        raise RuntimeError("بسته‌ی زبان انتخاب‌شده نصب نیست (traineddata را در tessdata بگذار).")
    text, _ = tess_run(exe, img, "+".join(use))
    return text, (("نصب‌نشده: " + langs_label(missing)) if missing else "")


def run_ocr(data, opts):
    t0 = time.time()
    from PIL import Image
    exe = find_tesseract()
    if not exe:
        raise RuntimeError("Tesseract پیدا نشد.\nآن را نصب کن، یا پوشه‌ی Tesseract-OCR را "
                           "کنار برنامه بگذار (نام پوشه: tesseract).")
    have = get_have(exe)
    img = preprocess(Image.open(io.BytesIO(data)))
    if opts["auto"]:
        text, note = auto_ocr(exe, img, have)
    else:
        text, note = manual_ocr(exe, img, have, opts["langs"])
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.strip(), f"{note}   ⏱ {time.time() - t0:.1f}s".strip()


class Worker(QThread):
    done = pyqtSignal(int, str, str)
    failed = pyqtSignal(int, str)

    def __init__(self, job, data, opts):
        super().__init__()
        self.job, self.data, self.opts = job, data, opts

    def run(self):
        try:
            text, note = run_ocr(self.data, self.opts)
            self.done.emit(self.job, text, note)
        except Exception as e:
            self.failed.emit(self.job, str(e))


# ───────────────────────── میانبر سراسری (ویندوز) ─────────────────────────
MOD_MAP = [(Qt.KeyboardModifier.ControlModifier, 0x0002), (Qt.KeyboardModifier.ShiftModifier, 0x0004),
           (Qt.KeyboardModifier.AltModifier, 0x0001), (Qt.KeyboardModifier.MetaModifier, 0x0008)]
SPECIAL_VK = {
    Qt.Key.Key_Space: 0x20, Qt.Key.Key_Print: 0x2C, Qt.Key.Key_Insert: 0x2D,
    Qt.Key.Key_Delete: 0x2E, Qt.Key.Key_Home: 0x24, Qt.Key.Key_End: 0x23,
    Qt.Key.Key_PageUp: 0x21, Qt.Key.Key_PageDown: 0x22, Qt.Key.Key_Tab: 0x09,
    Qt.Key.Key_Return: 0x0D, Qt.Key.Key_Backspace: 0x08, Qt.Key.Key_Left: 0x25,
    Qt.Key.Key_Up: 0x26, Qt.Key.Key_Right: 0x27, Qt.Key.Key_Down: 0x28,
    Qt.Key.Key_QuoteLeft: 0xC0, Qt.Key.Key_Minus: 0xBD, Qt.Key.Key_Equal: 0xBB,
    Qt.Key.Key_Comma: 0xBC, Qt.Key.Key_Period: 0xBE, Qt.Key.Key_Slash: 0xBF,
    Qt.Key.Key_Semicolon: 0xBA, Qt.Key.Key_BracketLeft: 0xDB,
    Qt.Key.Key_BracketRight: 0xDD, Qt.Key.Key_Backslash: 0xDC,
    Qt.Key.Key_Apostrophe: 0xDE, Qt.Key.Key_Pause: 0x13, Qt.Key.Key_ScrollLock: 0x91,
}
NO_MOD_OK = {Qt.Key.Key_Print, Qt.Key.Key_Pause, Qt.Key.Key_ScrollLock}


def _val(k):
    return k.value if hasattr(k, "value") else int(k)


def parse_hotkey(spec):
    """'Ctrl+Alt+O' -> (modifiers, vk) یا None اگر نامعتبر باشد"""
    ks = QKeySequence(spec)
    if ks.isEmpty():
        return None
    comb = ks[0]
    key, mods = comb.key(), comb.keyboardModifiers()
    m = 0
    for qm, v in MOD_MAP:
        if mods & qm:
            m |= v
    k = _val(key)
    f1, f24 = _val(Qt.Key.Key_F1), _val(Qt.Key.Key_F24)
    is_f = f1 <= k <= f24
    if 0x41 <= k <= 0x5A or 0x30 <= k <= 0x39:
        vk = k
    elif is_f:
        vk = 0x70 + (k - f1)
    elif key in SPECIAL_VK:
        vk = SPECIAL_VK[key]
    else:
        return None
    if m == 0 and not (is_f or key in NO_MOD_OK):
        return None
    return m, vk


class HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, cb):
        super().__init__()
        self.cb = cb

    def nativeEventFilter(self, event_type, message):
        if IS_WIN and bytes(event_type) == b"windows_generic_MSG":
            from ctypes import wintypes
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312:                       # WM_HOTKEY
                hid = int(msg.wParam)
                QTimer.singleShot(0, lambda: self.cb(hid))
        return False, 0


# ───────────────────────── اجرای خودکار با ویندوز ─────────────────────────
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def is_autostart():
    if not IS_WIN:
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except OSError:
        return False


def set_autostart(enable):
    if not IS_WIN:
        return
    import winreg
    if getattr(sys, "frozen", False):
        cmd = f'"{sys.executable}" --background'
    else:
        py = Path(sys.executable).with_name("pythonw.exe")
        cmd = f'"{py}" "{Path(__file__).resolve()}" --background'
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                        winreg.KEY_SET_VALUE | winreg.KEY_READ) as k:
        if enable:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except FileNotFoundError:
                pass


# ───────────────────────── آیکون ─────────────────────────
def make_icon_pixmap(size=256):
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 128, size / 128)
    g = QLinearGradient(0, 0, 128, 128)
    g.setColorAt(0, QColor("#9277FF"))
    g.setColorAt(1, QColor("#5636E8"))
    p.setBrush(QBrush(g))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(QRectF(6, 6, 116, 116), 30, 30)
    pen = QPen(QColor("white"), 9)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    a, b, L = 34, 94, 20
    for x, y, dx, dy in ((a, a, 1, 1), (b, a, -1, 1), (a, b, 1, -1), (b, b, -1, -1)):
        p.drawLine(x, y, x + dx * L, y)
        p.drawLine(x, y, x, y + dy * L)
    pen2 = QPen(QColor(255, 255, 255, 230), 7)
    pen2.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen2)
    p.drawLine(48, 64, 80, 64)
    p.end()
    return pm


# ───────────────────────── انتخاب ناحیه ─────────────────────────
class Overlay(QWidget):
    selected = pyqtSignal(QPixmap)
    cancelled = pyqtSignal()

    def __init__(self, screen, pix):
        super().__init__()
        self.pix = pix
        self.p0 = self.p1 = None
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint |
                            Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self.setScreen(screen)
        self.setGeometry(screen.geometry())

    def sel(self):
        return QRect(self.p0, self.p1).normalized() if self.p0 and self.p1 else None

    def _src(self, r):
        d = self.pix.devicePixelRatio()
        return QRect(int(r.x() * d), int(r.y() * d), int(r.width() * d), int(r.height() * d))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.drawPixmap(self.rect(), self.pix)
        p.fillRect(self.rect(), QColor(8, 8, 14, 150))
        r = self.sel()
        if r and r.width() > 1 and r.height() > 1:
            p.drawPixmap(r, self.pix, self._src(r))
            p.setPen(QPen(QColor(ACCENT), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(r)
            label = f"{r.width()} × {r.height()}"
            p.setFont(QFont("Segoe UI", 9))
            lw = p.fontMetrics().horizontalAdvance(label) + 16
            ly = r.bottom() + 8 if r.bottom() + 34 < self.height() else r.top() - 30
            tag = QRect(r.left(), ly, lw, 24)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(ACCENT))
            p.drawRoundedRect(tag, 8, 8)
            p.setPen(QColor("white"))
            p.drawText(tag, Qt.AlignmentFlag.AlignCenter, label)
        else:
            text = "ناحیه‌ی مورد نظر را بکش   ·   Esc / کلیک راست = لغو"
            f = QFont(); f.setFamilies(["Vazirmatn", "Segoe UI", "Tahoma"]); f.setPointSize(11)
            p.setFont(f)
            w = p.fontMetrics().horizontalAdvance(text) + 44
            pill = QRect((self.width() - w) // 2, 40, w, 42)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(20, 20, 28, 230))
            p.drawRoundedRect(pill, 21, 21)
            p.setPen(QColor("#E8E6FF"))
            p.drawText(pill, Qt.AlignmentFlag.AlignCenter, text)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.RightButton:
            self.cancelled.emit()
            return
        self.p0 = self.p1 = e.position().toPoint()
        self.update()

    def mouseMoveEvent(self, e):
        if self.p0:
            self.p1 = e.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, e):
        r = self.sel()
        if r and r.width() > 8 and r.height() > 8:
            self.selected.emit(self.pix.copy(self._src(r)))
        else:
            self.p0 = self.p1 = None
            self.update()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()


# ───────────────────────── استایل ─────────────────────────
STYLE = f"""
#card {{ background:#13131A; border:1px solid #262634; border-radius:20px; }}
QDialog {{ background:#13131A; }}
QLabel {{ color:#cfd0dc; background:transparent; }}
QCheckBox {{ color:#cfd0dc; spacing:8px; }}
#title {{ font-size:15px; font-weight:700; color:#ffffff; }}
#sub {{ color:#7d7e92; font-size:12px; }}
#status {{ color:#8e8fa6; font-size:12px; }}
QPushButton {{ font-family:"Vazirmatn","Segoe UI","Tahoma"; }}
#x {{ background:transparent; color:#7d7e92; border:none; font-size:15px; padding:4px 8px; border-radius:8px; }}
#x:hover {{ background:#2a1d28; color:#ff6b81; }}
QPushButton[chip="true"] {{ background:#1c1c27; color:#9a9bb0; border:1px solid #2a2a3a;
    border-radius:13px; padding:5px 12px; font-size:12px; }}
QPushButton[chip="true"]:hover {{ border:1px solid #4a4a66; }}
QPushButton[chip="true"]:checked {{ background:#2b2358; color:#e0daff; border:1px solid {ACCENT}; }}
#primary {{ background:{ACCENT}; color:white; border:none; border-radius:12px; padding:9px 20px; font-weight:600; }}
#primary:hover {{ background:#8d72ff; }}
#ghost {{ background:#1c1c27; color:#dcdcea; border:1px solid #2a2a3a; border-radius:12px; padding:9px 20px; }}
#ghost:hover {{ border:1px solid {ACCENT}; }}
QTextEdit, QKeySequenceEdit QLineEdit {{ background:#0e0e14; color:#f1f1f7; border:1px solid #232331;
    border-radius:12px; padding:8px; selection-background-color:{ACCENT}; }}
QTextEdit {{ font-size:15px; padding:10px; border-radius:14px; }}
QScrollBar:vertical {{ background:transparent; width:8px; margin:4px; }}
QScrollBar::handle:vertical {{ background:#2c2c3d; border-radius:4px; min-height:30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
"""


def is_rtl(text):
    rtl = sum(1 for ch in text if "\u0590" <= ch <= "\u08FF" or "\uFB50" <= ch <= "\uFEFF")
    ltr = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    return rtl > 0 and rtl >= ltr


# ───────────────────────── پنجره نتیجه ─────────────────────────
class ResultWindow(QWidget):
    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.has_content = False
        self._drag = None
        self.setWindowTitle("Snap OCR")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setStyleSheet(STYLE)
        self.resize(600, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        card = QFrame(); card.setObjectName("card")
        sh = QGraphicsDropShadowEffect(blurRadius=40, xOffset=0, yOffset=8)
        sh.setColor(QColor(0, 0, 0, 170))
        card.setGraphicsEffect(sh)
        root.addWidget(card)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(22, 16, 22, 18)
        lay.setSpacing(12)

        head = QHBoxLayout()
        t = QLabel("Snap OCR"); t.setObjectName("title")
        s = QLabel("تشخیص متن از تصویر"); s.setObjectName("sub")
        x = QPushButton("✕"); x.setObjectName("x")
        x.setCursor(Qt.CursorShape.PointingHandCursor)
        x.clicked.connect(self.hide)
        head.addWidget(t); head.addSpacing(8); head.addWidget(s)
        head.addStretch(); head.addWidget(x)
        lay.addLayout(head)

        cfg = ctl.cfg
        grid = QGridLayout(); grid.setSpacing(8)
        self.chip_auto = self._chip("🌐 خودکار", cfg["auto"])
        grid.addWidget(self.chip_auto, 0, 0)
        self.chips = {}
        for i, (code, name, _) in enumerate(LANGS):
            b = self._chip(name, (not cfg["auto"]) and code in cfg["langs"])
            self.chips[code] = b
            grid.addWidget(b, (i + 1) // 6, (i + 1) % 6)
        lay.addLayout(grid)

        self.edit = QTextEdit()
        self.edit.setPlaceholderText("متن اینجا نمایش داده می‌شود…")
        lay.addWidget(self.edit, 1)

        foot = QHBoxLayout()
        self.status = QLabel(""); self.status.setObjectName("status")
        self.btn_new = QPushButton("✂  انتخاب مجدد"); self.btn_new.setObjectName("primary")
        self.btn_copy = QPushButton("کپی"); self.btn_copy.setObjectName("ghost")
        for b in (self.btn_new, self.btn_copy):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_new.clicked.connect(lambda: self.ctl.start_capture("window"))
        self.btn_copy.clicked.connect(self.copy)
        foot.addWidget(self.btn_new); foot.addWidget(self.btn_copy)
        foot.addStretch(); foot.addWidget(self.status)
        lay.addLayout(foot)

        g = QGuiApplication.primaryScreen().availableGeometry()
        self.move(g.center().x() - self.width() // 2, g.center().y() - self.height() // 2)

    def _chip(self, text, checked):
        b = QPushButton(text)
        b.setProperty("chip", True)
        b.setCheckable(True)
        b.setChecked(checked)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(self.on_lang)
        return b

    def on_lang(self):
        if self.sender() is self.chip_auto:
            self.chip_auto.setChecked(True)
            for b in self.chips.values():
                b.setChecked(False)
        else:
            self.chip_auto.setChecked(False)
            if not any(b.isChecked() for b in self.chips.values()):
                self.chip_auto.setChecked(True)
        cfg = self.ctl.cfg
        cfg["auto"] = self.chip_auto.isChecked()
        cfg["langs"] = [c for c, b in self.chips.items() if b.isChecked()] or ["en"]
        save_cfg(cfg)
        self.ctl.rerun()

    def show_loading(self):
        self.edit.clear()
        self.status.setText("⏳ در حال خواندن…")
        self.popup()

    def popup(self):
        self.show(); self.raise_(); self.activateWindow()

    def show_text(self, text, note, copied):
        self.has_content = True
        opt = QTextOption()
        opt.setTextDirection(Qt.LayoutDirection.RightToLeft if is_rtl(text)
                             else Qt.LayoutDirection.LeftToRight)
        self.edit.document().setDefaultTextOption(opt)
        self.edit.setPlainText(text)
        if text:
            self.status.setText(("✓ کپی شد   " if copied else "") + note)
        else:
            self.status.setText("متنی پیدا نشد   " + note)

    def show_error(self, msg):
        self.has_content = True
        self.edit.setPlainText(msg)
        self.status.setText("خطا")

    def copy(self):
        QGuiApplication.clipboard().setText(self.edit.toPlainText())
        self.status.setText("✓ کپی شد")

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and e.position().y() < 70:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, _):
        self._drag = None

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.hide()


# ───────────────────────── تنظیمات ─────────────────────────
class SettingsDialog(QDialog):
    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.setWindowTitle("تنظیمات Snap OCR")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setStyleSheet(STYLE)
        self.setMinimumWidth(440)
        cfg = ctl.cfg
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(10)

        t = QLabel("تنظیمات"); t.setObjectName("title")
        v.addWidget(t)
        hint = QLabel("روی کادر کلیک کن و ترکیب کلید دلخواهت را بزن (مثلاً Ctrl+Alt+O یا F8).\n"
                      "برای غیرفعال کردن یک میانبر، کادرش را خالی بگذار (Backspace).")
        hint.setObjectName("sub"); hint.setWordWrap(True)
        v.addWidget(hint)

        v.addWidget(QLabel("میانبر انتخاب + نمایش پنجره:"))
        self.k1 = QKeySequenceEdit(QKeySequence(cfg["hk_window"]))
        v.addWidget(self.k1)
        v.addWidget(QLabel("میانبر حالت سریع (فقط کپی در کلیپ‌بورد):"))
        self.k2 = QKeySequenceEdit(QKeySequence(cfg["hk_quick"]))
        v.addWidget(self.k2)
        for k in (self.k1, self.k2):
            k.setMaximumSequenceLength(1)

        self.c_auto = QCheckBox("اجرا همراه روشن شدن ویندوز")
        self.c_auto.setChecked(is_autostart())
        self.c_copy = QCheckBox("کپی خودکار متن در کلیپ‌بورد")
        self.c_copy.setChecked(cfg["autocopy"])
        v.addSpacing(6); v.addWidget(self.c_auto); v.addWidget(self.c_copy)

        row = QHBoxLayout()
        ok = QPushButton("ذخیره"); ok.setObjectName("primary")
        no = QPushButton("انصراف"); no.setObjectName("ghost")
        ok.clicked.connect(self.save); no.clicked.connect(self.reject)
        row.addWidget(ok); row.addWidget(no); row.addStretch()
        v.addSpacing(8); v.addLayout(row)

    @staticmethod
    def _txt(edit):
        return edit.keySequence().toString(QKeySequence.SequenceFormat.PortableText)

    def save(self):
        s1, s2 = self._txt(self.k1), self._txt(self.k2)
        for s in (s1, s2):
            if s and not parse_hotkey(s):
                QMessageBox.warning(self, "میانبر نامعتبر",
                                    f"«{s}» قابل استفاده نیست.\nبا Ctrl / Alt / Shift ترکیب کن یا از کلیدهای F استفاده کن.")
                return
        if s1 and s1 == s2:
            QMessageBox.warning(self, "میانبر تکراری", "دو میانبر نباید یکسان باشند.")
            return
        failed = self.ctl.apply_settings(s1, s2, self.c_copy.isChecked(), self.c_auto.isChecked())
        if failed:
            QMessageBox.warning(self, "میانبر در دسترس نیست",
                                "این ترکیب‌ها قبلاً توسط برنامه‌ی دیگری گرفته شده‌اند:\n" + "\n".join(failed))
        self.accept()


# ───────────────────────── کنترلر ─────────────────────────
class Controller:
    def __init__(self):
        self.cfg = load_cfg()
        self.result = ResultWindow(self)
        self.overlays = []
        self.workers = []
        self.job = 0
        self.mode = "window"
        self.last_pix = None
        self.dialog = None

        self.icon = QIcon(make_icon_pixmap(256))
        QApplication.instance().setWindowIcon(self.icon)
        self.result.setWindowIcon(self.icon)

        self.tray = QSystemTrayIcon(self.icon)
        self.tray.setToolTip("Snap OCR")
        self.tray.activated.connect(self._tray_click)
        self.menu = QMenu()
        self.tray.setContextMenu(self.menu)
        self.build_menu()
        self.tray.show()

        threading.Thread(target=warm_up, daemon=True).start()   # آماده‌سازی Tesseract در پس‌زمینه
        self.filter = HotkeyFilter(self.on_hotkey)
        QApplication.instance().installNativeEventFilter(self.filter)
        failed = self.register_hotkeys()

        self.server = QLocalServer()
        QLocalServer.removeServer(SERVER_NAME)
        self.server.listen(SERVER_NAME)
        self.server.newConnection.connect(self._on_conn)

        msg = "فعال است • میانبر: " + (self.cfg["hk_window"] or "—")
        if failed:
            msg += "\n⚠ میانبر ثبت نشد: " + "، ".join(failed)
        self.tray.showMessage("Snap OCR", msg, QSystemTrayIcon.MessageIcon.Information, 3500)

    # --- منو و تری
    def build_menu(self):
        m = self.menu
        m.clear()
        m.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        a1 = QAction(f"گرفتن متن   ({self.cfg['hk_window'] or '—'})", m)
        a1.triggered.connect(lambda: self.start_capture("window"))
        a2 = QAction(f"حالت سریع (فقط کپی)   ({self.cfg['hk_quick'] or '—'})", m)
        a2.triggered.connect(lambda: self.start_capture("quick"))
        a3 = QAction("نمایش آخرین نتیجه", m)
        a3.triggered.connect(self.result.popup)
        a4 = QAction("تنظیمات…", m)
        a4.triggered.connect(self.open_settings)
        a5 = QAction("خروج", m)
        a5.triggered.connect(self.quit)
        for a in (a1, a2, a3):
            m.addAction(a)
        m.addSeparator()
        m.addAction(a4)
        m.addAction(a5)

    def _tray_click(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.start_capture("window")

    def _on_conn(self):
        c = self.server.nextPendingConnection()
        c.waitForReadyRead(200)
        data = bytes(c.readAll())
        c.disconnectFromServer()
        if data == b"capture":
            self.start_capture("window")

    # --- میانبرها
    def register_hotkeys(self):
        failed = []
        if not IS_WIN:
            return failed
        import ctypes
        u = ctypes.windll.user32
        for hid, key in ((1, "hk_window"), (2, "hk_quick")):
            u.UnregisterHotKey(None, hid)
            spec = self.cfg.get(key, "")
            if not spec:
                continue
            p = parse_hotkey(spec)
            if not p or not u.RegisterHotKey(None, hid, p[0] | 0x4000, p[1]):   # 0x4000 = NOREPEAT
                failed.append(spec)
        return failed

    def on_hotkey(self, hid):
        self.start_capture("window" if hid == 1 else "quick")

    def open_settings(self):
        if self.dialog and self.dialog.isVisible():
            self.dialog.raise_(); self.dialog.activateWindow()
            return
        self.dialog = SettingsDialog(self)
        self.dialog.setWindowIcon(self.icon)
        self.dialog.show()

    def apply_settings(self, hk_window, hk_quick, autocopy, autostart):
        self.cfg.update(hk_window=hk_window, hk_quick=hk_quick, autocopy=autocopy)
        save_cfg(self.cfg)
        try:
            set_autostart(autostart)
        except Exception:
            pass
        self.build_menu()
        return self.register_hotkeys()

    # --- گرفتن صفحه
    def start_capture(self, mode="window"):
        self.close_overlays()
        self.mode = mode
        self.result.hide()
        QTimer.singleShot(150, self._capture)

    def _capture(self):
        self.close_overlays()
        for s in QGuiApplication.screens():
            ov = Overlay(s, s.grabWindow(0))
            ov.selected.connect(self.on_selected)
            ov.cancelled.connect(self.on_cancel)
            self.overlays.append(ov)
            ov.showFullScreen()
        if self.overlays:
            self.overlays[0].raise_()
            self.overlays[0].activateWindow()

    def close_overlays(self):
        for o in self.overlays:
            o.close()
        self.overlays = []

    def on_cancel(self):
        self.close_overlays()
        if self.mode == "window" and self.result.has_content:
            self.result.popup()

    def on_selected(self, pix):
        self.close_overlays()
        self.last_pix = pix
        if self.mode == "window":
            self.result.show_loading()
        QTimer.singleShot(40, self.start_job)

    def rerun(self):
        if self.last_pix is not None:
            self.mode = "window"
            self.result.status.setText("⏳ در حال خواندن…")
            self.start_job()

    # --- OCR
    def start_job(self):
        if self.last_pix is None:
            return
        self.job += 1
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        self.last_pix.save(buf, "PNG")
        opts = {"auto": self.cfg["auto"], "langs": list(self.cfg["langs"])}
        w = Worker(self.job, bytes(buf.data()), opts)
        w.done.connect(self.on_done)
        w.failed.connect(self.on_fail)
        w.finished.connect(lambda w=w: self.workers.remove(w) if w in self.workers else None)
        self.workers.append(w)
        w.start()

    def on_done(self, job, text, note):
        if job != self.job:
            return
        copied = bool(text) and (self.cfg["autocopy"] or self.mode == "quick")
        if copied:
            QGuiApplication.clipboard().setText(text)
        if self.mode == "window":
            self.result.show_text(text, note, copied)
        else:
            if text:
                prev = " ".join(text.split())[:110]
                self.tray.showMessage("✓ کپی شد  " + note, prev,
                                      QSystemTrayIcon.MessageIcon.Information, 2500)
            else:
                self.tray.showMessage("Snap OCR", "متنی پیدا نشد",
                                      QSystemTrayIcon.MessageIcon.Warning, 2000)

    def on_fail(self, job, msg):
        if job != self.job:
            return
        if self.mode == "window":
            self.result.show_error(msg)
        else:
            self.tray.showMessage("Snap OCR – خطا", msg[:200],
                                  QSystemTrayIcon.MessageIcon.Critical, 4000)

    def quit(self):
        self.close_overlays()
        if IS_WIN:
            import ctypes
            for hid in (1, 2):
                ctypes.windll.user32.UnregisterHotKey(None, hid)
        self.tray.hide()
        QApplication.quit()


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    f = QFont()
    f.setFamilies(["Vazirmatn", "Segoe UI", "Tahoma"])
    f.setPointSize(10)
    app.setFont(f)

    if "--make-icon" in sys.argv:                      # برای ساخت icon.ico (build_exe.bat)
        make_icon_pixmap(256).save("icon.png")
        try:
            from PIL import Image
            Image.open("icon.png").save("icon.ico",
                                        sizes=[(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)])
        except Exception as e:
            print("icon error:", e)
        return

    background = "--background" in sys.argv
    sock = QLocalSocket()                              # فقط یک نمونه از برنامه
    sock.connectToServer(SERVER_NAME)
    if sock.waitForConnected(300):
        sock.write(b"ping" if background else b"capture")
        sock.waitForBytesWritten(300)
        return

    ctl = Controller()
    if not background:                                 # اجرای دستی = همان لحظه انتخاب ناحیه
        ctl.start_capture("window")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
