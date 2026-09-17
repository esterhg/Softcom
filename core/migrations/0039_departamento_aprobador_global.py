from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0038_perfilusuario_expo_push_token'),
    ]

    operations = [
        migrations.AddField(
            model_name='departamento',
            name='aprobador_global',
            field=models.BooleanField(
                default=False,
                verbose_name='Aprobador Global de Requisiciones',
                help_text=(
                    'Marca este departamento como la fuente del aprobador global para el flujo '
                    'de Power Automate. Solo un departamento debe tener esta opción activa. '
                    'El campo "Aprobador de Requisiciones" de este departamento será usado.'
                ),
            ),
        ),
    ]
