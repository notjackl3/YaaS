import os
from dotenv import load_dotenv
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
from googleapiclient.http import MediaFileUpload


def get_authenticated_service(scope, port=8090):
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
        os.getenv('CLIENT_SECRET_FILE'), scope)
    credentials = flow.run_local_server(port=port)
    return googleapiclient.discovery.build("youtube", "v3", credentials=credentials)


class Uploader:
    def __init__(self):
        self._scopes = ["https://www.googleapis.com/auth/youtube.upload"]
        self._port = 8080

    def upload_video(self, file_path, title, description, tags=None, category_id="22", privacy_status="public"):
        youtube = get_authenticated_service(self._scopes, self._port)

        request_body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags or [],
                "categoryId": category_id,
            },
            "status": {
                "privacyStatus": privacy_status
            }
        }
        media = MediaFileUpload(file_path, mimetype="video/*", resumable=True)

        request = youtube.videos().insert(
            part="snippet,status",
            body=request_body,
            media_body=media
        )
        response = request.execute()
        return f"https://youtu.be/{response['id']}"


# upload_video(
#     file_path="output_video.mp4",
#     title="Test Video Upload",
#     description="This is an automated upload.",
#     tags=["test", "api", "upload"],
#     privacy_status="private"
# )
