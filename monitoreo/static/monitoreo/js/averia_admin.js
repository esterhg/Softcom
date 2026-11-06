/* Admin de Reporte de Avería: al elegir el activo muestra su unidad funcional. */
(function () {
  'use strict';

  function actualizar(activoId) {
    var destino = document.getElementById('av-unidad-funcional');
    if (!destino) return;
    if (!activoId) {
      destino.textContent = 'Se completa al elegir el activo';
      return;
    }
    destino.textContent = 'Cargando…';
    fetch('/monitoreo/averias/api/activo/' + encodeURIComponent(activoId) + '/', {
      credentials: 'same-origin',
      headers: { 'Accept': 'application/json' }
    })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
      .then(function (data) {
        destino.textContent = data.unidad_funcional || 'El activo no tiene ubicación asignada';
      })
      .catch(function () {
        destino.textContent = 'No se pudo obtener la unidad funcional';
      });
  }

  function init() {
    var select = document.getElementById('id_activo');
    if (!select) return;
    // El autocomplete del admin usa select2 (django.jQuery); escuchamos ambos eventos.
    select.addEventListener('change', function () { actualizar(select.value); });
    if (window.django && window.django.jQuery) {
      window.django.jQuery(select).on('select2:select select2:clear', function () {
        actualizar(select.value);
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
