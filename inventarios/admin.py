from django.contrib import admin
from django.contrib import messages
from django.urls import path, reverse
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.html import mark_safe
from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget
from import_export.admin import ImportExportModelAdmin
from .models import Material, StockRecord, MovimientoInventario, CategoriaMaterial, SolicitudMaterial, Lote, UnidadMedida, IngresoInventario, Rack, RackPosition, MaterialUtilizadoOT
from activos.models import Marca

class StockRecordInline(admin.TabularInline):
    model = StockRecord
    extra = 0
    max_num = 10
    can_delete = False
    raw_id_fields = ('lote', 'ubicacion')
    readonly_fields = ('material', 'actualizado_en')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('lote', 'ubicacion')

@admin.register(CategoriaMaterial)
class CategoriaMaterialAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'padre', 'codigo_exoneracion')
    search_fields = ('nombre',)
    list_filter = ('padre', 'codigo_exoneracion')
    raw_id_fields = ('codigo_exoneracion',)

@admin.register(Lote)
class LoteAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'material', 'fecha_vencimiento', 'fecha_fabricacion')
    search_fields = ('codigo', 'material__nombre', 'material__sku')
    list_filter = ('fecha_vencimiento',)

@admin.register(UnidadMedida)
class UnidadMedidaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'abreviatura')
    search_fields = ('nombre', 'abreviatura')

class MovimientoInventarioInline(admin.TabularInline):
    model = MovimientoInventario
    extra = 0
    max_num = 15
    show_change_link = True
    raw_id_fields = ('material', 'ubicacion_origen', 'ubicacion_destino', 'lote', 'orden_trabajo')
    exclude = ('devolucion', 'aprobado_por', 'fecha_aprobacion', 'es_inconsistente')
    readonly_fields = ('fecha_movimiento', 'estado', 'usuario')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'material', 'material__unidad_medida', 'usuario', 'lote',
            'ubicacion_origen', 'ubicacion_destino'
        )

@admin.register(SolicitudMaterial)
class SolicitudMaterialAdmin(admin.ModelAdmin):
    list_display = ('id', 'boton_fiori', 'usuario', 'fecha_solicitud', 'estado', 'ubicacion_origen', 'orden_trabajo', 'comentarios_cortos')
    list_filter = ('estado',)
    search_fields = ('id', 'usuario__username', 'usuario__first_name', 'usuario__last_name', 'comentarios_solicitud')
    raw_id_fields = ('usuario', 'ubicacion_origen', 'orden_trabajo', 'ticket', 'edificio_destino', 'nivel_destino')
    list_select_related = ('usuario', 'ubicacion_origen', 'orden_trabajo')
    list_per_page = 30
    inlines = [MovimientoInventarioInline]
    change_form_template = 'admin/inventarios/solicitudmaterial/change_form.html'

    def boton_fiori(self, obj):
        from django.utils.html import mark_safe
        url = f'/inventarios/solicitud/{obj.id}/detalle/'
        return mark_safe(
            f'<a href="{url}" target="_blank" style="padding:3px 8px; background:#0a6ed1; color:white; '
            f'font-size:0.7rem; font-weight:700; text-decoration:none; display:inline-block;">📋 Ver</a>'
        )
    boton_fiori.short_description = ''

    def comentarios_cortos(self, obj):
        if obj.comentarios_solicitud:
            return obj.comentarios_solicitud[:60] + ('...' if len(obj.comentarios_solicitud) > 60 else '')
        return '-'
    comentarios_cortos.short_description = 'Comentarios'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('usuario', 'ubicacion_origen', 'orden_trabajo')

@admin.register(IngresoInventario)
class IngresoInventarioAdmin(admin.ModelAdmin):
    list_display = ('id', 'fecha_ingreso', 'usuario', 'ubicacion_destino', 'get_requisicion')
    list_filter = ('fecha_ingreso', 'usuario', 'ubicacion_destino')
    search_fields = ('usuario__username', 'requisicion_origen__cr8ca_requisicion', 'comentarios')
    inlines = [MovimientoInventarioInline]

    def get_requisicion(self, obj):
        return obj.requisicion_origen.cr8ca_requisicion if obj.requisicion_origen else "--"
    get_requisicion.short_description = "Requisición"

class MaterialResource(resources.ModelResource):
    categoria = fields.Field(
        column_name='categoria',
        attribute='categoria',
        widget=ForeignKeyWidget(CategoriaMaterial, 'nombre')
    )
    marca = fields.Field(
        column_name='marca',
        attribute='marca',
        widget=ForeignKeyWidget(Marca, 'nombre')
    )
    unidad_medida = fields.Field(
        column_name='unidad_medida',
        attribute='unidad_medida',
        widget=ForeignKeyWidget(UnidadMedida, 'nombre')
    )
    # Campos virtuales (no son columnas del modelo). Permiten descargar el stock
    # actual, editarlo y volver a importar para que el sistema haga el AJUSTE.
    stock_actual = fields.Field(column_name='stock_actual')
    ubicacion = fields.Field(column_name='ubicacion')

    class Meta:
        model = Material
        import_id_fields = ('sku',)
        fields = (
            'id', 'sku', 'nombre', 'codigo_barras', 'marca', 'descripcion',
            'categoria', 'tipo_material', 'unidad_medida', 'precio_estimado',
            'stock_minimo', 'alto', 'ancho', 'peso', 'profundidad',
            'no_afecta_stock', 'es_tecnico', 'stock_actual', 'ubicacion', 'imagen'
        )
        export_order = fields
        skip_unchanged = True
        report_skipped = True

    def dehydrate_stock_actual(self, obj):
        """Exporta el stock total actual del material (suma de todas sus existencias)."""
        if not getattr(obj, 'pk', None):
            return ''
        if getattr(obj, 'no_afecta_stock', False):
            return ''
        from django.db.models import Sum
        total = obj.existencias.aggregate(total=Sum('cantidad'))['total']
        return total if total is not None else 0

    def dehydrate_ubicacion(self, obj):
        """
        Exporta la bodega donde el material tiene mayor stock, para que al
        re-importar el ajuste se aplique sobre esa misma ubicación.
        """
        if not getattr(obj, 'pk', None):
            return ''
        rec = obj.existencias.select_related('ubicacion').order_by('-cantidad').first()
        if rec and rec.ubicacion:
            return rec.ubicacion.nombre
        return ''

    def __init__(self, name_conflict_policy='update', **kwargs):
        """
        name_conflict_policy controla qué hacer cuando una fila NUEVA (sin SKU ni
        código de barras coincidente) trae un 'nombre' que ya existe en la base:
          - 'update' (por defecto): actualizar el material existente con ese nombre.
          - 'skip': ignorar la fila para no tocar el material existente.
        """
        super().__init__(**kwargs)
        self._instances_cache = {}
        self.name_conflict_policy = name_conflict_policy
        # SKUs de filas que se deben omitir por decisión del usuario (política 'skip')
        self._skipped_name_conflicts = set()

    def _clean_sku_string(self, val):
        if val is None:
            return None
        val_str = str(val).strip()
        if not val_str or val_str.lower() in ['none', 'nan', 'null', '']:
            return None
        if val_str.endswith('.0') and val_str[:-2].isdigit():
            val_str = val_str[:-2]
        return val_str

    @staticmethod
    def _norm_nombre(val):
        """
        Normalización SUAVE del nombre para comparar duplicados de forma segura:
        - quita espacios en los extremos (strip)
        - colapsa secuencias de espacios/tabs internos a un solo espacio
        - case-insensitive (lower)
        Ej: '  Cuchillo   Mesa ' -> 'cuchillo mesa'
        """
        if val is None:
            return ''
        import re
        s = str(val).strip()
        s = re.sub(r'\s+', ' ', s)
        return s.lower()

    @staticmethod
    def _norm_nombre_agresivo(val):
        """
        Normalización AGRESIVA: elimina TODOS los espacios y pasa a minúsculas.
        Solo se usa para DETECTAR posibles duplicados y advertir al usuario,
        nunca para unificar automáticamente.
        Ej: '( cuchillo)' -> '(cuchillo)'
        """
        if val is None:
            return ''
        import re
        return re.sub(r'\s+', '', str(val)).lower()

    def _cache_instance(self, obj):
        if not hasattr(self, '_instances_cache'):
            self._instances_cache = {}
        if not obj:
            return
        if getattr(obj, 'id', None):
            self._instances_cache[f"id:{obj.id}"] = obj
        if getattr(obj, 'sku', None):
            self._instances_cache[f"sku:{str(obj.sku).strip().lower()}"] = obj
        if getattr(obj, 'codigo_barras', None):
            self._instances_cache[f"cb:{str(obj.codigo_barras).strip().lower()}"] = obj
        if getattr(obj, 'nombre', None):
            self._instances_cache[f"nom:{self._norm_nombre(obj.nombre)}"] = obj

    def before_import(self, dataset, **kwargs):
        """
        Normaliza los encabezados del archivo Excel o CSV para aceptar variaciones,
        mayúsculas/minúsculas, tildes y nombres alternativos comunes.
        """
        self._instances_cache = {}
        if dataset.headers:
            header_map = {
                # SKU / Código
                'sku': 'sku',
                'sku / código interno': 'sku',
                'sku / codigo interno': 'sku',
                'código interno': 'sku',
                'codigo interno': 'sku',
                'código': 'sku',
                'codigo': 'sku',
                'cod': 'sku',
                'item_code': 'sku',
                'clave': 'sku',
                # ID
                'id': 'id',
                # Nombre
                'nombre': 'nombre',
                'nombre del material': 'nombre',
                'material': 'nombre',
                'producto': 'nombre',
                'artículo': 'nombre',
                'articulo': 'nombre',
                'item': 'nombre',
                # Marca
                'marca': 'marca',
                'brand': 'marca',
                # Categoría
                'categoria': 'categoria',
                'categoría': 'categoria',
                'category': 'categoria',
                # Unidad de medida
                'unidad_medida': 'unidad_medida',
                'unidad de medida': 'unidad_medida',
                'unidad': 'unidad_medida',
                'uom': 'unidad_medida',
                'medida': 'unidad_medida',
                # Código de barras
                'codigo_barras': 'codigo_barras',
                'código de barras': 'codigo_barras',
                'codigo de barras': 'codigo_barras',
                'barcode': 'codigo_barras',
                'upc': 'codigo_barras',
                'ean': 'codigo_barras',
                # Tipo de material
                'tipo_material': 'tipo_material',
                'tipo de material': 'tipo_material',
                'tipo': 'tipo_material',
                # Precio
                'precio_estimado': 'precio_estimado',
                'precio': 'precio_estimado',
                'precio estimado': 'precio_estimado',
                'costo': 'precio_estimado',
                'costo estimado': 'precio_estimado',
                'precio unitario': 'precio_estimado',
                'precio_unitario': 'precio_estimado',
                # Stock mínimo
                'stock_minimo': 'stock_minimo',
                'stock mínimo': 'stock_minimo',
                'stock min': 'stock_minimo',
                'stock_min': 'stock_minimo',
                'minimo': 'stock_minimo',
                'mínimo': 'stock_minimo',
                # Descripción
                'descripcion': 'descripcion',
                'descripción': 'descripcion',
                'description': 'descripcion',
                'detalles': 'descripcion',
                # Dimensiones
                'alto': 'alto',
                'altura': 'alto',
                'ancho': 'ancho',
                'anchura': 'ancho',
                'peso': 'peso',
                'profundidad': 'profundidad',
                # Banderas
                'no_afecta_stock': 'no_afecta_stock',
                'es_tecnico': 'es_tecnico',
                'es técnico': 'es_tecnico',
                # Stock inicial / Ubicación
                'stock_actual': 'stock_actual',
                'stock actual': 'stock_actual',
                'existencia actual': 'stock_actual',
                'inventario': 'stock_actual',
                'stock_inicial': 'stock_inicial',
                'cantidad_inicial': 'stock_inicial',
                'existencias': 'stock_inicial',
                'stock': 'stock_inicial',
                'ubicacion': 'ubicacion',
                'ubicación': 'ubicacion',
                'bodega': 'ubicacion',
                'almacen': 'ubicacion',
                'almacén': 'ubicacion',
                'lote': 'lote',
                'lote_codigo': 'lote_codigo',
                'vencimiento': 'lote_vencimiento',
                'lote_vencimiento': 'lote_vencimiento',
                'fecha_vencimiento': 'lote_vencimiento',
                'modelos_compatibles': 'modelos_compatibles',
                'repuesto_para': 'modelos_compatibles',
                'equipos': 'modelos_compatibles',
            }
            new_headers = []
            for h in dataset.headers:
                if h is None:
                    new_headers.append(h)
                    continue
                clean_h = str(h).strip().lower()
                new_headers.append(header_map.get(clean_h, clean_h))
            dataset.headers = new_headers
        super().before_import(dataset, **kwargs)

    @staticmethod
    def detectar_conflictos_nombre(dataset):
        """
        Recorre el dataset (ya normalizado por before_import) y clasifica las filas
        en dos grupos para el preview:

        1) 'conflictos' (conflicto por nombre - normalización SUAVE):
           la fila NO coincide por SKU ni código de barras, pero su nombre ya existe
           (comparando con strip + espacios colapsados + minúsculas).
           Estas entran al flujo "actualizar / ignorar".

        2) 'posibles_espacios' (ADVERTENCIA - normalización AGRESIVA):
           la fila NO es un conflicto suave, pero si se ignoran TODOS los espacios su
           nombre coincide con uno existente (ej. '( cuchillo)' vs '(cuchillo)').
           Solo se muestran como aviso; NO se unifican automáticamente.

        Retorna: {'conflictos': [...], 'posibles_espacios': [...]}
        """
        helper = MaterialResource()

        # Precargar materiales existentes una sola vez (id, sku, nombre)
        existentes = list(Material.objects.values('id', 'sku', 'nombre'))
        mapa_suave = {}       # nombre normalizado suave -> sku
        mapa_agresivo = {}    # nombre normalizado agresivo -> (sku, nombre_original)
        for m in existentes:
            ns = helper._norm_nombre(m['nombre'])
            na = helper._norm_nombre_agresivo(m['nombre'])
            if ns and ns not in mapa_suave:
                mapa_suave[ns] = m['sku']
            if na and na not in mapa_agresivo:
                mapa_agresivo[na] = (m['sku'], m['nombre'])

        skus_existentes = {str(m['sku']).strip().lower() for m in existentes if m['sku']}

        conflictos = []
        posibles_espacios = []
        for i, row in enumerate(dataset.dict, start=1):
            sku = helper._clean_sku_string(row.get('sku'))
            cb = helper._clean_sku_string(row.get('codigo_barras'))
            nombre = str(row.get('nombre') or '').strip()

            # Si coincide por SKU o código de barras existente, es actualización normal
            if sku and sku.lower() in skus_existentes:
                continue
            if cb and Material.objects.filter(codigo_barras__iexact=cb).exists():
                continue
            if not nombre:
                continue

            ns = helper._norm_nombre(nombre)
            na = helper._norm_nombre_agresivo(nombre)

            if ns in mapa_suave:
                # Conflicto por nombre "real" -> flujo actualizar/ignorar
                conflictos.append({
                    'fila': i,
                    'nombre': nombre,
                    'sku_existente': mapa_suave[ns],
                })
            elif na in mapa_agresivo:
                # Solo coincide al ignorar todos los espacios -> advertencia visible
                sku_ex, nombre_ex = mapa_agresivo[na]
                posibles_espacios.append({
                    'fila': i,
                    'nombre': nombre,
                    'nombre_existente': nombre_ex,
                    'sku_existente': sku_ex,
                })

        return {'conflictos': conflictos, 'posibles_espacios': posibles_espacios}

    def get_instance(self, instance_loader, row):
        """
        Búsqueda inteligente para evitar duplicar materiales y permitir actualizar
        los existentes.
        Criterios en orden de prioridad:
        1. Memoria caché de la importación actual (evita duplicados si viene repetido en el archivo)
        2. ID del registro (si viene y es válido)
        3. SKU / Código Interno (limpio, sin espacios y case-insensitive)
        4. Código de barras (si viene y no está vacío)
        5. Nombre del material (búsqueda case-insensitive)
        """
        if not hasattr(self, '_instances_cache'):
            self._instances_cache = {}

        # 1. Búsqueda por ID
        obj_id = row.get('id')
        if obj_id:
            id_str = str(obj_id).strip()
            if id_str.endswith('.0') and id_str[:-2].isdigit():
                id_str = id_str[:-2]
            cache_key = f"id:{id_str}"
            if cache_key in self._instances_cache:
                return self._instances_cache[cache_key]
            try:
                obj = self.get_queryset().filter(id=int(id_str)).first()
                if obj:
                    self._cache_instance(obj)
                    return obj
            except (ValueError, TypeError):
                pass

        # 2. Búsqueda por SKU
        sku = self._clean_sku_string(row.get('sku'))
        if sku:
            cache_key = f"sku:{sku.lower()}"
            if cache_key in self._instances_cache:
                return self._instances_cache[cache_key]
            obj = self.get_queryset().filter(sku__iexact=sku).first()
            if obj:
                self._cache_instance(obj)
                return obj

        # 3. Búsqueda por Código de Barras
        codigo_barras = self._clean_sku_string(row.get('codigo_barras'))
        if codigo_barras:
            cache_key = f"cb:{codigo_barras.lower()}"
            if cache_key in self._instances_cache:
                return self._instances_cache[cache_key]
            obj = self.get_queryset().filter(codigo_barras__iexact=codigo_barras).first()
            if obj:
                self._cache_instance(obj)
                return obj

        # 4. Búsqueda por Nombre exacto/case-insensitive
        # Este es el caso "conflicto por nombre": la fila NO coincidió por SKU ni
        # por código de barras, pero su nombre ya existe. Aquí aplica la política
        # elegida por el usuario (actualizar o ignorar).
        nombre = row.get('nombre')
        if nombre:
            nombre_norm = self._norm_nombre(nombre)  # strip + colapsa espacios + lower
            if nombre_norm:
                cache_key = f"nom:{nombre_norm}"
                if cache_key in self._instances_cache:
                    obj = self._instances_cache[cache_key]
                else:
                    obj = self._buscar_por_nombre_normalizado(nombre_norm, str(nombre).strip())
                if obj:
                    self._cache_instance(obj)
                    # Marcar la fila como conflicto por nombre para que skip_row
                    # pueda decidir según la política.
                    row['_name_conflict'] = True
                    if self.name_conflict_policy == 'skip':
                        row['_skip_name_conflict'] = True
                    return obj

        return None

    def _buscar_por_nombre_normalizado(self, nombre_norm, nombre_strip):
        """
        Busca un material comparando el nombre con normalización SUAVE (colapsando
        espacios internos). Primero intenta el match exacto en SQL (rápido); si no
        encuentra, compara en Python los candidatos que comparten la primera
        palabra para cubrir dobles espacios internos.
        """
        # 1) Intento rápido: coincidencia exacta case-insensitive en SQL
        obj = self.get_queryset().filter(nombre__iexact=nombre_strip).first()
        if obj:
            return obj
        # 2) Fallback: comparar normalizado en Python sobre un subconjunto acotado
        primera_palabra = nombre_norm.split(' ', 1)[0]
        if not primera_palabra:
            return None
        candidatos = self.get_queryset().filter(nombre__istartswith=primera_palabra)[:200]
        for c in candidatos:
            if self._norm_nombre(c.nombre) == nombre_norm:
                return c
        return None

    def skip_row(self, instance, original, row=None, import_validation_errors=None, **kwargs):
        """
        Omite la fila cuando es un conflicto por nombre y la política es 'skip'.
        Soporta distintas firmas de import_export pasando row de forma flexible.
        """
        row_data = row
        if row_data is None:
            # En versiones donde skip_row no recibe row, no podemos evaluar el flag
            row_data = {}
        try:
            if row_data.get('_skip_name_conflict'):
                return True
        except AttributeError:
            pass
        try:
            return super().skip_row(instance, original, row=row, import_validation_errors=import_validation_errors, **kwargs)
        except TypeError:
            # Compatibilidad con firmas antiguas de import_export
            return super().skip_row(instance, original)

    def import_field(self, field, obj, row, is_m2m=False, **kwargs):
        """
        Sparse update: Si el objeto ya existe en la BD (obj.pk) y el valor en la fila
        es nulo o vacío, NO sobrescribir el valor existente para proteger los datos.
        """
        # Los campos virtuales (stock_actual, ubicacion) no tienen attribute en el
        # modelo; se procesan en after_import_row, no se asignan al objeto.
        if not field.attribute:
            return
        if obj.pk:
            if field.attribute == 'sku':
                val_sku = self._clean_sku_string(row.get('sku'))
                if not val_sku:
                    return
            val = row.get(field.column_name)
            if val is None or str(val).strip() == '':
                return
        super().import_field(field, obj, row, is_m2m=is_m2m, **kwargs)

    def after_save_instance(self, instance, using_transactions, dry_run):
        super().after_save_instance(instance, using_transactions, dry_run)
        if instance:
            self._cache_instance(instance)

    def before_import_row(self, row, **kwargs):
        """
        Limpia y valida datos antes de procesar cada fila.
        Asegura que categorías, marcas y unidades de medida se encuentren o creen
        correctamente, y genera SKU automático si es un material nuevo sin código.
        """
        for key in list(row.keys()):
            val = row.get(key)
            if val is None:
                continue
            val_str = str(val).strip()
            if val_str.lower() in ['none', 'nan', 'null', '']:
                row[key] = None
            else:
                if isinstance(val, str):
                    row[key] = val.strip()
                else:
                    row[key] = val_str

        # Limpiar SKU
        sku_clean = self._clean_sku_string(row.get('sku'))
        if sku_clean:
            row['sku'] = sku_clean

        # Limpiar Código de Barras
        cb_clean = self._clean_sku_string(row.get('codigo_barras'))
        if cb_clean:
            row['codigo_barras'] = cb_clean

        # Auto-crear / Vincular Categoría
        cat_nombre = row.get('categoria')
        if cat_nombre:
            cat_clean = str(cat_nombre).strip()
            cat_obj = CategoriaMaterial.objects.filter(nombre__iexact=cat_clean).first()
            if not cat_obj:
                cat_obj = CategoriaMaterial.objects.create(nombre=cat_clean)
            row['categoria'] = cat_obj.nombre

        # Auto-crear / Vincular Marca
        marca_nombre = row.get('marca')
        if marca_nombre:
            marca_clean = str(marca_nombre).strip()
            marca_obj = Marca.objects.filter(nombre__iexact=marca_clean).first()
            if not marca_obj:
                marca_obj = Marca.objects.create(nombre=marca_clean)
            row['marca'] = marca_obj.nombre

        # Auto-crear / Vincular Unidad de Medida (buscando por nombre o abreviatura)
        unidad_nombre = row.get('unidad_medida')
        if unidad_nombre:
            u_clean = str(unidad_nombre).strip()
            u_obj = UnidadMedida.objects.filter(nombre__iexact=u_clean).first()
            if not u_obj:
                u_obj = UnidadMedida.objects.filter(abreviatura__iexact=u_clean).first()
            if not u_obj:
                abrev_candidate = u_clean[:10].upper()
                counter = 1
                while UnidadMedida.objects.filter(abreviatura__iexact=abrev_candidate).exists():
                    suffix = str(counter)
                    abrev_candidate = f"{u_clean[:10 - len(suffix)]}{suffix}"
                    counter += 1
                u_obj = UnidadMedida.objects.create(nombre=u_clean, abreviatura=abrev_candidate)
            row['unidad_medida'] = u_obj.nombre

        # Normalizar tipo_material
        tipo_raw = row.get('tipo_material')
        if tipo_raw:
            tipo_clean = str(tipo_raw).strip().upper()
            valid_tipos = dict(Material.TIPO_MATERIAL_CHOICES)
            if tipo_clean in valid_tipos:
                row['tipo_material'] = tipo_clean
            else:
                matched = None
                for k, v in Material.TIPO_MATERIAL_CHOICES:
                    if tipo_clean == v.upper() or tipo_clean in v.upper():
                        matched = k
                        break
                row['tipo_material'] = matched if matched else 'INSUMO'
        elif not row.get('tipo_material'):
            row['tipo_material'] = 'INSUMO'

        # Limpiar campos decimales / numéricos
        from decimal import Decimal
        for num_field in ['precio_estimado', 'stock_minimo', 'alto', 'ancho', 'peso', 'profundidad']:
            v = row.get(num_field)
            if v is not None:
                v_clean = str(v).replace('$', '').replace('Q', '').replace('L', '').replace('€', '').strip()
                if ',' in v_clean and '.' not in v_clean:
                    v_clean = v_clean.replace(',', '.')
                elif ',' in v_clean and '.' in v_clean:
                    v_clean = v_clean.replace(',', '')
                try:
                    row[num_field] = Decimal(v_clean)
                except Exception:
                    if num_field in ['precio_estimado', 'stock_minimo']:
                        row[num_field] = Decimal('0.00')
                    else:
                        row[num_field] = None

        # Normalizar campos booleanos
        for bool_field in ['no_afecta_stock', 'es_tecnico']:
            v = row.get(bool_field)
            if v is not None:
                v_str = str(v).strip().lower()
                row[bool_field] = v_str in ['true', '1', 'si', 'sí', 'yes', 't', 's']

        # Si no viene SKU y no es un material existente que ya tiene SKU,
        # generar un SKU único para no violar el constraint unique=True de la BD
        if not row.get('sku'):
            nombre = row.get('nombre')
            existing = None
            if nombre:
                existing = self._buscar_por_nombre_normalizado(
                    self._norm_nombre(nombre), str(nombre).strip()
                )
            if not existing and row.get('codigo_barras'):
                existing = Material.objects.filter(codigo_barras__iexact=str(row.get('codigo_barras')).strip()).first()

            if existing:
                row['sku'] = existing.sku
            else:
                if row.get('codigo_barras'):
                    candidate_sku = str(row.get('codigo_barras')).strip()
                    if not Material.objects.filter(sku__iexact=candidate_sku).exists():
                        row['sku'] = candidate_sku
                if not row.get('sku'):
                    import uuid
                    while True:
                        new_sku = f"MAT-{uuid.uuid4().hex[:8].upper()}"
                        if not Material.objects.filter(sku=new_sku).exists():
                            row['sku'] = new_sku
                            break

    def _resolver_ubicacion(self, ubicacion_nombre):
        """
        Resuelve la ubicación destino para los movimientos de stock.
        Si viene un nombre lo busca; si no, usa la bodega por defecto
        (es_almacen=True o tipo BODEGA).
        """
        from activos.models import Ubicacion
        if ubicacion_nombre:
            ub = Ubicacion.objects.filter(nombre__iexact=str(ubicacion_nombre).strip()).first()
            if ub:
                return ub
        # Fallback: primera bodega/almacén disponible
        return (
            Ubicacion.objects.filter(es_almacen=True).order_by('orden', 'id').first()
            or Ubicacion.objects.filter(tipo='BODEGA').order_by('orden', 'id').first()
        )

    def after_import_row(self, row, instance, **kwargs):
        """
        Procesa stock y compatibilidades de repuestos.

        Dos modos de stock soportados:
        - 'stock_actual' (viene del export): se trata como el valor ABSOLUTO
          deseado. Se crea un AJUSTE solo por la diferencia contra el stock
          actual, por lo que re-importar el mismo archivo NO duplica ni altera
          el inventario (operación idempotente).
        - 'stock_inicial' / 'cantidad_inicial' / 'existencias': carga inicial
          que SUMA al inventario (comportamiento clásico de alta masiva).
        """
        from decimal import Decimal

        if instance and getattr(instance, 'no_afecta_stock', False):
            # Materiales de servicio/gasto no manejan inventario
            stock_absoluto = stock_inicial = None
        else:
            stock_absoluto = row.get('stock_actual')
            stock_inicial = row.get('stock_inicial') or row.get('cantidad_inicial') or row.get('existencias')

        ubicacion_nombre = row.get('ubicacion') or row.get('bodega') or row.get('almacen')
        lote_codigo = row.get('lote_codigo') or row.get('lote')

        def _to_decimal(v):
            if v is None:
                return None
            s = str(v).strip()
            if s == '' or s.lower() in ['none', 'nan', 'null']:
                return None
            s = s.replace(',', '')
            try:
                return Decimal(s)
            except Exception:
                return None

        def _resolver_lote():
            if not lote_codigo:
                return None
            vencimiento = row.get('lote_vencimiento') or row.get('fecha_vencimiento') or row.get('vencimiento')
            lote_obj, _ = Lote.objects.get_or_create(
                material=instance,
                codigo=str(lote_codigo).strip(),
                defaults={'fecha_vencimiento': vencimiento}
            )
            return lote_obj

        # ---- Modo 1: stock_actual (valor absoluto -> AJUSTE por diferencia) ----
        if instance and stock_absoluto is not None:
            cantidad_deseada = _to_decimal(stock_absoluto)
            if cantidad_deseada is not None and cantidad_deseada >= 0:
                try:
                    ubicacion = self._resolver_ubicacion(ubicacion_nombre)
                    if ubicacion and not kwargs.get('dry_run'):
                        lote_obj = _resolver_lote()
                        from django.db.models import Sum
                        existente = instance.existencias.filter(
                            ubicacion=ubicacion, lote=lote_obj
                        ).aggregate(total=Sum('cantidad'))['total'] or Decimal('0')
                        diferencia = cantidad_deseada - existente
                        if diferencia != Decimal('0'):
                            if diferencia > 0:
                                MovimientoInventario.objects.create(
                                    material=instance, lote=lote_obj,
                                    tipo='AJUSTE', cantidad=diferencia,
                                    ubicacion_destino=ubicacion, estado='APROBADO',
                                    comentarios='Ajuste de stock por importación (valor absoluto)'
                                )
                            else:
                                MovimientoInventario.objects.create(
                                    material=instance, lote=lote_obj,
                                    tipo='AJUSTE', cantidad=abs(diferencia),
                                    ubicacion_origen=ubicacion, estado='APROBADO',
                                    comentarios='Ajuste de stock por importación (valor absoluto)'
                                )
                except Exception:
                    pass  # No romper la importación principal por errores de stock

        # ---- Modo 2: stock_inicial (SUMA, alta masiva clásica) ----
        elif instance and stock_inicial:
            try:
                ubicacion = self._resolver_ubicacion(ubicacion_nombre)
                cantidad = _to_decimal(stock_inicial)
                if ubicacion and cantidad and cantidad > 0 and not kwargs.get('dry_run'):
                    lote_obj = _resolver_lote()
                    MovimientoInventario.objects.create(
                        material=instance, lote=lote_obj,
                        tipo='ENTRADA', cantidad=cantidad,
                        ubicacion_destino=ubicacion, estado='APROBADO',
                        comentarios='Carga inicial desde importación masiva'
                    )
            except Exception:
                pass  # Errores silenciosos en stock para no romper la importación principal

        # 2. Procesar Compatibilidad (Repuestos para modelos específicos)
        modelos_compatibles = row.get('modelos_compatibles') or row.get('repuesto_para') or row.get('equipos')
        if modelos_compatibles:
            from activos.models import Modelo
            from .models import CompatibilidadMaterial
            
            # Formatos soportados: "Modelo A, Modelo B" o "Modelo A; Modelo B"
            delimitador = ';' if ';' in str(modelos_compatibles) else ','
            nombres = [n.strip() for n in str(modelos_compatibles).split(delimitador) if n.strip()]
            
            for nombre in nombres:
                modelo = Modelo.objects.filter(nombre__iexact=nombre).first()
                if not modelo:
                    # Intentar por código si no por nombre
                    modelo = Modelo.objects.filter(codigo__iexact=nombre).first()
                
                if modelo:
                    CompatibilidadMaterial.objects.get_or_create(
                        material=instance,
                        modelo=modelo
                    )

class MaterialMovimientoInline(admin.TabularInline):
    model = MovimientoInventario
    extra = 0
    max_num = 20
    can_delete = False
    show_change_link = True
    readonly_fields = ('fecha_movimiento', 'tipo', 'cantidad', 'ubicacion_origen', 'ubicacion_destino', 'estado', 'usuario')
    verbose_name = "Historial de Movimiento"
    verbose_name_plural = "Historial de Movimientos"
    ordering = ('-fecha_movimiento',)

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'usuario', 'ubicacion_origen', 'ubicacion_destino', 'lote', 'solicitud'
        )

class MaterialUsoEnOTInline(admin.TabularInline):
    model = MaterialUtilizadoOT
    fk_name = 'material'
    extra = 0
    max_num = 20
    can_delete = False
    show_change_link = True
    verbose_name = "Uso en Orden de Trabajo"
    verbose_name_plural = "Usos en Órdenes de Trabajo"
    ordering = ('-fecha_registro',)
    readonly_fields = ('orden_trabajo', 'activo', 'cantidad', 'fecha_registro', 'comentario')
    fields = ('orden_trabajo', 'activo', 'cantidad', 'fecha_registro', 'comentario')

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'orden_trabajo', 'activo'
        )


class TieneImagenFilter(admin.SimpleListFilter):
    """Filtra materiales según tengan o no imagen cargada."""
    title = 'Imagen'
    parameter_name = 'tiene_imagen'

    def lookups(self, request, model_admin):
        return (('si', 'Con imagen'), ('no', 'Sin imagen'))

    def queryset(self, request, queryset):
        if self.value() == 'si':
            return queryset.exclude(imagen='').exclude(imagen__isnull=True)
        if self.value() == 'no':
            from django.db.models import Q
            return queryset.filter(Q(imagen='') | Q(imagen__isnull=True))
        return queryset


class NivelStockFilter(admin.SimpleListFilter):
    """
    Filtra por nivel de stock calculado a partir de las existencias:
    - sin_stock: stock total = 0
    - bajo_minimo: 0 < stock total < stock_minimo
    - disponible: stock total > 0
    Ignora los materiales marcados como 'no_afecta_stock'.
    """
    title = 'Nivel de stock'
    parameter_name = 'nivel_stock'

    def lookups(self, request, model_admin):
        return (
            ('sin_stock', 'Sin stock'),
            ('bajo_minimo', 'Bajo el mínimo'),
            ('disponible', 'Con stock disponible'),
        )

    def queryset(self, request, queryset):
        from django.db.models import Sum, F, Value, DecimalField
        from django.db.models.functions import Coalesce
        val = self.value()
        if not val:
            return queryset
        qs = queryset.filter(no_afecta_stock=False).annotate(
            _stock_total=Coalesce(
                Sum('existencias__cantidad'),
                Value(0, output_field=DecimalField(max_digits=12, decimal_places=2)),
            )
        )
        if val == 'sin_stock':
            return qs.filter(_stock_total__lte=0)
        if val == 'disponible':
            return qs.filter(_stock_total__gt=0)
        if val == 'bajo_minimo':
            return qs.filter(_stock_total__gt=0, _stock_total__lt=F('stock_minimo'))
        return queryset


@admin.register(Material)
class MaterialAdmin(ImportExportModelAdmin):
    change_list_template = 'admin/inventarios/material/change_list.html'
    change_form_template = 'admin/inventarios/material/change_form.html'
    resource_class = MaterialResource
    list_display = ('sku', 'nombre', 'codigo_barras', 'marca', 'categoria', 'tipo_material', 'unidad_medida', 'peso', 'get_stock_total', 'tiene_imagen', 'es_tecnico', 'no_afecta_stock')
    search_fields = ('nombre', 'sku', 'codigo_barras', 'marca__nombre', 'categoria__nombre')
    list_filter = (
        'categoria', 'marca', 'tipo_material', 'unidad_medida',
        'es_tecnico', 'no_afecta_stock', 'departamentos',
        TieneImagenFilter, NivelStockFilter,
    )
    list_select_related = ('categoria', 'marca', 'unidad_medida')
    filter_horizontal = ('departamentos',)
    inlines = [StockRecordInline, MaterialUsoEnOTInline]
    readonly_fields = ('imagen_preview',)
    fieldsets = [
        (None, {
            'fields': ('sku', 'codigo_barras', 'nombre', 'marca', 'descripcion', 'categoria', 'unidad_medida', 'tipo_material', 'es_tecnico')
        }),
        ('Precio y Stock', {
            'fields': ('precio_estimado', 'stock_minimo', 'no_afecta_stock'),
            'description': 'Marque "No afecta stock" para materiales de servicio/gasto que no deben registrar inventario.'
        }),
        ('Dimensiones', {
            'fields': ('alto', 'ancho', 'peso', 'profundidad'),
            'classes': ('collapse',)
        }),
        ('Imagen', {
            'fields': ('imagen', 'imagen_preview'),
            'classes': ('collapse',)
        }),
        ('Departamentos', {
            'fields': ('departamentos',),
            'classes': ('collapse',)
        }),
    ]

    def tiene_imagen(self, obj):
        if obj.imagen:
            return mark_safe('<span style="color:#22c55e;font-weight:700;">✓</span>')
        return mark_safe('<span style="color:#94a3b8;">—</span>')
    tiene_imagen.short_description = 'Img'

    def imagen_preview(self, obj):
        if obj.imagen and hasattr(obj.imagen, 'url'):
            try:
                url = obj.imagen.url
            except Exception:
                url = None
            if url:
                return mark_safe(f'<img src="{url}" width="50" height="50" style="object-fit:cover; border-radius:4px;" />')
        fallback_svg = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='50' height='50' viewBox='0 0 24 24' fill='none' stroke='%233b82f6' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z'%3E%3C/path%3E%3Cpolyline points='3.27 6.96 12 12.01 20.73 6.96'%3E%3C/polyline%3E%3Cline x1='12' y1='22.08' x2='12' y2='12'%3E%3C/line%3E%3C/svg%3E"
        return mark_safe(f'<img src="{fallback_svg}" width="50" height="50" style="object-fit:cover; border-radius:4px; opacity:0.6;" />')
    imagen_preview.short_description = 'Imagen'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related('categoria', 'marca', 'unidad_medida')
        return qs

    def get_stock_total(self, obj):
        from django.db.models import Sum
        total = obj.existencias.aggregate(total=Sum('cantidad'))['total']
        return total if total is not None else 0
    get_stock_total.short_description = 'Stock Total'

    def get_urls(self):
        urls = super().get_urls()
        from . import views
        custom_urls = [
            path('import-background/', self.admin_site.admin_view(views.import_materiales_background), name='inventarios_material_import_background'),
            path('import-background/process/', csrf_exempt(self.admin_site.admin_view(views.import_materiales_process)), name='inventarios_material_import_process'),
            path('import-background/progress/', self.admin_site.admin_view(views.import_materiales_progress), name='inventarios_material_import_progress'),
            path('import-background/template/', self.admin_site.admin_view(self.download_template_view), name='inventarios_material_import_template'),
        ]
        return custom_urls + urls

    def download_template_view(self, request):
        """
        Genera un archivo Excel con las cabeceras del recurso de Materiales y una
        fila de ejemplo que explica el round-trip de stock.
        """
        dataset = MaterialResource().export(queryset=Material.objects.none())
        # Fila de ejemplo alineada al export_order del recurso. Las columnas
        # 'stock_actual' y 'ubicacion' permiten descargar, editar y re-importar.
        ejemplo = {
            'id': '',
            'sku': 'MAT-EJEMPLO-001',
            'nombre': 'Material de ejemplo (borre esta fila)',
            'codigo_barras': '7501234567890',
            'marca': 'Marca Ejemplo',
            'descripcion': 'Descripción opcional',
            'categoria': 'General',
            'tipo_material': 'INSUMO',
            'unidad_medida': 'Unidad',
            'precio_estimado': '0.00',
            'stock_minimo': '0',
            'alto': '',
            'ancho': '',
            'peso': '',
            'profundidad': '',
            'no_afecta_stock': 'FALSE',
            'es_tecnico': 'FALSE',
            'stock_actual': '0',
            'ubicacion': 'Bodega Central',
            'imagen': '',
        }
        try:
            dataset.append([ejemplo.get(h, '') for h in dataset.headers])
        except Exception:
            pass
        response = HttpResponse(dataset.xlsx, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="formato_importacion_materiales.xlsx"'
        return response

@admin.register(MovimientoInventario)
class MovimientoInventarioAdmin(admin.ModelAdmin):
    change_form_template = 'admin/inventarios/movimientoinventario/change_form.html'
    list_display = ('fecha_movimiento', 'material', 'lote', 'tipo', 'cantidad', 'ubicacion_origen', 'ubicacion_destino', 'estado', 'usuario', 'es_inconsistente')
    list_filter = ('estado', 'tipo', 'fecha_movimiento', 'es_inconsistente')
    search_fields = ('material__nombre', 'material__sku', 'usuario__username', 'orden_trabajo__id')
    autocomplete_fields = ('material', 'lote', 'ubicacion_origen', 'ubicacion_destino')
    readonly_fields = ('fecha_movimiento', 'fecha_aprobacion', 'aprobado_por')
    raw_id_fields = ('solicitud', 'orden_trabajo')
    
    actions = ['liquidar_movimientos']

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['es_almacen'] = request.user.groups.filter(name='Almacenes').exists() or request.user.is_superuser
        return super().change_view(request, object_id, form_url, extra_context=extra_context)

    def liquidar_movimientos(self, request, queryset):
        # Verificar permiso
        if not request.user.has_perm('inventarios.can_liquidar_movimiento') and not request.user.is_superuser:
            self.message_user(request, "No tienes permiso para liquidar movimientos.", level=messages.ERROR)
            return

        procesados = 0
        errores = 0
        
        for mov in queryset:
            if mov.estado != 'PENDIENTE':
                continue
                
            try:
                mov.liquidar(request.user)
                procesados += 1
            except ValueError as e:
                errores += 1
                self.message_user(request, f"Error en ID {mov.id}: {str(e)}", level=messages.ERROR)
        
        if procesados > 0:
            self.message_user(request, f"{procesados} movimientos liquidados exitosamente.", level=messages.SUCCESS)
        if errores > 0:
            self.message_user(request, f"{errores} movimientos no pudieron ser liquidados por falta de stock.", level=messages.WARNING)

    liquidar_movimientos.short_description = "Liquidar / Aprobar Movimientos Seleccionados"


class RackPositionInline(admin.TabularInline):
    model = RackPosition
    extra = 0
    max_num = 50
    raw_id_fields = ('material', 'lote')
    readonly_fields = ('codigo',)


@admin.register(Rack)
class RackAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'bodega', 'largo', 'alto', 'num_niveles', 'num_secciones', 'pos_x_m', 'pos_y_m', 'activo', 'ver_3d')
    list_filter = ('activo', 'bodega')
    search_fields = ('nombre', 'bodega__nombre')
    inlines = [RackPositionInline]

    fieldsets = (
        (None, {
            'fields': ('bodega', 'nombre', ('largo', 'alto'), ('num_niveles', 'num_secciones'), 'orden')
        }),
        ('Posición en Bodega', {
            'fields': (('pos_x_m', 'pos_y_m'),),
            'description': 'Coordenadas en metros dentro del área de la bodega. Origen (0,0) = esquina inferior izquierda.',
        }),
    )

    def ver_3d(self, obj):
        url = reverse('inventarios:rack_3d', args=[obj.pk])
        return mark_safe(f'<a class="button" href="{url}" target="_blank">🔲 Ver en 3D</a>')
    ver_3d.short_description = 'Vista 3D'

@admin.register(RackPosition)
class RackPositionAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'rack', 'nivel', 'seccion', 'material', 'cantidad')
    list_filter = ('rack__bodega', 'rack')
    search_fields = ('codigo', 'rack__nombre', 'material__nombre', 'material__sku')
    raw_id_fields = ('material', 'lote')


@admin.register(MaterialUtilizadoOT)
class MaterialUtilizadoOTAdmin(admin.ModelAdmin):
    list_display = ('orden_trabajo', 'material', 'activo', 'cantidad', 'registrado_por', 'fecha_registro')
    list_filter = ('fecha_registro', 'orden_trabajo__tipo')
    search_fields = ('material__nombre', 'material__sku', 'orden_trabajo__codigo_de_orden', 'activo__nombre')
    raw_id_fields = ('orden_trabajo', 'material', 'activo', 'movimiento')
    readonly_fields = ('fecha_registro',)
