# -*- coding: utf-8 -*-
"""
Crea (idempotente) UNA sola rutina "RUTINA GENERAL DE ELEVADORES" con el
checklist completo de mantenimiento mensual de ascensores.

A diferencia de seed_ascensores (que crea 6 protocolos rotativos), este comando
consolida TODAS las actividades en una única rutina general, lista para ser
usada en la programación mensual de elevadores.

Uso:
    python manage.py seed_rutina_general_elevadores
    python manage.py seed_rutina_general_elevadores --dry-run

El checklist se organiza por zonas (HEADER) y actividades (CHECK).
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q


CODIGO_RUTINA = "ASC-GENERAL"
NOMBRE_RUTINA = "RUTINA GENERAL DE ELEVADORES"

# Checklist consolidado. Cada entrada: (tipo, texto)
#   HEADER = encabezado de sección (zona o componente)
#   CHECK  = actividad que el técnico marca Sí/No/NA
#   NUMERICO = actividad que requiere anotar un valor medido
CHECKLIST = [
    # ───────────────────────── FOSO ─────────────────────────
    ("HEADER", "FOSO"),
    ("CHECK", "Comprobar si hay fugas en el acoplamiento hidráulico durante el funcionamiento o alrededor del sistema"),
    ("CHECK", "Comprobar el nivel de aceite del acoplamiento hidráulico a través de la pantalla situada en el tanque"),
    ("CHECK", "Los pistones deben introducirse en los elementos de la pared"),
    ("CHECK", "Inspeccionar el estado y la integridad del eje del cilindro del acoplamiento"),
    ("CHECK", "Inspeccionar la activación del acoplamiento en todos los pisos, analizando el ajuste entre el rodillo esférico y el soporte de apoyo en el piso"),
    ("CHECK", "Comprobar que la tuerca que sujeta el eje del acoplamiento está apretada"),
    ("CHECK", "Inspeccionar si hay una chaveta para bloquear las tuercas"),
    ("CHECK", "Inspeccionar el apriete de los tornillos que fijan la viga del acoplamiento"),
    ("CHECK", "Comprobar la limpieza del conjunto"),
    ("CHECK", "Inspeccionar los rodamientos del acoplamiento para detectar ruidos y hollín"),
    ("CHECK", "Limpieza de piso del foso"),

    # ─────────────────────── CABINA INTERNA ───────────────────────
    ("HEADER", "CABINA INTERNA"),
    ("HEADER", "Paneles, Frisos y Piso"),
    ("CHECK", "Integridad de los paneles, frisos y piso"),
    ("HEADER", "Espejo y Barandilla de Protección"),
    ("CHECK", "Compruebe la fijación del guarda corpo"),
    ("CHECK", "Compruebe la integridad del guarda corpo"),
    ("HEADER", "Panel de Operación"),
    ("CHECK", "Integridad del panel de operación"),
    ("CHECK", "Integridad de los botones"),
    ("CHECK", "Prueba el funcionamiento de la botonera de cabina"),
    ("CHECK", "Prueba la fijación de la botonera de cabina"),
    ("CHECK", "Limpieza de la botonera de cabina"),
    ("CHECK", "Inspeccionar si el interruptor apaga el equipo cuando se activa"),
    ("CHECK", "Comprueba la operación de la alarma"),
    ("CHECK", "Comprueba la operación del intercomunicador / MAX VOICE (si hay)"),
    ("CHECK", "Integridad de las placas de capacidad y avisos"),
    ("CHECK", "Comprueba la operación de la iluminación principal y de emergencia"),
    ("HEADER", "Puertas de Cabina"),
    ("CHECK", "Prueba la barrera electrónica de seguridad (puerta de cabina)"),
    ("CHECK", "Verifique la fijación de la barrera electrónica"),
    ("CHECK", "Comprueba el cierre de la puerta"),
    ("CHECK", "Inspeccione las correderas de puerta"),
    ("CHECK", "Inspeccionar el alineamiento de los indicadores"),
    ("HEADER", "Subtecho y Ventilador"),
    ("CHECK", "Integridad del sub-techo"),
    ("CHECK", "Limpieza del sub-techo"),
    ("CHECK", "Prueba el funcionamiento del ventilador"),
    ("CHECK", "Verifique la limpieza del ventilador"),

    # ─────────────────────── PISO ───────────────────────
    ("HEADER", "PISO"),
    ("CHECK", "Verificar e inspeccionar la integridad de las botoneras"),
    ("CHECK", "Testear el funcionamiento de las botoneras"),
    ("CHECK", "Comprobar que el indicador de posición está fijo y funciona, y que las flechas de dirección funcionan"),
    ("CHECK", "Inspeccionar el alineamiento de las botoneras y de los indicadores"),
    ("CHECK", "Comprobar que las puertas de piso llevan las señales obligatorias"),
    ("CHECK", "Compruebe el sonido de identificación de carga y descarga"),
    ("CHECK", "Comprobar la iluminación del dispositivo de señalización"),
    ("CHECK", "Comprobar la integridad del dispositivo de señalización"),

    # ─────────────────── MAQUINARIO Y COMANDO ───────────────────
    ("HEADER", "MAQUINARIO Y COMANDO"),
    ("CHECK", "Verifique la vigencia del extintor"),
    ("CHECK", "Verifique el cierre de la puerta"),
    ("CHECK", "Prueba de la llave y botones de rescate"),
    ("HEADER", "Máquina de Tracción"),
    ("CHECK", "Revise e inspeccione la limpieza de la máquina"),
    ("HEADER", "Gobernador de Velocidad"),
    ("CHECK", "Limpieza del gobernador de velocidad"),
    ("CHECK", "Compruebe la protección de la polea del gobernador"),
    ("HEADER", "Cuadro de Comando"),
    ("CHECK", "Limpieza del cuadro de comando"),
    ("CHECK", "Prueba el disyuntor de falta de fase"),
    ("CHECK", "Prueba de relé térmico"),
    ("NUMERICO", "Disyuntores (verifique el amperaje de acuerdo con la tabla de disyuntores)"),
    ("CHECK", "Compruebe el funcionamiento del IDR"),
    ("NUMERICO", "Fusibles (verifique el amperaje de acuerdo con la tabla de fusibles)"),
    ("CHECK", "Compruebe el cable de tierra"),
    ("CHECK", "Verifique el cable de tierra del conjunto de resistencias"),
    ("CHECK", "Verifique el cable de tierra del autotransformador"),
    ("CHECK", "Prueba de NOBREAK y rescate automático"),
    ("CHECK", "Inspección y teste del límite superior (límite de parada)"),
    ("CHECK", "Inspección y teste del límite inferior (límite de parada)"),
    ("CHECK", "Inspeccione y pruebe el límite de ascenso FINAL con la desactivación de la cabina y compárelo con LCP"),
    ("CHECK", "Inspeccione y pruebe el límite de la dirección de descenso con la desactivación de la cabina"),
    ("CHECK", "Inspeccione y pruebe el límite de descenso FINAL con la cabina y compárelo con LCAB"),
    ("CHECK", "Prueba el cierre de la puerta de inspección"),
    ("CHECK", "Prueba el cierre de la puerta de escotilla"),
    ("CHECK", "Inspeccionar la unidad hidráulica"),
    ("CHECK", "Comprobar la fijación/soporte de la unidad hidráulica"),
    ("HEADER", "Pesador de Carga 2:1 y 4:1"),
    ("CHECK", "Comprobar la integridad y la fijación del pesador de carga"),
    ("CHECK", "Inspeccionar el sensor y el imán de pesaje"),
    ("CHECK", "Inspeccionar el estado del cableado del pesador de carga"),

    # ─────────────────────── CABINA SUPERIOR ───────────────────────
    ("HEADER", "CABINA SUPERIOR"),
    ("CHECK", "Compruebe la puesta a tierra correcta de las puertas de pisos"),
    ("CHECK", "Prueba de comando de sube y baja (mantenimiento)"),
    ("CHECK", "Prueba de botón stop"),
    ("CHECK", "Verificar los cables de maniobra, terminales y fijación"),
    ("CHECK", "Revise e inspeccione la integridad y fijación de la placa de suspensión de cabina"),
    ("CHECK", "Revise e inspeccione la integridad y fijación de la placa de suspensión del contra-peso"),
    ("HEADER", "Estructura de la Cabina"),
    ("CHECK", "Comprobar la integridad de los artículos superiores de la cabina"),

    # ─────────────────────── CAJA DE CARRERA ───────────────────────
    ("HEADER", "CAJA DE CARRERA"),
    ("HEADER", "Guías de Cabina y Contrapeso"),
    ("CHECK", "Verifique la lubricación - rieles (CABINA Y CONTRAPESO)"),
    ("HEADER", "Soportes de Cabina y Contrapeso"),
    ("CHECK", "Inspeccione la limpieza de los braquetes"),
    ("HEADER", "Puertas de Piso"),
    ("CHECK", "Inspeccione la limpieza de las puertas de pasillo"),
    ("HEADER", "Soportes de Apoyo del Acoplamiento en el Piso"),
    ("CHECK", "Inspeccionar el ajuste entre el rodillo de la rótula y el soporte de apoyo del acoplamiento en el piso"),

    # ─────────────────────── CIERRE ───────────────────────
    ("HEADER", "CIERRE DEL MANTENIMIENTO"),
    ("TEXTO", "Material utilizado / Repuestos usados"),
    ("TEXTO", "Comentarios del técnico y recomendaciones"),
]


class Command(BaseCommand):
    help = "Crea la rutina única 'RUTINA GENERAL DE ELEVADORES' con su checklist completo (idempotente)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="No escribe en la BD; solo muestra el resumen.")
        parser.add_argument(
            "--aplicar-a-vacias", action="store_true",
            help="Ademas de crear ASC-GENERAL, carga este mismo checklist en TODAS "
                 "las rutinas de elevadores (tipo Ascensores) que NO tengan pasos. "
                 "Util para que las OTs ya generadas con rutinas vacias muestren el checklist."
        )

    def handle(self, *args, **opts):
        dry = opts["dry_run"]

        from activos.models import Categoria
        from mantenimiento.models import Rutina, PasoRutina, Frecuencia, Tipo

        with transaction.atomic():
            # 1) Categoría de activo de elevadores (reutiliza existente)
            categoria_activo = None
            for nombre in ("ELEVADORES", "Ascensores", "Elevadores", "ASCENSORES"):
                categoria_activo = Categoria.objects.filter(nombre__iexact=nombre).first()
                if categoria_activo:
                    break
            if not categoria_activo:
                categoria_activo = Categoria.objects.create(nombre="ELEVADORES")
                self.stdout.write(self.style.SUCCESS("  ✓ Categoría de activo 'ELEVADORES' creada."))
            else:
                self.stdout.write(f"  • Categoría de activo reutilizada: '{categoria_activo.nombre}' (id={categoria_activo.id}).")

            # 2) Tipo de mantenimiento raíz "Ascensores" (reutiliza el del seed existente)
            tipo_root, _ = Tipo.objects.get_or_create(
                codigo="ASC",
                defaults={"nombre": "Ascensores", "categoria_activo": categoria_activo},
            )
            if tipo_root.categoria_activo_id != categoria_activo.id:
                tipo_root.categoria_activo = categoria_activo
                tipo_root.save(update_fields=["categoria_activo"])

            # 3) Tipo hijo "General" bajo Ascensores (define la subcategoría en el cronograma)
            tipo_general, _ = Tipo.objects.get_or_create(
                codigo="ASC-GENERAL-TIPO",
                defaults={"nombre": "General", "padre": tipo_root, "categoria_activo": categoria_activo},
            )

            # 4) Frecuencia "Mensual"
            frec_mensual, _ = Frecuencia.objects.get_or_create(
                nombre="Mensual", defaults={"dias": 30}
            )

            n_act = sum(1 for t, _ in CHECKLIST if t in ("CHECK", "NUMERICO", "TEXTO"))
            n_hdr = sum(1 for t, _ in CHECKLIST if t == "HEADER")
            self.stdout.write(
                f"  Checklist: {n_hdr} secciones, {n_act} actividades, {len(CHECKLIST)} pasos totales."
            )

            # Previsualización de rutinas de elevadores vacías que recibirían el checklist
            if opts.get("aplicar_a_vacias"):
                tipos_ascensor_ids = list(
                    tipo_root.get_descendants(include_self=True).values_list("id", flat=True)
                ) if hasattr(tipo_root, "get_descendants") else [tipo_root.id]
                preview = Rutina.objects.filter(
                    Q(tipo_id__in=tipos_ascensor_ids) | Q(categoria_activo=categoria_activo)
                ).exclude(codigo_rutina=CODIGO_RUTINA).distinct()
                self.stdout.write("  Rutinas de elevadores candidatas:")
                for rut in preview:
                    npasos = rut.pasos.count()
                    marca = "se OMITE (ya tiene pasos)" if npasos > 0 else "RECIBIRÁ checklist"
                    self.stdout.write(f"    - '{rut.nombre}' ({rut.codigo_rutina or 's/c'}) pasos={npasos} -> {marca}")

            if dry:
                self.stdout.write(self.style.WARNING("DRY-RUN: no se escribió nada en la base de datos."))
                transaction.set_rollback(True)
                return

            # 5) Rutina (idempotente por codigo_rutina)
            rutina, created = Rutina.objects.update_or_create(
                codigo_rutina=CODIGO_RUTINA,
                defaults={
                    "nombre": NOMBRE_RUTINA,
                    "categoria_activo": categoria_activo,
                    "tipo": tipo_general,
                    "frecuencia": frec_mensual,
                    "descripcion": "Rutina general de mantenimiento mensual de elevadores. Checklist completo (foso, cabina, maquinario, comando, caja de carrera).",
                    "tiempo_estimado": timedelta(hours=3),
                    "cantidad_tecnicos": 1,
                    "es_invasiva": False,
                },
            )

            # 6) Reconstruir los pasos desde cero (idempotente)
            rutina.pasos.all().delete()
            pasos_bulk = []
            for orden, (tipo_resp, texto) in enumerate(CHECKLIST):
                pasos_bulk.append(PasoRutina(
                    rutina=rutina,
                    orden=orden,
                    descripcion=texto,
                    tipo_respuesta=tipo_resp,
                ))
            PasoRutina.objects.bulk_create(pasos_bulk)

            estado = "creada" if created else "actualizada"
            self.stdout.write(self.style.SUCCESS(
                f"  ✓ Rutina '{NOMBRE_RUTINA}' ({CODIGO_RUTINA}) {estado} con {len(pasos_bulk)} pasos."
            ))

            # 7) OPCIONAL: cargar el checklist en otras rutinas de elevadores VACÍAS
            #    (ej: "ACTIVIDADES MENSUAL - SISTEMA DE ELEVADORES" que usan las OTs ya generadas)
            if opts.get("aplicar_a_vacias"):
                tipos_ascensor_ids = list(
                    tipo_root.get_descendants(include_self=True).values_list("id", flat=True)
                ) if hasattr(tipo_root, "get_descendants") else [tipo_root.id]

                # Rutinas de elevadores: por tipo (Ascensores y descendientes) o por categoria_activo
                candidatas = Rutina.objects.filter(
                    Q(tipo_id__in=tipos_ascensor_ids) | Q(categoria_activo=categoria_activo)
                ).exclude(codigo_rutina=CODIGO_RUTINA).distinct()

                aplicadas = 0
                for rut in candidatas:
                    if rut.pasos.count() > 0:
                        self.stdout.write(f"    - '{rut.nombre}' ya tiene pasos, se omite.")
                        continue
                    nuevos = [
                        PasoRutina(rutina=rut, orden=o, descripcion=txt, tipo_respuesta=tr)
                        for o, (tr, txt) in enumerate(CHECKLIST)
                    ]
                    PasoRutina.objects.bulk_create(nuevos)
                    aplicadas += 1
                    self.stdout.write(self.style.SUCCESS(
                        f"    + Checklist cargado en '{rut.nombre}' ({rut.codigo_rutina or 's/c'}): {len(nuevos)} pasos."
                    ))

                self.stdout.write(self.style.SUCCESS(
                    f"  OK Checklist aplicado a {aplicadas} rutina(s) de elevadores vacia(s)."
                ))

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\nListo. Código de rutina: {CODIGO_RUTINA}  |  Úsalo en la columna 'rutina_codigo' del Excel de OTs."
        ))
