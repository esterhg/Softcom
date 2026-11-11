from django import forms
from .models import Requisicion, ArticuloRequisicion, DocumentoRequisicion
from inventarios.models import Material


class PartidaSelectWidget(forms.Select):
    """Select widget that adds data-presupuesto-id attribute to each option."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._partida_presupuesto_map = None

    def _get_presupuesto_map(self):
        if self._partida_presupuesto_map is None:
            from .models import PartidaPresupuestaria
            self._partida_presupuesto_map = dict(
                PartidaPresupuestaria.objects.values_list('id', 'presupuesto_anual_id')
            )
        return self._partida_presupuesto_map

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        if value:
            pmap = self._get_presupuesto_map()
            try:
                val_int = int(str(value))
                pres_id = pmap.get(val_int)
                if pres_id:
                    option['attrs']['data-presupuesto-id'] = str(pres_id)
            except (ValueError, TypeError):
                pass
        return option

class RequisicionForm(forms.ModelForm):
    class Meta:
        model = Requisicion
        fields = [
            'cr8ca_requisicion', 'fecha', 'fecha_aprobacion', 'partida', 'item_presupuesto', 'usuario_solicitante', 'usuario_en_nombre_de', 'aprobador', 'cr8ca_asunto', 'cr8ca_prioridad',
            'cr8ca_motivo', 'cr8ca_comentarios', 'cr8ca_id_oc', 'wizard_step', 'estado_requisicion', 'cr8ca_totalenarticulos', 'isv',
            'moneda_req',
            'proveedor', 'proveedores_sugeridos', 'proveedores_sugeridos_notas', 'tipo', 'grupo', 'forma_pago',
            'edificio', 'nivel', 'ubicacion',
        ]
        widgets = {
            'cr8ca_requisicion': forms.TextInput(attrs={'class': 'form-control', 'readonly': 'readonly'}),
            'fecha': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'fecha_aprobacion': forms.DateTimeInput(attrs={'class': 'form-control', 'readonly': 'readonly'}),
            'partida': forms.Select(attrs={'class': 'form-control select2-material'}),
            'item_presupuesto': forms.Select(attrs={'class': 'form-control select2-material'}),
            'cr8ca_asunto': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Asunto de la requisición'}),
            'cr8ca_prioridad': forms.Select(attrs={'class': 'form-control'}),
            'cr8ca_motivo': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Explica por qué se requiere la compra', 'title': 'Explica el por qué se requiere la compra'}),
            'cr8ca_comentarios': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'usuario_solicitante': forms.Select(attrs={'class': 'form-control', 'disabled': 'disabled'}),
            'usuario_en_nombre_de': forms.Select(attrs={'class': 'form-control select2-material'}),
            'aprobador': forms.Select(attrs={'class': 'form-control select2-material'}),
            'cr8ca_id_oc': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ID de Orden de Compra'}),
            'estado_requisicion': forms.Select(attrs={'class': 'form-control', 'disabled': 'disabled'}),
            'cr8ca_totalenarticulos': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00', 'step': '0.01'}),
            'isv': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00', 'step': '0.01'}),
            'moneda_req': forms.Select(attrs={'class': 'form-control', 'id': 'id_moneda_req'}),
            'proveedor': forms.Select(attrs={'class': 'form-control select2-material'}),
            'proveedores_sugeridos': forms.SelectMultiple(attrs={
                'class': 'form-control select2-material',
                'multiple': 'multiple'
            }),
            'proveedores_sugeridos_notas': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Detalle de qué artículos corresponden a cada proveedor...'}),
            'tipo': forms.Select(attrs={'class': 'form-control'}),
            'forma_pago': forms.Select(attrs={'class': 'form-control'}),
        }
        labels = {
            'cr8ca_totalenarticulos': 'Costo Aproximado'
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        # Lugar del servicio: edificio (select), nivel y ubicación se cargan por JS
        if 'edificio' in self.fields:
            from activos.models import Ubicacion
            self.fields['edificio'].queryset = Ubicacion.objects.filter(tipo='EDIFICIO').order_by('nombre')
            self.fields['edificio'].widget.attrs.update({'class': 'form-control', 'id': 'id_edificio'})
            self.fields['edificio'].empty_label = '— Seleccionar edificio —'
            for f in ('nivel', 'ubicacion'):
                self.fields[f].widget = forms.HiddenInput(attrs={'id': f'id_{f}'})
        if 'cr8ca_requisicion' in self.fields:
            self.fields['cr8ca_requisicion'].required = False
        if 'estado_requisicion' in self.fields:
            self.fields['estado_requisicion'].required = False
        if 'usuario_solicitante' in self.fields:
            self.fields['usuario_solicitante'].required = False
        if 'moneda_req' in self.fields:
            from .models import Moneda
            self.fields['moneda_req'].required = False
            self.fields['moneda_req'].empty_label = '— Seleccionar moneda —'
            self.fields['moneda_req'].queryset = Moneda.objects.all().order_by('codigo')
        if 'aprobador' in self.fields:
            self.fields['aprobador'].required = False
            if self.instance and not getattr(self.instance, 'aprobador_id', None):
                solicitante = getattr(self.instance, 'usuario_solicitante', None)
                if solicitante and hasattr(solicitante, 'perfil') and solicitante.perfil.departamento and solicitante.perfil.departamento.aprobador:
                    self.initial['aprobador'] = solicitante.perfil.departamento.aprobador_id

        # Filtrar partidas e ítems por departamento del solicitante o usuario
        if 'partida' in self.fields:
            from presupuestos.models import PartidaPresupuestaria, ItemPresupuesto
            from django.db.models import Q
            depto_id = None

            # 1. Intentar obtener el departamento del solicitante de la requisición
            if self.instance and getattr(self.instance, 'usuario_solicitante_id', None):
                solicitante = self.instance.usuario_solicitante
                if hasattr(solicitante, 'perfil') and solicitante.perfil.departamento_id:
                    depto_id = solicitante.perfil.departamento_id

            # 2. Si no hay solicitante, usar el del usuario autenticado
            if not depto_id and self.user and hasattr(self.user, 'perfil') and self.user.perfil.departamento_id:
                depto_id = self.user.perfil.departamento_id

            if depto_id:
                # Prioridad: partidas de presupuesto del propio departamento
                partidas_del_depto = PartidaPresupuestaria.objects.filter(
                    presupuesto_anual__departamento_id=depto_id
                ).filter(
                    Q(departamentos__isnull=True) | Q(departamentos__id=depto_id)
                ).distinct()

                if partidas_del_depto.exists():
                    # El departamento tiene su propio presupuesto con partidas → solo mostrar esas
                    partidas_permitidas = partidas_del_depto
                else:
                    # El departamento NO tiene presupuesto propio → mostrar globales
                    # (partidas cuyos presupuesto_anual no tienen departamento asignado)
                    # y también partidas cuyo m2m departamentos incluye al depto o está vacío
                    partidas_permitidas = PartidaPresupuestaria.objects.filter(
                        presupuesto_anual__departamento__isnull=True
                    ).filter(
                        Q(departamentos__isnull=True) | Q(departamentos__id=depto_id)
                    ).distinct()

                self.fields['partida'].queryset = partidas_permitidas

                # Usar widget personalizado para incluir data-presupuesto-id en cada opción
                self.fields['partida'].widget = PartidaSelectWidget(
                    attrs={'class': 'form-control select2-material'}
                )
                self.fields['partida'].widget.choices = self.fields['partida'].choices

                # Filtrar también los ítems de presupuesto a solo los de partidas permitidas
                if 'item_presupuesto' in self.fields:
                    self.fields['item_presupuesto'].queryset = ItemPresupuesto.objects.filter(
                        partida__in=partidas_permitidas
                    )
            # Si no hay departamento asociado, ve todas (comportamiento por defecto)
            else:
                # Sin filtro por departamento, igual poner widget con data attributes
                self.fields['partida'].widget = PartidaSelectWidget(
                    attrs={'class': 'form-control select2-material'}
                )
                self.fields['partida'].widget.choices = self.fields['partida'].choices


    def clean(self):
        cleaned = super().clean()
        # Proveedor obligatorio, salvo en servicios (si no existe, se solicita su alta a Procura)
        if cleaned.get('tipo') != 'SERVICIO' and not cleaned.get('proveedor'):
            self.add_error(
                'proveedor',
                'Debe seleccionar un proveedor. Si no existe, solicite su alta a Procura.')
        # Servicio: edificio, nivel y ubicación obligatorios
        if cleaned.get('tipo') == 'SERVICIO':
            for campo, nombre in (('edificio', 'el edificio'), ('nivel', 'el nivel'), ('ubicacion', 'la ubicación')):
                if not cleaned.get(campo):
                    self.add_error(campo, f'Para un servicio debe indicar {nombre}.')
        return cleaned


class MaterialConSkuField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"[{obj.sku}] {obj.nombre}"

class ArticuloRequisicionForm(forms.ModelForm):
    material = MaterialConSkuField(
        queryset=Material.objects.all(),
        widget=forms.Select(attrs={'class': 'form-control select2-material'}),
        required=False,
    )

    class Meta:
        model = ArticuloRequisicion
        fields = ['cr8ca_itemderequisicionid', 'proveedor', 'material', 'cr8ca_articulo', 'cr8ca_cantidad', 'cr8ca_costoaproximado']
        widgets = {
            'cr8ca_itemderequisicionid': forms.HiddenInput(),
            'proveedor': forms.Select(attrs={'class': 'form-control select2-material'}),
            'cr8ca_articulo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Descripción del artículo'}),
            'cr8ca_cantidad': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'cr8ca_costoaproximado': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # PK must be non-required for new rows in formsets
        if 'cr8ca_itemderequisicionid' in self.fields:
            self.fields['cr8ca_itemderequisicionid'].required = False
            self.fields['cr8ca_itemderequisicionid'].widget = forms.HiddenInput()
            
            # Si la instancia no ha sido guardada (no existe en DB),
            # limpiamos el valor inicial del UUID para evitar que el 'empty_form'
            # del formset use el mismo UUID para todas las filas nuevas.
            if self.instance._state.adding:
                self.initial['cr8ca_itemderequisicionid'] = ''
        
        if 'id' in self.fields:
            self.fields['id'].required = False
            self.fields['id'].widget = forms.HiddenInput()

        # Material: readonly display (hidden field for PK, text for SKU)
        if 'material' in self.fields:
            self.fields['material'].widget = forms.HiddenInput()
            if self.instance.pk and self.instance.material_id:
                self.initial['material'] = self.instance.material_id

class BaseArticuloFormSet(forms.BaseInlineFormSet):
    """Cada artículo debe ser un material/servicio del catálogo con cantidad > 0."""

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        activos = 0
        for i, f in enumerate(self.forms, start=1):
            if not hasattr(f, 'cleaned_data') or not f.cleaned_data:
                continue
            if f.cleaned_data.get('DELETE'):
                continue
            activos += 1
            nombre = (f.cleaned_data.get('cr8ca_articulo') or f'Artículo {i}')[:60]
            # Solo los servicios pueden ir sin material. Si el material no existe, se
            # solicita su alta a Almacén y se agrega cuando lo aprueben.
            es_servicio = getattr(self.instance, 'tipo', None) == 'SERVICIO'
            if not es_servicio and not f.cleaned_data.get('material'):
                raise forms.ValidationError(
                    f'"{nombre}": seleccione un material del catálogo. Si no existe, '
                    'use "Crear solicitud de material" y espere la aprobación de Almacén.')
            cant = f.cleaned_data.get('cr8ca_cantidad')
            if not cant or cant <= 0:
                raise forms.ValidationError(f'"{nombre}": la cantidad debe ser mayor a 0.')
        if activos == 0:
            raise forms.ValidationError('Debe agregar al menos un material o servicio.')


ArticuloFormSet = forms.inlineformset_factory(
    Requisicion, ArticuloRequisicion,
    form=ArticuloRequisicionForm,
    formset=BaseArticuloFormSet,
    extra=0,
    can_delete=True
)

class DocumentoRequisicionForm(forms.ModelForm):
    class Meta:
        model = DocumentoRequisicion
        fields = ['archivo', 'nombre']
        widgets = {
            'archivo': forms.FileInput(attrs={'class': 'form-control'}),
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre del archivo'}),
        }

DocumentoFormSet = forms.inlineformset_factory(
    Requisicion, DocumentoRequisicion,
    form=DocumentoRequisicionForm,
    extra=1,
    can_delete=True
)
