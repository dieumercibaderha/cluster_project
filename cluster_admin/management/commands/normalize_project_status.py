from django.core.management.base import BaseCommand
from django.utils import timezone
from cluster_admin.models import PROJETS
from datetime import date


class Command(BaseCommand):
    help = 'Normalise les statuts des projets selon la logique métier (dates de début/fin)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Affiche les changements sans les appliquer'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        today = date.today()
        
        règles_métier = {
            'Projet en cours': [],
            'Projet planifié': [],
            'Projet clôturé': [],
        }
        
        total_projects = PROJETS.objects.count()
        updated_count = 0
        errors = []

        self.stdout.write(f"\n{'='*70}")
        self.stdout.write(f"Normalisation des statuts de projets")
        self.stdout.write(f"{'='*70}")
        self.stdout.write(f"Nombre total de projets: {total_projects}")
        self.stdout.write(f"Mode: {'DRY-RUN (pas de changement)' if dry_run else 'MISE À JOUR RÉELLE'}")
        self.stdout.write(f"Date de référence: {today}\n")

        for projet in PROJETS.objects.select_related('user').all():
            try:
                début = projet.debut_du_projet
                fin = projet.fin_du_projet
                ancien_status = projet.etat_du_projet
                
                # Appliquer la règle métier
                if fin < today:
                    nouveau_status = 'Projet clôturé'
                    règles_métier['Projet clôturé'].append(projet.id)
                elif début > today:
                    nouveau_status = 'Projet planifié'
                    règles_métier['Projet planifié'].append(projet.id)
                else:
                    nouveau_status = 'Projet en cours'
                    règles_métier['Projet en cours'].append(projet.id)
                
                # Vérifier si un changement est nécessaire
                needs_update = ancien_status != nouveau_status
                
                if needs_update:
                    status_icon = '→' if needs_update else '='
                    self.stdout.write(
                        f"  [{projet.id}] {projet.titre[:40]:<40} | "
                        f"'{ancien_status}' {status_icon} '{nouveau_status}'"
                    )
                    
                    if not dry_run:
                        projet.etat_du_projet = nouveau_status
                        projet.save(update_fields=['etat_du_projet'])
                    
                    updated_count += 1
                    
            except Exception as e:
                error_msg = f"Erreur pour projet {projet.id}: {str(e)}"
                self.stdout.write(self.style.ERROR(f"  ✗ {error_msg}"))
                errors.append(error_msg)

        # Résumé final
        self.stdout.write(f"\n{'='*70}")
        self.stdout.write(f"RÉSUMÉ FINAL")
        self.stdout.write(f"{'='*70}")
        self.stdout.write(f"Projets modifiés: {updated_count}/{total_projects}")
        self.stdout.write(f"")
        self.stdout.write(f"Répartition par nouveau statut:")
        for status, ids in règles_métier.items():
            self.stdout.write(f"  • {status:<25} → {len(ids)} projet(s)")
        
        if errors:
            self.stdout.write(f"\n{self.style.ERROR(f'Erreurs rencontrées: {len(errors)}')}")
            for err in errors:
                self.stdout.write(f"  • {err}")
        
        if dry_run:
            self.stdout.write(f"\n{self.style.WARNING('⚠️  DRY-RUN: aucune modification n\'a été appliquée.')}")
            self.stdout.write(f"Relancer sans --dry-run pour appliquer les changements.\n")
        else:
            self.stdout.write(f"\n{self.style.SUCCESS('✓ Normalisation appliquée avec succès!')}\n")
