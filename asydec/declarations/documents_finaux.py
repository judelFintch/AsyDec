"""Première étape des documents finaux : licence et date du BL."""
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation


def preparer_licence(numero_dec, montant_fob, numero_validation, date_validation):
    numero_dec = numero_dec.strip()
    numero_validation = numero_validation.strip()
    if not numero_dec or not numero_validation:
        raise ValueError('Renseignez le numéro DEC et le numéro de validation de la licence.')
    try:
        fob = Decimal(montant_fob.replace(' ', '').replace('\u202f', '').replace('\u00a0', '').replace(',', '.'))
    except InvalidOperation:
        raise ValueError('Le montant FOB doit être un nombre positif.') from None
    if not fob.is_finite() or fob <= 0:
        raise ValueError('Le montant FOB doit être un nombre positif.')
    try:
        validation = datetime.strptime(date_validation.strip(), '%d/%m/%Y').date()
    except ValueError:
        raise ValueError('Saisissez une date de validation valide au format JJ/MM/AAAA.') from None
    # Jours calendaires ; premier lundi à vendredi dans la fenêtre J+3 à J+5.
    date_bl = validation + timedelta(days=3)
    while date_bl.weekday() >= 5:
        date_bl += timedelta(days=1)
    return dict(numero_dec=numero_dec, montant_fob=fob,
                numero_validation=numero_validation, date_validation=validation,
                date_bl=date_bl, delai=(date_bl - validation).days)
