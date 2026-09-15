# ScreenText OCR v2

A Windows desktop OCR utility that turns anything visible on your screen into selectable text. It reads pixels, so it works with screenshots, games, videos, PDFs, images, and text that cannot normally be copied.

## v2 features
- Polished Windows desktop interface
- Configurable global hotkey
- OCR language selector (requires the corresponding Windows OCR language pack)
- OCR history (up to 100 results, stored locally)
- **Capture Region** for precise OCR
- **OCR Entire Screen** with no manual selection
- **Auto Detect Text**: sends the full screen to Windows OCR, which identifies text regions/lines automatically
- Optional image enhancement for small UI/game text
- Optional automatic clipboard copying
- Multi-monitor screen capture
- Offline/local OCR using Windows.Media.Ocr

## Requirements
- Windows 10/11
- Python 3.10+ only for building from source
- PowerShell (included with Windows)
- Windows OCR language pack for languages you want to use

## Build the EXE
Run on Windows:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\build.ps1
```

The executable is created at `dist\ScreenTextOCR.exe`.

## GitHub Actions
Push this repository to GitHub. The workflow in `.github/workflows/build.yml` builds the EXE on Windows. Creating a tag such as `v2.0.0` creates a GitHub Release and attaches the executable.

## Privacy
Screenshots are processed locally by Windows OCR. The app does not upload screenshots or OCR text to a server. OCR history is stored locally in `%APPDATA%\ScreenTextOCR`.
