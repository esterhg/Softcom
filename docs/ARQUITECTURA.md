# Arquitectura de Softcom (Django por capas)

Estándar para las 23 apps Django de Softcom. Se adopta **de forma gradual**:
cada flujo se migra cuando se toca, sin reescribir el sistema y sin cambiar el
comportamiento para el usuario.

Tecnología: Python + Django (ORM, auth, sesiones, admin/Jazzmin, plantillas).
No se introducen FastAPI, Flask, React ni otros frameworks como sustituto.

---

## 1. Capas y responsabilidades

| Capa | Ubicación en la app | Hace | No hace |
|---|---|---|---|
| **URLs** | `urls.py` (+ `urls_<area>.py`) | Declara rutas y nombres (`app:nombre`). | Lógica. |
| **Views** | `views.py`, `views_<area>.py` (o `reportes.py`) | Lee `request` (GET/POST), valida permisos, llama a selectors/services, devuelve `render`, `redirect` o `JsonResponse`. | Consultas complejas, reglas de negocio, armado de archivos. |
| **Services** | `services/<area>.py` | Reglas de negocio y procesos: cálculos, agregaciones, validaciones, escrituras (con `transaction.atomic`), generación de Excel/PDF, notificaciones. | Conocer `request`/`HttpResponse`. |
| **Selectors** | `selectors/<area>.py` | Consultas de **lectura** reutilizables: QuerySets con `select_related`, filtros, anotaciones. | Escribir en BD, renderizar. |
| **Models** | `models.py` / `models/` | Entidades, campos, relaciones, `Meta`, validaciones de integridad del propio modelo. | Orquestar procesos entre modelos. |
| **Permissions** | `permissions.py` | Reglas de acceso (grupos de Django) y decoradores. Una sola definición por regla. | — |
| **Templates** | `templates/<app>/`, componentes en `templates/<app>/includes/` | Presentación. | Lógica de negocio. |
| **Middleware** | `core/middleware.py` | Procesos transversales (sesión, auditoría, contexto global). | Lógica de una app concreta. |

### Regla de dependencia

```
urls  ->  views  ->  services  ->  selectors  ->  models
                \-------------------^
```

- Las **views** pueden usar services, selectors y permissions.
- Los **services** pueden usar selectors y models; **nunca** `request`.
- Los **selectors** solo usan models (y utilidades de `core`).
- Los **models** no importan views, services ni selectors.
- Las utilidades de `core` no dependen de ninguna app de negocio.

### Parámetros entre capas

Las vistas pasan a selectors/services datos simples: `request.GET` (un
QueryDict se comporta como dict), ids, fechas, el usuario. Así los selectors y
services se prueban sin HTTP.

---

## 2. Estructura estándar de una app

```
<app>/
├── urls.py                 # rutas de la app (app_name = '<app>')
├── urls_<area>.py          # opcional: rutas de un área, incluidas desde urls.py
├── views.py                # vistas (o views_<area>.py por área)
├── permissions.py          # grupos y decoradores de acceso
├── selectors/
│   ├── __init__.py
│   └── <area>.py           # consultas de lectura
├── services/
│   ├── __init__.py
│   └── <area>.py           # reglas de negocio y procesos
├── models.py | models/
├── templates/<app>/
│   └── includes/           # componentes de la app
├── migrations/
└── test_<area>.py          # pruebas de services/selectors/vistas
```

Notas:
- `selectors/` y `services/` son paquetes dentro de la app, se importan como
  `from <app>.selectors import <area>`. No crear un `selectors.py` en la raíz
  del proyecto: chocaría con el módulo `selectors` de la librería estándar.
- Los servicios existentes con otro nombre (p. ej. `inventarios/services_salida.py`,
  `mantenimiento/services.py`) se mantienen y se integran cuando se migre su flujo.
- Pruebas: nombrar `test_<area>.py` (lo detectan `manage.py test` y `pytest`).

---

## 3. Componentes compartidos en `core`

| Módulo | Uso |
|---|---|
| `core/filtros_columna.py` | Motor de filtros por columna (`op_<key>` / `val_<key>`): `aplicar_filtros`, `columnas_con_estado`, operadores `OP_*` y fábricas `persona`, `a_texto`, `fecha_texto`, `no_vacio`. |
| `core/templates/core/includes/filtro_th.html` | Encabezado de tabla con panel "Filtrar por" (operador + valor, Aplicar / Borrar). |
| `core/templates/core/includes/filtros_columna_assets.html` | CSS + JS del panel (incluir una vez por página). |
| `core/excel.py` | Exportación a Excel con estilo Softcom: `estilos`, `escribir_headers`, `autoajustar`, `respuesta_xlsx`. |
| `core/fechas.py` | `parse_fecha_iso` para filtros de fecha (`desde` / `hasta`). |
| `core/navegacion.py` | `querystring_sin` (enlaces que conservan filtros) y `url_retorno` (`?next=` seguro). |

### Cómo agregar filtros por columna a una tabla

1. En el selector de la app, declarar las columnas:
   ```python
   from core.filtros_columna import OP_TEXTO, aplicar_filtros, persona
   COLUMNAS = [
       {'key': 'producto', 'label': 'Producto', 'kind': 'texto', 'ops': OP_TEXTO,
        'campos': ['material__nombre'], 'presencia': Q(material__isnull=False)},
       dict(key='usuario', label='Usuario', **persona('usuario', 'ann_usuario')),
   ]
   def listado(params):
       return aplicar_filtros(Modelo.objects.all(), params, COLUMNAS)
   ```
2. En la vista: `'columnas': columnas_con_estado(request.GET, COLUMNAS)`.
3. En la plantilla, dentro de un `<form id="filtros-form" method="get">` y la tabla:
   ```django
   <tr>{% for c in columnas %}{% include "core/includes/filtro_th.html" with c=c %}{% endfor %}</tr>
   ...
   {% include "core/includes/filtros_columna_assets.html" %}
   ```

---

## 4. Estándar de navegación

1. **Rutas con nombre.** Siempre `{% url 'app:nombre' %}` / `reverse()`; nunca
   URLs escritas a mano. Agrupar por área en `urls_<area>.py` cuando `urls.py`
   crece.
2. **Pantallas de consulta = GET.** Filtros, búsqueda, orden y página van en la
   URL. Así funcionan el botón Atrás, la recarga y los enlaces compartidos, y
   se conserva el estado de la pantalla.
   - Paginación y exportación conservan los filtros:
     `querystring_sin(request.GET, 'page')`.
   - Exportaciones: `.../excel/` con los mismos parámetros de la pantalla.
3. **Acciones que modifican datos = POST + Post/Redirect/Get.** La vista procesa
   el POST, guarda, agrega un mensaje (`django.contrib.messages`) y responde con
   `redirect(...)`. Nunca `render` tras un POST exitoso (evita reenvíos al
   recargar). Para formularios AJAX/modales, tras el éxito se navega por GET a
   la pantalla de destino.
4. **Destino de regreso.** Si una pantalla puede abrirse desde varios lugares,
   el origen pasa en `?next=<url>` y se valida con
   `url_retorno(request, default=reverse('app:inicio'))`.
5. **Permisos.** Sin sesión: redirección al login (`login_required`). Con sesión
   pero sin permiso: 403. La misma regla de `permissions.py` decide qué
   botones/pestañas se muestran.

---

## 5. Pruebas

- **Selectors**: verifican la consulta (filtros aplicados, regla de negocio).
- **Services**: verifican resultados con objetos de prueba (sin BD cuando es
  posible).
- **Vistas**: permisos (302/403/200) y contexto.

Ejecutar (con el entorno virtual activo):

```powershell
python manage.py test inventarios.test_reportes core.test_filtros_columna core.test_navegacion
```

> Atención: en local la base de datos apunta por túnel al servidor. Las pruebas
> que usan BD crean una base `test_*` en ese servidor. No ejecutarlas contra
> producción; usar una base de desarrollo (`DATABASE_URL` en `.env`).
> Las pruebas `SimpleTestCase` no usan BD y son seguras en cualquier entorno.

---

## 6. Proceso para migrar un flujo

1. **Mapear dependencias**: quién importa el código (`grep`), rutas y nombres,
   plantillas, permisos, otras apps.
2. Crear/ampliar `selectors/<area>.py` y `services/<area>.py` moviendo el
   código **sin cambiar comportamiento**.
3. Dejar la vista delgada. Mantener alias en el módulo original cuando otros
   módulos importen nombres antiguos.
4. Mover rutas a `urls_<area>.py` si aplica, conservando paths y nombres.
5. Escribir pruebas de selectors/services.
6. Verificar y documentar en la sección 7.

---

## 7. Registro de migración

| Paso | App / flujo | Estado |
|---|---|---|
| 1 | `inventarios` — Movimientos y Pases pendientes de justificar | Migrado (pendiente de validación) |
| — | `inventarios` — Centro de reportes, Inventario actual, Catálogo (Excel) | Pendiente (siguen en `reportes.py`) |
| — | Resto de apps | Pendiente |

### Paso 1 — `inventarios`: Movimientos y Pases pendientes

| Antes (`inventarios/reportes.py`) | Ahora |
|---|---|
| `GRUPO_SUPERVISOR_ALMACEN`, `es_supervisor_almacen`, `supervisor_almacen_required` | `inventarios/permissions.py` |
| `_estilos`, `_escribir_headers`, `_autoajustar` | `core/excel.py` (`estilos`, `escribir_headers`, `autoajustar`, + `respuesta_xlsx`) |
| `_parse_fecha` | `core/fechas.py` (`parse_fecha_iso`) |
| Motor de filtros (`OP_*`, `aplicar_filtros`, `columnas_con_estado`, fábricas) | `core/filtros_columna.py` |
| `COLUMNAS_MOVIMIENTOS`, `COLUMNAS_PASES` | `inventarios/selectors/reportes.py` |
| `_pases_pendientes_qs` | `selectors/reportes.py`: `pases_pendientes_base()`, `pases_pendientes(params)` |
| `_departamento_de` | `selectors/reportes.py`: `departamento_de()` |
| Consulta de `tabla_movimientos_view` | `selectors/reportes.py`: `movimientos_tabla(params)` |
| Consulta y mapa de activos de `export_movimientos_excel` | `selectors/reportes.py`: `movimientos_export(params)`, `activos_por_movimiento(qs)` |
| Resumen por departamento | `services/reportes.py`: `resumen_por_departamento()` |
| Armado de los Excel | `services/reportes.py`: `libro_excel_pases()`, `libro_excel_movimientos()` |
| Rutas de reportes en `urls.py` | `inventarios/urls_reportes.py` (mismos paths y nombres) |
| `templates/inventarios/includes/filtro_th.html` y `filtros_columna_assets.html` | `core/templates/core/includes/` (los anteriores quedan como alias) |

`inventarios/reportes.py` conserva alias con los nombres antiguos por
compatibilidad.

### Paso 2 — `presupuestos`: Solicitudes de alta (proveedor / material) en Requisiciones

Fase 1 (base, sin pantallas todavía). Pendiente de validación.

| Pieza | Ubicación |
|---|---|
| Modelos `SolicitudAltaProveedor`, `SolicitudAltaMaterial` | `presupuestos/models.py` (migración `0085_solicitudes_alta`, **no aplicada**) |
| Grupos: Procura/PROCURA (proveedores); Supervisor de Almacen y Almacenes (materiales) | `presupuestos/permissions.py` |
| Consultas de lectura (pendientes, conteos) | `presupuestos/selectors/solicitudes_alta.py` |
| Crear / aprobar / rechazar y bloqueos de la requisición | `presupuestos/services/solicitudes_alta.py` |
| Regla: proveedor y material obligatorios, **SERVICIO exento**; envío bloqueado con altas pendientes | `presupuestos/validaciones.py` (`errores_requisicion`), `presupuestos/forms.py` |
| Pruebas sin BD | `presupuestos/test_solicitudes_alta.py` |

Pendiente: botones de solicitud en el formulario, bandeja de aprobación y lista de proveedores.
