"""
Frequency 1: Driver Feed — Personal Audio + Email

Every Friday at 5 PM, each driver gets:
- A 90-second personal audio clip (Google Cloud TTS)
- A beautiful HTML email with personalized stats

Functions:
    generate_driver_script(driver_id) -> script text via Gemini Flash
    generate_driver_audio(script_text, driver_name) -> MP3 path
    generate_driver_email_html(driver_id, audio_url) -> HTML string
    send_driver_email(email, name, html) -> send via Gmail API
    run_friday_driver_feed() -> main orchestrator
"""

# TODO: Implement - Step 5
# Reference: PLAN.md Step 5 for full spec including Gemini prompts
