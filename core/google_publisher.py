"""
GEOPulse Google Publisher — Sites, Sheets, and Drive Integration

Publishes podcast episodes and fleet intelligence data to Google services:
  - Google Sheets: Weekly KPI dashboard
  - Google Drive: Podcast script + audio storage
  - Email: Executive notification with episode link

Setup:
  Uses the same service account as TTS (GOOGLE_APPLICATION_CREDENTIALS).
  Or set GOOGLE_SHEETS_ID for a specific spreadsheet.
"""

import os
import json
import logging
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def publish_to_sheets(week_data, episode_summary=None):
    """
    Update Google Sheets 'Fleet Intelligence Dashboard' with weekly KPIs.

    Adds a new row: week, key metrics, links to audio + script,
    and a Gemini-generated one-paragraph executive summary.

    Args:
        week_data: dict with fleet KPIs from gather_week_data()
        episode_summary: Optional one-paragraph summary from podcast script

    Returns:
        dict with success status
    """
    sheet_id = os.getenv("GOOGLE_SHEETS_ID")
    if not sheet_id:
        logger.warning("GOOGLE_SHEETS_ID not configured. Skipping Sheets publish.")
        return {"success": False, "error": "GOOGLE_SHEETS_ID not set"}

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds = service_account.Credentials.from_service_account_file(
            os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        service = build("sheets", "v4", credentials=creds)

        week_num = week_data.get("week_number", datetime.now().strftime("%W"))
        year = week_data.get("year", datetime.now().year)

        row = [
            f"Week {week_num}, {year}",
            datetime.now().strftime("%Y-%m-%d"),
            week_data.get("total_vehicles", 0),
            week_data.get("avg_deviation_score", 0),
            week_data.get("total_events_24h", 0),
            len(week_data.get("most_anomalous", [])),
            episode_summary or "",
        ]

        body = {"values": [row]}
        result = service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range="Dashboard!A:G",
            valueInputOption="USER_ENTERED",
            body=body,
        ).execute()

        logger.info(f"Sheets: appended row for Week {week_num}")
        return {"success": True, "updates": result.get("updates", {})}

    except Exception as e:
        logger.error(f"Sheets publish failed: {e}")
        return {"success": False, "error": str(e)}


def upload_to_drive(file_path, folder_id=None):
    """
    Upload a file to Google Drive.

    Args:
        file_path: Local path to the file
        folder_id: Optional Drive folder ID. Uses GOOGLE_DRIVE_FOLDER_ID env var.

    Returns:
        dict with success, file_id, and web_link
    """
    folder_id = folder_id or os.getenv("GOOGLE_DRIVE_FOLDER_ID")
    if not folder_id:
        logger.warning("GOOGLE_DRIVE_FOLDER_ID not configured. Skipping Drive upload.")
        return {"success": False, "error": "GOOGLE_DRIVE_FOLDER_ID not set"}

    if not os.path.exists(file_path):
        return {"success": False, "error": f"File not found: {file_path}"}

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        creds = service_account.Credentials.from_service_account_file(
            os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
            scopes=["https://www.googleapis.com/auth/drive.file"],
        )
        service = build("drive", "v3", credentials=creds)

        filename = os.path.basename(file_path)
        mime = "audio/mpeg" if filename.endswith(".mp3") else "text/plain"

        file_metadata = {"name": filename, "parents": [folder_id]}
        media = MediaFileUpload(file_path, mimetype=mime)

        result = service.files().create(
            body=file_metadata, media_body=media, fields="id, webViewLink"
        ).execute()

        logger.info(f"Drive: uploaded {filename} ({result.get('id')})")
        return {
            "success": True,
            "file_id": result.get("id"),
            "web_link": result.get("webViewLink"),
        }

    except Exception as e:
        logger.error(f"Drive upload failed: {e}")
        return {"success": False, "error": str(e)}


def publish_podcast_episode(episode_number, audio_path, script_text, week_summary, week_data=None):
    """
    Full podcast publishing pipeline:
    1. Upload audio to Google Drive
    2. Upload script to Google Drive
    3. Update Google Sheets with episode metadata
    4. Send email notification to exec list

    Args:
        episode_number: Episode number (e.g. week number)
        audio_path: Path to the MP3 file
        script_text: Full podcast script text
        week_summary: One-paragraph executive summary
        week_data: Optional dict with fleet metrics for Sheets publishing

    Returns:
        dict with all publishing results
    """
    results = {"episode": episode_number}

    # 1. Upload audio to Drive
    if audio_path and os.path.exists(audio_path):
        audio_result = upload_to_drive(audio_path)
        results["audio_upload"] = audio_result
    else:
        results["audio_upload"] = {"success": False, "error": "No audio file"}

    # 2. Save and upload script
    script_path = f"/tmp/geopulse_podcast_ep{episode_number}.txt"
    with open(script_path, "w") as f:
        f.write(f"GEOPulse Fleet Intelligence Podcast — Episode {episode_number}\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write("=" * 60 + "\n\n")
        f.write(script_text)

    script_result = upload_to_drive(script_path)
    results["script_upload"] = script_result

    # 3. Update Sheets — use real week_data if provided, otherwise basic metadata
    if week_data is None:
        week_data = {
            "week_number": str(episode_number),
            "year": datetime.now().year,
            "total_vehicles": 0,
            "avg_deviation_score": 0,
            "total_events_24h": 0,
            "most_anomalous": [],
        }
    sheets_result = publish_to_sheets(week_data, week_summary)
    results["sheets"] = sheets_result

    # 4. Send exec notification email
    exec_email = os.getenv("EXEC_EMAIL")
    if exec_email:
        from core.email_sender import send_email

        audio_link = results.get("audio_upload", {}).get("web_link", "#")
        email_html = _build_podcast_email(episode_number, week_summary, audio_link)
        email_result = send_email(
            exec_email,
            f"🎧 Fleet Podcast Episode {episode_number} is Ready",
            email_html,
        )
        results["email"] = email_result

    logger.info(f"Podcast episode {episode_number} publishing complete")
    return results


def _build_podcast_email(episode_number, summary, audio_link):
    """Build the executive notification email HTML."""
    today = datetime.now().strftime("%A, %B %d, %Y")
    return f"""
    <div style="background:#0D1117;color:#E6EDF3;font-family:'Inter',-apple-system,sans-serif;padding:32px;max-width:600px;margin:0 auto;">
        <div style="background:linear-gradient(135deg,#161B22,#1C2128);border:1px solid #30363D;border-radius:12px;padding:24px;">
            <div style="text-align:center;margin-bottom:20px;">
                <span style="font-size:36px;">🎧</span>
                <h1 style="font-size:22px;margin:8px 0 4px;">Fleet Intelligence Podcast</h1>
                <p style="color:#7D8590;font-size:14px;margin:0;">Episode {episode_number} · {today}</p>
            </div>

            <div style="margin:20px 0;padding:16px;background:#0D1117;border-radius:8px;font-size:14px;line-height:1.6;">
                {summary}
            </div>

            <div style="text-align:center;margin:24px 0;">
                <a href="{audio_link}" style="display:inline-block;background:#388BFD;color:white;
                   padding:14px 36px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:15px;">
                    ▶ Listen to Episode {episode_number}
                </a>
            </div>

            <div style="border-top:1px solid #30363D;margin-top:20px;padding-top:12px;">
                <p style="font-size:11px;color:#7D8590;text-align:center;margin:0;">
                    GEOPulse Fleet Intelligence · Auto-generated weekly
                </p>
            </div>
        </div>
    </div>
    """


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("📡 Testing Google publisher...")

    # Test Sheets
    test_data = {
        "week_number": "09",
        "year": 2026,
        "total_vehicles": 18,
        "avg_deviation_score": 34.5,
        "total_events_24h": 42,
        "most_anomalous": [{"name": "Vehicle 7"}],
    }
    result = publish_to_sheets(test_data, "Fleet performed well this week.")
    print(f"   Sheets: {result}")

    # Test Drive
    result = upload_to_drive("/tmp/test.txt")
    print(f"   Drive: {result}")
