from django.db import migrations

NOMBRE_GRUPO = 'Instalaciones'


def crear_grupo(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    # No duplicar si ya existe con otra capitalización (p. ej. 'instalaciones').
    if not Group.objects.filter(name__iexact=NOMBRE_GRUPO).exists():
        Group.objects.create(name=NOMBRE_GRUPO)


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('rrhh', '0001_initial'),
    ]

    # Al revertir no se borra el grupo: puede tener usuarios asignados.
    operations = [
        migrations.RunPython(crear_grupo, migrations.RunPython.noop),
    ]
