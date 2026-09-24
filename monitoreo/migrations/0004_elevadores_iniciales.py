"""
Migration de datos: carga los 40 elevadores del CCG con sus ubicaciones.
Si ya existen (por nombre) los actualiza, no los duplica.
"""
from django.db import migrations

ELEVADORES = [
    # (codigo, nombre, ubicacion, orden)
    ('L46', 'L46', 'Conjunto',      1),
    ('L45', 'L45', 'Sótanos',       2),
    ('L44', 'L44', 'Sótanos',       3),
    ('L43', 'L43', 'Sótanos',       4),
    ('L42', 'L42', 'Sótanos',       5),
    ('L41', 'L41', 'Sótanos',       6),
    ('L40', 'L40', 'Sótanos',       7),
    ('L34', 'L34', 'Cuerpo Bajo C', 8),
    ('L33', 'L33', 'Cuerpo Bajo C', 9),
    ('L32', 'L32', 'Cuerpo Bajo C', 10),
    ('L31', 'L31', 'Cuerpo Bajo C', 11),
    ('L24', 'L24', 'Cuerpo Bajo A', 12),
    ('L23', 'L23', 'Cuerpo Bajo A', 13),
    ('L22', 'L22', 'Cuerpo Bajo A', 14),
    ('L21', 'L21', 'Cuerpo Bajo A', 15),
    ('L30', 'L30', 'Cuerpo Bajo B', 16),
    ('L29', 'L29', 'Cuerpo Bajo B', 17),
    ('L28', 'L28', 'Cuerpo Bajo B', 18),
    ('L27', 'L27', 'Cuerpo Bajo B', 19),
    ('L26', 'L26', 'Cuerpo Bajo B', 20),
    ('L25', 'L25', 'Cuerpo Bajo B', 21),
    ('L2',  'L2',  'Torre 1',       22),
    ('L3',  'L3',  'Torre 1',       23),
    ('L4',  'L4',  'Torre 1',       24),
    ('L5',  'L5',  'Torre 1',       25),
    ('L6',  'L6',  'Torre 1',       26),
    ('L7',  'L7',  'Torre 1',       27),
    ('L8',  'L8',  'Torre 1',       28),
    ('L9',  'L9',  'Torre 1',       29),
    ('L10', 'L10', 'Torre 1',       30),
    ('L11', 'L11', 'Torre 2',       31),
    ('L12', 'L12', 'Torre 2',       32),
    ('L13', 'L13', 'Torre 2',       33),
    ('L14', 'L14', 'Torre 2',       34),
    ('L15', 'L15', 'Torre 2',       35),
    ('L16', 'L16', 'Torre 2',       36),
    ('L17', 'L17', 'Torre 2',       37),
    ('L18', 'L18', 'Torre 2',       38),
    ('L19', 'L19', 'Torre 2',       39),
    ('L20', 'L20', 'Torre 2',       40),
]


def cargar_elevadores(apps, schema_editor):
    Elevador = apps.get_model('monitoreo', 'Elevador')
    for codigo, nombre, ubicacion, orden in ELEVADORES:
        Elevador.objects.update_or_create(
            codigo=codigo,
            defaults={
                'nombre': nombre,
                'ubicacion': ubicacion,
                'orden': orden,
                'activo': True,
            },
        )


def revertir_elevadores(apps, schema_editor):
    Elevador = apps.get_model('monitoreo', 'Elevador')
    codigos = [e[0] for e in ELEVADORES]
    Elevador.objects.filter(codigo__in=codigos).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('monitoreo', '0003_menu_historial'),
    ]

    operations = [
        migrations.RunPython(cargar_elevadores, revertir_elevadores),
    ]
