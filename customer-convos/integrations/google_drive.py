from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
import config

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def get_service():
    creds = service_account.Credentials.from_service_account_file(
        config.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds)


def find_decks_for_call(start_time: datetime, window_days: int = 7) -> list[dict]:
    """
    Search all configured sales deck folders for files modified
    within window_days before or after the call date.
    """
    service = get_service()

    after = (start_time - timedelta(days=window_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    before = (start_time + timedelta(days=window_days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    seen = set()
    results = []

    for folder_id in config.GOOGLE_DRIVE_SALES_DECKS_FOLDER_IDS:
        parents_clause = " or ".join(f"'{folder_id}' in parents" for folder_id in [folder_id])
        query = (
            f"({parents_clause})"
            f" and modifiedTime >= '{after}'"
            f" and modifiedTime <= '{before}'"
            f" and trashed = false"
            f" and (mimeType = 'application/vnd.google-apps.presentation'"
            f"  or mimeType = 'application/vnd.openxmlformats-officedocument.presentationml.presentation')"
        )

        page_token = None
        while True:
            response = service.files().list(
                q=query,
                fields="nextPageToken, files(id, name, webViewLink, modifiedTime)",
                pageToken=page_token,
            ).execute()

            for f in response.get("files", []):
                if f["id"] not in seen:
                    seen.add(f["id"])
                    results.append({
                        "drive_file_id": f["id"],
                        "name": f["name"],
                        "url": f.get("webViewLink"),
                        "modified_at": datetime.fromisoformat(
                            f["modifiedTime"].replace("Z", "+00:00")
                        ),
                    })

            page_token = response.get("nextPageToken")
            if not page_token:
                break

    return results
