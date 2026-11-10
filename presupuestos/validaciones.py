"""Validaciones obligatorias de una Requisición antes de enviarla / generar OC."""


def es_servicio(req):
    """Los servicios son la única excepción: no exigen proveedor ni material."""
    return getattr(req, 'tipo', None) == 'SERVICIO'


def errores_requisicion(req):
    """Devuelve una lista de mensajes de error. Lista vacía = requisición completa."""
    from .services.solicitudes_alta import bloqueos_de_requisicion

    errores = []
    servicio = es_servicio(req)

    if not servicio and not req.proveedor_id:
        errores.append(
            'Debe seleccionar un proveedor (Paso 1). Si no existe, solicite su alta a Procura.')
    if servicio:
        faltan = [n for c, n in (('edificio_id', 'edificio'), ('nivel_id', 'nivel'), ('ubicacion_id', 'ubicación'))
                  if not getattr(req, c)]
        if faltan:
            errores.append(f"Para un servicio debe indicar: {', '.join(faltan)} (Paso 1).")

    articulos = list(req.articulos.select_related('material').all())
    if not articulos:
        errores.append('Debe agregar al menos un material o servicio (Paso 2).')
    for i, art in enumerate(articulos, start=1):
        nombre = (art.cr8ca_articulo or f'Artículo {i}')[:60]
        if not servicio and not art.material_id:
            errores.append(
                f'"{nombre}": debe ser un material del catálogo (Paso 2). '
                'Si no existe, solicite su alta a Almacén.')
        if not art.cr8ca_cantidad or art.cr8ca_cantidad <= 0:
            errores.append(f'"{nombre}": la cantidad debe ser mayor a 0 (Paso 2).')

    # Altas solicitadas y aún sin aprobar: no se puede continuar.
    errores.extend(bloqueos_de_requisicion(req))
    return errores


def asignar_proveedor_por_defecto(req):
    """Los artículos sin proveedor toman el proveedor de la requisición."""
    if req.proveedor_id:
        req.articulos.filter(proveedor__isnull=True).update(proveedor_id=req.proveedor_id)
