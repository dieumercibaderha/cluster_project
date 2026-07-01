from django.urls import path
from . import views

urlpatterns = [
    path('analytics/', views.analytics, name='analytics'),
    path('type_activites/', views.type_activites, name='type_activites'),
    path('apps_email/', views.apps_email, name='apps_email'),
    path('send_email/', views.send_email, name='send_email'),
    path('email/<int:pk>/details/', views.email_details, name='email_details'),
    path('email/<int:pk>/star/', views.email_toggle_star, name='email_toggle_star'),
    path('email/<int:pk>/read/', views.email_mark_read, name='email_mark_read'),
    path('email/<int:pk>/delete/', views.email_delete, name='email_delete'),
    path('email/bulk/', views.email_bulk_action, name='email_bulk_action'),
    path('email/users/suggestions/', views.email_user_suggestions, name='email_user_suggestions'),
    path('gestion_zones/', views.gestion_zones, name='gestion_zones'),
    path('activites/', views.activites, name='activites'),
    path('activites/carte/', views.activites_carte, name='activites_carte'),
    path('activites/carte/google/', views.activites_carte_google, name='activites_carte_google'),
    path('activites/carte/points/', views.activites_carte_points_api, name='activites_carte_points_api'),
    path('auth_404_cover/', views.auth_404_cover, name='auth_404_cover'),
    path('auth_404_creative/', views.auth_404_creative, name='auth_404_creative'),
    path('auth_404_minimal/', views.auth_404_minimal, name='auth_404_minimal'),
  
    path('auth_login_creative/', views.auth_login_creative, name='auth_login_creative'),
    path('logout/', views.auth_logout, name='auth_logout'),
    path('profile-details/', views.profile_details, name='profile_details'),
    path('account-settings/', views.account_settings, name='account_settings'),
    path('auth_maintenance_cover/', views.auth_maintenance_cover, name='auth_maintenance_cover'),
    path('auth_maintenance_creative/', views.auth_maintenance_creative, name='auth_maintenance_creative'),
    path('auth_maintenance_minimal/', views.auth_maintenance_minimal, name='auth_maintenance_minimal'),
    path('auth_register_minimal/', views.auth_register_minimal, name='auth_register_minimal'),
    
    path('password-reset/email/', views.password_reset_email_step, name='password_reset_email_step'),
    path('password-reset/otp/', views.password_reset_otp_step, name='password_reset_otp_step'),
    path('password-reset/password/', views.password_reset_password_step, name='password_reset_password_step'),
    path('auth_reset_creative/', views.password_reset_email_step, name='auth_reset_creative'),
  
    path('auth_verify_creative/', views.auth_verify_creative, name='auth_verify_creative'),
  
    path('utilisateurs_create/', views.utilisateurs_create, name='utilisateurs_create'),
    path('utilisateurs_view/<int:pk>/', views.utilisateurs_view, name='utilisateurs_view_pk'),
    path('utilisateurs/', views.utilisateurs, name='utilisateurs'),
    path('utilisateurs_export/', views.utilisateurs_export, name='utilisateurs_export'),
  
    path('', views.index, name='index'),
  
    path('creation_categorie/', views.creation_categorie_partenaire, name='creation_categorie_partenaire'),
    path('voir_categorie/<int:pk>/', views.voir_categorie_partenaire, name='voir_categorie_partenaire'),
    path('categorie_partenaires/', views.categorie_partenaires, name='categorie_partenaires'),
    path('partenaires/', views.partenaires, name='partenaires'),
    path('projects_create/', views.projects_create, name='projects_create'),
    path('projects_view/<int:pk>/', views.projects_view, name='projects_view_pk'),
    path('projects/', views.projects, name='projects'),
    
    path('reports_leads/', views.reports_leads, name='reports_leads'),
    path('reports_project/', views.reports_project, name='reports_project'),
    path('reports_sales/', views.reports_sales, name='reports_sales'),
    path('reports_timesheets/', views.reports_timesheets, name='reports_timesheets'),
    path('settings_utilisateurs/', views.settings_utilisateurs, name='settings_utilisateurs'),
    path('widgets_charts/', views.widgets_charts, name='widgets_charts'),
    path('widgets_lists/', views.widgets_lists, name='widgets_lists'),
    path('widgets_miscellaneous/', views.widgets_miscellaneous, name='widgets_miscellaneous'),
    path('widgets_statistics/', views.widgets_statistics, name='widgets_statistics'),
    path('widgets_tables/', views.widgets_tables, name='widgets_tables'),

]

