"""
Motor genérico de filtros por columna para tablas de Softcom.

Cada pantalla declara su lista de columnas (en el ``selectors`` de su app) y
este módulo aplica los filtros que llegan por GET:

    op_<key>=<operador>   y   val_<key>=<texto>

No depende de ninguna app concreta: se puede reutilizar en las 23 apps.
La interfaz (panel "Filtrar por" en el encabezado) está en
``core/templates/core/includes/filtro_th.html`` y ``filtros_columna_assets.html``.

Definición de una columna (dict):
    key          identificador (se usa en op_<key> / val_<key>)
    label        texto del encabezado
    kind         'texto' | 'eleccion' | 'numero' | 'fecha'
    ops          lista de (codigo, etiqueta) permitidos
    campos       (texto) lookups donde buscar, combinados con OR
    campo        (eleccion/numero/fecha) lookup único
    opciones     (eleccion) choices [(codigo, etiqueta)]
    presencia    Q que define "tiene datos" (para 'tiene' / 'vacio')
    anotar       {nombre: fabrica()} anotaciones auxiliares, se crean al usarse
    ann          (fecha) anotación de texto usada por 'contiene'
    placeholder  texto de ayuda opcional
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.db.models import CharField, Q, Value
from django.db.models.functions import Cast, Concat, TruncDate

# ---------------------------------------------------------------------------
# Operadores
# ---------------------------------------------------------------------------

OP_BASICO = [('igual', 'Es igual a'), ('contiene', 'Contiene'), ('no_contiene', 'No contiene')]
OP_TEXTO = OP_BASICO + [('tiene', 'Solo con datos'), ('vacio', 'Solo sin datos')]
OP_NUMERO = [('igual', 'Es igual a'), ('mayor', 'Mayor que'), ('menor', 'Menor que')]
OP_FECHA = [('igual', 'Es igual a'), ('mayor', 'Desde'), ('menor', 'Hasta'), ('contiene', 'Contiene')]

# Operadores que no necesitan texto
OPS_SIN_VALOR = ('tiene', 'vacio')

PLACEHOLDERS = {
    'texto': 'Texto a buscar',
    'eleccion': 'Texto a buscar',
    'numero': 'Número',
    'fecha': 'AAAA-MM-DD o DD/MM/AAAA',
}


# ---------------------------------------------------------------------------
# Fábricas para declarar columnas
# ---------------------------------------------------------------------------

def a_texto(campo):
    """Anotación: el campo convertido a texto (p. ej. un id numérico)."""
    return lambda: Cast(campo, CharField())


def fecha_texto(campo):
    """Anotación: la fecha (sin hora) del campo, como texto AAAA-MM-DD."""
    return lambda: Cast(TruncDate(campo), CharField())


def nombre_completo(base):
    """Anotación: '<first_name> <last_name>' de un usuario relacionado."""
    return lambda: Concat(
        f'{base}__first_name', Value(' '), f'{base}__last_name', output_field=CharField()
    )


def no_vacio(campo):
    """Q de presencia para campos de texto: no nulo y no vacío."""
    return Q(**{f'{campo}__isnull': False}) & ~Q(**{campo: ''})


def persona(base, ann):
    """Definición parcial de columna para un usuario relacionado (FK a User)."""
    return {
        'kind': 'texto', 'ops': OP_TEXTO,
        'campos': [f'{base}__username', f'{base}__first_name', f'{base}__last_name', ann],
        'anotar': {ann: nombre_completo(base)}, 'presencia': Q(**{f'{base}__isnull': False}),
    }


# ---------------------------------------------------------------------------
# Aplicación de filtros
# ---------------------------------------------------------------------------

def parse_fecha_flexible(valor):
    """'AAAA-MM-DD' o 'DD/MM/AAAA' -> date; None si no se reconoce."""
    for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(valor.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


def _q_campos(campos, lookup, valor):
    q = Q()
    for c in campos:
        q |= Q(**{f'{c}__{lookup}': valor})
    return q


def aplicar_filtros(qs, params, columnas):
    """Aplica a ``qs`` los filtros por columna (op_<key>/val_<key>) de ``params``.

    ``params`` es un dict o QueryDict (normalmente ``request.GET``).
    Operadores desconocidos, valores vacíos o no válidos se ignoran.
    """
    for col in columnas:
        op = (params.get(f"op_{col['key']}") or '').strip()
        valor = (params.get(f"val_{col['key']}") or '').strip()
        if not op or op not in dict(col['ops']):
            continue
        if op not in OPS_SIN_VALOR and not valor:
            continue  # operador sin texto: no filtra

        for nombre, fabrica in col.get('anotar', {}).items():
            qs = qs.annotate(**{nombre: fabrica()})

        kind = col['kind']
        if op == 'tiene':
            qs = qs.filter(col['presencia'])
        elif op == 'vacio':
            qs = qs.exclude(col['presencia'])
        elif kind == 'texto':
            if op == 'contiene':
                qs = qs.filter(_q_campos(col['campos'], 'icontains', valor))
            elif op == 'no_contiene':
                qs = qs.exclude(_q_campos(col['campos'], 'icontains', valor))
            elif op == 'igual':
                qs = qs.filter(_q_campos(col['campos'], 'iexact', valor))
        elif kind == 'eleccion':
            v = valor.lower()
            if op == 'igual':
                codigos = [c for c, l in col['opciones'] if v in (c.lower(), l.lower())]
            else:
                codigos = [c for c, l in col['opciones'] if v in c.lower() or v in l.lower()]
            if op == 'no_contiene':
                qs = qs.exclude(**{f"{col['campo']}__in": codigos})
            else:
                qs = qs.filter(**{f"{col['campo']}__in": codigos})
        elif kind == 'numero':
            try:
                num = Decimal(valor.replace(',', '.'))
            except InvalidOperation:
                continue
            lookup = {'igual': 'exact', 'mayor': 'gt', 'menor': 'lt'}[op]
            qs = qs.filter(**{f"{col['campo']}__{lookup}": num})
        elif kind == 'fecha':
            if op == 'contiene':
                qs = qs.filter(**{f"{col['ann']}__icontains": valor})
                continue
            dia = parse_fecha_flexible(valor)
            if not dia:
                continue
            lookup = {'igual': '__date', 'mayor': '__date__gte', 'menor': '__date__lte'}[op]
            qs = qs.filter(**{f"{col['campo']}{lookup}": dia})
    return qs


def columnas_con_estado(params, columnas):
    """Columnas con operador/valor actuales, para repintar los paneles de filtro.

    Devuelve dicts con: key, label, ops, op, val, placeholder.
    """
    resultado = []
    for col in columnas:
        op = (params.get(f"op_{col['key']}") or '').strip()
        resultado.append({
            'key': col['key'], 'label': col['label'], 'ops': col['ops'],
            'op': op if op in dict(col['ops']) else '',
            'val': (params.get(f"val_{col['key']}") or '').strip(),
            'placeholder': col.get('placeholder') or PLACEHOLDERS[col['kind']],
        })
    return resultado
