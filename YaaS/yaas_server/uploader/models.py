from django.db import models


class FileUpload(models.Model):
    file_name = models.CharField(max_length=200, default="untitled")
    original_file = models.FileField(upload_to="original_files/")
    yt_video_id = models.CharField(max_length=200, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    objects = models.Manager()

    def __str__(self):
        return self.file_name
