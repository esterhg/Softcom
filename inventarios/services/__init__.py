"""
Services de Inventarios: reglas de negocio y procesos.

Reglas:
- No conocen ``request`` ni ``HttpResponse``: reciben datos y devuelven datos
  (o realizan escrituras dentro de transacciones).
- Las consultas de lectura reutilizables viven en ``inventarios.selectors``.

Los servicios previos (p. ej. ``inventarios/services_salida.py``) se mantienen
donde están; se irán integrando aquí de forma gradual.
"""
