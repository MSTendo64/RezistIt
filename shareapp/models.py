from django.db import models
import random
import string
from django.utils import timezone
from datetime import timedelta
import os

def generate_unique_key():
    while True:
        length = random.randint(4, 6)
        key = ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))
        if not Transfer.objects.filter(key=key, is_active=True).exists():
            return key

class Statistics(models.Model):
    total_bytes_transferred = models.BigIntegerField(default=0)
    total_transfers = models.IntegerField(default=0)

    @classmethod
    def get_instance(cls):
        stats, _ = cls.objects.get_or_create(id=1)
        return stats

    def add_transfer(self, size):
        self.total_bytes_transferred += size
        self.total_transfers += 1
        self.save()

class Transfer(models.Model):
    key = models.CharField(max_length=6, unique=True, default=generate_unique_key)
    message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    total_size = models.BigIntegerField(default=0)  # Размер в байтах

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(minutes=15)
        super().save(*args, **kwargs)

    def calculate_size(self):
        """Подсчитывает общий размер всех файлов в передаче"""
        total = 0
        for file in self.files.all():
            if file.file:
                try:
                    total += file.file.size  # Используем атрибут size вместо проверки файловой системы
                except (OSError, AttributeError):
                    continue
        self.total_size = total
        self.save(update_fields=['total_size'])  # Обновляем только поле total_size
        
        # Добавляем размер в общую статистику
        stats = Statistics.get_instance()
        stats.add_transfer(total)

    def delete_with_files(self):
        # Удаляем физические файлы
        for file in self.files.all():
            if file.file and os.path.isfile(file.file.path):
                try:
                    os.remove(file.file.path)
                except (OSError, FileNotFoundError):
                    pass  # Игнорируем ошибки при удалении файлов
        
        # Удаляем запись из базы данных
        self.delete()

class TransferFile(models.Model):
    transfer = models.ForeignKey(Transfer, on_delete=models.CASCADE, related_name='files')
    file = models.FileField(upload_to='transfers/')
    filename = models.CharField(max_length=255)
