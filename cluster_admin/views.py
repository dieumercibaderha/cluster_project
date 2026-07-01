
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import get_user_model, authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.urls import reverse
from django.conf import settings
from django.utils.crypto import get_random_string
from django.utils import timezone
from django.utils.html import strip_tags
from django.http import HttpResponse, JsonResponse
from django.db.models import Q, Sum, Count
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from datetime import date, datetime, timedelta
from urllib.parse import quote
import base64
import csv
import importlib
import json
import os
import re
from email.mime.image import MIMEImage
from xml.sax.saxutils import escape
from .models import User, CATEGORIE_PARTENAIRE, PARTENAIRE, ZONE, PROJETS, TYPE_ACTIVITES, ACTIVITES, USER_ACTION_LOG, EmailLog, PasswordResetOTP


def send_email_now(user_id, to_emails, cc_emails, bcc_emails, subject, body,
                   message_type, attachment_names=None, **kwargs):
    """Envoie un email immédiatement et journalise l'opération."""
    try:
        user = User.objects.get(id=user_id)

        base_email_colors = {
            'hero_start': '#077f98',
            'hero_end': '#0a98b6',
            'chip_bg': 'rgba(255, 255, 255, 0.20)',
            'panel_bg': '#f3fbfd',
            'panel_border': '#d2edf3',
        }

        message_theme = {
            'notification': {
                'label': 'Notification',
                'intro': 'Vous recevez une information importante provenant de votre espace de travail.',
                'panel_title': 'Information de suivi',
                'cta_text': 'Ouvrir le portail',
            },
            'alert': {
                'label': 'Alerte',
                'intro': 'Ce message requiert votre attention prioritaire.',
                'panel_title': 'Action recommandee',
                'cta_text': 'Traiter maintenant',
            },
            'invitation': {
                'label': 'Invitation',
                'intro': 'Vous etes invite(e) a consulter les details et confirmer votre participation.',
                'panel_title': 'Participation',
                'cta_text': 'Voir l invitation',
            },
        }[message_type]

        logo_cid = 'logo_full'
        logo_content = None
        logo_candidates = [
            os.path.join(settings.BASE_DIR, 'static', 'assets', 'images', 'logo-full.png'),
        ]

        if getattr(settings, 'STATIC_ROOT', None):
            logo_candidates.append(
                os.path.join(settings.STATIC_ROOT, 'assets', 'images', 'logo-full.png')
            )

        for candidate in logo_candidates:
            if os.path.exists(candidate):
                with open(candidate, 'rb') as logo_file:
                    logo_content = logo_file.read()
                break

        logo_url = settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else 'localhost'
        logo_url = f"http://{logo_url}/static/assets/images/logo-full.png"

        subject_preview = subject if len(subject) <= 90 else f"{subject[:87]}..."
        sender_label = user.get_full_name().strip() or user.username or user.email
        sent_at_display = timezone.localtime(timezone.now()).strftime('%d/%m/%Y %H:%M')
        action_url_base = settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else 'localhost'
        action_url = f"http://{action_url_base}/email/"

        html_body = render_to_string(
            'emails/professional_outbound_email.html',
            {
                'subject': subject,
                'preview_text': f"{message_theme['label']} - {sender_label} - {subject_preview}",
                'body_html': body,
                'sender_display': sender_label,
                'sender_email': user.email or settings.DEFAULT_FROM_EMAIL,
                'sent_at': sent_at_display,
                'logo_url': logo_url,
                'logo_cid': logo_cid if logo_content else '',
                'action_url': action_url,
                'app_name': 'Cluster Securite Alimentaire',
                'message_type': message_type,
                'message_type_label': message_theme['label'],
                'message_intro': message_theme['intro'],
                'hero_start': base_email_colors['hero_start'],
                'hero_end': base_email_colors['hero_end'],
                'chip_bg': base_email_colors['chip_bg'],
                'panel_bg': base_email_colors['panel_bg'],
                'panel_border': base_email_colors['panel_border'],
                'panel_title': message_theme['panel_title'],
                'cta_text': message_theme['cta_text'],
            },
        )

        text_body = strip_tags(body or '') or '(Message HTML)'

        email = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=to_emails,
            cc=cc_emails,
            bcc=bcc_emails,
            reply_to=[user.email] if user.email else None,
        )
        email.attach_alternative(html_body, 'text/html')

        if logo_content:
            logo_mime = MIMEImage(logo_content, _subtype='png')
            logo_mime.add_header('Content-ID', f'<{logo_cid}>')
            logo_mime.add_header('Content-Disposition', 'inline', filename='logo-full.png')
            email.attach(logo_mime)

        email.send(fail_silently=False)

        EmailLog.objects.create(
            user=user,
            direction='sent',
            from_email=settings.DEFAULT_FROM_EMAIL,
            to_emails=json.dumps(to_emails),
            cc_emails=json.dumps(cc_emails),
            bcc_emails=json.dumps(bcc_emails),
            subject=subject,
            body=body,
            has_attachments=bool(attachment_names),
            is_read=True,
        )

        return {
            'status': 'success',
            'message': f"Email envoye avec succes a {len(to_emails)} destinataire(s).",
            'recipients_count': len(to_emails),
        }

    except Exception as e:
        try:
            user = User.objects.get(id=user_id)
            EmailLog.objects.create(
                user=user,
                direction='sent',
                from_email=settings.DEFAULT_FROM_EMAIL,
                to_emails=json.dumps(to_emails),
                subject=subject,
                body=f"[ERREUR] {str(e)}\\n\\n{body}",
                is_read=True,
            )
        except Exception:
            pass

        raise Exception(f"Erreur lors de l'envoi de l'email : {str(e)}")


def send_new_activity_notification_email(activity_obj, created_by_user):
    """Envoie un email de notification a tous les utilisateurs actifs ayant une adresse email."""
    recipients = list(
        User.objects
        .filter(is_active=True)
        .exclude(email__isnull=True)
        .exclude(email__exact="")
        .values_list("email", flat=True)
        .distinct()
    )

    if not recipients:
        return 0

    logo_cid = 'logo_full'
    logo_content = None
    logo_candidates = [
        os.path.join(settings.BASE_DIR, 'static', 'assets', 'images', 'logo-full.png'),
    ]

    if getattr(settings, 'STATIC_ROOT', None):
        logo_candidates.append(
            os.path.join(settings.STATIC_ROOT, 'assets', 'images', 'logo-full.png')
        )

    for candidate in logo_candidates:
        if os.path.exists(candidate):
            with open(candidate, 'rb') as logo_file:
                logo_content = logo_file.read()
            break

    host = settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else 'localhost'
    app_url = f"http://{host}"
    activities_url = f"{app_url}{reverse('activites')}"

    subject = f"[CLUSTER] Nouvelle activite creee : {activity_obj.Titre or 'Sans titre'}"
    created_at_display = timezone.localtime(timezone.now()).strftime('%d/%m/%Y a %H:%M')
    creator_display = created_by_user.get_full_name().strip() or created_by_user.username or created_by_user.email

    html_body = render_to_string(
        'emails/new_activity_notification_email.html',
        {
            'logo_cid': logo_cid if logo_content else '',
            'activity': activity_obj,
            'created_by_display': creator_display,
            'created_at_display': created_at_display,
            'activities_url': activities_url,
            'app_name': 'CLUSTER Securite Alimentaire',
        },
    )
    text_body = strip_tags(html_body)

    email_msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[settings.DEFAULT_FROM_EMAIL],
        bcc=recipients,
    )
    email_msg.attach_alternative(html_body, 'text/html')

    if logo_content:
        logo_mime = MIMEImage(logo_content, _subtype='png')
        logo_mime.add_header('Content-ID', f'<{logo_cid}>')
        logo_mime.add_header('Content-Disposition', 'inline', filename='logo-full.png')
        email_msg.attach(logo_mime)

    email_msg.send(fail_silently=False)
    return len(recipients)


@login_required
def auth_logout(request):
    logout(request)
    messages.info(request, "Vous avez été déconnecté avec succès.")
    return redirect('auth_login_creative')


@login_required
def profile_details(request):
    recent_activities = (
        ACTIVITES.objects
        .filter(user=request.user)
        .select_related("Projet", "zone")
        .order_by("-dates")[:10]
    )
    return render(
        request,
        'profile-details.html',
        {
            'user_obj': request.user,
            'recent_activities': recent_activities,
        },
    )



@login_required
def account_settings(request):
    user = request.user
    password_form = PasswordChangeForm(user)

    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'update_profile':
            # Mise à jour des champs standards
            user.first_name = request.POST.get('first_name', user.first_name)
            user.last_name = request.POST.get('last_name', user.last_name)
            user.email = request.POST.get('email', user.email)
            # Mise à jour des champs personnalisés
            user.Organisation = request.POST.get('Organisation', user.Organisation)
            user.Fonction = request.POST.get('Fonction', user.Fonction)
            
            # Gestion de l'upload de photo
            if 'Photo' in request.FILES:
                user.Photo = request.FILES['Photo']
                
            user.save()
            messages.success(request, "Votre profil a été mis à jour avec succès.")
            return redirect('account_settings')
            
        elif action == 'change_password':
            password_form = PasswordChangeForm(user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)  # Important pour ne pas déconnecter l'utilisateur
                messages.success(request, "Votre mot de passe a été changé avec succès.")
                return redirect('account_settings')
            else:
                messages.error(request, "Erreur lors du changement de mot de passe. Veuillez vérifier les champs.")

    # Ajout de la classe form-control pour le style Bootstrap
    for field in password_form.fields.values():
        field.widget.attrs.update({'class': 'form-control'})

    return render(request, 'account_settings.html', {'password_form': password_form})



def auth_login_creative(request):
    if request.user.is_authenticated:
        return redirect('index')
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            messages.success(request, f"Ravi de vous revoir, {user.username} !")
            # Redirection vers le tableau de bord (index) après connexion réussie
            return redirect('index')
        else:
            messages.error(request, "Nom d'utilisateur ou mot de passe incorrect.")
            
    return render(request, 'auth-login-creative.html')

def auth_register_minimal(request):
    if request.method == 'POST':
        # Récupération du modèle utilisateur actif (par défaut ou personnalisé)
        User = get_user_model()
        
        # Récupération des données du formulaire
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        username = request.POST.get('username')
        email = request.POST.get('email')
        Organisation = request.POST.get('Organisation')
        Fonction = request.POST.get('Fonction')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        Photo = request.FILES.get('Photo')

        # --- Validations ---
        if password != confirm_password:
            messages.error(request, "Les mots de passe ne correspondent pas.")
            return render(request, 'auth-register-minimal.html')
        
        if User.objects.filter(username=username).exists():
            messages.error(request, "Ce nom d'utilisateur est déjà pris.")
            return render(request, 'auth-register-minimal.html')
            
        if User.objects.filter(email=email).exists():
            messages.error(request, "Cette adresse email est déjà utilisée.")
            return render(request, 'auth-register-minimal.html')

        try:
            
            
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                is_staff=False,
                is_superuser=False,
            )
            user.admin = True
            user.first_name = first_name
            user.last_name = last_name
            
            # Sauvegarde des champs supplémentaires si le modèle les supporte
            user.Organisation = Organisation
            user.Fonction = Fonction
            if Photo:
                user.Photo = Photo
                
            user.save()
            
            messages.success(request, "Compte créé avec succès ! Vous pouvez maintenant vous connecter.")
            return redirect('auth_login_creative')
            
        except Exception as e:
            messages.error(request, f"Une erreur s'est produite lors de l'inscription : {e}")
            return render(request, 'auth-register-minimal.html')

    # Si c'est une requête GET, on affiche simplement le formulaire
    return render(request, 'auth-register-minimal.html')

# Create your views here.
def analytics(request):
    return render(request, 'analytics.html')

def type_activites(request, pk=None):
    # TYPE_ACTIVITES CRUD via type_activites.html
    url_name = getattr(getattr(request, "resolver_match", None), "url_name", "") or ""
    if url_name == "type_activites_update":
        action_hint = "update"
    elif url_name == "type_activites_delete":
        action_hint = "delete"
    else:
        action_hint = None

    if request.method == "POST":
        action = request.POST.get("action") or request.GET.get("action") or action_hint or "create"
        pk = pk or request.POST.get("pk") or request.GET.get("pk")

        if action == "delete" and pk:
            obj = get_object_or_404(TYPE_ACTIVITES, pk=pk)
            obj.delete()
            messages.success(request, "Type activite supprime avec succes.")
            return redirect("type_activites")

        if action == "update" and pk:
            obj = get_object_or_404(TYPE_ACTIVITES, pk=pk)
            obj.nom = request.POST.get("nom") or request.POST.get("note-has-title") or obj.nom
            obj.description = request.POST.get("description") or request.POST.get("note-has-description") or obj.description
            obj.save()
            messages.success(request, "Type activite mis a jour avec succes.")
            return redirect("type_activites")

        # create
        nom = request.POST.get("nom") or request.POST.get("note-has-title") or ""
        description = request.POST.get("description") or request.POST.get("note-has-description") or ""
        if nom or description:
            TYPE_ACTIVITES.objects.create(nom=nom, description=description)
            messages.success(request, "Type activite cree avec succes.")
            return redirect("type_activites")

    activites = TYPE_ACTIVITES.objects.all()
    activite = get_object_or_404(TYPE_ACTIVITES, pk=pk) if pk else None
    return render(request, "type_activites.html", {"activites": activites, "activite": activite})

@login_required
def apps_email(request):
    onglet_actif = request.GET.get('tab', 'sent')  # 'sent' par défaut
    numero_page = request.GET.get('page', 1)

    qs_base = EmailLog.objects.filter(user=request.user, is_deleted=False)

    if onglet_actif == 'starred':
        qs = qs_base.filter(is_starred=True)
    elif onglet_actif == 'draft':
        qs = qs_base.filter(direction='draft')
    elif onglet_actif == 'inbox':
        qs = qs_base.filter(direction='received')
    else:
        qs = qs_base.filter(direction='sent')

    paginateur = Paginator(qs, 15)
    pagination = paginateur.get_page(numero_page)

    nb_envoyes = qs_base.filter(direction='sent').count()
    nb_brouillons = qs_base.filter(direction='draft').count()
    nb_favoris = qs_base.filter(is_starred=True).count()
    nb_non_lus = qs_base.filter(direction='received', is_read=False).count()

    contexte = {
        'courriels': pagination,
        'pagination': pagination,
        'onglet_actif': onglet_actif,
        'nb_envoyes': nb_envoyes,
        'nb_brouillons': nb_brouillons,
        'nb_favoris': nb_favoris,
        'nb_non_lus': nb_non_lus,
    }
    return render(request, 'apps-email.html', contexte)


@login_required
def send_email(request):
    max_attachments = 10
    max_attachment_size = 10 * 1024 * 1024  # 10 MB par fichier

    def parse_recipients(raw_value):
        tokens = re.split(r'[;,\n\r]+', raw_value or '')
        cleaned = []
        invalid = []

        for token in tokens:
            email_value = token.strip()
            if not email_value:
                continue
            try:
                validate_email(email_value)
                cleaned.append(email_value)
            except ValidationError:
                invalid.append(email_value)

        # Garde l'ordre tout en supprimant les doublons.
        unique_cleaned = list(dict.fromkeys(cleaned))
        return unique_cleaned, invalid

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Méthode non autorisée.'}, status=405)

    to = request.POST.get('to', '').strip()
    cc = request.POST.get('cc', '').strip()
    bcc = request.POST.get('bcc', '').strip()
    subject = request.POST.get('subject', '').strip() or '(Sans objet)'
    body = request.POST.get('body', '').strip()
    raw_message_type = (request.POST.get('message_type') or '').strip().lower()
    action = request.POST.get('action', 'send')  # 'send' ou 'draft'
    attachments = request.FILES.getlist('attachments')
    draft_id_raw = (request.POST.get('draft_id') or '').strip()

    valid_message_types = {'notification', 'alert', 'invitation'}
    detected_text = f"{subject} {strip_tags(body or '')}".lower()

    if raw_message_type in valid_message_types:
        message_type = raw_message_type
    elif any(keyword in detected_text for keyword in ['urgent', 'alerte', 'incident', 'attention', 'important']):
        message_type = 'alert'
    elif any(keyword in detected_text for keyword in ['invitation', 'invite', 'reunion', 'meeting', 'event']):
        message_type = 'invitation'
    else:
        message_type = 'notification'

    base_email_colors = {
        'hero_start': '#077f98',
        'hero_end': '#0a98b6',
        'chip_bg': 'rgba(255, 255, 255, 0.20)',
        'panel_bg': '#f3fbfd',
        'panel_border': '#d2edf3',
    }

    message_theme = {
        'notification': {
            'label': 'Notification',
            'intro': 'Vous recevez une information importante provenant de votre espace de travail.',
            'panel_title': 'Information de suivi',
            'cta_text': 'Ouvrir le portail',
        },
        'alert': {
            'label': 'Alerte',
            'intro': 'Ce message requiert votre attention prioritaire.',
            'panel_title': 'Action recommandee',
            'cta_text': 'Traiter maintenant',
        },
        'invitation': {
            'label': 'Invitation',
            'intro': 'Vous etes invite(e) a consulter les details et confirmer votre participation.',
            'panel_title': 'Participation',
            'cta_text': 'Voir l invitation',
        },
    }[message_type]

    draft_obj = None
    if draft_id_raw.isdigit():
        draft_obj = EmailLog.objects.filter(
            pk=int(draft_id_raw),
            user=request.user,
            direction='draft',
            is_deleted=False,
        ).first()

    if action == 'draft':
        # En mode brouillon, on n'impose pas de destinataire valide.
        to_list = [x.strip() for x in re.split(r'[;,\n\r]+', to or '') if x.strip()]
        cc_list = [x.strip() for x in re.split(r'[;,\n\r]+', cc or '') if x.strip()]
        bcc_list = [x.strip() for x in re.split(r'[;,\n\r]+', bcc or '') if x.strip()]

        if draft_obj:
            draft_obj.from_email = getattr(request.user, 'email', '') or settings.DEFAULT_FROM_EMAIL
            draft_obj.to_emails = json.dumps(to_list)
            draft_obj.cc_emails = json.dumps(cc_list)
            draft_obj.bcc_emails = json.dumps(bcc_list)
            draft_obj.subject = subject
            draft_obj.body = body
            draft_obj.has_attachments = bool(attachments)
            draft_obj.save(
                update_fields=['from_email', 'to_emails', 'cc_emails', 'bcc_emails', 'subject', 'body', 'has_attachments']
            )
        else:
            EmailLog.objects.create(
                user=request.user,
                direction='draft',
                from_email=getattr(request.user, 'email', '') or settings.DEFAULT_FROM_EMAIL,
                to_emails=json.dumps(to_list),
                cc_emails=json.dumps(cc_list),
                bcc_emails=json.dumps(bcc_list),
                subject=subject,
                body=body,
                has_attachments=bool(attachments),
                is_read=True,
            )

        return JsonResponse({'success': True, 'message': 'Brouillon enregistré avec succès.'})

    # --- Envoi réel ---
    if not to:
        return JsonResponse({'success': False, 'message': 'Le champ « À » est obligatoire.'}, status=400)

    to_list, to_invalid = parse_recipients(to)
    cc_list, cc_invalid = parse_recipients(cc)
    bcc_list, bcc_invalid = parse_recipients(bcc)

    invalid_recipients = to_invalid + cc_invalid + bcc_invalid
    if invalid_recipients:
        return JsonResponse(
            {
                'success': False,
                'message': 'Adresses email invalides : ' + ', '.join(invalid_recipients)
            },
            status=400,
        )

    if not to_list:
        return JsonResponse({'success': False, 'message': 'Le champ « À » doit contenir au moins une adresse valide.'}, status=400)

    if len(attachments) > max_attachments:
        return JsonResponse(
            {'success': False, 'message': f'Trop de pièces jointes. Maximum autorisé : {max_attachments}.'},
            status=400,
        )

    oversized = [f.name for f in attachments if f.size and f.size > max_attachment_size]
    if oversized:
        return JsonResponse(
            {
                'success': False,
                'message': 'Fichier trop volumineux (10 MB max) : ' + ', '.join(oversized)
            },
            status=400,
        )

    attachment_names = [f.name for f in attachments]

    try:
        send_email_now(
            user_id=request.user.id,
            to_emails=to_list,
            cc_emails=cc_list,
            bcc_emails=bcc_list,
            subject=subject,
            body=body,
            message_type=message_type,
            attachment_names=attachment_names,
        )

        if draft_obj:
            draft_obj.is_deleted = True
            draft_obj.save(update_fields=['is_deleted'])

        return JsonResponse(
            {
                'success': True,
                'message': f"Email envoyé avec succès ({len(attachments)} pièce(s) jointe(s)).",
            }
        )
    except Exception as inner_e:
        return JsonResponse(
            {
                'success': False,
                'message': f"Erreur lors de l'envoi de l'email : {str(inner_e)}",
            },
            status=500,
        )


@login_required
def email_toggle_star(request, pk):
    if request.method != 'POST':
        return JsonResponse({'success': False}, status=405)
    email_obj = get_object_or_404(EmailLog, pk=pk, user=request.user)
    email_obj.is_starred = not email_obj.is_starred
    email_obj.save(update_fields=['is_starred'])
    return JsonResponse({'success': True, 'starred': email_obj.is_starred})


@login_required
def email_mark_read(request, pk):
    if request.method != 'POST':
        return JsonResponse({'success': False}, status=405)
    email_obj = get_object_or_404(EmailLog, pk=pk, user=request.user)
    email_obj.is_read = True
    email_obj.save(update_fields=['is_read'])
    return JsonResponse({'success': True})


@login_required
def email_delete(request, pk):
    if request.method != 'POST':
        return JsonResponse({'success': False}, status=405)
    email_obj = get_object_or_404(EmailLog, pk=pk, user=request.user)
    email_obj.is_deleted = True
    email_obj.save(update_fields=['is_deleted'])
    return JsonResponse({'success': True})


@login_required
def email_details(request, pk):
    email_obj = get_object_or_404(EmailLog, pk=pk, user=request.user, is_deleted=False)

    def charger_liste_json(valeur):
        try:
            return json.loads(valeur or '[]')
        except (TypeError, ValueError):
            return []

    to_list = charger_liste_json(email_obj.to_emails)
    cc_list = charger_liste_json(email_obj.cc_emails)
    bcc_list = charger_liste_json(email_obj.bcc_emails)

    return JsonResponse(
        {
            'success': True,
            'courriel': {
                'id': email_obj.pk,
                'sujet': email_obj.subject or '(Sans objet)',
                'expediteur': email_obj.from_email,
                'destinataires': to_list,
                'destinataires_affichage': ', '.join(to_list),
                'copie': cc_list,
                'copie_cachee': bcc_list,
                'date_creation': timezone.localtime(email_obj.created_at).strftime('%d/%m/%Y %H:%M'),
                'corps_html': email_obj.body or '<p>Aucun contenu.</p>',
                'est_favori': email_obj.is_starred,
                'a_pieces_jointes': email_obj.has_attachments,
            },
        }
    )


@login_required
def email_bulk_action(request):
    if request.method != 'POST':
        return JsonResponse({'success': False}, status=405)
    action = request.POST.get('action')
    ids_raw = request.POST.getlist('ids[]') or request.POST.getlist('ids')
    try:
        ids = [int(i) for i in ids_raw if str(i).isdigit()]
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'message': 'IDs invalides.'}, status=400)

    if not ids:
        return JsonResponse({'success': False, 'message': 'Aucun email sélectionné.'}, status=400)

    qs = EmailLog.objects.filter(pk__in=ids, user=request.user)

    if action == 'delete':
        qs.update(is_deleted=True)
    elif action == 'star':
        qs.update(is_starred=True)
    elif action == 'unstar':
        qs.update(is_starred=False)
    elif action == 'read':
        qs.update(is_read=True)
    elif action == 'unread':
        qs.update(is_read=False)
    else:
        return JsonResponse({'success': False, 'message': 'Action inconnue.'}, status=400)

    return JsonResponse({'success': True, 'affected': qs.count()})


@login_required
def email_user_suggestions(request):
    recherche = (request.GET.get('q') or '').strip()
    inclure_tous = request.GET.get('include_all') == '1'

    utilisateurs = User.objects.exclude(email__isnull=True).exclude(email__exact='')

    if recherche:
        utilisateurs = utilisateurs.filter(
            Q(email__icontains=recherche)
            | Q(username__icontains=recherche)
            | Q(first_name__icontains=recherche)
            | Q(last_name__icontains=recherche)
        )

    utilisateurs = utilisateurs.order_by('first_name', 'last_name', 'username')[:12]

    suggestions = []
    for utilisateur in utilisateurs:
        nom_complet = (f"{utilisateur.first_name} {utilisateur.last_name}").strip()
        if not nom_complet:
            nom_complet = utilisateur.username

        suggestions.append(
            {
                'id': utilisateur.pk,
                'email': utilisateur.email,
                'name': nom_complet,
                'label': f"{nom_complet} <{utilisateur.email}>",
            }
        )

    tous_les_emails = []
    if inclure_tous:
        tous_les_emails = list(
            User.objects.exclude(email__isnull=True)
            .exclude(email__exact='')
            .order_by('email')
            .values_list('email', flat=True)
            .distinct()
        )

    return JsonResponse(
        {
            'success': True,
            'suggestions': suggestions,
            'all_emails': tous_les_emails,
        }
    )


def gestion_zones(request, pk=None):
    # ZONE CRUD via gestion_zones.html
    url_name = getattr(getattr(request, "resolver_match", None), "url_name", "") or ""
    if url_name == "zone_update":
        action_hint = "update"
    elif url_name == "zone_delete":
        action_hint = "delete"
    else:
        action_hint = None

    if request.method == "POST":
        action = request.POST.get("action") or request.GET.get("action") or action_hint or "create"
        pk = pk or request.POST.get("pk") or request.GET.get("pk")

        if action == "delete" and pk:
            obj = get_object_or_404(ZONE, pk=pk)
            obj.delete()
            messages.success(request, "Zone supprimee avec succes.")
            return redirect("apps_notes")

        if action == "update" and pk:
            obj = get_object_or_404(ZONE, pk=pk)
            obj.nom = request.POST.get("nom") or request.POST.get("note-has-title") or obj.nom
            obj.save()
            messages.success(request, "Zone mise a jour avec succes.")
            return redirect("apps_notes")

        # create
        nom = request.POST.get("nom") or request.POST.get("note-has-title") or ""
        if nom:
            ZONE.objects.create(nom=nom)
            messages.success(request, "Zone creee avec succes.")
            return redirect("gestion_zones")

    zones = ZONE.objects.all()
    zone = get_object_or_404(ZONE, pk=pk) if pk else None
    return render(request, "gestion_zones.html", {"zones": zones, "zone": zone})

def activites(request, pk=None):
    # ACTIVITES CRUD via apps-tasks.html (modal expected)
    def parse_iso_date(value):
        if not value:
            return None
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None

    def is_activity_range_valid(project_obj, start_date, end_date):
        project_start = getattr(project_obj, "debut_du_projet", None)
        project_end = getattr(project_obj, "fin_du_projet", None)

        if not project_start or not project_end:
            return False, "Le projet sélectionné doit avoir des dates de début et de fin définies."
        if not start_date or not end_date:
            return False, "Les dates de l'activité sont invalides."
        if end_date < start_date:
            return False, "La date de fin de l'activité doit être postérieure ou égale à la date de début."
        if start_date < project_start or end_date > project_end:
            return False, "Les dates de l'activité doivent être comprises dans la période du projet sélectionné."

        return True, ""

    def parse_float_value(value):
        if value is None:
            return None
        value = str(value).strip()
        if not value:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def parse_int_value(value):
        if value is None:
            return None
        value = str(value).strip()
        if not value:
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    def parse_datetime_value(value):
        if value is None:
            return None
        value = str(value).strip()
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
        if timezone.is_naive(dt):
            return timezone.make_aware(dt, timezone.get_current_timezone())
        return dt

    def normalize_geo_payload(post_data):
        payload = {
            "latitude": None,
            "longitude": None,
            "gps_accuracy_m": None,
            "gps_captured_at": None,
            "gps_source": "",
        }

        lat = parse_float_value(post_data.get("latitude"))
        lon = parse_float_value(post_data.get("longitude"))

        if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
            payload["latitude"] = round(lat, 6)
            payload["longitude"] = round(lon, 6)

        payload["gps_accuracy_m"] = parse_int_value(post_data.get("gps_accuracy_m"))
        payload["gps_captured_at"] = parse_datetime_value(post_data.get("gps_captured_at"))
        payload["gps_source"] = (post_data.get("gps_source") or "").strip()[:20]
        return payload

    def has_valid_coordinates(geo_payload):
        return geo_payload["latitude"] is not None and geo_payload["longitude"] is not None

    def is_browser_geo_payload(geo_payload):
        # Accepter 'browser' (GPS navigateur) et 'map-pick' (sélection manuelle sur carte)
        return has_valid_coordinates(geo_payload) and geo_payload["gps_source"] in ("browser", "map-pick")

    url_name = getattr(getattr(request, "resolver_match", None), "url_name", "") or ""
    if url_name == "activites_update":
        action_hint = "update"
    elif url_name == "activites_delete":
        action_hint = "delete"
    else:
        action_hint = None

    if request.method == "POST":
        action = request.POST.get("action") or request.GET.get("action") or action_hint or "create"
        pk = pk or request.POST.get("pk") or request.GET.get("pk")

        if action == "delete" and pk:
            obj = get_object_or_404(ACTIVITES, pk=pk)
            obj.delete()
            messages.success(request, "Activité supprimée avec succès.")
            return redirect("activites")

        if action == "update" and pk:
            obj = get_object_or_404(ACTIVITES, pk=pk)
            obj.Titre = request.POST.get("Titre") or obj.Titre
            geo_payload = normalize_geo_payload(request.POST)
            if not is_browser_geo_payload(geo_payload):
                messages.error(request, "La modification exige une géolocalisation récupérée depuis le navigateur.")
                return redirect("activites")

            selected_project = obj.Projet
            if request.POST.get("Projet"):
                selected_project = get_object_or_404(PROJETS, pk=request.POST.get("Projet"))

            if request.POST.get("Type_activites"):
                obj.Type_activites = get_object_or_404(TYPE_ACTIVITES, pk=request.POST.get("Type_activites"))
            if request.POST.get("zone"):
                obj.zone = get_object_or_404(ZONE, pk=request.POST.get("zone"))
            if request.POST.get("Homme"):
                obj.Homme = int(request.POST.get("Homme"))
            if request.POST.get("Femme"):
                obj.Femme = int(request.POST.get("Femme"))
            if request.POST.get("seed_kits"):
                obj.seed_kits = request.POST.get("seed_kits")
            if request.FILES.get("Donnees_mensuelles"):
                obj.Donnees_mensuelles = request.FILES.get("Donnees_mensuelles")
            if request.FILES.get("piece_jointe"):
                obj.piece_jointe = request.FILES.get("piece_jointe")

            selected_start = parse_iso_date(request.POST.get("Debut_de_lactivite") or obj.Debut_de_lactivite)
            selected_end = parse_iso_date(request.POST.get("fin_de_lactivite") or obj.fin_de_lactivite)
            is_valid, error_message = is_activity_range_valid(selected_project, selected_start, selected_end)
            if not is_valid:
                messages.error(request, error_message)
                return redirect("activites")

            obj.Projet = selected_project
            obj.Debut_de_lactivite = selected_start
            obj.fin_de_lactivite = selected_end

            if geo_payload["latitude"] is not None and geo_payload["longitude"] is not None:
                obj.latitude = geo_payload["latitude"]
                obj.longitude = geo_payload["longitude"]

            if geo_payload["gps_accuracy_m"] is not None:
                obj.gps_accuracy_m = geo_payload["gps_accuracy_m"]
            if geo_payload["gps_captured_at"] is not None:
                obj.gps_captured_at = geo_payload["gps_captured_at"]
            if geo_payload["gps_source"]:
                obj.gps_source = geo_payload["gps_source"]

            obj.save()
            messages.success(request, "Activité mise à jour avec succès.")
            return redirect("activites")

        # create
        create_project = get_object_or_404(PROJETS, pk=request.POST.get("Projet"))
        create_start = parse_iso_date(request.POST.get("Debut_de_lactivite"))
        create_end = parse_iso_date(request.POST.get("fin_de_lactivite"))
        is_valid, error_message = is_activity_range_valid(create_project, create_start, create_end)
        if not is_valid:
            messages.error(request, error_message)
            return redirect("activites")

        geo_payload = normalize_geo_payload(request.POST)
        if not is_browser_geo_payload(geo_payload):
            messages.error(request, "La création exige une géolocalisation récupérée depuis le navigateur.")
            return redirect("activites")

        created_activity = ACTIVITES.objects.create(
            user=request.user,
            Titre=request.POST.get("Titre", ""),
            Projet=create_project,
            Type_activites=get_object_or_404(TYPE_ACTIVITES, pk=request.POST.get("Type_activites")) if request.POST.get("Type_activites") else None,
            Homme=int(request.POST.get("Homme") or 0),
            Femme=int(request.POST.get("Femme") or 0),
            seed_kits=request.POST.get("seed_kits") or 0,
            zone=get_object_or_404(ZONE, pk=request.POST.get("zone")),
            Donnees_mensuelles=request.FILES.get("Donnees_mensuelles"),
            piece_jointe=request.FILES.get("piece_jointe"),
            Debut_de_lactivite=create_start,
            fin_de_lactivite=create_end,
            latitude=geo_payload["latitude"],
            longitude=geo_payload["longitude"],
            gps_accuracy_m=geo_payload["gps_accuracy_m"],
            gps_captured_at=geo_payload["gps_captured_at"],
            gps_source=geo_payload["gps_source"] or "browser",
        )

        try:
            notified_count = send_new_activity_notification_email(created_activity, request.user)
            if notified_count:
                messages.info(
                    request,
                    f"Notification email envoyée à {notified_count} utilisateur(s) suite à la création de l'activité."
                )
        except Exception:
            messages.warning(
                request,
                "Activité créée, mais l'envoi de la notification email a échoué."
            )

        messages.success(request, "Activité créée avec succès.")
        return redirect("activites")

    activites = ACTIVITES.objects.select_related("user", "Projet", "zone").all()
    show_only_mine = str(request.GET.get("mine", "")).lower() in {"1", "true", "yes", "mine"}
    if show_only_mine and request.user.is_authenticated:
        activites = activites.filter(user=request.user)

    activite = get_object_or_404(ACTIVITES, pk=pk) if pk else None
    projets = PROJETS.objects.select_related("partenaires").all()
    if show_only_mine and request.user.is_authenticated:
        projets_with_activities = projets.filter(activites__user=request.user).distinct()
    else:
        projets_with_activities = projets.filter(activites__isnull=False).distinct()
    return render(
        request,
        "activites.html",
        {
            "activites": activites,
            "activite": activite,
            "projets": projets,
            "projets_with_activities": projets_with_activities,
            "zones": ZONE.objects.all(),
            "type_activites": TYPE_ACTIVITES.objects.all(),
        },
    )

def _extract_activity_coordinates(activite):
    latitude = getattr(activite, "latitude", None)
    longitude = getattr(activite, "longitude", None)

    if latitude is not None and longitude is not None:
        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except (TypeError, ValueError):
            latitude, longitude = None, None

        if latitude is not None and -90 <= latitude <= 90 and -180 <= longitude <= 180:
            return latitude, longitude

    return None


def _parse_bbox_params(request):
    min_lat = request.GET.get("min_lat")
    max_lat = request.GET.get("max_lat")
    min_lng = request.GET.get("min_lng")
    max_lng = request.GET.get("max_lng")

    if not all([min_lat, max_lat, min_lng, max_lng]):
        return None

    try:
        min_lat = float(min_lat)
        max_lat = float(max_lat)
        min_lng = float(min_lng)
        max_lng = float(max_lng)
    except (TypeError, ValueError):
        return None

    if min_lat > max_lat:
        min_lat, max_lat = max_lat, min_lat
    if min_lng > max_lng:
        min_lng, max_lng = max_lng, min_lng

    return min_lat, max_lat, min_lng, max_lng


@login_required
def activites_carte(request):
    activites_qs = ACTIVITES.objects.select_related("Projet", "zone").order_by("-dates")

    activites_sans_coordonnees = 0
    premier_point = None
    for activite in activites_qs:
        coordonnees = _extract_activity_coordinates(activite)
        if not coordonnees:
            activites_sans_coordonnees += 1
            continue

        if premier_point is None:
            premier_point = coordonnees

    centre_lat = premier_point[0] if premier_point else 0
    centre_lon = premier_point[1] if premier_point else 0

    return render(
        request,
        "activites-carte.html",
        {
            "centre_lat": centre_lat,
            "centre_lon": centre_lon,
            "activites_sans_coordonnees": activites_sans_coordonnees,
            "projets_filtres": PROJETS.objects.order_by("titre").values("id", "titre"),
            "zones_filtres": ZONE.objects.order_by("nom").values("id", "nom"),
        },
    )


@login_required
def activites_carte_google(request):
    google_maps_api_key = (getattr(settings, "GOOGLE_MAPS_API_KEY", "") or "").strip()
    activites_qs = ACTIVITES.objects.select_related("Projet", "zone").order_by("-dates")

    activites_sans_coordonnees = 0
    premier_point = None
    for activite in activites_qs:
        coordonnees = _extract_activity_coordinates(activite)
        if not coordonnees:
            activites_sans_coordonnees += 1
            continue

        if premier_point is None:
            premier_point = coordonnees

    centre_lat = premier_point[0] if premier_point else 0
    centre_lon = premier_point[1] if premier_point else 0

    return render(
        request,
        "activites-carte-google.html",
        {
            "centre_lat": centre_lat,
            "centre_lon": centre_lon,
            "activites_sans_coordonnees": activites_sans_coordonnees,
            "projets_filtres": PROJETS.objects.order_by("titre").values("id", "titre"),
            "zones_filtres": ZONE.objects.order_by("nom").values("id", "nom"),
            "google_maps_api_key": google_maps_api_key,
            "google_maps_js_enabled": bool(google_maps_api_key),
        },
    )


@login_required
def activites_carte_points_api(request):
    bbox = _parse_bbox_params(request)
    projet_id = (request.GET.get("projet") or "").strip()
    zone_id = (request.GET.get("zone") or "").strip()

    activites_qs = ACTIVITES.objects.select_related("Projet", "zone").order_by("-dates")

    if projet_id.isdigit():
        activites_qs = activites_qs.filter(Projet_id=int(projet_id))
    if zone_id.isdigit():
        activites_qs = activites_qs.filter(zone_id=int(zone_id))

    points_carte = []
    ignores_bbox = 0
    ignores_invalides = 0

    for activite in activites_qs:
        coordonnees = _extract_activity_coordinates(activite)
        if not coordonnees:
            ignores_invalides += 1
            continue

        latitude, longitude = coordonnees
        if bbox:
            min_lat, max_lat, min_lng, max_lng = bbox
            if not (min_lat <= latitude <= max_lat and min_lng <= longitude <= max_lng):
                ignores_bbox += 1
                continue

        points_carte.append(
            {
                "id": activite.pk,
                "titre": activite.Titre,
                "projet": activite.Projet.titre,
                "zone": activite.zone.nom,
                "latitude": latitude,
                "longitude": longitude,
                "gps_accuracy_m": getattr(activite, "gps_accuracy_m", None),
                "gps_source": (getattr(activite, "gps_source", "") or "browser"),
            }
        )

    return JsonResponse(
        {
            "points": points_carte,
            "count": len(points_carte),
            "ignored_invalid": ignores_invalides,
            "ignored_bbox": ignores_bbox,
        }
    )
def auth_404_cover(request):
    return render(request, 'auth-404-cover.html')

def auth_404_creative(request):
    return render(request, 'auth-404-creative.html')

def auth_404_minimal(request):
    return render(request, 'auth-404-minimal.html')



def auth_maintenance_cover(request):
    return render(request, 'auth-maintenance-cover.html')

def auth_maintenance_creative(request):
    return render(request, 'auth-maintenance-creative.html')

def auth_maintenance_minimal(request):
    return render(request, 'auth-maintenance-minimal.html')
















def auth_reset_creative(request):
    return render(request, 'auth-reset-creative.html')

def auth_verify_creative(request):
    return render(request, 'auth-verify-creative.html')


@login_required
def utilisateurs_create(request):
    if not request.user.admin:
        return redirect('index')  # or some forbidden page
    # USER create/update via utilisateurs-create.html
    pk = request.GET.get("pk") or request.POST.get("pk")
    if request.method == "POST":
        if pk:
            user_obj = get_object_or_404(User, pk=pk)
            user_obj.username = request.POST.get("username") or request.POST.get("usernameInput") or user_obj.username
            user_obj.email = request.POST.get("email") or request.POST.get("mailInput") or user_obj.email
            user_obj.first_name = request.POST.get("first_name") or request.POST.get("fullnameInput") or user_obj.first_name
            user_obj.Organisation = request.POST.get("Organisation") or request.POST.get("companyInput") or user_obj.Organisation
            user_obj.Fonction = request.POST.get("Fonction") or request.POST.get("designationInput") or user_obj.Fonction
            if request.FILES.get("Photo"):
                user_obj.Photo = request.FILES.get("Photo")
            if request.POST.get("password"):
                user_obj.set_password(request.POST.get("password"))
            user_obj.save()
            messages.success(request, "Utilisateur mis a jour avec succes.")
            return redirect("utilisateurs")
        else:
            password = request.POST.get("password")
            password_confirm = request.POST.get("password_confirm")
            if password != password_confirm:
                messages.error(request, "Les mots de passe ne correspondent pas.")
                return redirect("utilisateurs_create")
            user_obj = User.objects.create_user(
                username=request.POST.get("username") or request.POST.get("usernameInput") or "",
                email=request.POST.get("email") or request.POST.get("mailInput") or "",
                password=password or "changeme123",
                is_staff=False,
                is_superuser=False,
            )
            user_obj.first_name = request.POST.get("first_name") or request.POST.get("prenomInput") or ""
            user_obj.last_name = request.POST.get("last_name") or request.POST.get("nomInput") or ""
            user_obj.Organisation = request.POST.get("Organisation") or request.POST.get("companyInput") or ""
            user_obj.Fonction = request.POST.get("Fonction") or request.POST.get("designationInput") or ""
            if request.FILES.get("Photo"):
                user_obj.Photo = request.FILES.get("Photo")
            user_obj.admin = request.POST.get("admin") == "on"
            user_obj.save()
            messages.success(request, "Utilisateur cree avec succes.")
            return redirect("utilisateurs")

    return render(request, "utilisateurs-create.html")
@login_required
def utilisateurs_view(request, pk):
    if not request.user.admin:
        return redirect('index')
    # USER detail/delete via utilisateurs-view.html
    pk = pk or request.GET.get("pk") or request.POST.get("pk")
    user_obj = get_object_or_404(User, pk=pk) if pk else None

    if user_obj and request.method == "POST":
        action = request.POST.get("action") or request.GET.get("action")

        if action == "delete":
            user_obj.delete()
            messages.success(request, "Utilisateur supprime avec succes.")
            return redirect("utilisateurs")

        if action == "activate":
            user_obj.is_active = True
            user_obj.save(update_fields=["is_active"])
            messages.success(request, "Utilisateur active avec succes.")
            return redirect("utilisateurs_view_pk", pk=user_obj.pk)

        if action == "deactivate":
            if request.user.pk == user_obj.pk:
                messages.error(request, "Vous ne pouvez pas desactiver votre propre compte.")
            else:
                user_obj.is_active = False
                user_obj.save(update_fields=["is_active"])
                messages.success(request, "Utilisateur desactive avec succes.")
            return redirect("utilisateurs_view_pk", pk=user_obj.pk)

        if action == "toggle_admin":
            user_obj.admin = not bool(user_obj.admin)
            user_obj.save(update_fields=["admin"])
            messages.success(request, "Role administrateur mis a jour.")
            return redirect("utilisateurs_view_pk", pk=user_obj.pk)

        if action == "reset_password":
            temporary_password = get_random_string(10)
            user_obj.set_password(temporary_password)
            user_obj.save(update_fields=["password"])
            messages.success(
                request,
                f"Mot de passe reinitialise. Nouveau mot de passe temporaire: {temporary_password}",
            )
            return redirect("utilisateurs_view_pk", pk=user_obj.pk)

        messages.warning(request, "Action non prise en charge.")
        return redirect("utilisateurs_view_pk", pk=user_obj.pk)
    user_detail = user_obj
    user_projects = PROJETS.objects.filter(user=user_obj).select_related("partenaires") if user_obj else []
    user_actions = USER_ACTION_LOG.objects.filter(user=user_obj)[:30] if user_obj else []
    return render(request, "utilisateurs-view.html", {
        "user_detail": user_detail,
        "user_projects": user_projects,
        "user_actions": user_actions,
    })

@login_required
def utilisateurs(request):
    if not request.user.admin:
        return redirect('index')
    queryset_utilisateurs, statut_filtre = _filtrer_utilisateurs_par_statut(request.GET.get("statut"))
    users_list = queryset_utilisateurs

    total_utilisateurs = queryset_utilisateurs.count()
    utilisateurs_actifs = queryset_utilisateurs.filter(is_active=True).count()
    utilisateurs_inactifs = queryset_utilisateurs.filter(is_active=False).count()
    nouveaux_utilisateurs = queryset_utilisateurs.filter(date_joined__gte=timezone.now() - timedelta(days=30)).count()

    taux_actifs = (utilisateurs_actifs * 100 / total_utilisateurs) if total_utilisateurs else 0
    taux_nouveaux = (nouveaux_utilisateurs * 100 / total_utilisateurs) if total_utilisateurs else 0
    taux_inactifs = (utilisateurs_inactifs * 100 / total_utilisateurs) if total_utilisateurs else 0

    return render(
        request,
        "utilisateurs.html",
        {
            "users_list": users_list,
            "total_utilisateurs": total_utilisateurs,
            "utilisateurs_actifs": utilisateurs_actifs,
            "nouveaux_utilisateurs": nouveaux_utilisateurs,
            "utilisateurs_inactifs": utilisateurs_inactifs,
            "taux_actifs": taux_actifs,
            "taux_nouveaux": taux_nouveaux,
            "taux_inactifs": taux_inactifs,
            "statut_filtre": statut_filtre,
        },
    )


def _filtrer_utilisateurs_par_statut(statut):
    queryset_utilisateurs = User.objects.all()
    statut_filtre = (statut or "tous").lower()

    if statut_filtre == "actifs":
        return queryset_utilisateurs.filter(is_active=True), "actifs"
    if statut_filtre in {"passifs", "inactifs", "inactive"}:
        return queryset_utilisateurs.filter(is_active=False), "passifs"
    return queryset_utilisateurs, "tous"


# ===== PASSWORD RESET WITH OTP =====

def password_reset_email_step(request):
    """Affiche le formulaire de demande d'email pour réinitialisation de mot de passe"""
    if request.user.is_authenticated:
        return redirect('index')
    
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        
        if not email:
            messages.error(request, "Veuillez entrer une adresse email.")
            return render(request, 'auth-resetting-creative.html', {'step': 'email'})
        
        try:
            user = User.objects.get(email=email)
            # Générer un code OTP (6 chiffres)
            otp_code = get_random_string(length=6, allowed_chars='0123456789')
            expired_at = timezone.now() + timedelta(minutes=10)
            
            # Supprimer tout OTP expiré ou existant pour cet utilisateur
            PasswordResetOTP.objects.filter(user=user).delete()
            
            # Créer le nouvel OTP
            otp_obj = PasswordResetOTP.objects.create(
                user=user,
                otp_code=otp_code,
                email=email,
                expired_at=expired_at
            )
            
            # Charger le logo en CID (image embarquée, fiable dans tous les clients email)
            logo_cid = 'otp_logo_full'
            logo_content = None
            logo_candidates = [
                os.path.join(settings.BASE_DIR, 'static', 'assets', 'images', 'logo-full.png'),
            ]
            if getattr(settings, 'STATIC_ROOT', None):
                logo_candidates.append(
                    os.path.join(settings.STATIC_ROOT, 'assets', 'images', 'logo-full.png')
                )
            for candidate in logo_candidates:
                if os.path.exists(candidate):
                    with open(candidate, 'rb') as lf:
                        logo_content = lf.read()
                    break

            # Envoyer l'email avec l'OTP
            otp_form_url = f"{request.build_absolute_uri(reverse('password_reset_otp_step'))}?email={quote(email)}"
            context = {
                'user': user,
                'otp_code': otp_code,
                'expiration_minutes': 10,
                'logo_cid': logo_cid if logo_content else '',
                'otp_form_url': otp_form_url,
                'reset_email': email,
            }

            html_email = render_to_string('emails/password_reset_otp_email.html', context)
            text_email = strip_tags(html_email)

            email_msg = EmailMultiAlternatives(
                subject="Code de réinitialisation de mot de passe - CLUSTER",
                body=text_email,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[email]
            )
            email_msg.attach_alternative(html_email, "text/html")

            if logo_content:
                logo_mime = MIMEImage(logo_content, _subtype='png')
                logo_mime.add_header('Content-ID', f'<{logo_cid}>')
                logo_mime.add_header('Content-Disposition', 'inline', filename='logo-full.png')
                email_msg.attach(logo_mime)

            email_msg.send(fail_silently=True)
            
            # Rediriger vers la page de vérification OTP
            request.session['reset_email'] = email
            messages.success(request, f"Un code OTP a été envoyé à {email}. Veuillez le vérifier.")
            return redirect('password_reset_otp_step')
        
        except User.DoesNotExist:
            # Pour la sécurité, ne pas révéler si l'email existe ou non
            messages.success(request, "Si cet email existe dans notre base de données, un code OTP a été envoyé.")
            request.session['reset_email'] = email
            return redirect('password_reset_otp_step')
    
    return render(request, 'auth-resetting-creative.html', {'step': 'email'})


def password_reset_otp_step(request):
    """Affiche le formulaire de vérification OTP"""
    if request.user.is_authenticated:
        return redirect('index')

    reset_email = request.session.get('reset_email')

    # Permet d'ouvrir directement l'étape OTP depuis un lien email.
    if not reset_email:
        email_from_link = request.GET.get('email', '').strip()
        if email_from_link:
            try:
                validate_email(email_from_link)
                reset_email = email_from_link
                request.session['reset_email'] = reset_email
            except ValidationError:
                reset_email = None

    if request.method == 'POST' and not reset_email:
        email_from_form = request.POST.get('reset_email', '').strip()
        if email_from_form:
            try:
                validate_email(email_from_form)
                reset_email = email_from_form
                request.session['reset_email'] = reset_email
            except ValidationError:
                reset_email = None

    if not reset_email:
        messages.error(request, "Veuillez d'abord entrer votre email.")
        return redirect('password_reset_email_step')
    
    if request.method == 'POST':
        otp_code = request.POST.get('otp_code', '').strip()
        
        if not otp_code or len(otp_code) != 6:
            messages.error(request, "Veuillez entrer un code OTP de 6 chiffres.")
            return render(request, 'auth-resetting-creative.html', {
                'step': 'otp',
                'reset_email': reset_email
            })
        
        try:
            user = User.objects.get(email=reset_email)
            otp_obj = PasswordResetOTP.objects.get(user=user, email=reset_email)
            
            if not otp_obj.is_valid():
                messages.error(request, "Le code OTP a expiré ou a déjà été utilisé. Veuillez recommencer.")
                return render(request, 'auth-resetting-creative.html', {
                    'step': 'otp',
                    'reset_email': reset_email
                })
            
            if otp_obj.otp_code != otp_code:
                messages.error(request, "Code OTP incorrect.")
                return render(request, 'auth-resetting-creative.html', {
                    'step': 'otp',
                    'reset_email': reset_email
                })
            
            # Marquer l'OTP comme vérifié
            otp_obj.is_verified = True
            otp_obj.save()
            
            request.session['otp_verified'] = True
            request.session['reset_user_id'] = user.id
            messages.success(request, "Code OTP vérifié. Vous pouvez maintenant réinitialiser votre mot de passe.")
            return redirect('password_reset_password_step')
        
        except (User.DoesNotExist, PasswordResetOTP.DoesNotExist):
            messages.error(request, "Code OTP introuvable ou expiré. Veuillez demander un nouveau code.")
            return render(request, 'auth-resetting-creative.html', {
                'step': 'otp',
                'reset_email': reset_email
            })
    
    return render(request, 'auth-resetting-creative.html', {
        'step': 'otp',
        'reset_email': reset_email
    })


def password_reset_password_step(request):
    """Affiche le formulaire de réinitialisation du mot de passe"""
    if request.user.is_authenticated:
        return redirect('index')
    
    otp_verified = request.session.get('otp_verified')
    reset_user_id = request.session.get('reset_user_id')
    reset_email = request.session.get('reset_email')
    
    if not otp_verified or not reset_user_id:
        messages.error(request, "Veuillez d'abord vérifier votre code OTP.")
        return redirect('password_reset_email_step')
    
    if request.method == 'POST':
        new_password = request.POST.get('new_password', '').strip()
        confirm_password = request.POST.get('confirm_password', '').strip()
        
        if not new_password or not confirm_password:
            messages.error(request, "Veuillez remplir tous les champs.")
            return render(request, 'auth-resetting-creative.html', {
                'step': 'password',
                'reset_email': reset_email
            })
        
        if new_password != confirm_password:
            messages.error(request, "Les mots de passe ne correspondent pas.")
            return render(request, 'auth-resetting-creative.html', {
                'step': 'password',
                'reset_email': reset_email
            })
        
        if len(new_password) < 8:
            messages.error(request, "Le mot de passe doit contenir au moins 8 caractères.")
            return render(request, 'auth-resetting-creative.html', {
                'step': 'password',
                'reset_email': reset_email
            })
        
        try:
            user = User.objects.get(id=reset_user_id, email=reset_email)
            user.set_password(new_password)
            user.save()
            
            # Supprimer l'OTP une fois utilisé
            PasswordResetOTP.objects.filter(user=user).delete()
            
            # Nettoyer la session
            for key in ['otp_verified', 'reset_user_id', 'reset_email']:
                request.session.pop(key, None)
            
            messages.success(request, "Votre mot de passe a été réinitialisé avec succès. Vous pouvez maintenant vous connecter.")
            return redirect('auth_login_creative')
        
        except User.DoesNotExist:
            messages.error(request, "Une erreur s'est produite. Veuillez recommencer.")
            return redirect('password_reset_email_step')
    
    return render(request, 'auth-resetting-creative.html', {
        'step': 'password',
        'reset_email': reset_email
    })


@login_required
def utilisateurs_export(request):
    if not request.user.admin:
        return redirect('index')
    export_format = (request.GET.get("format") or "csv").lower()
    utilisateurs_qs, statut_filtre = _filtrer_utilisateurs_par_statut(request.GET.get("statut"))
    utilisateurs_data = list(utilisateurs_qs.order_by("username"))

    if export_format == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = "attachment; filename=utilisateurs.csv"
        writer = csv.writer(response)
        writer.writerow(["username", "email", "organisation", "fonction", "is_active", "date_joined"])
        for user in utilisateurs_data:
            writer.writerow([
                user.username,
                user.email,
                user.Organisation,
                user.Fonction,
                "actif" if user.is_active else "passif",
                user.date_joined.strftime("%Y-%m-%d %H:%M"),
            ])
        return response

    if export_format == "txt":
        response = HttpResponse(content_type="text/plain; charset=utf-8")
        response["Content-Disposition"] = "attachment; filename=utilisateurs.txt"
        lines = ["Liste des utilisateurs", f"Filtre: {statut_filtre}", ""]
        for user in utilisateurs_data:
            lines.append(
                f"- {user.username} | {user.email} | {user.Organisation} | {user.Fonction} | {'actif' if user.is_active else 'passif'}"
            )
        response.write("\n".join(lines))
        return response

    if export_format == "xml":
        response = HttpResponse(content_type="application/xml; charset=utf-8")
        response["Content-Disposition"] = "attachment; filename=utilisateurs.xml"
        xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>', f'<utilisateurs filtre="{escape(statut_filtre)}">']
        for user in utilisateurs_data:
            xml_parts.append("  <utilisateur>")
            xml_parts.append(f"    <username>{escape(user.username or '')}</username>")
            xml_parts.append(f"    <email>{escape(user.email or '')}</email>")
            xml_parts.append(f"    <organisation>{escape(user.Organisation or '')}</organisation>")
            xml_parts.append(f"    <fonction>{escape(user.Fonction or '')}</fonction>")
            xml_parts.append(f"    <statut>{'actif' if user.is_active else 'passif'}</statut>")
            xml_parts.append(f"    <date_joined>{user.date_joined.strftime('%Y-%m-%d %H:%M')}</date_joined>")
            xml_parts.append("  </utilisateur>")
        xml_parts.append("</utilisateurs>")
        response.write("\n".join(xml_parts))
        return response

    if export_format == "excel":
        response = HttpResponse(content_type="application/vnd.ms-excel; charset=utf-8")
        response["Content-Disposition"] = "attachment; filename=utilisateurs.xls"
        writer = csv.writer(response, delimiter='\t')
        writer.writerow(["Username", "Email", "Organisation", "Fonction", "Statut", "Date inscription"])
        for user in utilisateurs_data:
            writer.writerow([
                user.username,
                user.email,
                user.Organisation,
                user.Fonction,
                "Actif" if user.is_active else "Passif",
                user.date_joined.strftime("%Y-%m-%d %H:%M"),
            ])
        return response

    if export_format == "pdf":
        rows = []
        for user in utilisateurs_data:
            rows.append(
                "<tr>"
                f"<td>{escape(user.username or '')}</td>"
                f"<td>{escape(user.email or '')}</td>"
                f"<td>{escape(user.Organisation or '')}</td>"
                f"<td>{escape(user.Fonction or '')}</td>"
                f"<td>{'Actif' if user.is_active else 'Passif'}</td>"
                "</tr>"
            )

        html = (
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<style>"
            "@page { size: A4; margin: 16mm; }"
            "body{font-family:Arial,sans-serif;color:#0f172a;font-size:12px}"
            "h2{margin:0 0 8px 0}"
            "p{margin:0 0 14px 0;color:#475569}"
            "table{width:100%;border-collapse:collapse}"
            "th,td{border:1px solid #dbe2ea;padding:8px;text-align:left;vertical-align:top}"
            "th{background:#f1f5f9;font-weight:700}"
            "</style></head><body>"
            "<h2>Export Utilisateurs</h2>"
            f"<p>Filtre: {escape(statut_filtre)}</p>"
            "<table><thead><tr><th>Username</th><th>Email</th><th>Organisation</th><th>Fonction</th><th>Statut</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
            "</body></html>"
        )

        try:
            weasyprint_module = importlib.import_module("weasyprint")
            html_renderer = weasyprint_module.HTML
        except ImportError:
            messages.error(request, "WeasyPrint n'est pas installé sur le serveur. Exécutez: pip install weasyprint")
            return redirect(f"{reverse('utilisateurs')}?statut={statut_filtre}")

        pdf_bytes = html_renderer(string=html, base_url=request.build_absolute_uri('/')).write_pdf()
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = "attachment; filename=utilisateurs.pdf"
        return response

    # print: page imprimable (navigateur -> Imprimer)
    rows = []
    for user in utilisateurs_data:
        rows.append(
            "<tr>"
            f"<td>{escape(user.username or '')}</td>"
            f"<td>{escape(user.email or '')}</td>"
            f"<td>{escape(user.Organisation or '')}</td>"
            f"<td>{escape(user.Fonction or '')}</td>"
            f"<td>{'Actif' if user.is_active else 'Passif'}</td>"
            "</tr>"
        )
    title = "Export Utilisateurs"
    auto_print = "window.print();" if export_format == "print" else ""
    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{title}</title>"
        "<style>body{font-family:Arial,sans-serif;padding:24px}"
        "table{width:100%;border-collapse:collapse}th,td{border:1px solid #ddd;padding:8px;text-align:left}"
        "th{background:#f4f6f8}</style></head><body>"
        f"<h2>{title}</h2><p>Filtre: {escape(statut_filtre)}</p>"
        "<table><thead><tr><th>Username</th><th>Email</th><th>Organisation</th><th>Fonction</th><th>Statut</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        f"<script>{auto_print}</script></body></html>"
    )
    return HttpResponse(html)






@login_required
def index(request):
    today = timezone.localdate()
    total_projects = PROJETS.objects.count()

    total_partenaires = PARTENAIRE.objects.count()
    awaiting_partenaires = PARTENAIRE.objects.filter(projets__isnull=True).count()
    awaiting_partenaires_percent = round((awaiting_partenaires / total_partenaires) * 100) if total_partenaires else 0
    partenaires_with_projects = PARTENAIRE.objects.filter(projets__isnull=False).distinct().count()
    partenaires_without_projects = max(total_partenaires - partenaires_with_projects, 0)
    partenaires_with_projects_percent = round((partenaires_with_projects / total_partenaires) * 100) if total_partenaires else 0
    partenaires_without_projects_percent = round((partenaires_without_projects / total_partenaires) * 100) if total_partenaires else 0

    total_categories = CATEGORIE_PARTENAIRE.objects.count()
    converted_categories = CATEGORIE_PARTENAIRE.objects.filter(partenaire__isnull=False).distinct().count()
    converted_categories_percent = round((converted_categories / total_categories) * 100) if total_categories else 0

    pending_keywords = [
        "en attente", "attente", "pending", "not started", "non commence", "non commencé",
        "a demarrer", "à démarrer", "to start", "planifie", "planifié"
    ]
    pending_query = Q()
    for keyword in pending_keywords:
        pending_query |= Q(etat_du_projet__icontains=keyword)

    pending_projects_count = PROJETS.objects.filter(pending_query).count()
    conversion_rate_percent = round((pending_projects_count / total_projects) * 100, 2) if total_projects else 0
    conversion_rate_bar_percent = round(conversion_rate_percent)
    pending_projects_qs = PROJETS.objects.filter(pending_query)
    partenaires_with_pending_projects = PARTENAIRE.objects.filter(projets__in=pending_projects_qs).distinct().count()
    partenaires_with_pending_projects_percent = round((partenaires_with_pending_projects / total_partenaires) * 100) if total_partenaires else 0

    completed_keywords = [
        "termine", "terminé", "completed", "complete", "done", "fini", "cloture", "clôturé", "closed"
    ]
    in_progress_keywords = [
        "en cours", "in progress", "progress", "ongoing"
    ]

    completed_query = Q()
    for keyword in completed_keywords:
        completed_query |= Q(etat_du_projet__icontains=keyword)

    in_progress_query = Q()
    for keyword in in_progress_keywords:
        in_progress_query |= Q(etat_du_projet__icontains=keyword)

    completed_projects = PROJETS.objects.filter(completed_query).count()
    in_progress_projects_qs = PROJETS.objects.filter(in_progress_query)
    in_progress_projects = in_progress_projects_qs.count()
    completed_projects_percent = round((completed_projects / total_projects) * 100) if total_projects else 0
    completed_projects_qs = PROJETS.objects.filter(completed_query)
    partenaires_with_completed_projects = PARTENAIRE.objects.filter(projets__in=completed_projects_qs).distinct().count()
    partenaires_with_completed_projects_percent = round((partenaires_with_completed_projects / total_partenaires) * 100) if total_partenaires else 0

    # Fallback: si les statuts ne suivent pas une nomenclature stable,
    # on considere les projets non termines comme "en cours".
    if in_progress_projects == 0 and total_projects > completed_projects:
        in_progress_projects_qs = PROJETS.objects.exclude(completed_query)
        in_progress_projects = in_progress_projects_qs.count()

    projects_progress_percent = round((in_progress_projects / total_projects) * 100) if total_projects else 0

    beneficiaries_by_activity_qs = (
        ACTIVITES.objects
        .values('Titre')
        .annotate(total_beneficiaires=Sum('Nbre_de_beneficiaires'))
        .order_by('-total_beneficiaires')[:6]
    )
    beneficiaries_by_activity = [
        {
            'title': item['Titre'] or 'Activite sans titre',
            'total_beneficiaires': int(item['total_beneficiaires'] or 0),
        }
        for item in beneficiaries_by_activity_qs
    ]
    beneficiaries_chart_labels = [item['title'] for item in beneficiaries_by_activity]
    beneficiaries_chart_values = [item['total_beneficiaires'] for item in beneficiaries_by_activity]
    total_beneficiaries = sum(beneficiaries_chart_values)

    beneficiaries_completed_projects = int(
        ACTIVITES.objects.filter(Projet__in=completed_projects_qs).aggregate(total=Sum('Nbre_de_beneficiaires'))['total'] or 0
    )
    beneficiaries_pending_projects = int(
        ACTIVITES.objects.filter(Projet__in=pending_projects_qs).aggregate(total=Sum('Nbre_de_beneficiaires'))['total'] or 0
    )
    beneficiaries_in_progress_projects = int(
        ACTIVITES.objects.filter(Projet__in=in_progress_projects_qs).aggregate(total=Sum('Nbre_de_beneficiaires'))['total'] or 0
    )

    completed_projects_with_beneficiaries = PROJETS.objects.filter(completed_query, activites__isnull=False).distinct().count()
    pending_projects_with_beneficiaries = PROJETS.objects.filter(pending_query, activites__isnull=False).distinct().count()
    in_progress_projects_with_beneficiaries = in_progress_projects_qs.filter(activites__isnull=False).distinct().count()

    beneficiaries_completed_percent = (beneficiaries_completed_projects / total_beneficiaries) * 100 if total_beneficiaries else 0
    beneficiaries_pending_percent = (beneficiaries_pending_projects / total_beneficiaries) * 100 if total_beneficiaries else 0
    beneficiaries_in_progress_percent = (beneficiaries_in_progress_projects / total_beneficiaries) * 100 if total_beneficiaries else 0

    def format_percent_display(value):
        if not value:
            return "0%"
        formatted = f"{value:.3f}".rstrip('0').rstrip('.')
        return f"{formatted.replace('.', ',')}%"

    beneficiaries_completed_percent_display = format_percent_display(beneficiaries_completed_percent)
    beneficiaries_pending_percent_display = format_percent_display(beneficiaries_pending_percent)
    beneficiaries_in_progress_percent_display = format_percent_display(beneficiaries_in_progress_percent)

    upcoming_activities = (
        ACTIVITES.objects
        .filter(Debut_de_lactivite__gte=today)
        .select_related('Projet', 'zone')
        .order_by('Debut_de_lactivite', 'id')[:4]
    )

    activites_du_jour_qs = (
        ACTIVITES.objects
        .filter(
            Q(Debut_de_lactivite=today)
            | Q(fin_de_lactivite=today)
            | Q(dates__date=today)
        )
        .select_related('Projet', 'zone')
        .order_by('-dates', '-id')
    )

    projets_du_jour_qs = (
        PROJETS.objects
        .filter(Q(debut_du_projet=today) | Q(fin_du_projet=today))
        .select_related('partenaires')
        .order_by('-id')
    )

    notifications_du_jour = []
    avatars_notification = [
        'assets/images/avatar/2.png',
        'assets/images/avatar/3.png',
        'assets/images/avatar/4.png',
    ]

    for activite in activites_du_jour_qs:
        notifications_du_jour.append(
            {
                'avatar': avatars_notification[len(notifications_du_jour) % len(avatars_notification)],
                'titre': activite.Titre or 'Activite sans titre',
                'description': f"Activite du jour - Projet: {activite.Projet.titre}",
                'date_affichage': "Aujourd'hui",
            }
        )

    for projet in projets_du_jour_qs:
        notifications_du_jour.append(
            {
                'avatar': avatars_notification[len(notifications_du_jour) % len(avatars_notification)],
                'titre': projet.titre or 'Projet sans titre',
                'description': f"Projet du jour - Etat: {projet.etat_du_projet or '-'}",
                'date_affichage': "Aujourd'hui",
            }
        )

    notifications_du_jour = notifications_du_jour[:6]
    nombre_notifications_du_jour = len(notifications_du_jour)

    # Beneficiaries par partenaire (total pour tous leurs projets) - Hommes et Femmes separes
    partenaires_beneficiaries = (
        PARTENAIRE.objects
        .annotate(
            total_homme=Sum('projets__activites__Homme'),
            total_femme=Sum('projets__activites__Femme')
        )
        .values('nom', 'total_homme', 'total_femme')
        .order_by('-total_homme', '-total_femme')
    )
    partenaires_chart_labels = [p['nom'] or 'Partenaire sans nom' for p in partenaires_beneficiaries]
    partenaires_chart_homme = [int(p['total_homme'] or 0) for p in partenaires_beneficiaries]
    partenaires_chart_femme = [int(p['total_femme'] or 0) for p in partenaires_beneficiaries]
    partenaires_chart_total = [h + f for h, f in zip(partenaires_chart_homme, partenaires_chart_femme)]

    # Beneficiaries par zone (uniquement les zones avec des activités) - Hommes et Femmes separes
    zones_beneficiaries = (
        ACTIVITES.objects
        .filter(zone__isnull=False)
        .values('zone__nom')
        .annotate(
            total_homme=Sum('Homme'),
            total_femme=Sum('Femme')
        )
        .order_by('-total_homme', '-total_femme')
    )
    zones_chart_labels = [z['zone__nom'] or 'Zone sans nom' for z in zones_beneficiaries if (z['total_homme'] or 0) + (z['total_femme'] or 0) > 0]
    zones_chart_homme = [int(z['total_homme'] or 0) for z in zones_beneficiaries if (z['total_homme'] or 0) + (z['total_femme'] or 0) > 0]
    zones_chart_femme = [int(z['total_femme'] or 0) for z in zones_beneficiaries if (z['total_homme'] or 0) + (z['total_femme'] or 0) > 0]
    zones_chart_total = [h + f for h, f in zip(zones_chart_homme, zones_chart_femme)]

    context = {
        'awaiting_partenaires': awaiting_partenaires,
        'total_partenaires': total_partenaires,
        'awaiting_partenaires_percent': awaiting_partenaires_percent,
        'converted_categories': converted_categories,
        'total_categories': total_categories,
        'converted_categories_percent': converted_categories_percent,
        'pending_projects_count': pending_projects_count,
        'conversion_rate_percent': conversion_rate_percent,
        'conversion_rate_bar_percent': conversion_rate_bar_percent,
        'projects_total': total_projects,
        'projects_completed': completed_projects,
        'completed_projects_percent': completed_projects_percent,
        'projects_in_progress': in_progress_projects,
        'projects_progress_percent': projects_progress_percent,
        'partenaires_with_projects': partenaires_with_projects,
        'partenaires_without_projects': partenaires_without_projects,
        'partenaires_with_projects_percent': partenaires_with_projects_percent,
        'partenaires_without_projects_percent': partenaires_without_projects_percent,
        'partenaires_with_pending_projects': partenaires_with_pending_projects,
        'partenaires_with_pending_projects_percent': partenaires_with_pending_projects_percent,
        'partenaires_with_completed_projects': partenaires_with_completed_projects,
        'partenaires_with_completed_projects_percent': partenaires_with_completed_projects_percent,
        'beneficiaries_by_activity': beneficiaries_by_activity,
        'beneficiaries_chart_labels': beneficiaries_chart_labels,
        'beneficiaries_chart_values': beneficiaries_chart_values,
        'total_beneficiaries': total_beneficiaries,
        'beneficiaries_completed_projects': beneficiaries_completed_projects,
        'beneficiaries_pending_projects': beneficiaries_pending_projects,
        'beneficiaries_in_progress_projects': beneficiaries_in_progress_projects,
        'completed_projects_with_beneficiaries': completed_projects_with_beneficiaries,
        'pending_projects_with_beneficiaries': pending_projects_with_beneficiaries,
        'in_progress_projects_with_beneficiaries': in_progress_projects_with_beneficiaries,
        'beneficiaries_completed_percent': beneficiaries_completed_percent,
        'beneficiaries_pending_percent': beneficiaries_pending_percent,
        'beneficiaries_in_progress_percent': beneficiaries_in_progress_percent,
        'beneficiaries_completed_percent_display': beneficiaries_completed_percent_display,
        'beneficiaries_pending_percent_display': beneficiaries_pending_percent_display,
        'beneficiaries_in_progress_percent_display': beneficiaries_in_progress_percent_display,
        'upcoming_activities': upcoming_activities,
        'notifications_du_jour': notifications_du_jour,
        'nombre_notifications_du_jour': nombre_notifications_du_jour,
        'partenaires_chart_labels': partenaires_chart_labels,
        'partenaires_chart_homme': partenaires_chart_homme,
        'partenaires_chart_femme': partenaires_chart_femme,
        'partenaires_chart_total': partenaires_chart_total,
        'zones_chart_labels': zones_chart_labels,
        'zones_chart_homme': zones_chart_homme,
        'zones_chart_femme': zones_chart_femme,
        'zones_chart_total': zones_chart_total,
    }
    return render(request, 'index.html', context)




@login_required
def creation_categorie_partenaire(request, pk=None):
    # CATEGORIE_PARTENAIRE create/update via categorie_create.html
    pk = pk or request.GET.get("pk") or request.POST.get("pk")
    if request.method == "POST":
        nom = request.POST.get("nom") or request.POST.get("fullnameInput") or request.POST.get("companyInput") or ""
        description = request.POST.get("description") or request.POST.get("descriptionInput") or ""
        if pk:
            obj = get_object_or_404(CATEGORIE_PARTENAIRE, pk=pk)
            obj.nom = nom or obj.nom
            obj.description = description or obj.description
            obj.save()
            messages.success(request, "Categorie partenaire mise a jour avec succes.")
            return redirect("categorie_partenaires")
        CATEGORIE_PARTENAIRE.objects.create(nom=nom, description=description)
        messages.success(request, "Categorie partenaire créée avec succes.")
        return redirect("categorie_partenaires")
    categorie = get_object_or_404(CATEGORIE_PARTENAIRE, pk=pk) if pk else None
    return render(request, "creation_categorie_partenaire.html", {"categorie": categorie})

@login_required
def voir_categorie_partenaire(request, pk):
    # CATEGORIE_PARTENAIRE detail/delete via categorie_view.html
    pk = pk or request.GET.get("pk") or request.POST.get("pk")
    if pk and request.method == "POST" and (request.POST.get("action") == "delete" or request.GET.get("action") == "delete"):
        obj = get_object_or_404(CATEGORIE_PARTENAIRE, pk=pk)
        obj.delete()
        messages.success(request, "Categorie partenaire supprimee avec succes.")
        return redirect("categorie_partenaires")
    categorie = get_object_or_404(CATEGORIE_PARTENAIRE, pk=pk) if pk else None
    return render(request, "voir_categorie.html", {"categorie": categorie})

@login_required
def categorie_partenaires(request):
    categories = CATEGORIE_PARTENAIRE.objects.all()
    return render(request, "categorie_partenaires.html", {"categories": categories})

@login_required
def partenaires(request, pk=None):
    # PARTENAIRE CRUD via partenaires.html
    url_name = getattr(getattr(request, "resolver_match", None), "url_name", "") or ""
    if url_name == "partenaire_update":
        action_hint = "update"
    elif url_name == "partenaire_delete":
        action_hint = "delete"
    else:
        action_hint = None

    if request.method == "POST":
        action = request.POST.get("action") or request.GET.get("action") or action_hint or "create"
        pk = pk or request.POST.get("pk") or request.GET.get("pk")

        if action == "delete" and pk:
            obj = get_object_or_404(PARTENAIRE, pk=pk)
            obj.delete()
            messages.success(request, "Partenaire supprime avec succes.")
            return redirect("partenaires")

        categorie_id = request.POST.get("categorie")
        categorie = get_object_or_404(CATEGORIE_PARTENAIRE, pk=categorie_id) if categorie_id else None

        if action == "update" and pk:
            obj = get_object_or_404(PARTENAIRE, pk=pk)
            obj.nom = request.POST.get("nom") or obj.nom
            if categorie:
                obj.categorie = categorie
            obj.bailleur_de_fonds = request.POST.get("bailleur_de_fonds") or obj.bailleur_de_fonds
            obj.contact = request.POST.get("contact") or obj.contact
            obj.Adresse_locale = request.POST.get("Adresse_locale") or obj.Adresse_locale
            obj.save()
            messages.success(request, "Partenaire mis a jour avec succes.")
            return redirect("partenaires")

        # create
        if categorie:
            PARTENAIRE.objects.create(
                nom=request.POST.get("nom", ""),
                categorie=categorie,
                bailleur_de_fonds=request.POST.get("bailleur_de_fonds", ""),
                contact=request.POST.get("contact", ""),
                Adresse_locale=request.POST.get("Adresse_locale", ""),
            )
            messages.success(request, "Partenaire cree avec succes.")
            return redirect("partenaires")

    partenaires_queryset = PARTENAIRE.objects.select_related("categorie").order_by("-pk")
    paginator = Paginator(partenaires_queryset, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    query_params = request.GET.copy()
    query_params.pop("page", None)
    pagination_query = query_params.urlencode()

    partenaires = page_obj.object_list
    partenaire = get_object_or_404(PARTENAIRE, pk=pk) if pk else None
    return render(
        request,
        "partenaires.html",
        {
            "partenaires": partenaires,
            "partenaire": partenaire,
            "categories": CATEGORIE_PARTENAIRE.objects.all(),
            "page_obj": page_obj,
            "pagination_query": pagination_query,
        },
    )

@login_required
def projects_create(request, pk=None):
    # PROJETS create/update via projects-create.html
    def parse_budget_value(raw_value, fallback=0):
        value = str(raw_value or "").strip()
        if value == "":
            return fallback, True
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return fallback, False
        if parsed < 0:
            return fallback, False
        return parsed, True

    pk = pk or request.GET.get("pk") or request.POST.get("pk")
    projet = get_object_or_404(PROJETS, pk=pk) if pk else None

    if request.method == "POST":
        action = request.POST.get("action") or ("update" if projet else "create")
        titre = request.POST.get("titre") or request.POST.get("projectName") or ""
        description = request.POST.get("description") or ""
        partenaire_id = request.POST.get("partenaires") or request.POST.get("projectClient")
        partenaire = PARTENAIRE.objects.filter(pk=partenaire_id).first() if partenaire_id else None
        debut = request.POST.get("debut_du_projet") or request.POST.get("projectReleaseDate")
        fin = request.POST.get("fin_du_projet") or request.POST.get("targetReleaseDate") or debut
        etat = request.POST.get("etat_du_projet") or request.POST.get("projectStatus") or ""
        bailleur = request.POST.get("Bailleur") or request.POST.get("billingType") or ""
        budget_raw = request.POST.get("budjets") or request.POST.get("budget") or request.POST.get("projectBudget") or request.POST.get("Budgets")
        zones_ids = request.POST.getlist("zone_dintervention")
        etat = etat.strip()

        if not etat and projet:
            etat = projet.etat_du_projet or ""

        if not etat:
            etat = "Non demarre"

        if not partenaire:
            messages.error(request, "Veuillez selectionner un partenaire valide.")
            return render(
                request,
                "projects-create.html",
                {"projet": projet, "partenaires": PARTENAIRE.objects.all(), "zones": ZONE.objects.all()},
            )

        if not debut or not fin:
            messages.error(request, "Veuillez renseigner les dates de debut et de fin du projet.")
            return render(
                request,
                "projects-create.html",
                {"projet": projet, "partenaires": PARTENAIRE.objects.all(), "zones": ZONE.objects.all()},
            )

        budget_value, budget_is_valid = parse_budget_value(
            budget_raw,
            fallback=(projet.budjets if projet else 0),
        )
        if not budget_is_valid:
            messages.error(request, "Le champ budjets doit etre un entier positif ou nul.")
            return render(
                request,
                "projects-create.html",
                {"projet": projet, "partenaires": PARTENAIRE.objects.all(), "zones": ZONE.objects.all()},
            )

        if action == "update" and projet:
            projet.titre = titre or projet.titre
            projet.description = description or projet.description
            projet.partenaires = partenaire
            projet.debut_du_projet = debut or projet.debut_du_projet
            projet.fin_du_projet = fin or projet.fin_du_projet
            projet.etat_du_projet = etat or projet.etat_du_projet
            projet.Bailleur = bailleur or projet.Bailleur
            projet.budjets = budget_value
            projet.Budgets = budget_value
            projet.save()
            if zones_ids:
                projet.zone_dintervention.set(ZONE.objects.filter(pk__in=zones_ids))
            messages.success(request, "Projet mis a jour avec succes.")
            return redirect("projects")

        new_projet = PROJETS.objects.create(
            user=request.user,
            titre=titre,
            description=description,
            partenaires=partenaire,
            Bailleur=bailleur,
            budjets=budget_value,
            Budgets=budget_value,
            debut_du_projet=debut,
            fin_du_projet=fin,
            etat_du_projet=etat,
        )
        if zones_ids:
            new_projet.zone_dintervention.set(ZONE.objects.filter(pk__in=zones_ids))
        messages.success(request, "Projet cree avec succes.")
        return redirect("projects")

    return render(
        request,
        "projects-create.html",
        {"projet": projet, "partenaires": PARTENAIRE.objects.all(), "zones": ZONE.objects.all()},
    )

@login_required
def projects_view(request, pk):
    projet = get_object_or_404(
        PROJETS.objects.select_related("user", "partenaires").prefetch_related("zone_dintervention"),
        pk=pk,
    )
    if request.method == "POST" and request.POST.get("action") == "delete":
        projet.delete()
        messages.success(request, "Projet supprimé avec succès.")
        return redirect("projects")
    activites = ACTIVITES.objects.filter(Projet=projet).select_related("zone", "user")
    activites_count = activites.count()
    if projet.debut_du_projet and projet.fin_du_projet:
        duration_delta = (projet.fin_du_projet - projet.debut_du_projet).days
        project_duration_days = duration_delta + 1 if duration_delta >= 0 else 0
        days_left_delta = (projet.fin_du_projet - date.today()).days
        project_days_left = days_left_delta if days_left_delta > 0 else 0
    else:
        project_duration_days = 0
        project_days_left = 0
    return render(request, "projects-view.html", {
        "projet": projet,
        "activites": activites,
        "activites_count": activites_count,
        "project_duration_days": project_duration_days,
        "project_days_left": project_days_left,
    })

@login_required
def projects(request):
    projets = PROJETS.objects.select_related("user", "partenaires").prefetch_related("zone_dintervention").all()
    total_projets = projets.count()
    total_budjets = projets.aggregate(total=Sum("budjets")).get("total") or 0
    total_budgets = projets.aggregate(total=Sum("Budgets")).get("total") or 0
    projets_en_cours = projets.filter(etat_du_projet="Projet en cours").count()
    projets_planifies = projets.filter(etat_du_projet__in=["Projet planifié", "Projet planifie"]).count()
    projets_clotures = projets.filter(etat_du_projet__in=["Projet clôturé", "Projet cloture"]).count()
    if total_projets > 0:
        pct_projets_en_cours = round((projets_en_cours / total_projets) * 100)
        pct_projets_planifies = round((projets_planifies / total_projets) * 100)
        pct_projets_clotures = round((projets_clotures / total_projets) * 100)
        pct_total_projets = 100
    else:
        pct_projets_en_cours = 0
        pct_projets_planifies = 0
        pct_projets_clotures = 0
        pct_total_projets = 0
    return render(request, "projects.html", {
        "projets": projets,
        "total_projets": total_projets,
        "total_budjets": total_budjets,
        "projets_en_cours": projets_en_cours,
        "projets_planifies": projets_planifies,
        "projets_clotures": projets_clotures,
        "pct_projets_en_cours": pct_projets_en_cours,
        "pct_projets_planifies": pct_projets_planifies,
        "pct_projets_clotures": pct_projets_clotures,
        "pct_total_projets": pct_total_projets,
        "total_budgets": total_budgets,
    })



@login_required
def reports_leads(request):
    return render(request, 'reports-leads.html')


def _parse_iso_date(value):
    if not value:
        return None


def _report_i18n(lang):
    is_en = lang == "en"
    if is_en:
        return {
            "title_report": "Project report",
            "title_report_donor": "Donor project report",
            "title_report_operational": "Operational project report",
            "title_report_executive": "Executive project report",
            "label_genre": "Genre",
            "label_type": "Type",
            "col_project": "Project",
            "col_state": "Status",
            "col_activities": "Activities",
            "col_beneficiaries": "Beneficiaries",
           
            "col_partner": "Partner",
            "col_zones": "Zones",
            "col_start": "Start",
            "col_end": "End",
            "col_duration": "Duration (days)",
            "col_remaining": "Remaining days",
            "col_timing": "Timeline status",
            "col_delta_activities": "Activities delta",
            "col_delta_beneficiaries": "Beneficiaries delta",
           
            "col_audit_score": "Audit score",
            "col_audit_points": "Checklist points",
            "total_projects": "Total projects",
            "total_activities": "Total activities",
            "total_beneficiaries": "Total beneficiaries",
          
            "timing_done": "Completed",
            "timing_overdue": "Overdue",
            "timing_active": "In progress",
            "narrative_empty": "No project matches the selected filters for this period.",
            "narrative_template": "The portfolio includes {projects} project(s), with {activities} activit(y/ies), {beneficiaries} beneficiary(ies). Dominant status distribution: {states}.",
            "cover_title": "Donor cover page",
            "cover_org": "Organization",
            "cover_author": "Author",
            "cover_generated": "Generated on",
            "cover_period": "Reporting period",
            "cover_period_default": "Period not specified",
            "annex_title": "Detailed annex by project",
            "annex_empty": "No annex data available.",
            "narrative_comparative": "In comparative view, observed deltas are: activities {activities}, beneficiaries {beneficiaries}.",
            "narrative_audit": "In audit mode, the average documentation completeness score is {score}%.",
        }

    return {
        "title_report": "Rapport projets",
        "title_report_donor": "Rapport bailleur projets",
        "title_report_operational": "Rapport operationnel projets",
        "title_report_executive": "Rapport executif projets",
        "label_genre": "Genre",
        "label_type": "Type",
        "col_project": "Projet",
        "col_state": "Etat",
        "col_activities": "Activites",
        "col_beneficiaries": "Beneficiaires",
        
        "col_partner": "Partenaire",
        "col_zones": "Zones",
        "col_start": "Debut",
        "col_end": "Fin",
        "col_duration": "Duree (jours)",
        "col_remaining": "Jours restants",
        "col_timing": "Statut delai",
        "col_delta_activities": "Delta activites",
        "col_delta_beneficiaries": "Delta beneficiaires",
        
        "col_audit_score": "Score audit",
        "col_audit_points": "Points controles",
        "total_projects": "Total projets",
        "total_activities": "Total activites",
        "total_beneficiaries": "Total beneficiaires",

        "timing_done": "Termine",
        "timing_overdue": "Echeance depassee",
        "timing_active": "En cours",
        "narrative_empty": "Aucun projet ne correspond aux filtres appliques pour cette periode.",
        "narrative_template": "Le portefeuille couvre {projects} projet(s), avec {activities} activite(s), {beneficiaries} beneficiaire(s). La repartition dominante des etats est: {states}.",
        "cover_title": "Page de garde bailleur",
        "cover_org": "Organisation",
        "cover_author": "Auteur",
        "cover_generated": "Date de generation",
        "cover_period": "Periode de reference",
        "cover_period_default": "Periode non specifiee",
        "annex_title": "Annexe detaillee par projet",
        "annex_empty": "Aucune annexe disponible.",
        "narrative_comparative": "En lecture comparative, les deltas observes sont: activites {activities}, beneficiaires {beneficiaries}.",
        "narrative_audit": "En mode audit, le score moyen de completude documentaire est de {score}%.",
    }
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _build_project_report_payload(request):
    report_models = [
        {
            "key": "executif",
            "label": "Modele executif",
            "description": "Vue synthetique pour coordination et prise de decision rapide.",
        },
        {
            "key": "operationnel",
            "label": "Modele operationnel",
            "description": "Suivi detaille des activites, zones et beneficiaires.",
        },
        {
            "key": "bailleur",
            "label": "Modele bailleur",
            "description": "Mise en forme orientee redevabilite financiere et indicateurs de resultat.",
        },
    ]

    report_genres = [
        {
            "key": "periodique",
            "label": "Genre periodique",
            "description": "Hebdomadaire, mensuel ou trimestriel.",
        },
        {
            "key": "comparatif",
            "label": "Genre comparatif",
            "description": "Comparaison entre periodes, zones ou partenaires.",
        },
        {
            "key": "audit",
            "label": "Genre audit",
            "description": "Conformite, traçabilite et preuves documentaires.",
        },
    ]

    report_types = [
        {
            "key": "synthese",
            "label": "Type synthese",
            "description": "KPIs globaux: projets, activites, beneficiaires.",
        },
        {
            "key": "activites",
            "label": "Type activites",
            "description": "Accent sur execution des activites par projet.",
        },
        {
            "key": "performance",
            "label": "Type performance",
            "description": "Analyse etat du projet, delais et progression terrain.",
        },
    ]

    selected_model = (request.GET.get("model") or "executif").lower()
    selected_genre = (request.GET.get("genre") or "periodique").lower()
    selected_type = (request.GET.get("report_type") or "synthese").lower()
    selected_report_lang = (request.GET.get("report_lang") or request.LANGUAGE_CODE or "fr").lower()
    if selected_report_lang not in ["fr", "en"]:
        selected_report_lang = "fr"
    selected_state = (request.GET.get("etat") or "all").strip()
    selected_project_id = (request.GET.get("project_id") or "all").strip()
    date_from_raw = (request.GET.get("date_from") or "").strip()
    date_to_raw = (request.GET.get("date_to") or "").strip()
    date_from = _parse_iso_date(date_from_raw)
    date_to = _parse_iso_date(date_to_raw)

    projects_qs = PROJETS.objects.select_related("partenaires", "user").prefetch_related("zone_dintervention")

    if selected_project_id != "all" and selected_project_id.isdigit():
        projects_qs = projects_qs.filter(id=int(selected_project_id))

    if selected_state and selected_state != "all":
        projects_qs = projects_qs.filter(etat_du_projet=selected_state)

    if date_from:
        projects_qs = projects_qs.filter(fin_du_projet__gte=date_from)
    if date_to:
        projects_qs = projects_qs.filter(debut_du_projet__lte=date_to)

    projects = list(projects_qs.order_by("-debut_du_projet", "id"))
    project_ids = [project.id for project in projects]

    activities_map = {}
    if project_ids:
        activity_stats = (
            ACTIVITES.objects.filter(Projet_id__in=project_ids)
            .values("Projet_id")
            .annotate(
                activities_count=Count("id"),
                total_beneficiaires=Sum("Nbre_de_beneficiaires"),
              
            )
        )
        activities_map = {
            item["Projet_id"]: {
                "activities_count": item.get("activities_count") or 0,
                "total_beneficiaires": item.get("total_beneficiaires") or 0,
               
            }
            for item in activity_stats
        }

    report_rows = []
    for project in projects:
        row_stats = activities_map.get(project.id, {})
        zones = ", ".join(project.zone_dintervention.values_list("nom", flat=True))
        duration_days = 0
        remaining_days = 0
        if project.debut_du_projet and project.fin_du_projet:
            delta_duration = (project.fin_du_projet - project.debut_du_projet).days
            duration_days = delta_duration + 1 if delta_duration >= 0 else 0
            delta_remaining = (project.fin_du_projet - date.today()).days
            remaining_days = delta_remaining if delta_remaining > 0 else 0

        i18n = _report_i18n(selected_report_lang)
        if project.etat_du_projet and "clot" in project.etat_du_projet.lower():
            timing_status = i18n["timing_done"]
        elif remaining_days == 0 and project.fin_du_projet and project.fin_du_projet < date.today():
            timing_status = i18n["timing_overdue"]
        else:
            timing_status = i18n["timing_active"]

        report_rows.append(
            {
                "id": project.id,
                "titre": project.titre,
                "etat": project.etat_du_projet,
                "partenaire": project.partenaires.nom if project.partenaires_id else "-",
                "bailleur": project.Bailleur,
                "debut": project.debut_du_projet,
                "fin": project.fin_du_projet,
                "zones": zones or "-",
                "activities_count": row_stats.get("activities_count", 0),
                "total_beneficiaires": row_stats.get("total_beneficiaires", 0),
                
                "duration_days": duration_days,
                "remaining_days": remaining_days,
                "timing_status": timing_status,
                "activities_delta": 0,
                "beneficiaires_delta": 0,
               
                "audit_score": "-",
                "audit_points": "-",
            }
        )

    if selected_genre == "comparatif" and report_rows:
        # Compare la periode active avec une periode precedente de meme duree.
        if date_from and date_to and date_to >= date_from:
            current_from = date_from
            current_to = date_to
        else:
            current_to = date.today()
            current_from = current_to - timedelta(days=29)

        period_days = max((current_to - current_from).days + 1, 1)
        previous_to = current_from - timedelta(days=1)
        previous_from = previous_to - timedelta(days=period_days - 1)

        current_stats = (
            ACTIVITES.objects.filter(
                Projet_id__in=project_ids,
                dates__gte=current_from,
                dates__lte=current_to,
            )
            .values("Projet_id")
            .annotate(
                activities_count=Count("id"),
                total_beneficiaires=Sum("Nbre_de_beneficiaires"),
               
            )
        )
        previous_stats = (
            ACTIVITES.objects.filter(
                Projet_id__in=project_ids,
                dates__gte=previous_from,
                dates__lte=previous_to,
            )
            .values("Projet_id")
            .annotate(
                activities_count=Count("id"),
                total_beneficiaires=Sum("Nbre_de_beneficiaires"),
               
            )
        )

        current_map = {
            item["Projet_id"]: {
                "activities_count": item.get("activities_count") or 0,
                "total_beneficiaires": item.get("total_beneficiaires") or 0,
               
            }
            for item in current_stats
        }
        previous_map = {
            item["Projet_id"]: {
                "activities_count": item.get("activities_count") or 0,
                "total_beneficiaires": item.get("total_beneficiaires") or 0,
               
            }
            for item in previous_stats
        }

        for row in report_rows:
            curr = current_map.get(row["id"], {})
            prev = previous_map.get(row["id"], {})
            row["activities_delta"] = (curr.get("activities_count") or 0) - (prev.get("activities_count") or 0)
            row["beneficiaires_delta"] = (curr.get("total_beneficiaires") or 0) - (prev.get("total_beneficiaires") or 0)
           

    if selected_genre == "audit" and report_rows:
        for row in report_rows:
            checks = [
                bool(row.get("etat")),
                bool(row.get("partenaire") and row.get("partenaire") != "-"),
                bool(row.get("zones") and row.get("zones") != "-"),
                bool(row.get("debut")),
                bool(row.get("fin")),
                (row.get("activities_count") or 0) > 0,
            ]
            passed = sum(1 for check in checks if check)
            total = len(checks)
            score = int(round((passed / total) * 100, 0)) if total else 0
            row["audit_score"] = f"{score}%"
            row["audit_points"] = f"{passed}/{total}"

    total_projects = len(report_rows)
    total_activities = sum(row["activities_count"] for row in report_rows)
    total_beneficiaires = sum(row["total_beneficiaires"] for row in report_rows)
   

    all_projects = PROJETS.objects.order_by("titre").only("id", "titre")
    project_states = (
        PROJETS.objects.exclude(etat_du_projet__isnull=True)
        .exclude(etat_du_projet__exact="")
        .values_list("etat_du_projet", flat=True)
        .distinct()
        .order_by("etat_du_projet")
    )

    return {
        "report_models": report_models,
        "report_genres": report_genres,
        "report_types": report_types,
        "selected_model": selected_model,
        "selected_genre": selected_genre,
        "selected_type": selected_type,
        "selected_report_lang": selected_report_lang,
        "selected_state": selected_state,
        "selected_project_id": selected_project_id,
        "selected_date_from": date_from_raw,
        "selected_date_to": date_to_raw,
        "project_states": list(project_states),
        "projects_for_filter": list(all_projects),
        "report_rows": report_rows,
        "total_projects": total_projects,
        "total_activities": total_activities,
        "total_beneficiaires": total_beneficiaires,
       
    }


def _resolve_report_layout(payload):
    selected_type = payload["selected_type"]
    selected_model = payload["selected_model"]
    selected_genre = payload["selected_genre"]
    i18n = _report_i18n(payload.get("selected_report_lang", "fr"))

    layout_by_type = {
        "synthese": [
            ("titre", i18n["col_project"]),
            ("etat", i18n["col_state"]),
            ("activities_count", i18n["col_activities"]),
            ("total_beneficiaires", i18n["col_beneficiaries"]),
            
        ],
        "activites": [
            ("titre", i18n["col_project"]),
            ("partenaire", i18n["col_partner"]),
            ("zones", i18n["col_zones"]),
            ("activities_count", i18n["col_activities"]),
            ("total_beneficiaires", i18n["col_beneficiaries"]),
            ("debut", i18n["col_start"]),
            ("fin", i18n["col_end"]),
        ],
        "performance": [
            ("titre", i18n["col_project"]),
            ("etat", i18n["col_state"]),
            ("duration_days", i18n["col_duration"]),
            ("remaining_days", i18n["col_remaining"]),
            ("timing_status", i18n["col_timing"]),
            ("activities_count", i18n["col_activities"]),
        ],
    }

    columns = layout_by_type.get(selected_type, layout_by_type["synthese"])

    if selected_genre == "comparatif":
        if selected_type == "performance":
            columns = columns + [
                ("activities_delta", i18n["col_delta_activities"]),
            ]
        else:
            columns = columns + [
                ("activities_delta", i18n["col_delta_activities"]),
                ("beneficiaires_delta", i18n["col_delta_beneficiaries"]),
                
            ]

    if selected_genre == "audit":
        columns = columns + [
            ("audit_score", i18n["col_audit_score"]),
            ("audit_points", i18n["col_audit_points"]),
        ]

    report_title = i18n["title_report"]
    if selected_model == "bailleur":
        report_title = i18n["title_report_donor"]
    elif selected_model == "operationnel":
        report_title = i18n["title_report_operational"]
    elif selected_model == "executif":
        report_title = i18n["title_report_executive"]

    subtitle = f"{i18n['label_genre']}: {selected_genre} | {i18n['label_type']}: {selected_type}"
    return report_title, subtitle, columns


def _stringify_cell(row, key):
    value = row.get(key, "")
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return "" if value is None else str(value)


def _build_project_narrative(payload):
    i18n = _report_i18n(payload.get("selected_report_lang", "fr"))
    row_count = payload["total_projects"]
    if row_count == 0:
        return i18n["narrative_empty"]

    states_counter = {}
    for row in payload["report_rows"]:
        state_label = row.get("etat") or "Non precise"
        states_counter[state_label] = states_counter.get(state_label, 0) + 1

    top_states = sorted(states_counter.items(), key=lambda item: item[1], reverse=True)[:3]
    states_text = ", ".join(f"{label} ({count})" for label, count in top_states)

    narrative = i18n["narrative_template"].format(
        projects=payload["total_projects"],
        activities=payload["total_activities"],
        beneficiaries=payload["total_beneficiaires"],
        
        states=states_text,
    )

    if payload.get("selected_genre") == "comparatif":
        delta_activities = sum(row.get("activities_delta") or 0 for row in payload["report_rows"])
        delta_beneficiaries = sum(row.get("beneficiaires_delta") or 0 for row in payload["report_rows"])
      
        narrative += " " + i18n["narrative_comparative"].format(
            activities=f"{delta_activities:+d}",
            beneficiaries=f"{delta_beneficiaries:+d}",
         
        )

    if payload.get("selected_genre") == "audit":
        scores = []
        for row in payload["report_rows"]:
            raw_score = str(row.get("audit_score") or "").replace("%", "").strip()
            if raw_score.isdigit():
                scores.append(int(raw_score))
        if scores:
            average_score = round(sum(scores) / len(scores), 1)
            narrative += " " + i18n["narrative_audit"].format(score=average_score)

    return narrative


def _export_project_report_excel(request, payload):
    try:
        openpyxl_module = importlib.import_module("openpyxl")
        workbook = openpyxl_module.Workbook()
    except ImportError:
        messages.error(request, "openpyxl n'est pas installe sur le serveur. Executez: pip install openpyxl")
        return redirect(reverse("reports_project"))

    sheet = workbook.active
    sheet.title = "Rapport projets"
    report_title, subtitle, columns = _resolve_report_layout(payload)
    i18n = _report_i18n(payload.get("selected_report_lang", "fr"))

    sheet.append([report_title])
    sheet.append([subtitle])
    sheet.append([_build_project_narrative(payload)])
    sheet.append([])
    sheet.append([label for _, label in columns])

    for row in payload["report_rows"]:
        sheet.append([_stringify_cell(row, key) for key, _ in columns])

    sheet.append([])
    sheet.append([i18n["total_projects"], payload["total_projects"]])
    sheet.append([i18n["total_activities"], payload["total_activities"]])
    sheet.append([i18n["total_beneficiaries"], payload["total_beneficiaires"]])
    

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = "attachment; filename=rapport_projets.xlsx"
    workbook.save(response)
    return response


def _export_project_report_pdf(request, payload):
    report_title, subtitle, columns = _resolve_report_layout(payload)
    i18n = _report_i18n(payload.get("selected_report_lang", "fr"))

    logo_data_uri = ""
    logo_candidates = [
        os.path.join(settings.BASE_DIR, "static", "assets", "images", "logo-full.png"),
    ]
    if getattr(settings, "STATIC_ROOT", None):
        logo_candidates.append(
            os.path.join(settings.STATIC_ROOT, "assets", "images", "logo-full.png")
        )

    for candidate in logo_candidates:
        if os.path.exists(candidate):
            with open(candidate, "rb") as logo_file:
                encoded_logo = base64.b64encode(logo_file.read()).decode("ascii")
                logo_data_uri = f"data:image/png;base64,{encoded_logo}"
            break

    rows_html = []

    def _audit_badge_html(score_text):
        raw = str(score_text or "").replace("%", "").strip()
        if not raw.isdigit():
            return escape(str(score_text or "-"))
        score = int(raw)
        if score >= 80:
            bg = "#dcfce7"
            fg = "#166534"
        elif score >= 50:
            bg = "#fef3c7"
            fg = "#92400e"
        else:
            bg = "#fee2e2"
            fg = "#991b1b"
        return (
            f"<span style='display:inline-block;padding:2px 8px;border-radius:999px;"
            f"background:{bg};color:{fg};font-weight:700'>{escape(str(score_text))}</span>"
        )

    for row in payload["report_rows"]:
        cell_parts = []
        for key, _ in columns:
            if key == "audit_score":
                cell_parts.append(f"<td>{_audit_badge_html(row.get(key))}</td>")
            else:
                cell_parts.append(f"<td>{escape(_stringify_cell(row, key))}</td>")
        cell_html = "".join(cell_parts)
        rows_html.append(
            "<tr>"
            f"{cell_html}"
            "</tr>"
        )

    headers_html = "".join(f"<th>{escape(label)}</th>" for _, label in columns)
    narrative = _build_project_narrative(payload)

    donor_cover_html = ""
    donor_annex_html = ""
    if payload.get("selected_model") == "bailleur":
        reporting_period = ""
        if payload.get("selected_date_from") or payload.get("selected_date_to"):
            reporting_period = f"{payload.get('selected_date_from') or '...'} au {payload.get('selected_date_to') or '...'}"
        else:
            reporting_period = i18n["cover_period_default"]

        donor_cover_html = (
            "<section style='margin-bottom:18px;padding:16px;border:1px solid #dbeafe;border-radius:8px;background:#f8fbff'>"
            f"<h3 style='margin:0 0 8px 0;color:#0f172a'>{escape(i18n['cover_title'])}</h3>"
            f"<p style='margin:0 0 6px 0'><strong>{escape(i18n['cover_org'])}:</strong> {escape(getattr(settings, 'APP_ORGANIZATION', 'Cluster Securite Alimentaire'))}</p>"
            f"<p style='margin:0 0 6px 0'><strong>{escape(i18n['cover_author'])}:</strong> {escape(request.user.get_full_name() or request.user.username)}</p>"
            f"<p style='margin:0 0 6px 0'><strong>{escape(i18n['cover_generated'])}:</strong> {timezone.localtime(timezone.now()).strftime('%Y-%m-%d %H:%M')}</p>"
            f"<p style='margin:0'><strong>{escape(i18n['cover_period'])}:</strong> {escape(reporting_period)}</p>"
            "</section>"
        )

        annex_cards = []
        for row in payload["report_rows"]:
            annex_cards.append(
                "<div style='margin-bottom:10px;padding:10px;border:1px dashed #cbd5e1;border-radius:6px'>"
                f"<div style='font-weight:700'>{escape(_stringify_cell(row, 'titre'))}</div>"
                f"<div>Etat: {escape(_stringify_cell(row, 'etat'))} | Partenaire: {escape(_stringify_cell(row, 'partenaire'))}</div>"
                f"<div>Zones: {escape(_stringify_cell(row, 'zones'))}</div>"
                f"<div>Activites: {escape(_stringify_cell(row, 'activities_count'))} | Beneficiaires: {escape(_stringify_cell(row, 'total_beneficiaires'))} </div>"
                "</div>"
            )
        donor_annex_html = (
            "<section style='margin-top:16px'>"
            f"<h3 style='margin:0 0 8px 0'>{escape(i18n['annex_title'])}</h3>"
            f"{''.join(annex_cards) if annex_cards else '<p>' + escape(i18n['annex_empty']) + '</p>'}"
            "</section>"
        )

    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>"
        "@page { size: A4 landscape; margin: 14mm; }"
        "body{font-family:Arial,sans-serif;color:#0f172a;font-size:11px}"
        "h2{margin:0 0 4px 0;font-size:15px;color:#0f172a}"
        "h3{margin:0 0 6px 0}"
        "p{margin:0 0 10px 0;color:#475569}"
        ".pdf-header{display:table;width:100%;margin-bottom:0}"
        ".pdf-header-logo{display:table-cell;vertical-align:middle;width:140px}"
        ".pdf-header-text{display:table-cell;vertical-align:middle;padding-left:14px}"
        ".pdf-header-title{font-size:15px;font-weight:700;color:#0f172a;margin:0 0 3px 0}"
        ".pdf-header-sub{font-size:10px;color:#64748b;margin:0}"
        ".pdf-header-org{font-size:10px;color:#077f98;font-weight:600;margin:2px 0 0 0}"
        ".pdf-divider{border:none;border-top:2px solid #077f98;margin:10px 0 12px 0}"
        ".meta{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px}"
        ".chip{background:#eef2ff;border:1px solid #dbeafe;border-radius:999px;padding:3px 8px;font-size:10px}"
        "table{width:100%;border-collapse:collapse}"
        "th,td{border:1px solid #dbe2ea;padding:7px;text-align:left;vertical-align:top}"
        "th{background:#f1f5f9;font-weight:700}"
        "</style></head><body>"
        "<div class='pdf-header'>"
        f"  <div class='pdf-header-logo'>{('<img src=\'' + logo_data_uri + '\' alt=\'Cluster logo\' style=\'height:48px;width:auto\'>') if logo_data_uri else '<span style=\"font-weight:700;color:#077f98;font-size:13px\">CLUSTER</span>'}</div>"
        "  <div class='pdf-header-text'>"
        f"    <div class='pdf-header-title'>{escape(report_title)}</div>"
        f"    <p class='pdf-header-sub'>{escape(subtitle)}</p>"
        f"    <p class='pdf-header-org'>{escape(getattr(settings, 'APP_ORGANIZATION', 'Cluster Securite Alimentaire'))} &bull; {timezone.localtime(timezone.now()).strftime('%d/%m/%Y')}</p>"
        "  </div>"
        "</div>"
        "<hr class='pdf-divider'>"
        f"<p style='color:#475569;margin-bottom:12px'>{escape(narrative)}</p>"
        f"{donor_cover_html}"
        f"<p>{i18n['total_projects']}: {payload['total_projects']} | {i18n['total_activities']}: {payload['total_activities']} | {i18n['total_beneficiaries']}: {payload['total_beneficiaires']} </p>"
        "<div class='meta'>"
        f"<span class='chip'>Modele: {escape(payload['selected_model'])}</span>"
        f"<span class='chip'>Genre: {escape(payload['selected_genre'])}</span>"
        f"<span class='chip'>Type: {escape(payload['selected_type'])}</span>"
        "</div>"
        f"<table><thead><tr>{headers_html}</tr></thead>"
        f"<tbody>{''.join(rows_html)}</tbody></table>"
        f"{donor_annex_html}"
        "</body></html>"
    )

    try:
        weasyprint_module = importlib.import_module("weasyprint")
        html_renderer = weasyprint_module.HTML
    except ImportError:
        messages.error(request, "WeasyPrint n'est pas installe sur le serveur. Executez: pip install weasyprint")
        return redirect(reverse("reports_project"))

    pdf_bytes = html_renderer(string=html, base_url=request.build_absolute_uri('/')).write_pdf()
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = "attachment; filename=rapport_projets.pdf"
    return response


@login_required
def reports_project(request):
    payload = _build_project_report_payload(request)
    export_format = (request.GET.get("export") or "").lower()

    if export_format == "excel":
        return _export_project_report_excel(request, payload)
    if export_format == "pdf":
        return _export_project_report_pdf(request, payload)

    report_title, subtitle, columns = _resolve_report_layout(payload)
    payload["report_preview_title"] = report_title
    payload["report_preview_subtitle"] = subtitle
    payload["report_preview_columns"] = columns

    return render(request, 'reports-project.html', payload)

@login_required
def reports_sales(request):
    return render(request, 'reports-sales.html')


def _activity_report_i18n(lang):
    is_en = lang == "en"
    if is_en:
        return {
            "title_report": "Activities report",
            "subtitle": "Operational export of field activities",
            "col_title": "Activity",
            "col_project": "Project",
            "col_zone": "Zone",
            "col_beneficiaries": "Beneficiaries",
          
            "col_seed_kits": "Seed kits",
            "col_start": "Start",
            "col_end": "End",
            "col_author": "Recorded by",
            "total_activities": "Total activities",
            "total_projects": "Projects covered",
            "total_beneficiaries": "Total beneficiaries",
          
            "total_seed_kits": "Total seed kits",
            "narrative_empty": "No activity matches the selected filters for this period.",
            "narrative_template": "The export includes {activities} activit(y/ies) across {projects} project(s), reaching {beneficiaries} beneficiaries,  and {seed_kits} seed kits.",
            "label_project": "Project",
            "label_zone": "Zone",
            "label_period": "Period",
            "period_not_specified": "Not specified",
        }

    return {
        "title_report": "Rapport des activites",
        "subtitle": "Export operationnel des activites terrain",
        "col_title": "Activite",
        "col_project": "Projet",
        "col_zone": "Zone",
        "col_beneficiaries": "Beneficiaires",
       
        "col_seed_kits": "Seed kits",
        "col_start": "Debut",
        "col_end": "Fin",
        "col_author": "Saisi par",
        "total_activities": "Total activites",
        "total_projects": "Projets couverts",
        "total_beneficiaries": "Total beneficiaires",
      
        "total_seed_kits": "Total seed kits",
        "narrative_empty": "Aucune activite ne correspond aux filtres appliques pour cette periode.",
        "narrative_template": "L export couvre {activities} activite(s) sur {projects} projet(s), pour {beneficiaries} beneficiaire(s), et {seed_kits} seed kits.",
        "label_project": "Projet",
        "label_zone": "Zone",
        "label_period": "Periode",
        "period_not_specified": "Non specifiee",
    }


def _build_activity_report_payload(request):
    selected_report_lang = (request.GET.get("report_lang") or request.LANGUAGE_CODE or "fr").lower()
    if selected_report_lang not in ["fr", "en"]:
        selected_report_lang = "fr"

    selected_project_id = (request.GET.get("project_id") or "all").strip()
    selected_zone_id = (request.GET.get("zone_id") or "all").strip()
    date_from_raw = (request.GET.get("date_from") or "").strip()
    date_to_raw = (request.GET.get("date_to") or "").strip()
    date_from = _parse_iso_date(date_from_raw)
    date_to = _parse_iso_date(date_to_raw)
    i18n = _activity_report_i18n(selected_report_lang)

    activities_qs = ACTIVITES.objects.select_related("Projet", "zone", "user")

    if selected_project_id != "all" and selected_project_id.isdigit():
        activities_qs = activities_qs.filter(Projet_id=int(selected_project_id))

    if selected_zone_id != "all" and selected_zone_id.isdigit():
        activities_qs = activities_qs.filter(zone_id=int(selected_zone_id))

    if date_from:
        activities_qs = activities_qs.filter(fin_de_lactivite__gte=date_from)
    if date_to:
        activities_qs = activities_qs.filter(Debut_de_lactivite__lte=date_to)

    activities = list(activities_qs.order_by("-Debut_de_lactivite", "-id"))
    report_rows = []
    covered_projects = set()
    total_beneficiaires = 0
   
    total_seed_kits = 0

    for activity in activities:
        covered_projects.add(activity.Projet_id)
        total_beneficiaires += activity.Nbre_de_beneficiaires or 0
       
        total_seed_kits += activity.seed_kits or 0
        report_rows.append(
            {
                "titre": activity.Titre,
                "projet": activity.Projet.titre if activity.Projet_id else "-",
                "zone": activity.zone.nom if activity.zone_id else "-",
                "beneficiaires": activity.Nbre_de_beneficiaires or 0,
              
                "seed_kits": activity.seed_kits or 0,
                "debut": activity.Debut_de_lactivite,
                "fin": activity.fin_de_lactivite,
                "auteur": activity.user.get_full_name() or activity.user.username,
            }
        )

    preview_columns = [
        ("titre", i18n["col_title"]),
        ("projet", i18n["col_project"]),
        ("zone", i18n["col_zone"]),
        ("beneficiaires", i18n["col_beneficiaries"]),
       
        ("seed_kits", i18n["col_seed_kits"]),
        ("debut", i18n["col_start"]),
        ("fin", i18n["col_end"]),
        ("auteur", i18n["col_author"]),
    ]

    selected_project_label = "Tous les projets"
    if selected_project_id != "all" and selected_project_id.isdigit():
        selected_project = next(
            (item for item in PROJETS.objects.filter(id=int(selected_project_id)).only("titre")),
            None,
        )
        if selected_project:
            selected_project_label = selected_project.titre

    selected_zone_label = "Toutes les zones"
    if selected_zone_id != "all" and selected_zone_id.isdigit():
        selected_zone = next(
            (item for item in ZONE.objects.filter(id=int(selected_zone_id)).only("nom")),
            None,
        )
        if selected_zone:
            selected_zone_label = selected_zone.nom

    return {
        "selected_report_lang": selected_report_lang,
        "selected_project_id": selected_project_id,
        "selected_project_label": selected_project_label,
        "selected_zone_id": selected_zone_id,
        "selected_zone_label": selected_zone_label,
        "selected_date_from": date_from_raw,
        "selected_date_to": date_to_raw,
        "projects_for_filter": list(PROJETS.objects.order_by("titre").only("id", "titre")),
        "zones_for_filter": list(ZONE.objects.order_by("nom").only("id", "nom")),
        "report_rows": report_rows,
        "report_preview_columns": preview_columns,
        "report_preview_title": i18n["title_report"],
        "report_preview_subtitle": i18n["subtitle"],
        "total_activities": len(report_rows),
        "total_projects": len(covered_projects),
        "total_beneficiaires": total_beneficiaires,
       
        "total_seed_kits": total_seed_kits,
    }


def _build_activity_report_narrative(payload):
    i18n = _activity_report_i18n(payload.get("selected_report_lang", "fr"))
    if not payload["report_rows"]:
        return i18n["narrative_empty"]
    return i18n["narrative_template"].format(
        activities=payload["total_activities"],
        projects=payload["total_projects"],
        beneficiaries=payload["total_beneficiaires"],
      
        seed_kits=payload["total_seed_kits"],
    )


def _slugify_export_part(value, fallback):
    cleaned = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return cleaned or fallback


def _build_activity_export_filename(payload, extension):
    project_part = _slugify_export_part(payload.get("selected_project_label"), "tous-projets")
    zone_part = _slugify_export_part(payload.get("selected_zone_label"), "toutes-zones")
    if payload.get("selected_date_from") or payload.get("selected_date_to"):
        period_part = _slugify_export_part(
            f"{payload.get('selected_date_from') or 'debut'}-{payload.get('selected_date_to') or 'fin'}",
            "periode",
        )
    else:
        period_part = "sans-periode"
    return f"rapport_activites_{project_part}_{zone_part}_{period_part}.{extension}"


def _style_excel_sheet(sheet, header_row_index, first_data_row_index, last_data_row_index, total_start_row_index=None):
    openpyxl_styles = importlib.import_module("openpyxl.styles")
    Font = openpyxl_styles.Font
    PatternFill = openpyxl_styles.PatternFill
    Border = openpyxl_styles.Border
    Side = openpyxl_styles.Side
    Alignment = openpyxl_styles.Alignment
    openpyxl_utils = importlib.import_module("openpyxl.utils")
    get_column_letter = openpyxl_utils.get_column_letter

    thin_side = Side(style="thin", color="D6DEE8")
    border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
    header_fill = PatternFill(fill_type="solid", fgColor="E6F7FB")
    title_fill = PatternFill(fill_type="solid", fgColor="F8FBFD")
    zebra_fill = PatternFill(fill_type="solid", fgColor="F8FBFD")
    total_fill = PatternFill(fill_type="solid", fgColor="EEF7FB")

    max_column = max(sheet.max_column, 2)
    last_column_letter = get_column_letter(max_column)

    for row_index in (1, 2, 3):
        sheet.merge_cells(f"A{row_index}:{last_column_letter}{row_index}")
        cell = sheet[f"A{row_index}"]
        cell.fill = title_fill
        cell.alignment = Alignment(wrap_text=True, vertical="top")

    sheet["A1"].font = Font(bold=True, size=14, color="0F172A")
    sheet["A2"].font = Font(bold=True, size=11, color="475569")
    sheet["A3"].font = Font(size=10, color="64748B")

    for row_index in range(4, header_row_index):
        for cell in sheet[row_index]:
            if cell.value:
                cell.fill = title_fill
                cell.alignment = Alignment(wrap_text=True, vertical="top")

    for cell in sheet[header_row_index]:
        cell.font = Font(bold=True, color="0F172A")
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(wrap_text=True, vertical="center")

    for row_index in range(first_data_row_index, last_data_row_index + 1):
        for cell in sheet[row_index]:
            cell.border = border
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            if (row_index - first_data_row_index) % 2 == 1:
                cell.fill = zebra_fill

    if total_start_row_index:
        for row_index in range(total_start_row_index, sheet.max_row + 1):
            for cell in sheet[row_index]:
                if cell.value not in (None, ""):
                    cell.border = border
                    cell.fill = total_fill
                    cell.alignment = Alignment(wrap_text=True, vertical="top")
            sheet[f"A{row_index}"].font = Font(bold=True, color="0F172A")

    sheet.freeze_panes = f"A{first_data_row_index}"
    if last_data_row_index >= first_data_row_index:
        sheet.auto_filter.ref = f"A{header_row_index}:{last_column_letter}{last_data_row_index}"

    for col_idx, column_cells in enumerate(sheet.columns, start=1):
        max_length = 0
        column_letter = get_column_letter(col_idx)
        for cell in column_cells:
            value_length = len(str(cell.value)) if cell.value is not None else 0
            max_length = max(max_length, value_length)
        sheet.column_dimensions[column_letter].width = min(max(max_length + 2, 12), 32)


def _export_activity_report_excel(request, payload):
    try:
        openpyxl_module = importlib.import_module("openpyxl")
        workbook = openpyxl_module.Workbook()
    except ImportError:
        messages.error(request, "openpyxl n'est pas installe sur le serveur. Executez: pip install openpyxl")
        return redirect(reverse("reports_timesheets"))

    i18n = _activity_report_i18n(payload.get("selected_report_lang", "fr"))
    sheet = workbook.active
    sheet.title = "Rapport activites"

    sheet.append([payload["report_preview_title"]])
    sheet.append([payload["report_preview_subtitle"]])
    sheet.append([_build_activity_report_narrative(payload)])
    sheet.append([])
    sheet.append([label for _, label in payload["report_preview_columns"]])

    header_row_index = sheet.max_row

    for row in payload["report_rows"]:
        sheet.append([_stringify_cell(row, key) for key, _ in payload["report_preview_columns"]])

    first_data_row_index = header_row_index + 1
    last_data_row_index = sheet.max_row

    sheet.append([])
    sheet.append([i18n["total_activities"], payload["total_activities"]])
    sheet.append([i18n["total_projects"], payload["total_projects"]])
    sheet.append([i18n["total_beneficiaries"], payload["total_beneficiaires"]])
   
    sheet.append([i18n["total_seed_kits"], payload["total_seed_kits"]])

    total_start_row_index = last_data_row_index + 2 if last_data_row_index >= first_data_row_index else header_row_index + 2

    if last_data_row_index >= first_data_row_index:
        _style_excel_sheet(
            sheet,
            header_row_index,
            first_data_row_index,
            last_data_row_index,
            total_start_row_index=total_start_row_index,
        )
    else:
        _style_excel_sheet(
            sheet,
            header_row_index,
            first_data_row_index,
            last_data_row_index,
            total_start_row_index=total_start_row_index,
        )

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f"attachment; filename={_build_activity_export_filename(payload, 'xlsx')}"
    workbook.save(response)
    return response


def _export_activity_report_pdf(request, payload):
    i18n = _activity_report_i18n(payload.get("selected_report_lang", "fr"))
    logo_data_uri = ""
    logo_candidates = [
        os.path.join(settings.BASE_DIR, "static", "assets", "images", "logo-full.png"),
    ]
    if getattr(settings, "STATIC_ROOT", None):
        logo_candidates.append(
            os.path.join(settings.STATIC_ROOT, "assets", "images", "logo-full.png")
        )

    for candidate in logo_candidates:
        if os.path.exists(candidate):
            with open(candidate, "rb") as logo_file:
                encoded_logo = base64.b64encode(logo_file.read()).decode("ascii")
                logo_data_uri = f"data:image/png;base64,{encoded_logo}"
            break

    headers_html = "".join(f"<th>{escape(label)}</th>" for _, label in payload["report_preview_columns"])
    rows_html = []
    for row in payload["report_rows"]:
        cell_html = "".join(
            f"<td>{escape(_stringify_cell(row, key))}</td>"
            for key, _ in payload["report_preview_columns"]
        )
        rows_html.append(f"<tr>{cell_html}</tr>")

    if payload.get("selected_date_from") or payload.get("selected_date_to"):
        period_text = f"{payload.get('selected_date_from') or '...'} au {payload.get('selected_date_to') or '...'}"
    else:
        period_text = i18n["period_not_specified"]

    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>"
        "@page { size: A4 landscape; margin: 14mm; }"
        "body{font-family:Arial,sans-serif;color:#0f172a;font-size:11px}"
        "p{margin:0 0 10px 0;color:#475569}"
        "table{width:100%;border-collapse:collapse}"
        "th,td{border:1px solid #dbe2ea;padding:7px;text-align:left;vertical-align:top}"
        "th{background:#f1f5f9;font-weight:700}"
        ".pdf-header{display:table;width:100%;margin-bottom:0}"
        ".pdf-header-logo{display:table-cell;vertical-align:middle;width:140px}"
        ".pdf-header-text{display:table-cell;vertical-align:middle;padding-left:14px}"
        ".pdf-header-title{font-size:15px;font-weight:700;color:#0f172a;margin:0 0 3px 0}"
        ".pdf-header-sub{font-size:10px;color:#64748b;margin:0}"
        ".pdf-header-org{font-size:10px;color:#077f98;font-weight:600;margin:2px 0 0 0}"
        ".pdf-divider{border:none;border-top:2px solid #077f98;margin:10px 0 12px 0}"
        ".meta{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px}"
        ".chip{background:#eef2ff;border:1px solid #dbeafe;border-radius:999px;padding:3px 8px;font-size:10px}"
        "</style></head><body>"
        "<div class='pdf-header'>"
        f"<div class='pdf-header-logo'>{('<img src=\'' + logo_data_uri + '\' alt=\'Cluster logo\' style=\'height:48px;width:auto\'>') if logo_data_uri else '<span style=\"font-weight:700;color:#077f98;font-size:13px\">CLUSTER</span>'}</div>"
        "<div class='pdf-header-text'>"
        f"<div class='pdf-header-title'>{escape(payload['report_preview_title'])}</div>"
        f"<p class='pdf-header-sub'>{escape(payload['report_preview_subtitle'])}</p>"
        f"<p class='pdf-header-org'>{escape(getattr(settings, 'APP_ORGANIZATION', 'Cluster Securite Alimentaire'))} &bull; {timezone.localtime(timezone.now()).strftime('%d/%m/%Y')}</p>"
        "</div>"
        "</div>"
        "<hr class='pdf-divider'>"
        f"<p>{escape(_build_activity_report_narrative(payload))}</p>"
        "<div class='meta'>"
        f"<span class='chip'>{escape(i18n['label_project'])}: {escape(payload.get('selected_project_id') or 'all')}</span>"
        f"<span class='chip'>{escape(i18n['label_zone'])}: {escape(payload.get('selected_zone_id') or 'all')}</span>"
        f"<span class='chip'>{escape(i18n['label_period'])}: {escape(period_text)}</span>"
        "</div>"
        f"<p>{i18n['total_activities']}: {payload['total_activities']} | {i18n['total_projects']}: {payload['total_projects']} | {i18n['total_beneficiaries']}: {payload['total_beneficiaires']} | {i18n['total_seed_kits']}: {payload['total_seed_kits']}</p>"
        f"<table><thead><tr>{headers_html}</tr></thead><tbody>{''.join(rows_html)}</tbody></table>"
        "</body></html>"
    )

    try:
        weasyprint_module = importlib.import_module("weasyprint")
        html_renderer = weasyprint_module.HTML
    except ImportError:
        messages.error(request, "WeasyPrint n'est pas installe sur le serveur. Executez: pip install weasyprint")
        return redirect(reverse("reports_timesheets"))

    pdf_bytes = html_renderer(string=html, base_url=request.build_absolute_uri('/')).write_pdf()
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = "attachment; filename=rapport_activites.pdf"
    return response


@login_required
def reports_timesheets(request):
    payload = _build_activity_report_payload(request)
    export_format = (request.GET.get("export") or "").lower()

    if export_format == "excel":
        return _export_activity_report_excel(request, payload)
    if export_format == "pdf":
        return _export_activity_report_pdf(request, payload)

    return render(request, 'reports-timesheets.html', payload)

@login_required
def settings_utilisateurs(request):
    return render(request, 'settings-customers.html')

@login_required
def settings_email(request):
    return render(request, 'settings-email.html')

@login_required
def settings_finance(request):
    return render(request, 'settings-finance.html')

@login_required
def settings_gateways(request):
    return render(request, 'settings-gateways.html')


def widgets_charts(request):
    return render(request, 'widgets-charts.html')


def widgets_lists(request):
    return render(request, 'widgets-lists.html')


def widgets_miscellaneous(request):
    return render(request, 'widgets-miscellaneous.html')


def widgets_statistics(request):
    return render(request, 'widgets-statistics.html')


def widgets_tables(request):
    return render(request, 'widgets-tables.html')



