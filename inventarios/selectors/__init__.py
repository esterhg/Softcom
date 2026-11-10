"""
Selectors de Inventarios: consultas de lectura reutilizables.

Reglas:
- Reciben parámetros simples (dict/QueryDict, ids, fechas), nunca ``request``.
- Devuelven QuerySets o estructuras de datos; no renderizan ni escriben en BD.
"""
