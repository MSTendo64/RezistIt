from django.core.management.base import BaseCommand
from django.utils import timezone
from shareapp.models import Transfer

class Command(BaseCommand):
    help = 'Удаляет истекшие передачи и их файлы'

    def handle(self, *args, **options):
        # Получаем все истекшие активные передачи
        expired_transfers = Transfer.objects.filter(
            is_active=True,
            expires_at__lt=timezone.now()
        )

        count = 0
        for transfer in expired_transfers:
            try:
                transfer.delete_with_files()
                count += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f'Ошибка при удалении передачи {transfer.key}: {str(e)}'
                ))

        self.stdout.write(self.style.SUCCESS(
            f'Успешно удалено {count} истекших передач'
        )) 