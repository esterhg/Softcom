"""
Migration de datos: agrega el item "Averías" al menú Monitoreo.
"""
from django.db import migrations

URL = '/monitoreo/averias/'


def agregar_item(apps, schema_editor):
    AdminNavMenu = apps.get_model('core', 'AdminNavMenu')
    AdminNavItem = apps.get_model('core', 'AdminNavItem')

    menu = AdminNavMenu.objects.filter(name='Monitoreo').first()
    if menu is None:
        return
    if not AdminNavItem.objects.filter(menu=menu, url=URL).exists():
        AdminNavItem.objects.create(
            menu=menu,
            name='Averías',
            url=URL,
            icon='fas fa-triangle-exclamation',
            group='Monitoreo',
            order=3,
        )


def revertir_item(apps, schema_editor):
    AdminNavItem = apps.get_model('core', 'AdminNavItem')
    AdminNavItem.objects.filter(url=URL).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('monitoreo', '0009_reporte_averia'),
    ]

    operations = [
        migrations.RunPython(agregar_item, revertir_item),
    ]
