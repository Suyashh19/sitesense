@echo off
rem First run: builds the data + models if they do not exist yet (needs internet, several minutes).
cd /d %~dp0backend
if not exist data\artifacts\status.json python -m app.pipeline.build
python -m uvicorn app.main:app --port 8000
