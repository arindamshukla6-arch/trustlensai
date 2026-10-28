@echo off
REM One-click launcher for Windows. Run setup steps in docs\WINDOWS_SETUP.md first.
if not exist .venv\Scripts\activate.bat (
  echo Creating virtual environment...
  python -m venv .venv
  call .venv\Scripts\activate.bat
  pip install -r requirements.txt
  if not exist .env copy .env.example .env
  python scripts\generate_sample_data.py
) else (
  call .venv\Scripts\activate.bat
)
streamlit run app.py
