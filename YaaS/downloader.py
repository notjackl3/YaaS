import subprocess
import os
from dotenv import load_dotenv
import boto3


class Downloader:
    def __init__(self, output_folder):
        self._cookies = os.getenv('COOKIES_FILE')
        self.output_folder = output_folder
        os.makedirs(output_folder, exist_ok=True)
        self.output_template = os.path.join(output_folder, "%(title)s.%(ext)s")

    def download_video(self, video_url: str):
        command = [
            "yt-dlp",
            "--cookies", self._cookies,
            "-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
            "--merge-output-format", "mp4",
            "--no-playlist",
            "--output", self.output_template,
            video_url
        ]
        subprocess.run(command)

        # directory = os.fsencode(self.output_folder)
        # for file in os.listdir(directory):
        #     full_path = os.path.join(self.output_folder, os.fsdecode(file))
        #     filename = os.fsdecode(file)
        #
        #     boto3.setup_default_session(
        #         aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        #         aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        #         region_name='us-east-1'
        #     )
        #     obj = boto3.client("s3")
        #     obj.upload_file(
        #         Filename=full_path,
        #         Bucket="downloaded-music",
        #         Key=filename
        #     )
            # Delete a file in a directory
            # pathlib.Path.unlink(full_path)

            # Delete a file in a bucket
            # s3 = boto3.resource('s3')
            # s3.Object('downloaded-music', filename).delete()


# video_url = "https://www.youtube.com/watch?v=yPSshiEsYh0&ab_channel=%CE%A3HAANTI-VirtualEnvironment"
