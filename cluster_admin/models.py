from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import FileExtensionValidator

class User(AbstractUser):
    admin = models.BooleanField(default=False)
    Organisation = models.CharField(max_length=255)
    Fonction = models.CharField(max_length=255)
    Photo = models.ImageField(upload_to='photos/', blank=True, null=True)
    Dates = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.username

class CATEGORIE_PARTENAIRE(models.Model):
    nom = models.CharField(max_length=255)
    description = models.TextField()

    def __str__(self):
        return self.nom

class PARTENAIRE(models.Model):
    nom = models.CharField(max_length=255)
    categorie = models.ForeignKey(CATEGORIE_PARTENAIRE, on_delete=models.CASCADE)
    bailleur_de_fonds = models.CharField(max_length=255)
    contact = models.CharField(max_length=255)
    Adresse_locale = models.TextField()

    def __str__(self):
        return self.nom

class ZONE(models.Model):
    nom = models.CharField(max_length=255)

    def __str__(self):
        return self.nom

class PROJETS(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    titre = models.CharField(max_length=255)
    description = models.TextField()
    budjets = models.IntegerField(default=0)
    partenaires = models.ForeignKey(PARTENAIRE, on_delete=models.CASCADE)
    Bailleur = models.CharField(max_length=255)
    debut_du_projet = models.DateField()
    fin_du_projet = models.DateField()
    etat_du_projet = models.CharField(max_length=255)
    zone_dintervention = models.ManyToManyField(ZONE)
    Budgets = models.IntegerField(default=0)
    

    def __str__(self):
        return self.titre

class TYPE_ACTIVITES(models.Model):
    nom = models.CharField(max_length=255)
    description = models.TextField()

    def __str__(self):
        return self.nom

class ACTIVITES(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    Titre = models.CharField(max_length=255)
    Projet = models.ForeignKey(PROJETS, on_delete=models.CASCADE)
    Type_activites = models.ForeignKey(TYPE_ACTIVITES, on_delete=models.CASCADE, null=True, blank=True)
    Homme = models.IntegerField(default=0)
    Femme = models.IntegerField(default=0)
    Nbre_de_beneficiaires = models.IntegerField(default=0)
    seed_kits = models.IntegerField()
    zone = models.ForeignKey(ZONE, on_delete=models.CASCADE)
    Donnees_mensuelles = models.FileField(
        upload_to='documents/',
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'doc', 'docx', 'xls', 'xlsx', 'csv'])]
    )
    piece_jointe = models.FileField(
        upload_to='media/',
        validators=[FileExtensionValidator(allowed_extensions=['mp4', 'avi', 'mov', 'jpg', 'jpeg', 'png', 'gif'])]
    )
    Debut_de_lactivite = models.DateField()
    fin_de_lactivite = models.DateField()
    dates = models.DateTimeField(auto_now_add=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    gps_accuracy_m = models.IntegerField(null=True, blank=True)
    gps_captured_at = models.DateTimeField(null=True, blank=True)
    gps_source = models.CharField(max_length=20, blank=True, default="browser")

    class Meta:
        indexes = [
            models.Index(fields=["latitude", "longitude"], name="activites_lat_lon_idx"),
            models.Index(fields=["Projet", "zone"], name="activites_proj_zone_idx"),
            models.Index(fields=["gps_captured_at"], name="activites_gps_time_idx"),
        ]

    def save(self, *args, **kwargs):
        #自动计算受益人总数
        self.Nbre_de_beneficiaires = (self.Homme or 0) + (self.Femme or 0)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.Titre


class USER_ACTION_LOG(models.Model):
    ACTION_CHOICES = [
        ("creation", "Creation"),
        ("modification", "Modification"),
        ("suppression", "Suppression"),
        ("consultation", "Consultation"),
        ("autre", "Autre"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    action_type = models.CharField(max_length=20, choices=ACTION_CHOICES, default="autre")
    method = models.CharField(max_length=10)
    path = models.CharField(max_length=500)
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} - {self.action_type} - {self.path}"


class EmailLog(models.Model):
    DIRECTION_CHOICES = [('sent', 'Envoyé'), ('received', 'Reçu'), ('draft', 'Brouillon')]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='email_logs')
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES, default='sent')
    from_email = models.EmailField()
    to_emails = models.TextField(default='[]')    # JSON list
    cc_emails = models.TextField(blank=True, default='[]')
    bcc_emails = models.TextField(blank=True, default='[]')
    subject = models.CharField(max_length=500, blank=True)
    body = models.TextField(blank=True)
    has_attachments = models.BooleanField(default=False)
    is_read = models.BooleanField(default=True)   # les envoyés sont considérés lus par défaut
    is_starred = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    label = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'direction', 'is_deleted']),
            models.Index(fields=['user', 'is_starred']),
        ]

    def __str__(self):
        return f"[{self.direction}] {self.subject or '(sans objet)'} — {self.user.username}"

    def get_to_list(self):
        import json as _json
        try:
            return _json.loads(self.to_emails)
        except Exception:
            return []

    def get_to_display(self):
        lst = self.get_to_list()
        return ', '.join(lst) if lst else ''


class PasswordResetOTP(models.Model):
    """Modèle pour stocker les codes OTP temporaires pour la réinitialisation de mot de passe"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='password_reset_otp')
    otp_code = models.CharField(max_length=6)
    email = models.EmailField()
    created_at = models.DateTimeField(auto_now_add=True)
    expired_at = models.DateTimeField()
    is_verified = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def is_valid(self):
        from django.utils import timezone
        return not self.is_verified and timezone.now() < self.expired_at

    def __str__(self):
        return f"OTP for {self.user.username} - {self.email}"