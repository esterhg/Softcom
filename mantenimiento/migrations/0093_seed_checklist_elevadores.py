# Generated migration: seed de checklist de mantenimiento mensual de ascensores/elevadores
# Fuente: Formato OT-2026-00001 – Reporte Mantenimiento Elevadores, CCG
#
# Esta migración crea la Rutina "Mantenimiento Mensual de Ascensores" con todos
# sus PasoRutina organizados por secciones (HEADER), listos para usarse en OTs.
# Si ya existe una rutina con ese nombre, la migración no duplica datos.

from django.db import migrations


PASOS = [
    # (orden, tipo_respuesta, descripcion)
    # ── FOSO ────────────────────────────────────────────────────────────────
    (10,  'HEADER', 'FOSO'),
    (20,  'CHECK', 'Comprobación de la existencia de fijación de escalera de acceso al foso'),
    (30,  'CHECK', 'Prueba de el botón stop'),
    (40,  'CHECK', 'Limpieza de el botón stop'),
    (50,  'CHECK', 'Verificar e inspeccionar la fijación de las corredizas'),
    (60,  'CHECK', 'Comprobar e inspeccionar el faldón de seguridad: fijación, limpieza y robustez de su suspensión'),
    (70,  'CHECK', 'Comprobar e inspeccionar el faldón de seguridad: la medida debe ser igual o superior a 750 mm'),
    (80,  'CHECK', 'Comprobar la puesta a tierra del foso'),
    (90,  'CHECK', 'Verificar e inspeccionar el contacto eléctrico del pistón hidráulico de la cabina y contrapeso (actuación)'),
    (100, 'CHECK', 'Verificar e inspeccionar LFA – límite de carrera del pistón hidráulico y muelle de la cabina y contrapeso (mover, medir y actuación)'),
    (110, 'CHECK', 'Limpieza del dispositivo de seguridad'),
    (120, 'CHECK', 'Ajuste del dispositivo de seguridad'),
    (130, 'CHECK', 'Comprobar el funcionamiento del contacto GRS'),
    (140, 'CHECK', 'Comprobar la posición del seno de cadena de compensación (no debe golpear el piso)'),
    (150, 'CHECK', 'Comprobar las guías de la cadena de compensación'),
    (160, 'CHECK', 'Comprobar la integridad de la cadena de compensación y de las guías'),
    (170, 'CHECK', 'Comprobar que la cadena está fijada al soporte y que los tornillos allen están apretados'),
    (180, 'CHECK', 'Comprobar la fijación de la cadena al contrapeso'),
    (190, 'CHECK', 'Cuando el ascensor está equipado con cable de compensación: inspeccionar el estado del cable y comprobar su tensión'),
    (200, 'CHECK', 'Verificar la integridad de los cables de la polea de compensación'),
    (210, 'CHECK', 'Comprobar la fijación de la polea de compensación'),
    (220, 'CHECK', 'Verificar la limpieza de la polea de compensación'),
    (230, 'CHECK', 'Verificar e inspeccionar el contacto eléctrico de la polea de compensación'),
    (240, 'CHECK', 'Activar manualmente el contacto eléctrico y comprobar que funciona'),
    (250, 'CHECK', 'Comprobar la integridad de la polea tensora'),
    (260, 'CHECK', 'Inspeccionar la fijación del conjunto de polea tensora'),
    (270, 'CHECK', 'Comprobar la altura del peso de la polea tensora en relación al primer punto de impacto (mínimo 150 mm según proyecto ejecutivo)'),
    (280, 'NUMERICO', 'LCAB – Medida de deslizamiento de la cabina (anotar en mm)'),
    (290, 'NUMERICO', 'LCP – Medida de la distancia del amortiguador hasta la placa de contrapeso (anotar en mm)'),
    (300, 'CHECK', 'Comprobar si hay fugas en el acoplamiento hidráulico durante el funcionamiento o alrededor del sistema'),
    (310, 'CHECK', 'Comprobar el nivel de aceite del acoplamiento hidráulico a través de la pantalla situada en el tanque'),
    (320, 'CHECK', 'Los pistones deben introducirse en los elementos de la pared'),
    (330, 'CHECK', 'Activar el equipo y comprobar que el manómetro funciona cuando se activa el acoplamiento'),
    (340, 'CHECK', 'Comprobar que la tuerca que sujeta el eje del acoplamiento está apretada'),
    (350, 'CHECK', 'Inspeccionar el apriete de los tornillos que fijan la viga del acoplamiento'),
    (360, 'CHECK', 'Comprobar la limpieza del conjunto del acoplamiento'),
    (370, 'CHECK', 'Inspeccionar los rodamientos del acoplamiento para detectar ruidos y hollín'),

    # ── CAJA DE CARRERA ─────────────────────────────────────────────────────
    (380, 'HEADER', 'CAJA DE CARRERA'),
    (390, 'CHECK', 'Inspeccionar el ajuste entre el rodillo de la rótula y el soporte de apoyo del acoplamiento en el piso'),

    # ── PISO ─────────────────────────────────────────────────────────────────
    (400, 'HEADER', 'PISO'),
    (410, 'CHECK', 'Comprobar el sonido de identificación de carga y descarga'),
    (420, 'CHECK', 'Comprobar la iluminación del dispositivo de señalización'),
    (430, 'CHECK', 'Comprobar la integridad del dispositivo de señalización'),

    # ── MAQUINARIA Y COMANDO ─────────────────────────────────────────────────
    (440, 'HEADER', 'MAQUINARIA Y COMANDO'),
    (450, 'CHECK', 'Comprobar la protección de la polea del limitador'),
    (460, 'CHECK', 'Verificar la integridad de los canales de la polea'),
    (470, 'CHECK', 'Inspeccionar el sello de seguridad del limitador de velocidad'),
    (480, 'CHECK', 'Comprobar la integridad del cable de acero de la polea del limitador'),
    (490, 'CHECK', 'Comprobar el accionamiento mecánico del limitador de velocidad (OGT)'),
    (500, 'CHECK', 'Prueba de activación dinámica del limitador de velocidad con acuñamiento de la cabina sin carga'),
    (510, 'CHECK', 'Comprobar si el ascensor es desconectado al activar el contacto eléctrico del limitador de velocidad'),
    (520, 'CHECK', 'Verificar el cable de tierra del limitador de velocidad'),
    (530, 'CHECK', 'Inspeccionar la unidad hidráulica'),
    (540, 'CHECK', 'Comprobar la fijación/soporte de la unidad hidráulica'),
    (550, 'CHECK', 'Comprobar el nivel de aceite de la unidad hidráulica con la cabina detenida en la última planta'),
    (560, 'CHECK', 'Inspeccionar la integridad del intercambiador de calor'),
    (570, 'CHECK', 'Comprobar que no hay fugas alrededor del intercambiador y analizar la limpieza del componente'),
    (580, 'CHECK', 'Comprobar el sentido de funcionamiento del ventilador del motor según la flecha del intercambiador de calor'),
    (590, 'CHECK', 'Comprobar si el intercambiador de calor está sucio'),
    (600, 'CHECK', 'Comprobar la integridad y la fijación del pesador de carga'),
    (610, 'CHECK', 'Inspeccionar el sensor y el imán de pesaje'),
    (620, 'CHECK', 'Inspeccionar el estado del cableado del pesador de carga'),
    (630, 'CHECK', 'Prueba y verificación de activación del aparato de seguridad de cabina y contrapeso'),
    (640, 'CHECK', 'Comprobar la activación del contacto GRS en la cabina'),

    # ── CABINA SUPERIOR ───────────────────────────────────────────────────────
    (650, 'HEADER', 'CABINA SUPERIOR'),
    (660, 'CHECK', 'Comprobar la integridad y lubricación de las corredizas superiores de cabina'),
    (670, 'CHECK', 'Revisar e inspeccionar la integridad y fijación de la placa de suspensión de cabina'),
    (680, 'CHECK', 'Revisar e inspeccionar la integridad y fijación de la placa de suspensión del contrapeso'),
    (690, 'NUMERICO', 'Medida HA (anotar en mm)'),
    (700, 'NUMERICO', 'Medida HB (anotar en mm)'),
    (710, 'NUMERICO', 'Medida HC (anotar en mm)'),
    (720, 'CHECK', 'Verificar la fijación de la protección de la polea de desvío de la cabina'),
    (730, 'CHECK', 'Verificar la lubricación de la polea de desvío de cabina'),
    (740, 'CHECK', 'Comprobar la existencia de la protección de la polea de desvío de cabina'),
    (750, 'CHECK', 'Comprobar la existencia de la protección de la polea de desvío del contrapeso'),
    (760, 'CHECK', 'Comprobar la protección de salida de cables de polea de desvío del contrapeso'),
    (770, 'CHECK', 'Comprobar la integridad de los artículos superiores de la cabina'),
    (780, 'CHECK', 'Inspeccionar el dispositivo de seguridad superior de la cabina'),
    (790, 'CHECK', 'Comprobar que el sistema de activación está libre'),

    # ── CIERRE ────────────────────────────────────────────────────────────────
    (800, 'HEADER', 'MATERIALES Y CIERRE'),
    (810, 'TEXTO',  'Material utilizado / Repuestos usados (descripción)'),
    (820, 'TEXTO',  'Comentarios y recomendaciones del técnico'),
]


def seed_data(apps, schema_editor):
    Rutina = apps.get_model('mantenimiento', 'Rutina')
    PasoRutina = apps.get_model('mantenimiento', 'PasoRutina')
    Frecuencia = apps.get_model('mantenimiento', 'Frecuencia')

    # Obtener o crear frecuencia "Mensual"
    frecuencia_mensual, _ = Frecuencia.objects.get_or_create(
        nombre='Mensual',
        defaults={'dias': 30},
    )

    # Sólo crear si no existe una rutina con este nombre exacto
    rutina, created = Rutina.objects.get_or_create(
        nombre='MANTENIMIENTO MENSUAL DE ASCENSORES / ELEVADORES',
        defaults={
            'codigo_rutina': 'MANT-ASC-MENSUAL',
            'frecuencia': frecuencia_mensual,
            'descripcion': (
                'Procedimiento de mantenimiento mensual para ascensores / elevadores. '
                'Cubre: Foso, Caja de Carrera, Piso, Maquinaria y Comando, Cabina Superior. '
                'Basado en formato OT-2026-00001 (Operadora de Infraestructura de Honduras).'
            ),
            'herramientas': (
                'Linterna, multímetro, cinta métrica, llaves allen, '
                'lubricante para guías, aceite hidráulico, trapos de limpieza, '
                'EPP completo (casco, arnés, guantes).'
            ),
        }
    )

    if created:
        # Crear todos los pasos
        pasos_bulk = [
            PasoRutina(
                rutina=rutina,
                orden=orden,
                tipo_respuesta=tipo,
                descripcion=desc,
            )
            for orden, tipo, desc in PASOS
        ]
        PasoRutina.objects.bulk_create(pasos_bulk)


def unseed_data(apps, schema_editor):
    """Elimina solo si tiene el código único que asignamos."""
    Rutina = apps.get_model('mantenimiento', 'Rutina')
    Rutina.objects.filter(codigo_rutina='MANT-ASC-MENSUAL').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('mantenimiento', '0092_empresa_domicilio_empresa_numero_proveedor_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_data, unseed_data),
    ]
