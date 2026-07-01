from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cluster_admin", "0002_user_action_log"),
    ]

    operations = [
        migrations.AlterField(
            model_name="activites",
            name="coordonnees_geo",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="activites",
            name="latitude",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name="activites",
            name="longitude",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name="activites",
            name="gps_accuracy_m",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="activites",
            name="gps_captured_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="activites",
            name="gps_source",
            field=models.CharField(blank=True, default="browser", max_length=20),
        ),
        migrations.AddField(
            model_name="activites",
            name="adresse_geo",
            field=models.TextField(blank=True, default=""),
        ),
    ]
