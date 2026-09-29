# Carga Masiva Unificada: Categorías + Rutinas + Actividades

Permite crear en **un solo archivo** toda la jerarquía de mantenimiento:
**Categoría → Rutina → Actividades (Pasos)**.

Acceso: **Mantenimiento → Rutinas (Dashboard)** → botón **🌳 Importar Árbol**
(URL: `/mantenimiento/rutinas/dashboard/` → `/mantenimiento/import-arbol/`).

## Cómo funciona

- **Cada fila representa una actividad (paso)** y arrastra el contexto de su categoría y rutina.
- Repite `categoria_ruta` y `rutina_codigo` en cada fila de paso para agruparlas bajo la misma rutina.
- Las **categorías** se crean automáticamente por su ruta (crea los niveles que falten).
- Las **rutinas** se identifican por `rutina_codigo` (crea o actualiza — *upsert*).
- Los **pasos** se identifican por `rutina_codigo` + `paso_orden` (crea o actualiza).

## Columnas de la plantilla

| Columna | Requerida | Descripción / Ejemplo |
|---|---|---|
| `categoria_ruta` | ✅ Sí | Ruta completa separada por `>`. Ej: `Eléctrica > Transformadores`. Crea los niveles que falten. |
| `categoria_codigo` | Opcional | Código único de la categoría hoja. |
| `rutina_codigo` | Para crear rutina | Identificador único de la rutina (upsert). Ej: `RUT-TR-001`. |
| `rutina_nombre` | Opcional | Nombre de la rutina (autogenerado si vacío). |
| `frecuencia` | Opcional | Nombre de una frecuencia **existente**. Ej: `Mensual`. |
| `tiempo_estimado` | Opcional | `HH:MM:SS`, `HH:MM` o horas decimales (`1.5`). |
| `cantidad_tecnicos` | Opcional | Entero. Por defecto 1. |
| `rutina_descripcion` | Opcional | Texto descriptivo de la rutina. |
| `paso_orden` | Para paso | Orden del paso (entero). Identificador dentro de la rutina. |
| `paso_descripcion` | Para paso | Descripción de la actividad/paso. |
| `paso_tipo` | Opcional | `INSTRUCCION`, `CHECK`, `NUMERICO`, `TEXTO`, `MEDICION`, `FOTO`, `HEADER`. |
| `paso_verificacion` | Opcional | Qué debe verificar el técnico. |
| `paso_unidad` | Opcional | Unidad de medida (ej. `°C`, `Bar`). |
| `paso_valor_objetivo` | Opcional | Valor ideal (numérico). |
| `paso_rango_min` / `paso_rango_max` | Opcional | Rangos numéricos aceptables. |

## Ejemplo

| categoria_ruta | rutina_codigo | rutina_nombre | frecuencia | tiempo_estimado | paso_orden | paso_descripcion | paso_tipo | paso_unidad | paso_valor_objetivo |
|---|---|---|---|---|---|---|---|---|---|
| Eléctrica > Transformadores | RUT-TR-001 | Inspección mensual | Mensual | 01:00:00 | 1 | Verificar nivel de aceite | CHECK | | |
| Eléctrica > Transformadores | RUT-TR-001 | | | | 2 | Medir temperatura devanado | NUMERICO | °C | 65 |
| Eléctrica > Transformadores | RUT-TR-001 | | | | 3 | Tomar foto de la placa | FOTO | | |
| Climatización > Aires Acondicionados | RUT-AA-001 | Limpieza de filtros | Semanal | 00:30:00 | 1 | Retirar y limpiar filtros | INSTRUCCION | | |

## Flujo de uso

1. Descarga la **plantilla** (Excel o CSV) desde la pantalla de importación (viene con filas de ejemplo).
2. Completa tus filas.
3. Sube el archivo. Se ejecuta primero una **vista previa** (dry run) que muestra:
   categorías a crear, rutinas nuevas/actualizadas, pasos y avisos.
4. Confirma para ejecutar la importación real.
5. Opción **"Solo analizar"**: revisa el archivo sin crear ni modificar nada.

## Notas

- Las **frecuencias deben existir previamente** (Mantenimiento → Frecuencias); si no existen se reportan como aviso.
- La importación corre en **segundo plano (Celery)** con barra de progreso.
- Es idempotente: reimportar el mismo archivo actualiza en lugar de duplicar (por `rutina_codigo` y `paso_orden`).
