$ErrorActionPreference = "Stop"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m PyInstaller --noconfirm --clean --onefile --windowed --name ScreenTextOCR --add-data "ocr.ps1;." main.py
Write-Host "Built dist\\ScreenTextOCR.exe"
