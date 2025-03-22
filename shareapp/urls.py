from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', views.index, name='index'),
    path('create/', views.create_transfer, name='create_transfer'),
    path('receive/<str:key>/', views.receive_transfer, name='receive_transfer'),
    path('kill/<str:key>/', views.kill_transfer, name='kill_transfer'),
    path('download-zip/<str:key>/', views.download_zip, name='download_zip'),
    path('scan-qr/', views.scan_qr, name='scan_qr'),
]

# Добавляем обработку медиа-файлов в режиме разработки
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
