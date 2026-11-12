"""Origine et port de chargement : une seule source pour la licence, le CVI, le BL et la facture.

- L'origine vient toujours des articles de la licence (pays d'origine), jamais d'une valeur par défaut.
- Le port de chargement est saisi une fois (Infos BL) ; il donne le pays de provenance, les conditions
  « FOB <port> PORT, <pays> » du BL et le « Port of Loading » de la facture.
- Sans saisie, le port proposé est le port habituel du pays d'origine (Inde -> CHENNAI).
"""
import re
from collections import Counter

from asydec.declarations.xml_licence import pays as pays_licence

# Ports connus -> pays (en anglais, comme sur les BL).
PORTS = {
    'CHENNAI': 'INDIA', 'MADRAS': 'INDIA', 'NHAVA SHEVA': 'INDIA', 'MUMBAI': 'INDIA', 'MUNDRA': 'INDIA',
    'KOLKATA': 'INDIA', 'VISAKHAPATNAM': 'INDIA', 'TUTICORIN': 'INDIA', 'COCHIN': 'INDIA',
    'JEBEL ALI': 'UAE', 'DUBAI': 'UAE', 'ABU DHABI': 'UAE', 'SHARJAH': 'UAE', 'AJMAN': 'UAE',
    'SHANGHAI': 'CHINA', 'NINGBO': 'CHINA', 'QINGDAO': 'CHINA', 'SHENZHEN': 'CHINA', 'GUANGZHOU': 'CHINA',
    'XIAMEN': 'CHINA', 'TIANJIN': 'CHINA', 'YANTIAN': 'CHINA', 'NANSHA': 'CHINA',
    'DAR ES SALAAM': 'TANZANIA', 'MOMBASA': 'KENYA', 'DURBAN': 'SOUTH AFRICA', 'BEIRA': 'MOZAMBIQUE',
    'WALVIS BAY': 'NAMIBIA', 'MERSIN': 'TURKEY', 'ISTANBUL': 'TURKEY', 'KARACHI': 'PAKISTAN',
    'PORT KLANG': 'MALAYSIA', 'LAEM CHABANG': 'THAILAND', 'BUSAN': 'KOREA', 'YOKOHAMA': 'JAPAN',
    'ANTWERP': 'BELGIUM', 'ROTTERDAM': 'NETHERLANDS', 'HAMBURG': 'GERMANY',
}
# Pays d'origine (code ISO) -> port de chargement proposé par défaut.
PORT_PAR_ORIGINE = {'IN': 'CHENNAI', 'CN': 'SHANGHAI', 'AE': 'JEBEL ALI', 'TR': 'MERSIN', 'PK': 'KARACHI'}
# Code ISO -> nom anglais en capitales (BL, facture) et nom français en capitales (CVI).
NOMS = {'IN': ('INDIA', 'INDE'), 'CN': ('CHINA', 'CHINE'), 'AE': ('UAE', 'EMIRATS ARABES UNIS'),
        'TZ': ('TANZANIA', 'TANZANIE'), 'ZM': ('ZAMBIA', 'ZAMBIE'), 'ZA': ('SOUTH AFRICA', 'AFRIQUE DU SUD'),
        'KE': ('KENYA', 'KENYA'), 'JP': ('JAPAN', 'JAPON'), 'TH': ('THAILAND', 'THAILANDE'),
        'ID': ('INDONESIA', 'INDONESIE'), 'VN': ('VIETNAM', 'VIETNAM'), 'MY': ('MALAYSIA', 'MALAISIE'),
        'PK': ('PAKISTAN', 'PAKISTAN'), 'TR': ('TURKEY', 'TURQUIE'), 'KR': ('KOREA', 'COREE'),
        'US': ('USA', 'ETATS-UNIS'), 'DE': ('GERMANY', 'ALLEMAGNE'), 'FR': ('FRANCE', 'FRANCE'),
        'IT': ('ITALY', 'ITALIE'), 'BE': ('BELGIUM', 'BELGIQUE'), 'NL': ('NETHERLANDS', 'PAYS-BAS'),
        'GB': ('UNITED KINGDOM', 'ROYAUME-UNI')}
_CODE_PAR_NOM_ANGLAIS = {anglais: code for code, (anglais, _) in NOMS.items()}


def code_origine(licence):
    """Code ISO du pays d'origine le plus représenté parmi les articles de la licence, ou None."""
    codes = Counter()
    for produit in licence.get('produits') or []:
        code, _ = pays_licence(produit.get('pays_origine'))
        if code:
            codes[code] += 1
    return codes.most_common(1)[0][0] if codes else None


def origine_cvi(licence):
    """Pays d'origine pour le CVI (français, capitales), ex. « INDE » ; None si la licence ne le donne pas."""
    code = code_origine(licence)
    if code is None:
        brut = next((str(p.get('pays_origine')).strip() for p in licence.get('produits') or []
                     if str(p.get('pays_origine') or '').strip()), '')
        return brut.upper() or None
    return NOMS.get(code, (None, pays_licence(code)[1] or code))[1].upper()


def normaliser_port(port):
    return ' '.join(re.sub(r'\bPORT\b', '', str(port or '').upper()).split()).strip(' ,')


def pays_du_port(port):
    """Pays (anglais, capitales) d'un port connu, sinon None."""
    return PORTS.get(normaliser_port(port))


def port_par_defaut(licence):
    return PORT_PAR_ORIGINE.get(code_origine(licence))


def conditions_fob(port):
    """« FOB CHENNAI PORT, INDIA » pour un port connu, « FOB <port> PORT » sinon."""
    nom = normaliser_port(port)
    if not nom:
        return ''
    pays = pays_du_port(nom)
    return f'FOB {nom} PORT' + (f', {pays}' if pays else '')


def lieu_chargement(port):
    """« CHENNAI, INDIA » pour la facture (Port of Loading)."""
    nom = normaliser_port(port)
    pays = pays_du_port(nom)
    return f'{nom}, {pays}' if pays else nom


def alertes(licence, port):
    """Incohérences à signaler (non bloquantes : un transbordement reste possible)."""
    resultat = []
    code = code_origine(licence)
    pays_port = pays_du_port(port)
    if code and pays_port and _CODE_PAR_NOM_ANGLAIS.get(pays_port) != code:
        resultat.append(f'Port de chargement {normaliser_port(port)} ({pays_port}) alors que les articles sont '
                        f'd’origine {NOMS.get(code, (code,))[0]} : vérifiez le BL et la facture.')
    if port and not pays_port:
        resultat.append(f'Port {normaliser_port(port)} inconnu : son pays n’apparaîtra pas dans les conditions FOB.')
    return resultat
