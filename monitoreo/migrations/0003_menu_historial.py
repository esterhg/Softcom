"""
Migration de datos: agrega el item "Historial de Reportes" al menú Monitoreo.
"""
from django.db import migrations


def agregar_item_historial(apps, schema_editor):
    AdminNavMenu = apps.get_model('core', 'AdminNavMenu')
    AdminNavItem = apps.get_model('core', 'AdminNavItem')

    try:
        menu = AdminNavMenu.objects.get(name='Monitoreo')
    except AdminNavMenu.DoesNotExist:
        # Si la migration 0002 no corrió aún, crear el menú base
        menu = AdminNavMenu.objects.create(
            name='Monitoreo',
            icon='fas fa-tv',
            color='#0070f2',
            descripcion='Monitoreo operacional de equipos críticos del edificio.',
            url='',
            superuser_only=False,
            order=50,
            active=True,
        )
        AdminNavItem.objects.create(
            menu=menu,
            name='Elevadores',
            url='/monitoreo/elevadores/',
            icon='fas fa-elevator',
            group='Monitoreo',
            order=1,
        )

    # Evitar duplicados
    if not AdminNavItem.objects.filter(menu=menu, url='/monitoreo/elevadores/historial/').exists():
        AdminNavItem.objects.create(
            menu=menu,
            name='Historial de Reportes',
            url='/monitoreo/elevadores/historial/',
            icon='fas fa-history',
            group='Monitoreo',
            order=2,
        )


def revertir_item_historial(apps, schema_editor):
    AdminNavItem = apps.get_model('core', 'AdminNavItem')
    AdminNavItem.objects.filter(url='/monitoreo/elevadores/historial/').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('monitoreo', '0002_menu_monitoreo'),
    ]

    operations = [
        migrations.RunPython(agregar_item_historial, revertir_item_historial),
    ]
