"""Taux de change de la déclaration (case 23), saisi à l'étape 3.

Il ne sert qu'à l'affichage sur la déclaration Word : il est rangé hors des informations de déclaration
(clé « taux_change » du dossier), si bien que le changer n'invalide ni la mise à jour des répartitions,
ni les factures, ni le CVI, ni les XML. Seules les déclarations sont à régénérer.

Taux proposé par défaut, du plus proche au plus général : celui déjà retenu pour le dossier, celui des
XML SYDONIA importés pour ce dossier, le dernier taux retenu sur un autre dossier, celui de la plus
récente déclaration réelle du dossier XML_LICENCES, enfin le taux saisi dans les préférences.
"""
from decimal import Decimal, InvalidOperation
from pathlib import Path
import xml.etree.ElementTree as ET

CHEMIN_TAUX = 'Valuation/Gs_Invoice/Currency_rate'
DECIMALES = 4


def lire(valeur):
    """Decimal positif, ou None si vide ; ValueError si illisible."""
    texte = str(valeur if valeur is not None else '').replace(' ', '').replace(' ', '').replace('\xa0', '').strip()
    if not texte:
        return None
    if texte.count(',') == 1 and '.' not in texte:
        avant, apres = texte.split(',')
        # « 2,256 » : un taux CDF/USD vaut des milliers, la virgule y sépare les milliers.
        milliers = avant.isdigit() and 1 <= len(avant) <= 3 and apres.isdigit() and len(apres) == 3
        texte = texte.replace(',', '' if milliers else '.')
    elif ',' in texte and '.' in texte and texte.rfind(',') > texte.rfind('.'):
        texte = texte.replace('.', '').replace(',', '.')  # « 2.256,017 »
    else:
        texte = texte.replace(',', '')
    try:
        taux = Decimal(texte)
    except InvalidOperation:
        taux = None
    if taux is None or not taux.is_finite() or taux <= 0:
        raise ValueError(f'Taux de change « {valeur} » invalide : saisissez un nombre positif (CDF pour 1 USD).')
    return taux


def texte(taux):
    """« 2262.3200 » : forme enregistrée."""
    return format(Decimal(taux).quantize(Decimal(1).scaleb(-DECIMALES)), 'f')


def _taux_xml(contenu):
    try:
        racine = ET.fromstring(contenu) if isinstance(contenu, (str, bytes)) else ET.parse(contenu).getroot()
        return lire(racine.findtext(CHEMIN_TAUX))
    except (ET.ParseError, OSError, ValueError):
        return None


def du_dossier(licence):
    """Taux retenu pour ce dossier (Decimal) ou None : la déclaration garde alors celui du XML SYDONIA."""
    try:
        return lire((licence.get('taux_change') or {}).get('valeur'))
    except ValueError:
        return None


def proposer(licence, autres=(), dossier_reel=None, preference=None):
    """(taux Decimal, source) ou (None, '').

    autres : contenus des autres dossiers, du plus récent au plus ancien."""
    taux = du_dossier(licence)
    if taux:
        return taux, 'taux retenu pour ce dossier'
    for i in (licence.get('recuperation_simulation') or {}).get('imports') or []:
        if i.get('simule'):  # XML de vérification AsyDec : son taux vient déjà de ce dossier
            continue
        taux = _taux_xml(i.get('contenu') or '')
        if taux:
            return taux, 'XML SYDONIA importé ' + Path(i.get('fichier') or '').name
    for autre in autres:
        taux = du_dossier(autre)
        if taux:
            return taux, f"dernier taux retenu (dossier {autre.get('numero_validation', '')})".replace(' ()', '')
    if dossier_reel:
        fichiers = sorted(Path(dossier_reel).glob('*.xml'), key=lambda p: p.stat().st_mtime, reverse=True)
        for fichier in fichiers:
            taux = _taux_xml(fichier)
            if taux:
                return taux, f'déclaration réelle {fichier.name}'
    try:
        taux = lire(preference)
    except ValueError:
        taux = None
    return (taux, 'préférences') if taux else (None, '')
