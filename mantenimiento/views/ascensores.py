# -*- coding: utf-8 -*-
"""
Flujo de mantenimiento de ASCENSORES.

- Supervisor: crea el mantenimiento eligiendo el ascensor + fecha + técnico y
  marcando qué rutinas (protocolos) ejecutar. Se genera UNA OT por rutina marcada.
- Técnico: llena el checklist y firma (reutiliza la vista mobile_ot_finalizar).
- PDF: formato estilo TKE (sin logo TKE), descargable.
"""
from datetime import timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone

from activos.models import Activo, Categoria, Ubicacion
from ..models import OrdenTrabajo, Rutina, TecnicoPuesto


# Nombres aceptados para la categoría de activo de ascensores/elevadores.
# El primero es el preferido; se buscan todos (case-insensitive) por si la
# instalación los nombró distinto.
CATEGORIAS_ASCENSORES = ["ELEVADORES", "Ascensores", "Elevadores", "ASCENSORES"]


def _categoria_ascensores():
    for nombre in CATEGORIAS_ASCENSORES:
        cat = Categoria.objects.filter(nombre__iexact=nombre).first()
        if cat:
            return cat
    return None


def _activos_ascensores(cat):
    """
    Activos de ascensores. Un activo pertenece a la categoría a través de su
    modelo (Activo.modelo.categoria). Se incluye toda la subjerarquía de la
    categoría 'Ascensores' (por si hay subcategorías).
    """
    if not cat:
        return Activo.objects.none()
    try:
        cats = cat.get_descendants(include_self=True)
    except Exception:  # noqa
        cats = Categoria.objects.filter(pk=cat.pk)
    return (Activo.objects
            .filter(modelo__categoria__in=cats)
            .select_related("ubicacion", "modelo")
            .order_by("nombre"))


def _rutinas_ascensores():
    """Rutinas de la categoría Ascensores (las 6 cargadas por seed_ascensores)."""
    cat = _categoria_ascensores()
    qs = Rutina.objects.filter(codigo_rutina__startswith="ASC-").order_by("codigo_rutina")
    if not qs.exists() and cat:
        qs = Rutina.objects.filter(categoria_activo=cat).order_by("codigo_rutina")
    return qs


# Qué protocolo (codigo_rutina) corresponde a cada mes (plan rotativo anual)
PLAN_ANUAL = {
    1: "ASC-LIMPIEZA", 5: "ASC-LIMPIEZA", 9: "ASC-LIMPIEZA",
    2: "ASC-SEGURIDAD-I",
    3: "ASC-PUERTA", 7: "ASC-PUERTA", 11: "ASC-PUERTA",
    4: "ASC-COMANDO", 10: "ASC-COMANDO",
    6: "ASC-MAQUINARIA", 12: "ASC-MAQUINARIA",
    8: "ASC-SEGURIDAD-II",
}


@staff_member_required
def crear_mantenimiento_ascensor(request):
    """
    Pantalla del supervisor: elige ascensor, fecha, técnico y marca las rutinas.
    Crea 1 OT por rutina marcada.
    """
    cat = _categoria_ascensores()
    rutinas = list(_rutinas_ascensores())

    if request.method == "POST":
        activo_id = request.POST.get("activo")
        ubicacion_id = request.POST.get("ubicacion")
        tecnico_id = request.POST.get("tecnico")
        fecha_str = request.POST.get("fecha")  # YYYY-MM-DD
        rutinas_ids = request.POST.getlist("rutinas")

        if not rutinas_ids:
            return JsonResponse({"status": "error", "message": "Debe seleccionar al menos una rutina."}, status=400)

        activo = Activo.objects.filter(pk=activo_id).first() if activo_id else None
        ubicacion = Ubicacion.objects.filter(pk=ubicacion_id).first() if ubicacion_id else None
        if activo and not ubicacion:
            ubicacion = activo.ubicacion
        tecnico_puesto = TecnicoPuesto.objects.filter(pk=tecnico_id).first() if tecnico_id else None

        # Fecha/hora de inicio programado
        inicio = timezone.now()
        if fecha_str:
            try:
                d = timezone.datetime.strptime(fecha_str, "%Y-%m-%d")
                inicio = timezone.make_aware(d.replace(hour=8, minute=0))
            except ValueError:
                pass

        creadas = []
        for rid in rutinas_ids:
            rutina = Rutina.objects.filter(pk=rid).first()
            if not rutina:
                continue
            duracion = rutina.tiempo_estimado or timedelta(hours=2)
            ot = OrdenTrabajo.objects.create(
                tipo="PREVENTIVA",
                rutina=rutina,
                ubicacion=ubicacion,
                tecnico_puesto=tecnico_puesto,
                supervisor=request.user,
                estado="PROGRAMADA",
                inicio_programado=inicio,
                fin_programado=inicio + duracion,
                descripcion_corta=f"Mantenimiento ascensor: {rutina.nombre}",
            )
            if activo:
                ot.activos.add(activo)
            creadas.append({"id": ot.id, "codigo": ot.codigo_de_orden, "rutina": rutina.nombre})

        return JsonResponse({
            "status": "success",
            "message": f"Se crearon {len(creadas)} orden(es) de trabajo.",
            "ordenes": creadas,
        })

    # GET → render form
    activos = _activos_ascensores(cat)

    ubicaciones = Ubicacion.objects.all().order_by("nombre")
    tecnicos = TecnicoPuesto.objects.filter(esta_vigente=True).order_by("nombre", "apellido")

    mes_actual = timezone.now().month
    codigo_sugerido = PLAN_ANUAL.get(mes_actual)

    rutinas_ctx = []
    for r in rutinas:
        rutinas_ctx.append({
            "obj": r,
            "sugerida": r.codigo_rutina == codigo_sugerido,
            "n_pasos": r.pasos.exclude(tipo_respuesta="HEADER").count(),
        })

    meses_nombre = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

    return render(request, "mantenimiento/ascensores_crear.html", {
        "categoria": cat,
        "activos": activos,
        "ubicaciones": ubicaciones,
        "tecnicos": tecnicos,
        "rutinas": rutinas_ctx,
        "mes_actual_nombre": meses_nombre[mes_actual],
        "hoy": timezone.now().date().isoformat(),
    })


@staff_member_required
def ascensor_pdf(request, ot_id):
    """Genera y devuelve el PDF del reporte de ascensor (formato estilo TKE sin logo TKE)."""
    from ..utils.pdf_ascensores import generate_ascensor_pdf_bytes

    ot = get_object_or_404(OrdenTrabajo, pk=ot_id)
    try:
        pdf_bytes = generate_ascensor_pdf_bytes(ot, request=request)
    except Exception as e:  # noqa
        import logging
        logging.getLogger(__name__).error("Error generando PDF ascensor OT %s: %s", ot_id, e, exc_info=True)
        return JsonResponse({"status": "error", "message": str(e)}, status=500)

    filename = f"Reporte_Ascensor_{ot.codigo_de_orden or ot.id}.pdf"
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    disp = "attachment" if request.GET.get("download") else "inline"
    resp["Content-Disposition"] = f'{disp}; filename="{filename}"'
    return resp
