"""Ouverture de licence depuis un fichier Excel (ex. liste des DEC exportée par la banque).

Le fichier peut contenir une ou plusieurs licences : une ligne d'en-tête est cherchée
(Déclaration, Désignation client, Montant licence, Devise, Date de validation,
Date d'extrême validité), puis chaque ligne en dessous devient une licence proposée.
Seules les informations présentes dans le fichier sont reprises ; le reste se complète
dans le formulaire comme pour une saisie manuelle.
"""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
import unicodedata

EXTENSIONS = ('.xlsx', '.xlsm')

# Colonne → libellés acceptés (sans accents, en minuscules). Le premier qui correspond l'emporte.
COLONNES = {
    'numero_validation': ('declaration', 'numero licence', 'n licence', 'licence', 'numero dec', 'dec'),
    'soussigne': ('designation client', 'client', 'importateur', 'soussigne', 'raison sociale'),
    'montant_fob': ('montant licence', 'montant fob', 'montant', 'fob', 'valeur'),
    'devise': ('devise', 'monnaie'),
    'date_validation': ('date de validation', 'date validation', 'validation'),
    'date_extreme': ("date d'extreme validite", 'date extreme validite', 'extreme validite', 'date d expiration',
                     'expiration', 'echeance'),
}
OBLIGATOIRES = ('numero_validation', 'montant_fob', 'date_validation')


def _normaliser(texte):
    texte = ''.join(c for c in unicodedata.normalize('NFD', str(texte)) if not unicodedata.combining(c))
    texte = texte.lower().replace('’', "'").replace('°', ' ')
    return re.sub(r'\s+', ' ', re.sub(r"[^a-z0-9' ]", ' ', texte)).strip()


def _colonnes(ligne):
    """Indices des colonnes reconnues dans une ligne d'en-tête, ou None."""
    trouvees = {}
    for indice, cellule in enumerate(ligne):
        if cellule is None or not str(cellule).strip():
            continue
        libelle = _normaliser(cellule)
        for cle, synonymes in COLONNES.items():
            if cle in trouvees:
                continue
            # Libellé exact, ou commençant par un synonyme (évite « validation » dans « extrême validité »).
            if any(libelle == s or libelle.startswith(s + ' ') for s in synonymes):
                if cle == 'date_validation' and 'extreme' in libelle:
                    continue
                trouvees[cle] = indice
                break
    return trouvees if all(c in trouvees for c in OBLIGATOIRES) else None


def _date(valeur):
    if valeur is None or str(valeur).strip() == '':
        return ''
    if isinstance(valeur, datetime):
        return valeur.strftime('%d/%m/%Y')
    if isinstance(valeur, date):
        return valeur.strftime('%d/%m/%Y')
    texte = str(valeur).strip()
    for format_date in ('%d/%m/%Y', '%d-%m-%Y', '%d.%m.%Y', '%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%d/%m/%y'):
        try:
            return datetime.strptime(texte, format_date).strftime('%d/%m/%Y')
        except ValueError:
            pass
    return texte  # laissé tel quel : le formulaire signalera une date invalide


def _montant(valeur):
    if valeur is None:
        return ''
    if isinstance(valeur, (int, float, Decimal)):
        nombre = Decimal(str(valeur))
    else:
        texte = re.sub(r'[\s  ]', '', str(valeur))
        if ',' in texte and '.' in texte:
            decimal = ',' if texte.rfind(',') > texte.rfind('.') else '.'
            texte = texte.replace('.' if decimal == ',' else ',', '').replace(decimal, '.')
        else:
            texte = texte.replace(',', '.')
        try:
            nombre = Decimal(texte)
        except InvalidOperation:
            return str(valeur).strip()
    nombre = nombre.quantize(Decimal('.01'))
    return format(nombre.normalize(), 'f') if nombre == nombre.to_integral_value() else format(nombre, 'f')


def numero_dec(numero_validation):
    """DEC1837831-AE0AAEDB6212-RC → DEC1837831 (même règle pour IB, RC…)."""
    trouve = re.match(r'\s*(DEC[0-9]+)\b', str(numero_validation or ''), re.I)
    return trouve.group(1).upper() if trouve else ''


def lire_excel(chemin):
    """Liste des licences lues : dicts prêts pour le formulaire, plus devise et date d'extrême validité."""
    from openpyxl import load_workbook
    chemin = Path(chemin)
    if chemin.suffix.lower() not in EXTENSIONS:
        raise ValueError('Choisissez un fichier Excel .xlsx (les anciens .xls doivent être réenregistrés en .xlsx).')
    try:
        classeur = load_workbook(chemin, read_only=True, data_only=True)
    except Exception as exc:
        raise ValueError(f'Fichier Excel illisible : {exc}') from None
    licences = []
    try:
        for feuille in classeur.worksheets:
            colonnes = None
            for ligne in feuille.iter_rows(values_only=True):
                if colonnes is None:
                    colonnes = _colonnes(ligne)
                    continue
                valeur = lambda cle: ligne[colonnes[cle]] if cle in colonnes and colonnes[cle] < len(ligne) else None
                numero = str(valeur('numero_validation') or '').strip()
                if not numero:
                    continue
                licences.append(dict(
                    numero_validation=numero, numero_dec=numero_dec(numero),
                    montant_fob=_montant(valeur('montant_fob')),
                    date_validation=_date(valeur('date_validation')),
                    devise=str(valeur('devise') or '').strip().upper(),
                    date_extreme=_date(valeur('date_extreme')),
                    soussigne=' '.join(str(valeur('soussigne') or '').split()),
                    feuille=feuille.title))
    finally:
        classeur.close()
    if not licences:
        raise ValueError('Aucune licence trouvée : le fichier doit avoir une ligne d’en-tête avec au moins '
                         '« Déclaration », « Montant licence » et « Date de validation ».')
    return licences


def valeurs_formulaire(ligne, importateur=None, fournisseur=None):
    """Valeurs à charger dans le formulaire d'ouverture de licence.

    importateur / fournisseur : coordonnées complètes reprises d'une licence existante
    (nom, adresse, téléphone, e-mail, identifiants…). Sans importateur choisi, seul le
    nom du client du fichier Excel est repris.
    """
    from copy import deepcopy
    soussigne = deepcopy(importateur) if importateur else ({'nom': ligne['soussigne']} if ligne.get('soussigne') else {})
    if not soussigne.get('nom') and ligne.get('soussigne'):
        soussigne['nom'] = ligne['soussigne']
    return dict(numero_validation=ligne['numero_validation'], numero_dec=ligne['numero_dec'],
                montant_fob=ligne['montant_fob'], date_validation=ligne['date_validation'],
                numero_facture='', date_facture='', soussigne=soussigne,
                fournisseur=deepcopy(fournisseur) if fournisseur else {}, produits=[])


def sources_existantes(fichier=None):
    """Importateurs et fournisseurs des licences déjà ouvertes (voir reprises_licence)."""
    from asydec.declarations.reprises_licence import parties_existantes
    return parties_existantes(fichier)


def expiree(ligne, aujourdhui=None):
    try:
        return datetime.strptime(ligne.get('date_extreme') or '', '%d/%m/%Y').date() < (aujourdhui or date.today())
    except ValueError:
        return False


def ouvrir_plusieurs(lignes, fichier=None, importateur=None, fournisseur=None):
    """Enregistre plusieurs licences d'un coup (étape 1), sans écraser celles déjà ouvertes.

    Renvoie (ouvertes, ignorees, erreurs) : numéros enregistrés, numéros déjà présents,
    et liste de (numéro, message) pour les lignes invalides (ex. date non ouvrable).
    Les produits (et le fournisseur s'il n'est pas repris) restent à compléter en rouvrant chaque licence.
    """
    from asydec.declarations import licences_ouvertes
    from asydec.declarations.documents_finaux import preparer_licence
    deja = {str(l['numero']).strip().upper() for l in licences_ouvertes.lister(fichier)}
    ouvertes, ignorees, erreurs = [], [], []
    for ligne in lignes:
        numero = ligne['numero_validation']
        if numero.upper() in deja:
            ignorees.append(numero)
            continue
        valeurs = valeurs_formulaire(ligne, importateur, fournisseur)
        try:
            if ligne.get('devise') and ligne['devise'] != 'USD':
                raise ValueError(f"devise {ligne['devise']} : à ouvrir une par une pour vérifier le montant")
            licence = preparer_licence(valeurs['numero_dec'], valeurs['montant_fob'], numero, valeurs['date_validation'])
            # Client connu : fiche complète et dernier fournisseur repris automatiquement (si non choisis).
            from asydec.declarations.reprises_licence import completer_parties
            complete = completer_parties(valeurs['soussigne'], valeurs['fournisseur'], fichier)
            licence.update(soussigne=complete['soussigne'], fournisseur=complete['fournisseur'], produits=[],
                           nombre_produits_attendu=None)
            licences_ouvertes.enregistrer(licence, fichier)
        except (ValueError, OSError) as exc:
            erreurs.append((numero, str(exc)))
            continue
        deja.add(numero.upper())
        ouvertes.append(numero)
    return ouvertes, ignorees, erreurs
