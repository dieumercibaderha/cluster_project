from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("cluster_admin", "0004_activites_gps_indexes"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="activites",
            name="adresse_geo",
        ),
    ]
