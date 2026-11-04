# -*- coding: utf-8 -*-
"""
Resetea una o varias Órdenes de Trabajo a su estado inicial, borrando todo lo
que capturó el técnico (checklist, firmas, fotos, cierre) PERO manteniendo la OT,
su rutina, técnico, activo, ubicación y fechas programadas.

Útil para dejar un mantenimiento de prueba "como nuevo" para que el técnico lo
vuelva a ejecutar desde cero.

Uso:
    # Por código de orden
    python manage.py resetear_ot --codigo MP_ELEV_1126_L25

    # Por ID
    python manage.py resetear_ot --id 70260

    # Varias a la vez
    python manage.py resetear_ot --codigo MP_ELEV_1126_L25 MP_ELEV_1126_L34

    # Ver qué haría sin borrar nada
    python manage.py resetear_ot --codigo MP_ELEV_1126_L25 --dry-run

    # Elegir el estado final (por defecto PROGRAMADA)
    python manage.py resetear_ot --codigo MP_ELEV_1126_L25 --estado ESPERA
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = "Resetea OTs a estado inicial (borra checklist, firmas, fotos y cierre; mantiene la OT)."

    def add_arguments(self, parser):
        parser.add_argument("--codigo", nargs="+", default=[], help="Código(s) de orden (codigo_de_orden).")
        parser.add_argument("--id", nargs="+", type=int, default=[], help="ID(s) de la orden de trabajo.")
        parser.add_argument("--estado", default="PROGRAMADA",
                            help="Estado final tras el reset (default: PROGRAMADA).")
        parser.add_argument("--dry-run", action="store_true", help="No borra nada; solo muestra el resumen.")

    def handle(self, *args, **opts):
        from mantenimiento.models import OrdenTrabajo, ValorPasoOrden, ArchivoOrdenTrabajo, CierreOrdenTrabajo

        codigos = opts["codigo"]
        ids = opts["id"]
        estado_final = opts["estado"]
        dry = opts["dry_run"]

        if not codigos and not ids:
            raise CommandError("Debes indicar al menos --codigo o --id.")

        estados_validos = dict(OrdenTrabajo.ESTADO_CHOICES)
        if estado_final not in estados_validos:
            raise CommandError(
                f"Estado '{estado_final}' no válido. Opciones: {', '.join(estados_validos.keys())}"
            )

        # Reunir las OTs objetivo
        from django.db.models import Q
        q = Q()
        if codigos:
            q |= Q(codigo_de_orden__in=codigos)
        if ids:
            q |= Q(id__in=ids)
        ordenes = OrdenTrabajo.objects.filter(q)

        if not ordenes.exists():
            self.stdout.write(self.style.WARNING("No se encontró ninguna OT con esos criterios."))
            return

        for ot in ordenes:
            n_checklist = ValorPasoOrden.objects.filter(orden_trabajo=ot).count()
            n_archivos = ArchivoOrdenTrabajo.objects.filter(orden_trabajo=ot).count()
            tiene_cierre = CierreOrdenTrabajo.objects.filter(orden_trabajo=ot).exists()
            tiene_firma = bool(ot.firma_tecnico or ot.firma_cliente)

            self.stdout.write(self.style.MIGRATE_HEADING(
                f"\nOT {ot.codigo_de_orden or ot.id} (estado actual: {ot.estado})"
            ))
            self.stdout.write(
                f"  Checklist a borrar: {n_checklist} | Archivos: {n_archivos} | "
                f"Cierre: {'sí' if tiene_cierre else 'no'} | Firmas: {'sí' if tiene_firma else 'no'}"
            )
            self.stdout.write(f"  Técnico (se mantiene): {ot.tecnico or '—'} | Rutina: {ot.rutina or '—'}")
            self.stdout.write(f"  Estado final tras reset: {estado_final}")

            if dry:
                continue

            with transaction.atomic():
                # 1. Borrar respuestas del checklist
                ValorPasoOrden.objects.filter(orden_trabajo=ot).delete()

                # 2. Borrar archivos/evidencias (incluye el PDF generado y fotos)
                ArchivoOrdenTrabajo.objects.filter(orden_trabajo=ot).delete()

                # 3. Borrar registro de cierre si existe
                CierreOrdenTrabajo.objects.filter(orden_trabajo=ot).delete()

                # 4. Limpiar firmas y datos de reporte de campo
                ot.firma_tecnico = None
                ot.firma_tecnico_nombre = None
                ot.firma_cliente = None
                ot.firma_cliente_nombre = None
                ot.firma_fecha = None
                ot.operativo_salida = None
                ot.comentarios_tecnico = None
                ot.materiales_utilizados = None
                ot.comentarios_cliente = None
                ot.fecha_ejecucion = None

                # 5. Volver al estado inicial (NO toca técnico, rutina, activos, fechas programadas)
                ot.estado = estado_final
                ot.save()

            self.stdout.write(self.style.SUCCESS(f"  ✓ OT {ot.codigo_de_orden or ot.id} reseteada."))

        if dry:
            self.stdout.write(self.style.WARNING("\nDRY-RUN: no se borró nada."))
        else:
            self.stdout.write(self.style.MIGRATE_HEADING("\nListo. Las OTs quedaron como nuevas para el técnico."))
