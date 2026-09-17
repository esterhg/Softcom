from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('presupuestos', '0081_ordencompra_tipo_contrato'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ConfiguracionFlujoAprobacion',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('aprobador_nombre', models.CharField(
                    default='Ricardo Enrique Zerrate Torres',
                    help_text='Nombre que aparece en el correo de aprobación de Power Automate.',
                    max_length=200,
                    verbose_name='Nombre completo del Aprobador',
                )),
                ('aprobador_email', models.EmailField(
                    default='ricardo.zerrate@gia.mx',
                    help_text='Email al que Power Automate enviará la solicitud de aprobación.',
                    max_length=254,
                    verbose_name='Email del Aprobador',
                )),
                ('actualizado_en', models.DateTimeField(auto_now=True, verbose_name='Última actualización')),
                ('actualizado_por', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Actualizado por',
                )),
            ],
            options={
                'verbose_name': 'Configuración de Flujo de Aprobación',
                'verbose_name_plural': 'Configuración de Flujo de Aprobación',
            },
        ),
    ]
