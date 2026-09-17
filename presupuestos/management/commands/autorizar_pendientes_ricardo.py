from django.core.management.base import BaseCommand
from django.utils import timezone
from presupuestos.models import Requisicion, RequisicionHistorial

# Requisiciones en PENDIENTE que ya fueron aprobadas por Ricardo Zerrate
# pero el flujo antiguo (dos aprobadores) nunca recibió el APROBAR final.
# Este comando las mueve a AUTORIZADO y registra el evento en el historial.

APROBADOR_NOMBRE = "Ricardo Enrique Zerrate Torres"
KEYWORDS = ["Ricardo", "Zerrate", "APROBACION_PARCIAL"]


class Command(BaseCommand):
    help = (
        "Mueve a AUTORIZADO las requisiciones en PENDIENTE que ya tienen "
        "aprobación de Ricardo Zerrate en su historial."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo muestra qué requisiciones se verían afectadas, sin hacer cambios.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        pendientes = Requisicion.objects.filter(estado_requisicion='PENDIENTE')
        self.stdout.write(f"Requisiciones en PENDIENTE: {pendientes.count()}")

        afectadas = 0
        omitidas = 0

        for req in pendientes:
            # Buscar en el historial alguna entrada que mencione a Ricardo
            tiene_aprobacion = req.historial.filter(
                **{'descripcion__' + 'icontains': kw}
            ).exists() if False else any(
                req.historial.filter(descripcion__icontains=kw).exists()
                for kw in KEYWORDS
            )

            if not tiene_aprobacion:
                omitidas += 1
                self.stdout.write(f"  OMITIDA  {req.cr8ca_requisicion} — sin aprobación de Ricardo en historial")
                continue

            afectadas += 1
            if dry_run:
                self.stdout.write(
                    self.style.WARNING(f"  DRY-RUN  {req.cr8ca_requisicion} → se movería a AUTORIZADO")
                )
                continue

            # Registrar en historial
            RequisicionHistorial.objects.create(
                requisicion=req,
                estado_anterior='PENDIENTE',
                estado_nuevo='AUTORIZADO',
                usuario=None,
                descripcion=(
                    f"Autorizado retroactivamente — {APROBADOR_NOMBRE} ya había aprobado "
                    f"(flujo anterior requería dos aprobadores). Corregido el "
                    f"{timezone.now().strftime('%d/%m/%Y %H:%M')}."
                ),
            )

            req.estado_requisicion = 'AUTORIZADO'
            req.fecha_aprobacion = req.fecha_aprobacion or timezone.now()
            req.save(update_fields=['estado_requisicion', 'fecha_aprobacion'])

            self.stdout.write(
                self.style.SUCCESS(f"  AUTORIZADA  {req.cr8ca_requisicion}")
            )

        self.stdout.write("")
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"DRY-RUN completado: {afectadas} se moverían a AUTORIZADO, {omitidas} omitidas."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"Listo: {afectadas} requisiciones autorizadas, {omitidas} omitidas."
            ))
