"""Première étape des documents finaux : licence et date du BL."""
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import random
from asydec.declarations.dates_documents import exiger_ouvrable, est_ouvrable

# Date de facture proposée : jour ouvrable tiré entre ECART_FACTURE_MIN et ECART_FACTURE_MAX jours avant la
# validation. La facture portée par une licence importée fait foi, même un jour avant la licence ;
# seule une facture postérieure à la licence est refusée.
ECART_FACTURE_MIN = 30
ECART_FACTURE_MAX = 45


def _jour(valeur):
    if isinstance(valeur, datetime):
        return valeur.date()
    if isinstance(valeur, date):
        return valeur
    texte = str(valeur or '').strip()
    for format_ in ('%d/%m/%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(texte, format_).date()
        except ValueError:
            pass
    raise ValueError(f'Date invalide : {texte or "vide"}.')


def proposer_date_facture(date_validation, tirage=None):
    """JJ/MM/AAAA : jour ouvrable tiré entre ECART_FACTURE_MIN et ECART_FACTURE_MAX jours avant la licence."""
    validation = _jour(date_validation)
    candidats = [validation - timedelta(days=d) for d in range(ECART_FACTURE_MIN, ECART_FACTURE_MAX + 1)]
    candidats = [j for j in candidats if est_ouvrable(j)]
    return (tirage or random.SystemRandom()).choice(candidats).strftime('%d/%m/%Y')


def controler_date_facture(date_facture, date_validation):
    """ValueError si la facture est datée après la licence (impossible)."""
    if not str(date_facture or '').strip() or not str(date_validation or '').strip():
        return
    facture, validation = _jour(date_facture), _jour(date_validation)
    if facture > validation:
        raise ValueError(f'La date de facture ({facture:%d/%m/%Y}) ne peut pas suivre la licence ({validation:%d/%m/%Y}).')


def references_facture(numero_facture='', date_facture='', obligatoire=False):
    """N° et date de la facture portée par la licence : (numéro sans espaces, JJ/MM/AAAA)."""
    numero = ''.join(str(numero_facture or '').split())
    texte = str(date_facture or '').strip()
    if obligatoire and (not numero or not texte):
        raise ValueError('Renseignez le numéro et la date de facture de la licence.')
    if not texte:
        return numero, ''
    try:
        jour = datetime.strptime(texte.replace('-', '/').replace('.', '/'), '%d/%m/%Y').date()
    except ValueError:
        raise ValueError('Saisissez une date de facture valide au format JJ/MM/AAAA.') from None
    return numero, jour.strftime('%d/%m/%Y')


def preparer_licence(numero_dec, montant_fob, numero_validation, date_validation, numero_facture='', date_facture=''):
    numero_dec = numero_dec.strip()
    numero_validation = numero_validation.strip()
    if not numero_dec or not numero_validation:
        raise ValueError('Renseignez le numéro licence et le numéro DEC.')
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
    exiger_ouvrable(validation, 'La date de validation de la licence')
    # Jours calendaires ; premier lundi à vendredi dans la fenêtre J+3 à J+5.
    candidats = [validation + timedelta(days=j) for j in (3, 4, 5)]
    date_bl = next((j for j in candidats if est_ouvrable(j)), None)
    if date_bl is None:
        raise ValueError('Aucune date BL ouvrable entre J+3 et J+5 avec le calendrier RDC.')
    numero_facture, date_facture = references_facture(numero_facture, date_facture)
    controler_date_facture(date_facture, validation)
    return dict(numero_dec=numero_dec, montant_fob=fob,
                numero_validation=numero_validation, date_validation=validation,
                date_bl=date_bl, delai=(date_bl - validation).days,
                numero_facture=numero_facture, date_facture=date_facture)
