from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.conf import settings
from .models import Transfer, TransferFile, Statistics
from datetime import datetime
import json
import base64
import qrcode
from pyzbar.pyzbar import decode
from io import BytesIO
import zipfile
import os
import tempfile
from wsgiref.util import FileWrapper
import shutil
from django.db import models
import cv2
import numpy as np
from django.views.decorators.http import require_http_methods
import re

def index(request):
    # Получаем статистику
    stats = Statistics.get_instance()
    active_transfers = Transfer.objects.filter(is_active=True).count()
    
    total_mb = round(stats.total_bytes_transferred / (1024 * 1024), 2)
    
    return render(request, 'shareapp/index.html', {
        'total_mb': total_mb,
        'total_transfers': stats.total_transfers,
        'active_transfers': active_transfers
    })

@csrf_exempt
def create_transfer(request):
    if request.method == 'POST':
        message = request.POST.get('message', '').strip()
        files = request.FILES.getlist('files')
        
        if not message and not files:
            return JsonResponse({
                'error': 'Необходимо добавить файлы или сообщение'
            }, status=400)
        
        transfer = Transfer.objects.create()
        if message:
            transfer.message = message
            transfer.save()
        
        for file in files:
            TransferFile.objects.create(
                transfer=transfer,
                file=file,
                filename=file.name
            )
        
        # Подсчитываем общий размер файлов
        transfer.calculate_size()
        
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(request.build_absolute_uri(f'/receive/{transfer.key}/'))
        qr.make(fit=True)
        qr_image = qr.make_image(fill_color="black", back_color="white")
        
        buffer = BytesIO()
        qr_image.save(buffer, format='PNG')
        qr_code = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        return JsonResponse({
            'key': transfer.key,
            'qr_code': qr_code,
            'expires_at': transfer.expires_at.isoformat()
        })

def receive_transfer(request, key):
    try:
        transfer = get_object_or_404(Transfer, key=key)
        
        # Проверяем активность и срок действия
        if not transfer.is_active or timezone.now() > transfer.expires_at:
            # Если передача истекла, удаляем её полностью
            transfer.delete_with_files()
            return render(request, 'shareapp/transfer_not_found.html')
        
        return render(request, 'shareapp/receive.html', {'transfer': transfer})
    except:
        return render(request, 'shareapp/transfer_not_found.html')

def kill_transfer(request, key):
    transfer = get_object_or_404(Transfer, key=key, is_active=True)
    try:
        transfer.delete_with_files()
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

def download_zip(request, key):
    transfer = get_object_or_404(Transfer, key=key, is_active=True)
    
    # Создаем директорию для временных файлов, если её нет
    temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp')
    os.makedirs(temp_dir, exist_ok=True)
    
    # Создаем ZIP файл
    zip_filename = f'transfer_{key}.zip'
    zip_path = os.path.join(temp_dir, zip_filename)
    
    # Создаем ZIP архив
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for file in transfer.files.all():
            file_path = file.file.path
            zip_file.write(file_path, file.filename)
    
    # Создаем FileResponse
    response = FileResponse(
        open(zip_path, 'rb'),
        content_type='application/zip'
    )
    response['Content-Disposition'] = f'attachment; filename={zip_filename}'
    
    # Добавляем middleware для удаления файла после отправки
    response._transfer_file_to_delete = zip_path
    
    return response

# Создаем middleware для удаления файла после отправки
class DeleteAfterDownloadMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        # Проверяем, есть ли файл для удаления
        if hasattr(response, '_transfer_file_to_delete'):
            try:
                # Удаляем файл после отправки
                os.unlink(response._transfer_file_to_delete)
            except (OSError, FileNotFoundError):
                pass
        
        return response

@require_http_methods(["POST"])
def scan_qr(request):
    try:
        print("Starting QR scan process...")
        print("Files in request:", request.FILES)

        if 'qr_image' not in request.FILES:
            return JsonResponse({
                'error': 'Изображение не найдено в запросе'
            }, status=400)
            
        image_file = request.FILES['qr_image']
        print(f"Received image: {image_file.name}, size: {image_file.size}, type: {image_file.content_type}")

        try:
            # Читаем изображение
            image_bytes = image_file.read()
            nparr = np.frombuffer(image_bytes, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if image is None:
                raise ValueError("Не удалось декодировать изображение")
            
            print(f"Original image shape: {image.shape}")

            # Предварительная обработка изображения
            # 1. Изменяем размер, если изображение слишком большое
            max_dimension = 1000
            height, width = image.shape[:2]
            if height > max_dimension or width > max_dimension:
                scale = max_dimension / max(height, width)
                new_width = int(width * scale)
                new_height = int(height * scale)
                image = cv2.resize(image, (new_width, new_height))
                print(f"Resized image shape: {image.shape}")

            # 2. Преобразуем в оттенки серого
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # 3. Применяем размытие для уменьшения шума
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            
            # 4. Применяем адаптивную бинаризацию
            binary = cv2.adaptiveThreshold(
                blurred,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                11,
                2
            )
            
            # Пытаемся найти QR код в разных вариантах изображения
            decoded_objects = []
            
            # Пробуем исходное изображение
            decoded_objects = decode(image)
            if not decoded_objects:
                # Пробуем черно-белое изображение
                decoded_objects = decode(binary)
            
            if not decoded_objects:
                # Пробуем инвертированное изображение
                inverted = cv2.bitwise_not(binary)
                decoded_objects = decode(inverted)

            print(f"Decoded objects: {len(decoded_objects)}")

            if not decoded_objects:
                return JsonResponse({
                    'error': 'QR-код не найден на изображении. Пожалуйста, убедитесь, что QR-код хорошо виден и попробуйте еще раз.'
                }, status=400)
            
            # Получаем данные из первого найденного QR-кода
            qr_data = decoded_objects[0].data.decode('utf-8')
            print(f"QR data: {qr_data}")
            
            # Проверяем формат данных
            match = re.search(r'/receive/([A-Z0-9]{4,6})/', qr_data)
            
            if not match:
                return JsonResponse({
                    'error': 'QR-код не содержит корректный ключ передачи',
                    'data': qr_data
                }, status=400)
            
            key = match.group(1)
            print(f"Found key: {key}")
            
            # Проверяем существование передачи
            transfer = Transfer.objects.filter(key=key).first()
            
            if not transfer:
                return JsonResponse({
                    'error': 'Передача не найдена',
                    'key': key
                }, status=404)
            
            print("Success! Returning key")
            return JsonResponse({'key': key})
            
        except Exception as e:
            print(f"Error processing image: {str(e)}")
            import traceback
            traceback.print_exc()
            return JsonResponse({
                'error': f'Ошибка при обработке изображения. Пожалуйста, попробуйте сделать фото более четким.'
            }, status=400)
            
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error': 'Внутренняя ошибка сервера'
        }, status=500)
