# Generated by Django 5.2 on 2025-05-03 23:18

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('uploader', '0002_fileupload_file_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='fileupload',
            name='yt_video_link',
            field=models.CharField(default='', max_length=200),
        ),
    ]
