from django.db.models import Q
from django.utils import timezone

from .models import ACTIVITES, PROJETS


def notifications_globales_du_jour(request):
    """Expose les notifications du jour dans tous les templates."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {
            "notifications_du_jour": [],
            "nombre_notifications_du_jour": 0,
        }

    aujourd_hui = timezone.localdate()

    activites_du_jour_qs = (
        ACTIVITES.objects
        .filter(
            Q(Debut_de_lactivite=aujourd_hui)
            | Q(fin_de_lactivite=aujourd_hui)
            | Q(dates__date=aujourd_hui)
        )
        .select_related("Projet", "zone")
        .order_by("-dates", "-id")
    )

    projets_du_jour_qs = (
        PROJETS.objects
        .filter(Q(debut_du_projet=aujourd_hui) | Q(fin_du_projet=aujourd_hui))
        .select_related("partenaires")
        .order_by("-id")
    )

    notifications_du_jour = []
    avatars_notification = [
        "assets/images/avatar/2.png",
        "assets/images/avatar/3.png",
        "assets/images/avatar/4.png",
    ]

    for activite in activites_du_jour_qs:
        notifications_du_jour.append(
            {
                "avatar": avatars_notification[len(notifications_du_jour) % len(avatars_notification)],
                "titre": activite.Titre or "Activite sans titre",
                "description": f"Activite du jour - Projet: {activite.Projet.titre}",
                "date_affichage": "Aujourd'hui",
            }
        )

    for projet in projets_du_jour_qs:
        notifications_du_jour.append(
            {
                "avatar": avatars_notification[len(notifications_du_jour) % len(avatars_notification)],
                "titre": projet.titre or "Projet sans titre",
                "description": f"Projet du jour - Etat: {projet.etat_du_projet or '-'}",
                "date_affichage": "Aujourd'hui",
            }
        )

    notifications_du_jour = notifications_du_jour[:6]

    return {
        "notifications_du_jour": notifications_du_jour,
        "nombre_notifications_du_jour": len(notifications_du_jour),
    }
