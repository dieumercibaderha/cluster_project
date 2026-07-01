from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cluster_admin", "0003_activites_structured_gps_fields"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="activites",
            index=models.Index(fields=["latitude", "longitude"], name="activites_lat_lon_idx"),
        ),
        migrations.AddIndex(
            model_name="activites",
            index=models.Index(fields=["Projet", "zone"], name="activites_proj_zone_idx"),
        ),
        migrations.AddIndex(
            model_name="activites",
            index=models.Index(fields=["gps_captured_at"], name="activites_gps_time_idx"),
        ),
    ]
