from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("cluster_admin", "0005_remove_activites_adresse_geo"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="activites",
            name="coordonnees_geo",
        ),
    ]
