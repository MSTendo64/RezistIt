from django.apps import AppConfig
import os
from django.conf import settings
import shutil


class ShareappConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'shareapp'

    def ready(self):
        # Импортируем модели здесь, чтобы избежать циклических импортов
        from .models import Transfer, Statistics
        
        # Очищаем временную директорию при запуске
        temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp')
        if os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                os.makedirs(temp_dir)
            except OSError:
                pass

        # Очищаем директорию с загруженными файлами
        transfers_dir = os.path.join(settings.MEDIA_ROOT, 'transfers')
        if os.path.exists(transfers_dir):
            try:
                shutil.rmtree(transfers_dir)
                os.makedirs(transfers_dir)
            except OSError:
                pass

        try:
            # Получаем все передачи
            transfers = Transfer.objects.all()
            
            # Удаляем каждую передачу с файлами
            for transfer in transfers:
                transfer.delete_with_files()
                
        except Exception as e:
            print(f"Ошибка при очистке передач: {e}")
