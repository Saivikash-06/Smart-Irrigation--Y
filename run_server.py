"""
GreenPulse Launcher Script
Starts the FastAPI backend with Uvicorn.
"""
import sys
import os
import uvicorn

# Ensure the backend directory is in Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "backend")))

if __name__ == "__main__":
    print("==================================================")
    print("GreenPulse – Smart Irrigation & Garden Monitoring")
    print("Starting FastAPI Backend Server on http://0.0.0.0:8000")
    print("Swagger API Docs: http://localhost:8000/docs")
    print("Web Dashboard:    http://localhost:8000")
    print("==================================================")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
