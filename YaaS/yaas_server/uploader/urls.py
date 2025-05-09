from django.urls import path
from . import views
from . import processor

urlpatterns = [
    path("", views.back_home),
    # path('', index, name='index'),
    path("home/", views.home, name="home"),
    path("upload/", views.upload_file),
    path("download/", views.download_file),
    path('authorize/', views.authorize, name='authorize'),
    path('remove_authorize/', views.remove_authorize, name='remove_authorize'),
    path('oauth2callback/', views.oauth2callback, name='oauth2callback')
]
