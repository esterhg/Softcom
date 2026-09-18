"""
Management command para asegurar que las monedas básicas existan en la BD.
Uso: python manage.py ensure_monedas
"""
from django.core.management.base import BaseCommand
from presupuestos.models import Moneda


MONEDAS = [
    {'codigo': 'HNL', 'nombre': 'Lempiras',             'simbolo': 'L'},
    {'codigo': 'USD', 'nombre': 'Dólares',               'simbolo': '$'},
    {'codigo': 'DOP', 'nombre': 'Pesos Dominicanos',     'simbolo': 'RD$'},
    {'codigo': 'EUR', 'nombre': 'Euro',                  'simbolo': '€'},
]


class Command(BaseCommand):
    help = 'Crea las monedas básicas (HNL, USD, DOP, EUR) si no existen.'

    def handle(self, *args, **options):
        for data in MONEDAS:
            obj, created = Moneda.objects.get_or_create(
                codigo=data['codigo'],
                defaults={'nombre': data['nombre'], 'simbolo': data['simbolo']},
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'  Creada: {obj.codigo} — {obj.nombre} ({obj.simbolo})'))
            else:
                self.stdout.write(f'  Ya existe: {obj.codigo} — {obj.nombre} ({obj.simbolo})')

        self.stdout.write(self.style.SUCCESS('\nListo. Monedas disponibles en el sistema.'))
