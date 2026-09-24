"""
Migration de datos: agrega el menú "Monitoreo" al sistema de navegación (AdminNavMenu).
Depende de que la tabla core_adminnavmenu ya exista (se crea con la app core).
"""
from django.db import migrations


def agregar_menu_monitoreo(apps, schema_editor):
    AdminNavMenu = apps.get_model('core', 'AdminNavMenu')
    AdminNavItem = apps.get_model('core', 'AdminNavItem')

    # Evitar duplicados
    if AdminNavMenu.objects.filter(name='Monitoreo').exists():
        return

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


def revertir_menu_monitoreo(apps, schema_editor):
    AdminNavMenu = apps.get_model('core', 'AdminNavMenu')
    AdminNavMenu.objects.filter(name='Monitoreo').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('monitoreo', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(agregar_menu_monitoreo, revertir_menu_monitoreo),
    ]
