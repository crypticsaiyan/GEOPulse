"""
GEOPulse Backend API Server (FastAPI)

REST endpoints that the Add-In dashboard calls:
    GET  /api/live-positions   - Vehicle positions + deviation scores
    GET  /api/live-events      - Exception events with version token
    GET  /api/driver/:id       - Full driver DNA + weekly delta
    GET  /api/anomalies        - All high-deviation drivers
    POST /api/generate-commentary - Gemini-powered sportscaster text
    POST /api/write-back/group - Create Geotab group
"""

# TODO: Implement - Step 6f
# Reference: PLAN.md Step 6f for full endpoint spec
