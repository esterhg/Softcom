from django.db import migrations

NOMBRE_GRUPO = 'Supervisor de Almacen'


def crear_grupo(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.get_or_create(name=NOMBRE_GRUPO)


def eliminar_grupo(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(name=NOMBRE_GRUPO).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('inventarios', '0046_solicitudmaterial_foto_entrega_and_more'),
    ]

    operations = [
        migrations.RunPython(crear_grupo, eliminar_grupo),
    ]
