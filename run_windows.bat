@echo off
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe app.py
) else (
  python app.py
)
