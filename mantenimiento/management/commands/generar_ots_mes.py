# -*- coding: utf-8 -*-
"""
Materializa (crea en la base de datos) las Órdenes de Trabajo REALES de un mes
a partir de las Programaciones existentes.

En el cronograma, las actividades futuras se muestran como PROYECCIONES (ghost
OTs) calculadas al vuelo desde cada Programación por su frecuencia. NO existen en
la BD hasta que se "materializan". Este comando las convierte en OTs reales para
que el técnico las vea en /app/ y pueda llenar el checklist.

Uso:
    # Materializar TODAS las programaciones hasta fin de noviembre 2026
    python manage.py generar_ots_mes --year 2026 --month 11

    # Solo las de elevadores (rutinas con código que empieza en ASC)
    python manage.py generar_ots_mes --year 2026 --month 11 --rutina-prefijo ASC

    # Solo una rutina concreta
    python manage.py generar_ots_mes --year 2026 --month 11 --rutina-codigo ASC-GENERAL

    # Ver qué haría sin escribir nada
    python manage.py generar_ots_mes --year 2026 --month 11 --rutina-prefijo ASC --dry-run

Notas:
- `generar_ordenes(fecha_corte)` genera OTs desde fecha_inicio de la programación
  HASTA la fecha de corte. Aquí la fecha de corte = último día del mes indicado.
- Es acumulativo: si una programación arranca en enero y pides noviembre,
  materializa todo lo pendiente hasta noviembre (no solo noviembre aislado).
  Las OTs ya existentes no se duplican (la generación agrupa por día/área/técnico).
"""
import calendar
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q


class Command(BaseCommand):
    help = "Materializa las OTs reales de un mes desde las programaciones (ghost -> real)."

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int, required=True, help="Año (ej: 2026)")
        parser.add_argument("--month", type=int, required=True, help="Mes 1-12 (ej: 11 para noviembre)")
        parser.add_argument("--rutina-prefijo", type=str, default=None,
                            help="Solo programaciones cuya rutina.codigo_rutina empiece con este prefijo (ej: ASC)")
        parser.add_argument("--rutina-codigo", type=str, default=None,
                            help="Solo la programación de esta rutina exacta (ej: ASC-GENERAL)")
        parser.add_argument("--dry-run", action="store_true", help="No escribe en la BD; solo muestra el resumen.")

    def handle(self, *args, **opts):
        from mantenimiento.models import Programacion

        year = opts["year"]
        month = opts["month"]
        if not (1 <= month <= 12):
            raise CommandError("El mes debe estar entre 1 y 12.")

        last_day = calendar.monthrange(year, month)[1]
        fecha_corte = date(year, month, last_day)

        meses = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                 "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"Materializando OTs hasta {meses[month]} {year} (corte: {fecha_corte})"
        ))

        # Programaciones cuyo rango cubre el mes solicitado
        progs = Programacion.objects.filter(
            fecha_inicio__lte=fecha_corte
        ).filter(
            Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=date(year, month, 1))
        ).select_related("rutina")

        prefijo = opts.get("rutina_prefijo")
        codigo = opts.get("rutina_codigo")
        if codigo:
            progs = progs.filter(rutina__codigo_rutina=codigo)
        elif prefijo:
            progs = progs.filter(rutina__codigo_rutina__startswith=prefijo)

        if not progs.exists():
            self.stdout.write(self.style.WARNING(
                "No se encontraron programaciones que coincidan con los filtros. "
                "¿Existe la Programación de elevadores en el admin?"
            ))
            return

        dry = opts["dry_run"]
        total_generadas = 0
        total_progs = 0
        errores = []

        for prog in progs:
            rut_nombre = prog.rutina.nombre if prog.rutina else "¿sin rutina?"
            rut_cod = prog.rutina.codigo_rutina if prog.rutina else "-"

            if dry:
                self.stdout.write(
                    f"  [DRY] Prog #{prog.id} | {rut_cod} | {rut_nombre} | "
                    f"inicio={prog.fecha_inicio} fin={prog.fecha_fin or 's/f'} procesada={prog.procesada}"
                )
                continue

            try:
                # fecha_corte permite generar aunque esté marcada como 'procesada'
                c = prog.generar_ordenes(fecha_corte=fecha_corte)
                total_generadas += c
                total_progs += 1
                self.stdout.write(self.style.SUCCESS(
                    f"  ✓ Prog #{prog.id} ({rut_cod}): {c} OT(s) generadas."
                ))
            except Exception as e:
                errores.append(f"Prog #{prog.id} ({rut_cod}): {e}")
                self.stdout.write(self.style.ERROR(f"  ✗ Prog #{prog.id} ({rut_cod}): {e}"))

        if dry:
            self.stdout.write(self.style.WARNING(
                f"\nDRY-RUN: {progs.count()} programación(es) coinciden. No se escribió nada."
            ))
            return

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\nListo. {total_generadas} OT(s) generadas en {total_progs} programación(es)."
        ))
        if errores:
            self.stdout.write(self.style.ERROR("Errores:"))
            for e in errores:
                self.stdout.write(self.style.ERROR(f"  - {e}"))
