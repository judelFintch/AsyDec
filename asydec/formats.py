"""Mise en forme française des nombres et des dates, commune aux écrans, aux PDF et aux analyses."""
from datetime import datetime


def nombre(valeur, decimales=0):
    """1234567.5 -> « 1 234 567,50 » ; valeur absente -> « — »."""
    if valeur is None:
        return "—"
    return f"{valeur:,.{decimales}f}".replace(",", " ").replace(".", ",")


def date_locale(valeur_iso):
    """Date ISO (UTC) -> « 27/10/2026 17:04:02 » à l'heure de l'ordinateur."""
    return datetime.fromisoformat(valeur_iso).astimezone().strftime("%d/%m/%Y %H:%M:%S")
