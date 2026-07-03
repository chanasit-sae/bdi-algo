"""FastAPI backend for the SMART-ICU ventilator waveform viewer.

Run from the `backend/` directory so the sibling algorithm modules
(`parser`, `breath_segment`, `breath_metrics`) resolve on the path:

    cd backend
    uvicorn server.main:app --reload --port 8000
"""
