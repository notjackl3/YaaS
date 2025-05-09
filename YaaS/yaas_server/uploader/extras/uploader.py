import os
import time
from dotenv import load_dotenv
import pickle
from google.auth.transport.requests import Request
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

CLIENT_SECRET_FILE = os.getenv('CLIENT_SECRET_FILE')
SCOPE = ["https://www.googleapis.com/auth/youtube.upload",
         "https://www.googleapis.com/auth/youtube.force-ssl"]


def get_authenticated_service(request):
    # credentials = None
    #
    # if os.path.exists("secrets/token.pickle"):
    #     with open("secrets/token.pickle", "rb") as token:
    #         print("Read token.")
    #         credentials = pickle.load(token)
    #         print(credentials)
    #
    # if credentials and credentials.expired and credentials.refresh_token:
    #     print("Credentials not working.")
    #     credentials.refresh(Request())
    if 'credentials' not in request.session:
        return None  # or redirect to authorize view

    creds_data = request.session['credentials']
    credentials = Credentials(
        token=creds_data['token'],
        refresh_token=creds_data.get('refresh_token'),
        token_uri=creds_data['token_uri'],
        client_id=creds_data['client_id'],
        client_secret=creds_data['client_secret'],
        scopes=creds_data['scopes']
    )

    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        request.session['credentials']['token'] = credentials.token

    return googleapiclient.discovery.build("youtube", "v3", credentials=credentials)


def set_up_authenticated_service(port=8090):
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
        CLIENT_SECRET_FILE, SCOPE)

    credentials = flow.run_local_server(
        port=port,
        access_type='offline',
        include_granted_scopes='true'
    )

    with open("secrets/token.pickle", "wb") as file:
        pickle.dump(credentials, file)

    return googleapiclient.discovery.build("youtube", "v3", credentials=credentials)


class Uploader:
    def __init__(self):
        self._scopes = ["https://www.googleapis.com/auth/youtube.upload",
                        "https://www.googleapis.com/auth/youtube.force-ssl"]
        self._port = 8080

    def upload_video(self, request, file_path, title, description, tags=None, category_id="22", privacy_status="public"):
        youtube = get_authenticated_service(request)

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


if __name__ == "__main__":
    set_up_authenticated_service()
