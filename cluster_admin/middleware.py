from .models import USER_ACTION_LOG


class UserActionLogMiddleware:
    EXCLUDED_PREFIXES = ("/static/", "/media/", "/favicon.ico")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        user = getattr(request, "user", None)
        path = getattr(request, "path", "") or ""
        method = (getattr(request, "method", "GET") or "GET").upper()

        if not user or not user.is_authenticated:
            return response
        if any(path.startswith(prefix) for prefix in self.EXCLUDED_PREFIXES):
            return response
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            return response

        action_type = self._infer_action_type(request, method)
        description = self._build_description(request, action_type)

        try:
            USER_ACTION_LOG.objects.create(
                user=user,
                action_type=action_type,
                method=method,
                path=path,
                description=description,
            )
        except Exception:
            pass

        return response

    def _infer_action_type(self, request, method):
        if method == "DELETE":
            return "suppression"
        if method in {"PUT", "PATCH"}:
            return "modification"

        action_raw = (
            request.POST.get("action")
            or request.GET.get("action")
            or ""
        )
        action = str(action_raw).lower()

        url_name = ""
        resolver_match = getattr(request, "resolver_match", None)
        if resolver_match:
            url_name = (resolver_match.url_name or "").lower()

        combined = f"{action} {url_name}"

        if any(token in combined for token in ["delete", "remove", "suppr"]):
            return "suppression"
        if any(token in combined for token in ["update", "edit", "activate", "deactivate", "toggle", "reset", "change", "modif"]):
            return "modification"
        if any(token in combined for token in ["create", "add", "new", "register", "cree", "creation"]):
            return "creation"

        if method == "GET":
            return "consultation"
        return "autre"

    def _build_description(self, request, action_type):
        url_name = ""
        resolver_match = getattr(request, "resolver_match", None)
        if resolver_match:
            url_name = resolver_match.url_name or ""

        if action_type == "creation":
            label = "Creation"
        elif action_type == "modification":
            label = "Modification"
        elif action_type == "suppression":
            label = "Suppression"
        elif action_type == "consultation":
            label = "Consultation"
        else:
            label = "Action"

        if url_name:
            return f"{label} sur {url_name}"
        return f"{label} sur {request.path}"
