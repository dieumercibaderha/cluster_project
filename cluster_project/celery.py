"""
Configuration Celery pour cluster_project
"""
import os
from celery import Celery

# Définir le module settings Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cluster_project.settings')

# Créer l'application Celery
app = Celery('cluster_project')

# Charger la configuration depuis Django settings
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover les tâches depuis les modules tasks.py des applications
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
