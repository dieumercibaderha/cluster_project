from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('cluster_admin', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='USER_ACTION_LOG',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action_type', models.CharField(choices=[('creation', 'Creation'), ('modification', 'Modification'), ('suppression', 'Suppression'), ('consultation', 'Consultation'), ('autre', 'Autre')], default='autre', max_length=20)),
                ('method', models.CharField(max_length=10)),
                ('path', models.CharField(max_length=500)),
                ('description', models.CharField(blank=True, max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
