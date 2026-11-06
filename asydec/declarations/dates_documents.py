"""Calendrier RDC des documents finaux : lundi à vendredi hors jours fériés.

Ordonnance 23/042 du 30 mars 2023, art. 1 et 2 :
https://droitcongolais.info/files/143.03.23_Ordonnance-du-30-mars-2023_jours-feries.pdf
Report exceptionnel du 17 janvier 2026 au 19 janvier : communiqué ministériel
relayé par ACP le 12 janvier 2026.
"""
from datetime import date, datetime, timedelta


def jours_feries(annee):
    fixes = ((1,1),(1,4),(1,16),(1,17),(5,1),(5,17),(6,30),(8,1),(12,25))
    jours = {date(annee,m,j) for m,j in fixes}
    if annee >= 2023:
        jours.add(date(annee,4,6))
    # Le texte légal reporte au jour précédent un férié tombant un dimanche.
    jours.update(j - timedelta(days=1) for j in tuple(jours) if j.weekday()==6)
    if annee == 2026:
        jours.add(date(2026,1,19))
    return jours


def est_ouvrable(jour):
    if isinstance(jour, datetime):
        jour = jour.date()
    return jour.weekday() < 5 and jour not in jours_feries(jour.year)


def exiger_ouvrable(jour, libelle):
    if not est_ouvrable(jour):
        raise ValueError(f'{libelle} doit tomber un jour ouvrable, du lundi au vendredi hors jours fériés RDC.')
    return jour


def precedent_ouvrable(jour):
    while not est_ouvrable(jour):
        jour -= timedelta(days=1)
    return jour


def suivant_ouvrable(jour):
    while not est_ouvrable(jour):
        jour += timedelta(days=1)
    return jour
