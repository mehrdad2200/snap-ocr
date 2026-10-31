<div align="center">

# ✂️ Snap OCR

**Select any part of your screen — get the text. Instantly, offline, in any language.**

[فارسی](README.fa.md) · English

![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-blue)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

</div>

<!-- Add a screenshot or GIF here:  ![Demo](docs/demo.gif) -->

Snap OCR is a tiny, always-running Windows tray app. Press a hotkey, drag a rectangle over anything on your screen (images, videos, PDFs, scanned pages, games, remote desktops…) and the recognized text is copied to your clipboard. It runs fully **offline** on top of [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) and automatically detects the language, including **right-to-left scripts such as Persian and Arabic**.

## Features

- **Global hotkeys you choose** – any combination (e.g. `Ctrl+Alt+O`, `F8`, `Ctrl+Shift+Space`), set from the tray menu.
- **Two modes** – *Window mode* shows the result in a clean dark window; *Quick mode* only copies the text and shows a small notification.
- **Automatic language detection** – Persian, Arabic and English are tried first in a single pass; if confidence is low, other scripts (Cyrillic, Chinese, Japanese, Korean, Greek, Hebrew, Hindi, Thai) and Latin-script languages (Turkish, French, German, Spanish, …) are tested in parallel. Works with any language whose Tesseract data is installed.
- **Manual language chips** – click languages to force them when you know what you're reading.
- **RTL-aware output** – Persian/Arabic text is displayed right-to-left automatically.
- **Smart pre-processing** – upscaling of small text, automatic inversion of dark backgrounds, contrast normalisation.
- **Multi-monitor and HiDPI** support.
- **Runs in the tray** – start with Windows (optional), single instance (launching it again triggers a capture).
- **Private** – no network access, no telemetry. Everything happens on your machine.
- **Single file** – one Python file, or one `.exe`.

## Requirements

- Windows 10 / 11
- Python 3.9+ (only if you run from source)
- [Tesseract-OCR](https://github.com/UB-Mannheim/tesseract/wiki) with the language data you need

## Install

### 1. Tesseract
Download the Windows installer from the [UB-Mannheim page](https://github.com/UB-Mannheim/tesseract/wiki).
During setup open **Additional language data** and tick **Persian**, **Arabic** and any other language you want. Keep the default path `C:\Program Files\Tesseract-OCR`.

Check it:

```bat
"C:\Program Files\Tesseract-OCR\tesseract.exe" --list-langs
```

### 2. Run from source

```bat
git clone <repository-url>
cd snap-ocr
pip install -r requirements.txt
python snap_ocr.pyw
```

### …or use the exe
Grab `SnapOCR.exe` from the [Releases](../../releases) page (or build it yourself, see below).

## Usage

1. Launch the app → the screen dims immediately. (After the first run it keeps living in the tray.)
2. **Drag** a rectangle over the text. `Esc` or right-click cancels.
3. The text is recognized and copied to the clipboard.

| Action | How |
| --- | --- |
| Capture (window mode) | `Ctrl+Alt+O` (default) or left-click the tray icon |
| Capture (quick, copy only) | `Ctrl+Alt+Q` (default) |
| Change hotkeys / autostart | Tray icon → right-click → **Settings** |
| Hide result window | `Esc` or ✕ |
| Quit | Tray icon → right-click → **Exit** |

Command-line flags: `--background` (start silently in the tray, used by autostart), `--make-icon` (generate `icon.ico`).

Hotkeys need at least one modifier (`Ctrl`/`Alt`/`Shift`/`Win`), except for `F1…F24`, `Print Screen`, `Pause` and `Scroll Lock`.

## How automatic language detection works

1. One Tesseract pass with `fas+ara+eng` (whichever are installed). Text *and* confidence come from that single run. If the confidence is ≥ 60 % the result is returned immediately – this covers the common case in well under a second or two.
2. Otherwise, further candidates (other scripts and Latin-script languages) are run in parallel and the result with the highest confidence wins.

Tips: for accented European text, select the language manually for the best accuracy. Install `tessdata_best` models for higher accuracy, or `tessdata_fast` for more speed.

## Build the exe

```bat
build_exe.bat
```

Output: `dist\SnapOCR.exe`. The exe does **not** include Tesseract. Either install Tesseract on the target PC, or make a portable bundle: copy the `Tesseract-OCR` folder next to `SnapOCR.exe` and rename it to `tesseract`.

A GitHub Actions workflow (`.github/workflows/build.yml`) builds the exe and attaches it to a release when you push a tag like `v1.0.0`.

## Configuration

Settings are stored in `%USERPROFILE%\.snap_ocr.json` (hotkeys, language mode, auto-copy). Autostart uses the `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` registry key.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| "Tesseract not found" | Install it, or put the folder next to the app and name it `tesseract`. |
| Language missing / empty result | Run `tesseract --list-langs`; add the `.traineddata` file to Tesseract's `tessdata` folder; restart the app. |
| Hotkey "could not be registered" | Another program owns that combination. Choose a different one in Settings. |
| Slow results | Make sure only needed languages are installed/selected; use `tessdata_fast` models. |
| Text is wrong | Select a slightly larger area with some margin, avoid cutting lines in half, pick the language manually. |

## Project structure

```
snap-ocr/
├── snap_ocr.pyw        # the whole application
├── build_exe.bat       # PyInstaller build script
├── requirements.txt
├── .github/workflows/  # CI build
├── README.md / README.fa.md
└── LICENSE
```

## Contributing

Issues and pull requests are welcome. Ideas: Windows OCR engine backend, history of recent captures, image-to-clipboard translate, macOS/Linux hotkey backends.

## License

[MIT](LICENSE)

## Credits

Built with [PyQt6](https://riverbankcomputing.com/software/pyqt/), [Pillow](https://python-pillow.org/) and [Tesseract OCR](https://github.com/tesseract-ocr/tesseract).
