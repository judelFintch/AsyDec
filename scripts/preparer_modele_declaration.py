"""Prépare le modèle Word de la déclaration (DCU) : chaque valeur d'exemple de l'original devient une balise
{{CHAMP}}, à la même place et dans les mêmes segments de texte. Polices, positions, zones et image de fond
restent ceux de l'original. Usage : python scripts/preparer_modele_declaration.py ORIGINAL.docx MODELE.docx
"""
from io import BytesIO
import sys
from xml.dom import minidom
from zipfile import ZipFile

sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent.parent))
from asydec.declarations.preparer_facture import texte, remplacer  # noqa: E402

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

# Case n° (paire Choice/Fallback dans l'ordre du document) -> remplacements par paragraphe.
# Paragraphe : liste de (texte d'exemple, balise), dans l'ordre d'apparition ; LISTE = un paragraphe gardé.
CASES = {
    0: [[('IN', 'PAYS_TRANSACTION')]],
    1: [[('Motocycles à moteur à piston, d’une cylindrée n’excèdent pas 50cm3', 'DESIGNATION')]],
    2: [[('4647', 'NUMERO_Q'), ('05/11/2025', 'DATE_Q')]],
    3: [[('DEC1500886', 'NUMERO_LICENCE')]],
    4: [[('9797', 'NUMERO_E'), ('05/11/2025', 'DATE_E')]],
    5: [[('93,405,115', 'TAXES_ARTICLE')]],
    6: [[('135,703,015', 'TOTAL_TAXES')]],
    7: [[('2025', 'REF_ANNEE'), ('443NCA', 'REF_SUITE')]],
    8: 'PAYEUR',
    9: [[('Inde', 'NOM_PAYS_ORIGINE')]],
    10: [[('Inde', 'NOM_PAYS_EXPORT')]],
    11: 'TAXE_MONTANT',
    12: 'TAXE_BASE',
    13: 'EXPORTATEUR',
    14: 'DESTINATAIRE',
    15: [[('A2220284Y', 'CODE_DESTINATAIRE')]],
    16: [[('A2220284Y', 'CODE_PAYEUR')]],
    17: [[('4', 'PROCEDURE')]],
    18: [[('725B', 'CODE_BUREAU')], [('COMEXAS AFRIQUE', 'NOM_BUREAU')]],
    19: [[('1', 'FORMULAIRE')]],
    20: [[('1', 'TOTAL_FORMULAIRES')]],
    21: [[('1', 'NOMBRE_ARTICLES')]],
    22: [[('180', 'TOTAL_COLIS')]],
    23: [[('2025 6765', 'MANIFESTE')]],
    24: 'DECLARANT',
    25: [[('000313', 'CODE_DECLARANT')]],
    26: [[('15,187,815', 'FRAIS')]],
    27: [[('ID', 'CODE_PAYS_EXPORT')]],
    28: [[('CD', 'CODE_DESTINATION')]],
    29: [[('République Démocratique du', 'NOM_DESTINATION')]],
    30: [[('T443FFV/T543VVC', 'PLAQUE_ARRIVEE'), ('TZ', 'NATIONALITE_ARRIVEE')]],
    31: [[('T443FFV/T543VVC', 'PLAQUE_FRONTIERE')]],
    32: [[('CIF', 'CODE_LIVRAISON'), ('LUBUMBASHI', 'LIEU_LIVRAISON')]],
    33: [[('USD', 'DEVISE'), ('126,360.00', 'TOTAL_FACTURE'), ('2,139.1288', 'TAUX')]],
    34: [[('5130', 'CODE_BANQUE')]],
    35: [[('CPT', 'CODE_TERMES'), ('Comptant', 'LIBELLE_TERMES')]],
    36: [[('RAWBANK / LUBUMBASHI', 'NOM_BANQUE')]],
    37: [[('51', 'AGENCE_BANQUE')]],
    38: [[('30', 'MODE_FRONTIERE')]],
    39: [[('30', 'MODE_INTERIEUR')]],
    40: [[('722B', 'CODE_BUREAU_FRONTIERE'), ('KASUMBALESA WISKY', 'NOM_BUREAU_FRONTIERE'), ('725B000', 'LIEU_MARCHANDISES')]],
    41: [[('ADD', 'MARQUES')]],
    42: [[('180.00', 'NOMBRE_COLIS'), ('PC', 'CODE_COLIS')]],
    43: [[('Colis', 'NOM_COLIS')]],
    44: [[('871410000', 'CODE_SH')]],
    45: [[('ID', 'CODE_ORIGINE'), ('24,000.000', 'POIDS_BRUT')]],
    46: [[('4000', 'PROCEDURE_ETENDUE'), ('000', 'PROCEDURE_NATIONALE'), ('24,000,000', 'POIDS_NET')]],
    47: [[('1', 'DOCUMENT_PRECEDENT')]],
    48: [[('UNT', 'CODE_UNITE'), ('1.000', 'QUANTITE_UNITE'), ('126,360.00', 'PRIX_ARTICLE')]],
    49: [[('26,898,504+0+284,0+0-0', 'DETAIL_VALEUR')]],
    50: [[('FCMTTRFRICAA', 'DOCUMENTS_JOINTS')]],
    51: [[('1.0000', 'TAUX_AJUSTEMENT')]],
    52: [[('285,488,130', 'VALEUR_STATISTIQUE')]],
    53: 'TAXE_CODE',
    54: 'TAXE_TAUX',
    55: [[('COMPTANT', 'MODE_PAIEMENT')]],
    56: [[('9729', 'NUMERO_L'), ('05/11/2025', 'DATE_L')]],
    57: [[('0', 'GARANTIE')]],
    58: [[('42,297,900', 'TAXES_GLOBALES')]],
}


def paragraphes(boite):
    return [p for p in boite.getElementsByTagNameNS(W, 'p')]


def preparer(source):
    archive = ZipFile(BytesIO(source))
    doc = minidom.parseString(archive.read('word/document.xml'))
    boites = list(doc.getElementsByTagNameNS(W, 'txbxContent'))
    if len(boites) != 2 * len(CASES):
        raise SystemExit(f'{len(boites)} zones de texte, {2 * len(CASES)} attendues : original différent.')
    for i, boite in enumerate(boites):
        case = CASES[i // 2]
        paras = paragraphes(boite)
        if isinstance(case, str):  # liste : un seul paragraphe, cloné au remplissage
            premier = paras[0]
            remplacer(premier, 0, len(texte(premier)), '{{' + case + '}}')
            for p in paras[1:]:
                p.parentNode.removeChild(p)
            continue
        for p, remplacements in zip(paras, case):
            contenu, position = texte(p), 0
            reperes = []
            for exemple, balise in remplacements:
                debut = contenu.find(exemple, position)
                if debut < 0:
                    raise SystemExit(f'Case {i // 2} : « {exemple} » introuvable dans « {contenu} ».')
                reperes.append((debut, debut + len(exemple), balise))
                position = debut + len(exemple)
            for debut, fin, balise in reversed(reperes):
                remplacer(p, debut, fin, '{{' + balise + '}}')
    sortie = BytesIO()
    with ZipFile(sortie, 'w') as cible:
        for info in archive.infolist():
            cible.writestr(info, doc.toxml(encoding='UTF-8') if info.filename == 'word/document.xml'
                           else archive.read(info.filename))
    return sortie.getvalue()


if __name__ == '__main__':
    with open(sys.argv[1], 'rb') as f:
        resultat = preparer(f.read())
    with open(sys.argv[2], 'wb') as f:
        f.write(resultat)
    print('Modèle préparé :', sys.argv[2])
