"""
Frequency 3: Executive Podcast — Weekly Two-Host Audio

Every Monday at 5 AM, generates a 5-minute two-host podcast:
- Alex (lead) + Jamie (analyst) discuss fleet performance
- Uses Gemini Pro for script generation
- Google Cloud TTS with two distinct voices for audio
- Published to Google Sites + Google Sheets

Functions:
    generate_podcast_script(week_data) -> formatted script
    generate_podcast_audio(script_text) -> MP3 path
    publish_to_sites(episode_number, audio_path, script, summary)
    run_monday_podcast() -> main orchestrator
"""

# TODO: Implement - Step 7
# Reference: PLAN.md Step 7 for full spec including Gemini prompts
