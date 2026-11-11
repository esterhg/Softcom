from django import forms

from rrhh.selectors import horas as sel


class _UsuarioChoice(forms.ModelChoiceField):
    def label_from_instance(self, u):
        return u.get_full_name() or u.username


class ReporteHorasForm(forms.Form):
    colaborador = _UsuarioChoice(queryset=None, label='Colaborador')
    autorizado_por = _UsuarioChoice(queryset=None, required=False, label='Autorizado por')
    solicitado_por = _UsuarioChoice(queryset=None, required=False, label='Solicitado por')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nombre in ('colaborador', 'autorizado_por', 'solicitado_por'):
            self.fields[nombre].queryset = sel.usuarios_activos()


class CategoriaForm(forms.Form):
    nombre = forms.CharField(label='Nombre de la categoría', max_length=80,
                             error_messages={'required': 'El nombre de la categoría es obligatorio.'})


class _ReporteChoice(forms.ModelChoiceField):
    def label_from_instance(self, r):
        nombre = r.colaborador.get_full_name() or r.colaborador.username
        return f'{r.codigo} — {nombre}'


class HoraExtraForm(forms.Form):
    reporte = _ReporteChoice(queryset=None, label='Reporte Horas',
                             error_messages={'required': 'Selecciona el reporte de horas.'})
    colaborador = _UsuarioChoice(queryset=None, label='Colaborador')
    categoria = forms.ModelChoiceField(queryset=None, required=False, label='Categoría')
    entrada = forms.DateTimeField(label='Entrada', input_formats=['%Y-%m-%dT%H:%M'])
    salida = forms.DateTimeField(label='Salida', input_formats=['%Y-%m-%dT%H:%M'])
    cena = forms.BooleanField(required=False, label='Cena')
    justificacion = forms.CharField(
        label='Justificación (actividad realizada)',
        error_messages={'required': 'La justificación es obligatoria.'})

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['reporte'].queryset = sel.reportes_recientes()
        self.fields['colaborador'].queryset = sel.usuarios_activos()
        # Se aceptan categorías inactivas para no romper la edición de registros antiguos.
        self.fields['categoria'].queryset = sel.todas_las_categorias()
        for nombre in ('reporte', 'colaborador', 'categoria'):
            self.fields[nombre].widget.attrs['class'] = 'form-control'
        self.fields['reporte'].widget.attrs['required'] = True
        self.fields['colaborador'].widget.attrs['required'] = True

    def clean_justificacion(self):
        texto = self.cleaned_data['justificacion'].strip()
        if not texto:
            raise forms.ValidationError('La justificación es obligatoria.')
        return texto

    def clean(self):
        datos = super().clean()
        entrada, salida = datos.get('entrada'), datos.get('salida')
        if entrada and salida and salida <= entrada:
            self.add_error('salida', 'La salida debe ser posterior a la entrada.')
        return datos
