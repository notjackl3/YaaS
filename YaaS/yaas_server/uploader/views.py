from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.http import FileResponse
from oauthlib.oauth2 import MismatchingStateError

from .models import FileUpload
from django.contrib import messages
from django.urls import reverse
from .processor import main_upload_function, main_download_function, extract_youtube_video_id
from django.shortcuts import redirect
from google_auth_oauthlib.flow import Flow
import os
from django.utils.safestring import mark_safe
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# this is for local
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
CLIENT_SECRETS_FILE = "uploader/secrets/client_secret.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.force-ssl"]
REDIRECT_URI = "http://localhost:8000/oauth2callback/"


def authorize(request):
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )

    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )

    request.session['state'] = state
    request.session.modified = True
    request.session.save()

    return redirect(authorization_url)


def oauth2callback(request):
    try:
        state = request.session['state']

        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            state=state,
            redirect_uri=REDIRECT_URI
        )

        print("State in session:", request.session.get('state'))
        print("State in response:", request.GET.get('state'))

        flow.fetch_token(authorization_response=request.build_absolute_uri())
        credentials = flow.credentials

        if credentials.expired:
            if credentials.refresh_token:
                credentials.refresh(Request())
                request.session['credentials']['token'] = credentials.token
            else:
                request.session.pop('credentials', None)
                return redirect('/authorize')

        request.session['credentials'] = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }

        return redirect('/home')
    except MismatchingStateError:
        return redirect('/authorize')


def remove_authorize(request):
    request.session.pop('credentials', None)
    return redirect('/home')


def is_user_authenticated(request):
    return 'credentials' in request.session


def home(request):
    authenticated = 'credentials' in request.session
    channel_name = "Youtube account missing."
    uploaded = request.GET.get('uploaded', False)
    message_type = request.GET.get("message")

    if authenticated:
        data = request.session['credentials']
        credentials = Credentials(
            token=data['token'],
            refresh_token=data.get('refresh_token'),
            token_uri=data['token_uri'],
            client_id=data['client_id'],
            client_secret=data['client_secret'],
            scopes=data['scopes'],
        )

        if credentials.expired:
            if credentials.refresh_token:
                credentials.refresh(Request())
                request.session['credentials']['token'] = credentials.token
            else:
                request.session.pop('credentials', None)
                return redirect('/authorize')

        youtube = build('youtube', 'v3', credentials=credentials)

        response = youtube.channels().list(
            part='snippet,contentDetails',
            mine=True
        ).execute()

        channel_name = response['items'][0]['snippet']['title']

    return render(request, "home.html",
                  {'authenticated': authenticated, 'channel_name': channel_name, "uploaded": uploaded,
                   "message_type": message_type})


def upload_file(request):
    # file_upload = request.POST.get('file_upload')
    file_upload = request.FILES.get('file_upload')
    file_name = request.POST.get('file_name')
    if file_upload and file_name:
        new_file_upload = FileUpload(original_file=file_upload, file_name=file_name)
        new_file_upload.save()
        yt_video_link = main_upload_function(request, new_file_upload.original_file.path, new_file_upload.file_name)
        new_file_upload.yt_video_id = extract_youtube_video_id(yt_video_link)
        new_file_upload.save()
        list(messages.get_messages(request))  # clear existing messages
        messages.add_message(request, messages.INFO, mark_safe(
            f"File uploaded. <a href=\"{yt_video_link}\" target=\"_blank\"> {yt_video_link} </a>"))
        return HttpResponseRedirect(reverse('home') + "?uploaded=false&message=upload")
    else:
        list(messages.get_messages(request))  # clear existing messages
        messages.add_message(request, messages.INFO, mark_safe(
            f"File uploaded. <a href=\"{'https://google.com'}\" target=\"_blank\"> link to video </a>"))

        # messages.add_message(request, messages.INFO, "Missing information.")
        return HttpResponseRedirect(reverse('home') + "?uploaded=false&message=upload")
        # return redirect('/home')
        # return render(request, "home.html", {'uploaded': False})


def back_home(request):
    return redirect('/home')


def download_file(request):
    yt_video_link = request.POST.get("youtube_link")
    yt_video_id = extract_youtube_video_id(yt_video_link)
    if yt_video_link:
        try:
            target_file_upload = FileUpload.objects.get(yt_video_id=yt_video_id)
        except:
            target_file_upload = None
        if target_file_upload:
            file_name = target_file_upload.file_name
            final_file_path = main_download_function(file_name, yt_video_link)
            root, ext = os.path.splitext(target_file_upload.original_file.path)
            list(messages.get_messages(request))  # clear existing messages
            messages.add_message(request, messages.INFO, "File downloaded.")
            response = FileResponse(open(final_file_path, "rb"), as_attachment=True, filename=f"{file_name}{ext}")
            response['Location'] = reverse('home') + "?downloaded=true&message=download"
            return response
        else:
            list(messages.get_messages(request))  # clear existing messages
            messages.add_message(request, messages.INFO, "Cannot find youtube video.")
            return HttpResponseRedirect(reverse('home') + "?downloaded=false&message=download")
    else:
        list(messages.get_messages(request))  # clear existing messages
        messages.add_message(request, messages.INFO, "Missing link.")
        return HttpResponseRedirect(reverse('home') + "?downloaded=false&message=download")
