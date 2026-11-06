"""Informations complémentaires saisies avant l’export XML."""
from datetime import date, datetime, timedelta
import calendar
import random
from asydec.declarations.dates_documents import exiger_ouvrable, precedent_ouvrable, suivant_ouvrable, est_ouvrable

CHAMPS = (
    ('numero_e', 'Numéro E', 'Identification/Registration/Number'),
    ('date_enregistrement', 'Date d’enregistrement · automatique', 'Identification/Registration/Date'),
    ('numero_liquidation', 'Numéro liquidation', 'Identification/Assessment/Number'),
    ('date_liquidation', 'Date liquidation · automatique', 'Identification/Assessment/Date'),
    ('numero_quittance', 'Numéro Q / quittance', 'Identification/receipt/Number'),
    ('date_quittance', 'Date quittance · automatique', 'Identification/receipt/Date'),
    ('date_cvi', 'Date CVI · automatique', None),
    ('manifeste', 'Numéro manifeste', 'Identification/Manifest_reference_number'),
    ('reference', 'Référence de la déclaration', 'Declarant/Reference/Number'),
    ('date_declaration', 'Date de déclaration (JJ/MM/AAAA)', 'Property/Date_of_declaration'),
    ('bureau_code', 'Code du bureau douanier', 'Identification/Office_segment/Customs_clearance_office_code'),
    ('bureau_nom', 'Nom du bureau douanier', 'Identification/Office_segment/Customs_Clearance_office_name'),
    ('plaque', 'Plaque du moyen de transport', 'Transport/Means_of_transport/Departure_arrival_information/Identity'),
    ('numero_bl', 'Numéro BL', None),
)


def verifier(valeurs):
    resultat = {cle: str(valeurs.get(cle, '')).strip() for cle, _, _ in CHAMPS}
    resultat['observations'] = str(valeurs.get('observations', '')).strip()
    if not any(resultat.values()):
        raise ValueError('Renseignez les informations de déclaration avant de les enregistrer.')
    if resultat['date_enregistrement']:
        try:
            enregistrement = datetime.strptime(resultat['date_enregistrement'], '%d/%m/%Y').date()
        except ValueError:
            raise ValueError('Date d’enregistrement invalide : utilisez JJ/MM/AAAA.') from None
        exiger_ouvrable(enregistrement, 'La date d’enregistrement')
        if enregistrement > date.today():
            raise ValueError('La date d’enregistrement ne doit pas dépasser aujourd’hui.')
        resultat['date_enregistrement'] = enregistrement.strftime('%d/%m/%Y')
    if resultat['date_declaration']:
        try:
            jour = datetime.strptime(resultat['date_declaration'], '%d/%m/%Y')
        except ValueError:
            raise ValueError('Date de déclaration invalide : utilisez JJ/MM/AAAA.') from None
        exiger_ouvrable(jour, 'La date de déclaration')
        resultat['date_declaration'] = jour.strftime('%d/%m/%Y')
    if resultat['date_liquidation'] or resultat['date_quittance']:
        if not resultat['date_enregistrement']:
            raise ValueError('La date d’enregistrement est nécessaire pour la liquidation et la quittance.')
        e = lire_date(resultat['date_enregistrement'])
        dates = {}
        for cle in ('date_liquidation', 'date_quittance'):
            if not resultat[cle]:
                raise ValueError('Les dates de liquidation et de quittance doivent être générées ensemble.')
            jour = lire_date(resultat[cle])
            exiger_ouvrable(jour, 'La ' + cle.replace('_', ' '))
            if (jour-e).days not in (0,2,3) or jour > date.today():
                raise ValueError('Liquidation et quittance : jour E, E+2 ou E+3, sans dépasser aujourd’hui.')
            dates[cle] = jour
            resultat[cle] = jour.strftime('%d/%m/%Y')
        if dates['date_quittance'] < dates['date_liquidation']:
            raise ValueError('La quittance ne peut pas précéder la liquidation.')
    if resultat['date_cvi']:
        if not resultat['date_liquidation']:
            raise ValueError('La date de liquidation est nécessaire pour la date CVI.')
        cvi = lire_date(resultat['date_cvi'])
        exiger_ouvrable(cvi, 'La date CVI')
        ecart = (cvi - lire_date(resultat['date_liquidation'])).days
        if ecart < ECARTS_CVI[0] or (ecart > ECARTS_CVI[-1] and cvi != proposer_date_cvi(resultat['date_liquidation'])):
            raise ValueError('Date CVI : entre 2 et 4 jours après la liquidation, jour ouvrable.')
        resultat['date_cvi'] = cvi.strftime('%d/%m/%Y')
    return resultat


def lire_date(valeur):
    if isinstance(valeur, datetime):
        return valeur.date()
    if isinstance(valeur, date):
        return valeur
    for format_date in ('%Y-%m-%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(str(valeur).strip(), format_date).date()
        except ValueError:
            pass
    raise ValueError('La date du BL est absente ou invalide.')


def ajouter_mois(jour, nombre):
    mois = jour.year * 12 + jour.month - 1 + nombre
    annee, mois = divmod(mois, 12)
    mois += 1
    return date(annee, mois, min(jour.day, calendar.monthrange(annee, mois)[1]))


def proposer_date_enregistrement(date_bl, aujourdhui=None):
    """Dernier jour ouvrable entre un et deux mois après le BL, sans dépasser aujourd’hui."""
    bl = lire_date(date_bl)
    limite = aujourdhui or date.today()
    exiger_ouvrable(bl, 'La date du BL')
    debut = ajouter_mois(bl, 1)
    fin = ajouter_mois(bl, 2)
    proposition = precedent_ouvrable(min(fin, limite))
    if proposition < debut:
        # Un mois tombant un jour non ouvrable : prochain jour ouvrable.
        proposition = suivant_ouvrable(debut)
    if proposition > limite:
        raise ValueError('Aucune date d’enregistrement ouvrable possible sans dépasser aujourd’hui, au moins un mois après le BL.')
    complet = proposition == precedent_ouvrable(fin)
    return dict(date=proposition, mois=2 if complet else 1, exceptionnel=not complet)


def date_enregistrement_possible_le(date_bl, aujourdhui=None):
    """Premier jour où une date d'enregistrement pourra être proposée (un mois ouvrable après le BL),
    ou None si elle est déjà possible ou si le BL est absent ou invalide."""
    try:
        proposer_date_enregistrement(date_bl, aujourdhui)
        return None
    except ValueError:
        try:
            return suivant_ouvrable(ajouter_mois(lire_date(date_bl), 1))
        except ValueError:
            return None


def alerte_enregistrement(licence, aujourdhui=None):
    """Message d'alerte quand le BL a moins d'un mois et qu'aucune date d'enregistrement n'est saisie."""
    if (licence.get('informations_declaration') or {}).get('date_enregistrement'):
        return ''
    possible = date_enregistrement_possible_le(licence.get('date_bl'), aujourdhui)
    if possible is None:
        return ''
    return (f"BL du {lire_date(licence['date_bl']):%d/%m/%Y} : moins d’un mois, "
            f"numéro E possible à partir du {possible:%d/%m/%Y}")


ECARTS_CVI = (2, 3, 4)


def proposer_date_cvi(date_liquidation, tirage=None):
    """Jour ouvrable tiré entre 2 et 4 jours après la liquidation."""
    liquidation = lire_date(date_liquidation)
    candidats = [liquidation + timedelta(days=d) for d in ECARTS_CVI if est_ouvrable(liquidation + timedelta(days=d))]
    if not candidats:
        return suivant_ouvrable(liquidation + timedelta(days=ECARTS_CVI[-1]))
    return (tirage or random.SystemRandom()).choice(candidats)


DATES_AUTO = ('date_enregistrement', 'date_liquidation', 'date_quittance', 'date_cvi')


def proposer_dates_declaration(date_bl, aujourdhui=None, tirage=None):
    limite = aujourdhui or date.today()
    e = proposer_date_enregistrement(date_bl, limite)['date']
    candidats = [e + timedelta(days=d) for d in (0,2,3)
                 if e + timedelta(days=d) <= limite and est_ouvrable(e + timedelta(days=d))]
    couples = [(l,q) for l in candidats for q in candidats if q >= l]
    tirage = tirage or random.SystemRandom()
    liquidation, quittance = tirage.choice(couples)
    return dict(date_enregistrement=e.strftime('%d/%m/%Y'),
                date_liquidation=liquidation.strftime('%d/%m/%Y'),
                date_quittance=quittance.strftime('%d/%m/%Y'),
                date_cvi=proposer_date_cvi(liquidation, tirage).strftime('%d/%m/%Y'))
