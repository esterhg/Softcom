from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from ..models import OrdenTrabajo, Aviso, TecnicoPuesto, Empresa, Rutina
from seguridad.models import TipoPermiso
from callcenter.models import SolicitudTicket, FallaTicket
from core.models import Departamento
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta

@staff_member_required
def mantenimiento_dashboard(request):
    """
    Dashboard principal premium para el módulo de Mantenimiento.
    Muestra métricas clave, OTs del día y avisos pendientes.
    """
    now = timezone.now()
    today = now.date()
    
    # Métricas de OTs activas (sin contar las finalizadas)
    activas_filter = Q(estado__in=['ESPERA', 'PROGRAMADA', 'EJECUCION'])
    
    ots_totales = OrdenTrabajo.objects.filter(activas_filter).count()
    ots_pendientes = OrdenTrabajo.objects.filter(estado='ESPERA').count()
    ots_ejecucion = OrdenTrabajo.objects.filter(estado='EJECUCION').count()
    
    ots_preventivas = OrdenTrabajo.objects.filter(activas_filter, tipo='PREVENTIVA').count()
    ots_correctivas = OrdenTrabajo.objects.filter(activas_filter, tipo='CORRECTIVA').count()
    
    # Avisos (Notificaciones de falla) - Solo los abiertos
    avisos_abiertos = Aviso.objects.filter(estado='ABIERTO').count()
    avisos_criticos = Aviso.objects.filter(estado='ABIERTO', prioridad='CRITICA').count()
    
    # Personal
    tecnicos_total = TecnicoPuesto.objects.count()
    tecnicos_disponibles = TecnicoPuesto.objects.filter(disponible=True).count()
    
    # OTs para hoy (proximas 24 horas o del calendario de hoy)
    # Incluye NO_PROGRAMADA sin filtro de fecha (siempre visibles)
    proximas_ots = OrdenTrabajo.objects.filter(
        Q(inicio_programado__date=today, estado__in=['ESPERA', 'PROGRAMADA', 'EJECUCION']) |
        Q(tipo='NO_PROGRAMADA')
    ).select_related('rutina', 'aviso', 'ubicacion', 'tecnico').order_by('inicio_programado')[:15]
    
    # Avisos recientes y críticos
    avisos_prioritarios = Aviso.objects.filter(
        estado__in=['ABIERTO', 'PROCESO']
    ).select_related('ubicacion', 'activo', 'solicitante').order_by('-prioridad', '-creado_en')[:8]

    # Datos para modal de creación de OTNP
    personales = TecnicoPuesto.objects.select_related('user', 'puesto', 'empresa').filter(esta_vigente=True).order_by('nombre')
    empresas = Empresa.objects.filter(activo=True).order_by('nombre')
    prioridades = OrdenTrabajo.PRIORIDAD_CHOICES
    tipos_permiso = TipoPermiso.objects.all().order_by('nombre')

    # Órdenes del departamento del usuario
    ots_mi_departamento = 0
    nombre_departamento = ""
    try:
        perfil = getattr(request.user, 'perfil', None)
        if perfil and perfil.departamento:
            nombre_departamento = perfil.departamento.nombre
            ots_mi_departamento = OrdenTrabajo.objects.filter(
                activas_filter,
                aviso__departamento=perfil.departamento
            ).count()
    except Exception:
        pass

    # Tickets abiertos del mes del departamento del usuario
    tickets_mi_depto = 0
    tickets_list = []
    inicio_mes = today.replace(day=1)
    try:
        perfil = getattr(request.user, 'perfil', None)
        if perfil and perfil.departamento:
            tickets_qs = SolicitudTicket.objects.filter(
                fecha_cierre__isnull=True, cierre_enviado=False,
                fecha_solicitud__gte=inicio_mes,
                falla_reportada__departamento_responsable=perfil.departamento
            ).select_related('ubicacion').order_by('-fecha_solicitud')[:50]
            tickets_mi_depto = tickets_qs.count()
            tickets_list = [
                {
                    'id': t.id,
                    'folio': t.folio or f"TKT-{t.id_solicitud}",
                    'solicitante': t.solicitante or '—',
                    'descripcion': (t.solicitud_descripcion or t.falla_descripcion or '')[:120],
                    'fecha': t.fecha_solicitud,
                    'ubicacion': t.ubicacion.nombre if t.ubicacion else '—',
                    'estado': 'Abierto',
                }
                for t in tickets_qs
            ]
    except Exception:
        pass

    context = {
        'title': 'Sistema de Gestión de Mantenimiento',
        'ots_totales': ots_totales,
        'ots_pendientes': ots_pendientes,
        'ots_ejecucion': ots_ejecucion,
        'ots_preventivas': ots_preventivas,
        'ots_correctivas': ots_correctivas,
        'ots_mi_departamento': ots_mi_departamento,
        'nombre_departamento': nombre_departamento,
        'avisos_abiertos': avisos_abiertos,
        'avisos_criticos': avisos_criticos,
        'tecnicos_total': tecnicos_total,
        'tecnicos_disponibles': tecnicos_disponibles,
        'proximas_ots': proximas_ots,
        'avisos_prioritarios': avisos_prioritarios,
        'personales': personales,
        'empresas': empresas,
        'prioridades': prioridades,
        'tipos_permiso': tipos_permiso,
        'tickets_mi_depto': tickets_mi_depto,
        'tickets_list': tickets_list,
    }
    
    return render(request, 'mantenimiento/dashboard.html', context)


@staff_member_required
def ordenes_lista_view(request):
    """Vista de listado de órdenes de trabajo con búsqueda avanzada y selección de columnas."""
    from django.db.models import Max

    q = request.GET.get('q', '')
    estado = request.GET.get('estado', '')
    tipo = request.GET.get('tipo', '')
    prioridad = request.GET.get('prioridad', '')
    rutina_id = request.GET.get('rutina', '').split(',')[0].strip()
    if rutina_id and not rutina_id.isdigit():
        rutina_id = ''

    ordenes = OrdenTrabajo.objects.select_related(
        'rutina', 'ubicacion', 'tecnico_puesto', 'empresa_responsable'
    ).order_by('-inicio_programado')

    if q:
        ordenes = ordenes.filter(
            Q(codigo_de_orden__icontains=q) |
            Q(descripcion_corta__icontains=q) |
            Q(descripcion_detallada__icontains=q) |
            Q(rutina__nombre__icontains=q) |
            Q(ubicacion__nombre__icontains=q)
        )
    if estado:
        ordenes = ordenes.filter(estado=estado)
    if tipo:
        ordenes = ordenes.filter(tipo=tipo)
    if prioridad:
        ordenes = ordenes.filter(prioridad=prioridad)
    if rutina_id:
        ordenes = ordenes.filter(rutina_id=rutina_id)

    # Filtro de rango de fechas
    fecha_desde = request.GET.get('fecha_desde', '')
    fecha_hasta = request.GET.get('fecha_hasta', '')
    
    # Validar que las fechas tengan un año razonable (>= 2020)
    if fecha_desde:
        try:
            from datetime import datetime as dt
            parsed = dt.strptime(fecha_desde, '%Y-%m-%d')
            if parsed.year < 2020:
                fecha_desde = ''
        except (ValueError, TypeError):
            fecha_desde = ''
    if fecha_hasta:
        try:
            from datetime import datetime as dt
            parsed = dt.strptime(fecha_hasta, '%Y-%m-%d')
            if parsed.year < 2020:
                fecha_hasta = ''
        except (ValueError, TypeError):
            fecha_hasta = ''
    
    if fecha_desde:
        ordenes = ordenes.filter(inicio_programado__date__gte=fecha_desde)
    if fecha_hasta:
        ordenes = ordenes.filter(inicio_programado__date__lte=fecha_hasta)

    # Rutinas para el selector
    rutinas = Rutina.objects.order_by('nombre').values_list('id', 'nombre')

    # Paginación
    from django.core.paginator import Paginator
    page_num = request.GET.get('page', '1')
    try:
        page_num = int(page_num)
    except (ValueError, TypeError):
        page_num = 1
    
    total = ordenes.count()
    paginator = Paginator(ordenes, 100)
    page_obj = paginator.get_page(page_num)

    context = {
        'ordenes': page_obj,
        'total': total,
        'page_obj': page_obj,
        'q': q,
        'estado_filter': estado,
        'tipo_filter': tipo,
        'prioridad_filter': prioridad,
        'rutina_filter': rutina_id,
        'rutinas': rutinas,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
    }
    return render(request, 'mantenimiento/ordenes_lista.html', context)


@staff_member_required
def ordenes_bulk_delete(request):
    """Eliminación masiva de órdenes de trabajo con verificación de contraseña (con gracia de 10 min)."""
    import json
    from django.http import JsonResponse
    from django.contrib.auth import authenticate
    from django.utils import timezone

    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)

    try:
        data = json.loads(request.body)
        password = data.get('password', '')
        orden_ids = data.get('ids', [])

        if not orden_ids:
            return JsonResponse({'status': 'error', 'message': 'No se seleccionaron órdenes.'}, status=400)

        # Check if password was verified recently (10-minute grace period)
        last_verified = request.session.get('bulk_delete_verified_at')
        now = timezone.now().timestamp()
        grace_period = 600  # 10 minutes

        if last_verified and (now - last_verified) < grace_period:
            # Within grace period — no password needed
            pass
        else:
            # Require password verification
            if not password:
                return JsonResponse({'status': 'error', 'message': 'Ingresa tu contraseña.'}, status=403)
            user = authenticate(username=request.user.username, password=password)
            if user is None:
                return JsonResponse({'status': 'error', 'message': 'Contraseña incorrecta.'}, status=403)
            # Store verification timestamp
            request.session['bulk_delete_verified_at'] = now

        # Eliminar las órdenes
        ordenes = OrdenTrabajo.objects.filter(id__in=orden_ids)
        count = ordenes.count()
        ordenes.delete()

        return JsonResponse({
            'status': 'success',
            'message': f'{count} orden(es) eliminada(s) correctamente.'
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@staff_member_required
def ordenes_bulk_status(request):
    """Cambio masivo de estado de órdenes de trabajo con fecha de finalización."""
    import json
    from django.http import JsonResponse
    from django.utils import timezone
    from datetime import datetime

    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)

    try:
        data = json.loads(request.body)
        ordenes_data = data.get('ordenes', [])

        if not ordenes_data:
            return JsonResponse({'status': 'error', 'message': 'No se enviaron órdenes.'}, status=400)

        updated = 0
        for item in ordenes_data:
            ot_id = item.get('id')
            nuevo_estado = item.get('estado')
            fecha_fin_str = item.get('fecha_fin', '')

            if not ot_id or not nuevo_estado:
                continue

            try:
                ot = OrdenTrabajo.objects.get(id=ot_id)
                if nuevo_estado in dict(OrdenTrabajo.ESTADO_CHOICES):
                    ot.estado = nuevo_estado
                    if nuevo_estado == 'REALIZADA' and fecha_fin_str:
                        try:
                            ot.fin_programado = datetime.strptime(fecha_fin_str, '%Y-%m-%d')
                        except ValueError:
                            pass
                    if nuevo_estado == 'EJECUCION' and not ot.fecha_ejecucion:
                        ot.fecha_ejecucion = timezone.now()
                    ot.save()
                    updated += 1
            except OrdenTrabajo.DoesNotExist:
                continue

        return JsonResponse({
            'status': 'success',
            'message': f'{updated} orden(es) actualizada(s) correctamente.'
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@staff_member_required
def ot_reporte_html(request, pk):
    """Reporte HTML imprimible completo de una Orden de Trabajo."""
    from ..models import OrdenTrabajo
    from django.shortcuts import get_object_or_404

    ot = get_object_or_404(
        OrdenTrabajo.objects.select_related(
            'rutina', 'ubicacion', 'tecnico', 'tecnico_puesto',
            'empresa_responsable', 'aviso', 'cierre'
        ).prefetch_related(
            'activos', 'archivos', 'colaboradores_puesto',
            'solicitudes_material__items__material__unidad_medida',
            'resultados_checklist__paso'
        ),
        pk=pk
    )

    # Pasos de rutina con resultados
    pasos = []
    if ot.rutina:
        pasos_qs = ot.rutina.pasos.all().order_by('orden')
        resultados_dict = {r.paso_id: r for r in ot.resultados_checklist.all()}
        for p in pasos_qs:
            p.resultado = resultados_dict.get(p.id)
            pasos.append(p)

    context = {
        'ot': ot,
        'pasos': pasos,
        'cierre': getattr(ot, 'cierre', None),
        'archivos': ot.archivos.all().order_by('momento', '-creado_en'),
        'solicitudes': ot.solicitudes_material.prefetch_related('items__material__unidad_medida').all(),
        'activos': ot.activos.all(),
        'colaboradores': ot.colaboradores_puesto.all(),
    }
    return render(request, 'mantenimiento/ot_reporte_html.html', context)


@staff_member_required
def export_ordenes_excel(request):
    """
    Descarga un archivo Excel con todas las órdenes de trabajo que coincidan
    con los filtros activos del listado (/mantenimiento/ordenes/).
    Los parámetros GET son los mismos que ordenes_lista_view.
    """
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    from django.http import HttpResponse
    from django.db.models import Q
    from django.utils import timezone
    from datetime import datetime as dt

    # ── Replicar los filtros del listado ──────────────────────────────────────
    q         = request.GET.get('q', '')
    estado    = request.GET.get('estado', '')
    tipo      = request.GET.get('tipo', '')
    prioridad = request.GET.get('prioridad', '')
    rutina_id = request.GET.get('rutina', '').split(',')[0].strip()
    if rutina_id and not rutina_id.isdigit():
        rutina_id = ''

    fecha_desde = request.GET.get('fecha_desde', '')
    fecha_hasta = request.GET.get('fecha_hasta', '')

    def _valid_date(s):
        try:
            p = dt.strptime(s, '%Y-%m-%d')
            return s if p.year >= 2020 else ''
        except (ValueError, TypeError):
            return ''

    fecha_desde = _valid_date(fecha_desde)
    fecha_hasta = _valid_date(fecha_hasta)

    ordenes = OrdenTrabajo.objects.select_related(
        'rutina', 'ubicacion', 'tecnico_puesto', 'empresa_responsable', 'cierre'
    ).prefetch_related('activos').order_by('-inicio_programado')

    if q:
        ordenes = ordenes.filter(
            Q(codigo_de_orden__icontains=q) |
            Q(descripcion_corta__icontains=q) |
            Q(descripcion_detallada__icontains=q) |
            Q(rutina__nombre__icontains=q) |
            Q(ubicacion__nombre__icontains=q)
        )
    if estado:
        ordenes = ordenes.filter(estado=estado)
    if tipo:
        ordenes = ordenes.filter(tipo=tipo)
    if prioridad:
        ordenes = ordenes.filter(prioridad=prioridad)
    if rutina_id:
        ordenes = ordenes.filter(rutina_id=rutina_id)
    if fecha_desde:
        ordenes = ordenes.filter(inicio_programado__date__gte=fecha_desde)
    if fecha_hasta:
        ordenes = ordenes.filter(inicio_programado__date__lte=fecha_hasta)

    # ── Crear el workbook ─────────────────────────────────────────────────────
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Órdenes de Trabajo"

    # Estilos
    header_fill   = PatternFill("solid", fgColor="354A5F")   # azul shell SAP
    header_font   = Font(name="Calibri", bold=True, color="FFFFFF", size=10)
    header_align  = Alignment(horizontal="center", vertical="center", wrap_text=True)
    cell_align    = Alignment(vertical="center", wrap_text=False)
    thin          = Side(style="thin", color="D9D9D9")
    cell_border   = Border(left=thin, right=thin, top=thin, bottom=thin)

    status_colors = {
        'ESPERA':     'FEF7E0',
        'PROGRAMADA': 'E8F0FE',
        'EJECUCION':  'FFF3CD',
        'REALIZADA':  'E6F4EA',
        'CANCELADA':  'F1F3F4',
    }
    prio_colors = {
        'BAJA':    'F1F5F9',
        'MEDIA':   'EFF6FF',
        'ALTA':    'FEF2F2',
        'CRITICA': '7F1D1D',
    }

    # ── Encabezados ───────────────────────────────────────────────────────────
    headers = [
        "Código OT", "Tipo", "Prioridad", "Estado",
        "Descripción", "Rutina", "Ubicación",
        "Técnico / Responsable", "Empresa",
        "Inicio Programado", "Fin Programado",
        "Fecha Ejecución", "Activos",
        "HH Reales", "Comentarios Cierre",
        "Creado En",
    ]
    col_widths = [16, 14, 11, 14, 35, 30, 25, 22, 22, 18, 18, 18, 30, 10, 40, 18]

    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font   = header_font
        cell.fill   = header_fill
        cell.alignment = header_align
        cell.border = cell_border
        ws.column_dimensions[get_column_letter(col_idx)].width = col_widths[col_idx - 1]

    ws.row_dimensions[1].height = 28
    ws.freeze_panes = "A2"

    # ── Filas de datos ────────────────────────────────────────────────────────
    tz_local = timezone.get_current_timezone()

    def fmt_dt(value):
        if not value:
            return ""
        local = timezone.localtime(value, tz_local) if timezone.is_aware(value) else value
        return local.strftime("%d/%m/%Y %H:%M")

    for row_idx, ot in enumerate(ordenes, start=2):
        cierre = getattr(ot, 'cierre', None)
        activos_str = ", ".join(a.codigo_interno or a.nombre for a in ot.activos.all()) or "—"

        row_data = [
            ot.codigo_de_orden or "—",
            ot.get_tipo_display(),
            ot.get_prioridad_display(),
            ot.get_estado_display(),
            ot.descripcion_corta or "—",
            ot.rutina.nombre if ot.rutina else "—",
            str(ot.ubicacion) if ot.ubicacion else "—",
            str(ot.tecnico_puesto) if ot.tecnico_puesto else (
                ot.tecnico.get_full_name() or ot.tecnico.username if ot.tecnico else "—"
            ),
            str(ot.empresa_responsable) if ot.empresa_responsable else "—",
            fmt_dt(ot.inicio_programado),
            fmt_dt(ot.fin_programado),
            fmt_dt(ot.fecha_ejecucion),
            activos_str,
            cierre.horas_hombre if cierre else "",
            cierre.comentarios or "" if cierre else "",
            fmt_dt(ot.creado_en),
        ]

        for col_idx, value in enumerate(row_data, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.alignment = cell_align
            cell.border    = cell_border
            cell.font      = Font(name="Calibri", size=9)

        # Color de fondo por estado (columna 4)
        estado_color = status_colors.get(ot.estado)
        if estado_color:
            ws.cell(row=row_idx, column=4).fill = PatternFill("solid", fgColor=estado_color)

        # Color de fondo por prioridad (columna 3)
        prio_color = prio_colors.get(ot.prioridad)
        if prio_color:
            ws.cell(row=row_idx, column=3).fill = PatternFill("solid", fgColor=prio_color)

        # Texto blanco para prioridad CRITICA
        if ot.prioridad == 'CRITICA':
            ws.cell(row=row_idx, column=3).font = Font(name="Calibri", size=9, color="FFFFFF", bold=True)

        # Filas alternadas
        if row_idx % 2 == 0:
            for col_idx in range(1, len(headers) + 1):
                existing = ws.cell(row=row_idx, column=col_idx).fill
                if existing.fill_type == "none" or not existing.fgColor.rgb or existing.fgColor.rgb == "00000000":
                    ws.cell(row=row_idx, column=col_idx).fill = PatternFill("solid", fgColor="F7F7F7")

    # ── Autofilter en encabezados ─────────────────────────────────────────────
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}1"

    # ── Metadata y nombre de archivo ─────────────────────────────────────────
    total_rows = row_idx - 1 if len(list(ordenes)) > 0 else 0  # approximate

    # Segunda hoja: resumen de filtros aplicados
    ws_meta = wb.create_sheet(title="Filtros Aplicados")
    ws_meta.column_dimensions["A"].width = 25
    ws_meta.column_dimensions["B"].width = 40
    meta_header_fill = PatternFill("solid", fgColor="0A6ED1")
    meta_rows = [
        ("Parámetro", "Valor"),
        ("Generado el", dt.now().strftime("%d/%m/%Y %H:%M")),
        ("Generado por", request.user.get_full_name() or request.user.username),
        ("Búsqueda (q)", q or "—"),
        ("Estado", estado or "Todos"),
        ("Tipo", tipo or "Todos"),
        ("Prioridad", prioridad or "Todas"),
        ("Rutina ID", rutina_id or "—"),
        ("Fecha desde", fecha_desde or "—"),
        ("Fecha hasta", fecha_hasta or "—"),
    ]
    for r_idx, (k, v) in enumerate(meta_rows, start=1):
        ws_meta.cell(row=r_idx, column=1, value=k).font = Font(
            bold=True, color="FFFFFF" if r_idx == 1 else "32363A", name="Calibri", size=10
        )
        ws_meta.cell(row=r_idx, column=2, value=str(v)).font = Font(name="Calibri", size=10)
        if r_idx == 1:
            ws_meta.cell(row=r_idx, column=1).fill = meta_header_fill
            ws_meta.cell(row=r_idx, column=2).fill = meta_header_fill
            ws_meta.cell(row=r_idx, column=2).font = Font(bold=True, color="FFFFFF", name="Calibri", size=10)

    # ── Respuesta HTTP ────────────────────────────────────────────────────────
    filename = "ordenes_trabajo_{}.xlsx".format(dt.now().strftime("%Y%m%d_%H%M%S"))
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response
