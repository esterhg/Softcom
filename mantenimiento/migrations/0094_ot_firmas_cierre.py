from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mantenimiento', '0093_seed_checklist_elevadores'),
    ]

    operations = [
        migrations.AddField(
            model_name='ordentrabajo',
            name='operativo_salida',
            field=models.BooleanField(blank=True, null=True, help_text='Indica si el equipo quedó operativo al finalizar el mantenimiento', verbose_name='¿Operativo a la salida del técnico?'),
        ),
        migrations.AddField(
            model_name='ordentrabajo',
            name='comentarios_tecnico',
            field=models.TextField(blank=True, null=True, verbose_name='Comentarios y recomendaciones del técnico'),
        ),
        migrations.AddField(
            model_name='ordentrabajo',
            name='materiales_utilizados',
            field=models.TextField(blank=True, null=True, verbose_name='Material utilizado / Repuestos usados'),
        ),
        migrations.AddField(
            model_name='ordentrabajo',
            name='comentarios_cliente',
            field=models.TextField(blank=True, null=True, verbose_name='Comentarios del cliente'),
        ),
        migrations.AddField(
            model_name='ordentrabajo',
            name='firma_tecnico',
            field=models.TextField(blank=True, null=True, verbose_name='Firma del técnico (imagen)'),
        ),
        migrations.AddField(
            model_name='ordentrabajo',
            name='firma_tecnico_nombre',
            field=models.CharField(blank=True, max_length=150, null=True, verbose_name='Nombre del técnico que firma'),
        ),
        migrations.AddField(
            model_name='ordentrabajo',
            name='firma_cliente',
            field=models.TextField(blank=True, null=True, verbose_name='Firma del cliente (imagen)'),
        ),
        migrations.AddField(
            model_name='ordentrabajo',
            name='firma_cliente_nombre',
            field=models.CharField(blank=True, max_length=150, null=True, verbose_name='Nombre del cliente que firma'),
        ),
        migrations.AddField(
            model_name='ordentrabajo',
            name='firma_fecha',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Fecha/hora de firma'),
        ),
    ]
