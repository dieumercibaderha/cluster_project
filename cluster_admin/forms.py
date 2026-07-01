from django import forms
from .models import (
    User,
    CATEGORIE_PARTENAIRE,
    PARTENAIRE,
    ZONE,
    PROJETS,
    TYPE_ACTIVITES,
    ACTIVITES,
)


class StyledModelForm(forms.ModelForm):
    """Ajoute automatiquement les classes Bootstrap aux champs."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = "form-check-input"
            else:
                css = widget.attrs.get("class", "")
                widget.attrs["class"] = f"{css} form-control".strip()
            if self.errors.get(name):
                widget.attrs["class"] = f"{widget.attrs['class']} is-invalid".strip()


class CategoriePartenaireForm(StyledModelForm):
    class Meta:
        model = CATEGORIE_PARTENAIRE
        fields = "__all__"


class PartenaireForm(StyledModelForm):
    class Meta:
        model = PARTENAIRE
        fields = "__all__"


class ZoneForm(StyledModelForm):
    class Meta:
        model = ZONE
        fields = "__all__"


class ProjetsForm(StyledModelForm):
    class Meta:
        model = PROJETS
        fields = "__all__"
        widgets = {
            "debut_du_projet": forms.DateInput(attrs={"type": "date"}),
            "fin_du_projet": forms.DateInput(attrs={"type": "date"}),
            "zone_dintervention": forms.SelectMultiple(attrs={"class": "form-select"}),
        }


class TypeActivitesForm(StyledModelForm):
    class Meta:
        model = TYPE_ACTIVITES
        fields = "__all__"


class ActivitesForm(StyledModelForm):
    class Meta:
        model = ACTIVITES
        exclude = (
            "latitude",
            "longitude",
            "gps_accuracy_m",
            "gps_captured_at",
            "gps_source",
        )
        widgets = {
            "Debut_de_lactivite": forms.DateInput(attrs={"type": "date"}),
            "fin_de_lactivite": forms.DateInput(attrs={"type": "date"}),
        }


class UserForm(StyledModelForm):
    class Meta:
        model = User
        fields = (
            "username",
            "first_name",
            "last_name",
            "email",
            "Organisation",
            "Fonction",
            "Photo",
            "admin",
            "is_active",
        )
