"""
Root URL configuration for Pine Labs backend.
"""

from django.contrib import admin
from django.urls import include, path

from transactions.views import chat_ui, serve_intro_video, serve_navbar_image

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/transactions/", include("transactions.urls")),
    path("chat/", chat_ui, name="chat_ui_root"),
    path("intro-video/", serve_intro_video, name="intro_video"),
    path("navbar-image/", serve_navbar_image, name="navbar_image"),
    path("", chat_ui, name="chat_ui_home"),
]
