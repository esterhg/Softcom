"""
Migration de datos: actualiza y completa la lista de 43 elevadores del CCG.
Agrega L1 (Torre 1), L35 (Cuerpo Bajo C) y L47 (Conjunto) que faltaban.
"""
from django.db import migrations

ELEVADORES = [
    # (codigo, nombre, ubicacion, orden)
    ('L47', 'L47', 'Conjunto',      1),
    ('L46', 'L46', 'Conjunto',      2),
    ('L45', 'L45', 'Sótanos',       3),
    ('L44', 'L44', 'Sótanos',       4),
    ('L43', 'L43', 'Sótanos',       5),
    ('L42', 'L42', 'Sótanos',       6),
    ('L41', 'L41', 'Sótanos',       7),
    ('L40', 'L40', 'Sótanos',       8),
    ('L35', 'L35', 'Cuerpo Bajo C', 9),
    ('L34', 'L34', 'Cuerpo Bajo C', 10),
    ('L33', 'L33', 'Cuerpo Bajo C', 11),
    ('L32', 'L32', 'Cuerpo Bajo C', 12),
    ('L31', 'L31', 'Cuerpo Bajo C', 13),
    ('L24', 'L24', 'Cuerpo Bajo A', 14),
    ('L23', 'L23', 'Cuerpo Bajo A', 15),
    ('L22', 'L22', 'Cuerpo Bajo A', 16),
    ('L21', 'L21', 'Cuerpo Bajo A', 17),
    ('L30', 'L30', 'Cuerpo Bajo B', 18),
    ('L29', 'L29', 'Cuerpo Bajo B', 19),
    ('L28', 'L28', 'Cuerpo Bajo B', 20),
    ('L27', 'L27', 'Cuerpo Bajo B', 21),
    ('L26', 'L26', 'Cuerpo Bajo B', 22),
    ('L25', 'L25', 'Cuerpo Bajo B', 23),
    ('L1',  'L1',  'Torre 1',       24),
    ('L2',  'L2',  'Torre 1',       25),
    ('L3',  'L3',  'Torre 1',       26),
    ('L4',  'L4',  'Torre 1',       27),
    ('L5',  'L5',  'Torre 1',       28),
    ('L6',  'L6',  'Torre 1',       29),
    ('L7',  'L7',  'Torre 1',       30),
    ('L8',  'L8',  'Torre 1',       31),
    ('L9',  'L9',  'Torre 1',       32),
    ('L10', 'L10', 'Torre 1',       33),
    ('L11', 'L11', 'Torre 2',       34),
    ('L12', 'L12', 'Torre 2',       35),
    ('L13', 'L13', 'Torre 2',       36),
    ('L14', 'L14', 'Torre 2',       37),
    ('L15', 'L15', 'Torre 2',       38),
    ('L16', 'L16', 'Torre 2',       39),
    ('L17', 'L17', 'Torre 2',       40),
    ('L18', 'L18', 'Torre 2',       41),
    ('L19', 'L19', 'Torre 2',       42),
    ('L20', 'L20', 'Torre 2',       43),
]


def actualizar_elevadores(apps, schema_editor):
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


def revertir(apps, schema_editor):
    # Solo elimina los tres nuevos
    Elevador = apps.get_model('monitoreo', 'Elevador')
    Elevador.objects.filter(codigo__in=['L1', 'L35', 'L47']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('monitoreo', '0004_elevadores_iniciales'),
    ]

    operations = [
        migrations.RunPython(actualizar_elevadores, revertir),
    ]
