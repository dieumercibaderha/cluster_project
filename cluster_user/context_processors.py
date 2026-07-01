def app_role(request):
    """Expose un indicateur de rôle pour les pages de l'application utilisateur."""
    path = request.path_info or request.path
    segments = [segment for segment in path.split('/') if segment]
    if segments and (segments[0] == 'user' or (len(segments) > 1 and segments[1] == 'user')):
        return {'app_role': 'user'}
    return {}
