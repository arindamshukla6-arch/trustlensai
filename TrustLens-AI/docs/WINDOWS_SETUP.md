# Running TrustLens AI on Windows with VS Code (beginner guide)

## 1. Install the tools (once)
1. **Python 3.10–3.12** from https://www.python.org/downloads/ — on the first installer screen tick
   **"Add python.exe to PATH"**.
2. **VS Code** from https://code.visualstudio.com/ and, inside VS Code, the **Python** extension (Microsoft).
3. *(Optional, for OCR)* **Tesseract**: install the Windows build from the UB Mannheim project
   (https://github.com/UB-Mannheim/tesseract/wiki). The default path
   `C:\Program Files\Tesseract-OCR\tesseract.exe` is detected automatically. Without it, OCR steps say
   "not installed" and everything else still works.

## 2. Open the project
1. Unzip `TrustLens-AI.zip` somewhere simple, e.g. `C:\hackathon\TrustLens-AI`.
2. VS Code → **File → Open Folder…** → choose the `TrustLens-AI` folder.
3. **Terminal → New Terminal** (it opens in the project folder).

## 3. Set up a virtual environment
```powershell
python -m venv .venv
.venv\Scripts\activate
```
If PowerShell says scripts are disabled, run this once, then activate again:
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```
You should see `(.venv)` at the start of the prompt. In VS Code press `Ctrl+Shift+P` →
**Python: Select Interpreter** → pick the one inside `.venv`.

## 4. Install and configure
```powershell
pip install -r requirements.txt
copy .env.example .env
notepad .env          # change REVIEWER_ACCESS_CODE, save
python scripts\download_models.py
python scripts\generate_sample_data.py
```
`download_models.py` fetches the two OpenCV face models (~37 MB). If it fails (e.g. a blocked network),
download the two files it prints and put them in the `models` folder — or skip it: face matching will show
**Not run** and every other check still works.

## 5. Run
```powershell
streamlit run app.py
```
Your browser opens at http://localhost:8501. Sign in from the sidebar with a reviewer ID such as `rev.team`
and the access code from `.env`.

## 6. Test
```powershell
python -m pytest -q
```
Expected: `33 passed`.

## Troubleshooting
| Problem | Fix |
|---|---|
| `'python' is not recognized` | Reinstall Python with "Add to PATH", or use `py` instead of `python` |
| `ModuleNotFoundError` | The venv is not active: run `.venv\Scripts\activate` |
| Webcam not shown on the challenge tab | Allow camera access for the browser; use `localhost`, not an IP address |
| A video says "could not open" | Re-export as MP4 (H.264). Some phone codecs are not supported by OpenCV |
| Port in use | `streamlit run app.py --server.port 8502` |
| Start from a clean slate | Close the app and delete the `data` folder |
