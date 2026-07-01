from functools import wraps
from django.urls import path
from cluster_admin import views as admin_views

app_name = 'cluster_user'


def user_route(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        request.app_role = 'user'
        return view(request, *args, **kwargs)

    return wrapped

urlpatterns = [
    path('analytics/', user_route(admin_views.analytics), name='analytics'),
    path('type_activites/', user_route(admin_views.type_activites), name='type_activites'),
    path('apps_email/', user_route(admin_views.apps_email), name='apps_email'),
    path('send_email/', user_route(admin_views.send_email), name='send_email'),
    path('email/<int:pk>/details/', user_route(admin_views.email_details), name='email_details'),
    path('email/<int:pk>/star/', user_route(admin_views.email_toggle_star), name='email_toggle_star'),
    path('email/<int:pk>/read/', user_route(admin_views.email_mark_read), name='email_mark_read'),
    path('email/<int:pk>/delete/', user_route(admin_views.email_delete), name='email_delete'),
    path('email/bulk/', user_route(admin_views.email_bulk_action), name='email_bulk_action'),
    path('email/users/suggestions/', user_route(admin_views.email_user_suggestions), name='email_user_suggestions'),
    path('gestion_zones/', user_route(admin_views.gestion_zones), name='gestion_zones'),
    path('activites/', user_route(admin_views.activites), name='activites'),
    path('activites/carte/', user_route(admin_views.activites_carte), name='activites_carte'),
    path('activites/carte/google/', user_route(admin_views.activites_carte_google), name='activites_carte_google'),
    path('activites/carte/points/', user_route(admin_views.activites_carte_points_api), name='activites_carte_points_api'),
    path('auth_404_cover/', user_route(admin_views.auth_404_cover), name='auth_404_cover'),
    path('auth_404_creative/', user_route(admin_views.auth_404_creative), name='auth_404_creative'),
    path('auth_404_minimal/', user_route(admin_views.auth_404_minimal), name='auth_404_minimal'),
    path('auth_login_creative/', user_route(admin_views.auth_login_creative), name='auth_login_creative'),
    path('logout/', user_route(admin_views.auth_logout), name='auth_logout'),
    path('profile-details/', user_route(admin_views.profile_details), name='profile_details'),
    path('account-settings/', user_route(admin_views.account_settings), name='account_settings'),
    path('auth_maintenance_cover/', user_route(admin_views.auth_maintenance_cover), name='auth_maintenance_cover'),
    path('auth_maintenance_creative/', user_route(admin_views.auth_maintenance_creative), name='auth_maintenance_creative'),
    path('auth_maintenance_minimal/', user_route(admin_views.auth_maintenance_minimal), name='auth_maintenance_minimal'),
    path('auth_register_minimal/', user_route(admin_views.auth_register_minimal), name='auth_register_minimal'),
    path('password-reset/email/', user_route(admin_views.password_reset_email_step), name='password_reset_email_step'),
    path('password-reset/otp/', user_route(admin_views.password_reset_otp_step), name='password_reset_otp_step'),
    path('password-reset/password/', user_route(admin_views.password_reset_password_step), name='password_reset_password_step'),
    path('auth_reset_creative/', user_route(admin_views.password_reset_email_step), name='auth_reset_creative'),
    path('auth_verify_creative/', user_route(admin_views.auth_verify_creative), name='auth_verify_creative'),
    path('utilisateurs_export/', user_route(admin_views.utilisateurs_export), name='utilisateurs_export'),
    path('', user_route(admin_views.index), name='index'),
    path('creation_categorie/', user_route(admin_views.creation_categorie_partenaire), name='creation_categorie_partenaire'),
    path('voir_categorie/<int:pk>/', user_route(admin_views.voir_categorie_partenaire), name='voir_categorie_partenaire'),
    path('categorie_partenaires/', user_route(admin_views.categorie_partenaires), name='categorie_partenaires'),
    path('partenaires/', user_route(admin_views.partenaires), name='partenaires'),
    path('projects_create/', user_route(admin_views.projects_create), name='projects_create'),
    path('projects_view/<int:pk>/', user_route(admin_views.projects_view), name='projects_view_pk'),
    path('projects/', user_route(admin_views.projects), name='projects'),
    path('reports_leads/', user_route(admin_views.reports_leads), name='reports_leads'),
    path('reports_project/', user_route(admin_views.reports_project), name='reports_project'),
    path('reports_sales/', user_route(admin_views.reports_sales), name='reports_sales'),
    path('reports_timesheets/', user_route(admin_views.reports_timesheets), name='reports_timesheets'),
    path('settings_utilisateurs/', user_route(admin_views.settings_utilisateurs), name='settings_utilisateurs'),
    path('widgets_charts/', user_route(admin_views.widgets_charts), name='widgets_charts'),
    path('widgets_lists/', user_route(admin_views.widgets_lists), name='widgets_lists'),
    path('widgets_miscellaneous/', user_route(admin_views.widgets_miscellaneous), name='widgets_miscellaneous'),
    path('widgets_statistics/', user_route(admin_views.widgets_statistics), name='widgets_statistics'),
    path('widgets_tables/', user_route(admin_views.widgets_tables), name='widgets_tables'),
]
