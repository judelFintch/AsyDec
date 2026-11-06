"""Préparation du modèle fourni : CVI, ou CVI puis BL avec inclure_bl=True."""
from io import BytesIO
import copy
from zipfile import ZipFile
from xml.dom import minidom
from asydec.declarations.preparer_facture import texte, remplacer

ZONES = {
    95: 'NUMERO_BL', 93: 'CONSTAT', 91: 'PLAQUE', 89: 'ORIGINE', 87: 'MODE_TRANSPORT',
    85: 'FOURNISSEUR', 81: 'ADRESSE_IMPORTATEUR', 79: 'IMPORTATEUR', 77: 'NUMERO_QUITTANCE',
    75: 'REGIME', 73: 'NUMERO_LIQUIDATION', 71: 'NUMERO_E', 69: 'BORDEREAU',
    59: 'POSTE_ENTREE', 57: 'ENTITE', 55: 'DOSSIER_OCC', 53: 'NUMERO_CVI',
    51: 'DATE_CVI', 47: 'RAPPORT_INSPECTION', 45: 'FRET', 43: 'ASSURANCE', 41: 'DEVISE',
    39: 'PROVENANCE', 37: 'FOB', 35: 'CIF', 33: 'POIDS_GLOBAL_CVI', 31: 'QUANTITE',
    29: 'NUMERO_LICENCE', 27: 'DESTINATION',
}


def preparer(contenu, inclure_bl=False):
    with ZipFile(BytesIO(contenu)) as archive:
        doc = minidom.parseString(archive.read('word/document.xml'))
        # Le saut explicite sépare le certificat (page 1) du BL (page 2).
        sauts = [b for b in doc.getElementsByTagName('w:br') if b.getAttribute('w:type') == 'page']
        if len(sauts) != 1:
            raise ValueError('Structure du modèle CVI non reconnue : séparation CVI / BL absente.')
        run = sauts[0]
        while run.parentNode.localName != 'p':
            run = run.parentNode
        parent = run.parentNode
        if not inclure_bl:
            while run is not None:
                suivant = run.nextSibling
                parent.removeChild(run)
                run = suivant
        presentes = set()
        for zone in doc.getElementsByTagName('v:shape'):
            identifiant = zone.getAttribute('id')
            if not identifiant.startswith('Zone de texte '):
                continue
            numero = int(identifiant.rsplit(' ', 1)[-1])
            if numero == 49:
                p = zone.getElementsByTagName('w:p')[0]
                ancien = texte(p)
                # Deux tabulations séparent N°, désignation, quantité : garder les tabulations.
                debut, fin = 1, ancien.index('1 800,000')
                remplacer(p, fin, len(ancien), '{{QUANTITE_ARTICLE}}')
                remplacer(p, debut, fin, '{{DESIGNATION}}')
                # Fixer la colonne quantité à sa position d'origine (216 pt) :
                # une désignation courte ne doit pas changer de colonne.
                tabs = p.getElementsByTagName('w:tabs')[0]
                tab = doc.createElementNS('http://schemas.openxmlformats.org/wordprocessingml/2006/main', 'w:tab')
                tab.setAttribute('w:val', 'left')
                tab.setAttribute('w:pos', '4320')
                tabs.appendChild(tab)
                presentes.add(49)
            elif numero in ZONES:
                p = zone.getElementsByTagName('w:p')[0]
                remplacer(p, 0, len(texte(p)), '{{'+ZONES[numero]+'}}')
                presentes.add(numero)
        if presentes != set(ZONES) | {49}:
            raise ValueError('Zones CVI manquantes : ' + str((set(ZONES) | {49}) - presentes))
        if inclure_bl:
            preparer_bl(doc)
        sortie = BytesIO()
        with ZipFile(sortie, 'w') as z:
            for info in archive.infolist():
                z.writestr(info, doc.toxml(encoding='UTF-8') if info.filename == 'word/document.xml' else archive.read(info.filename))
        return sortie.getvalue()


def _ecrire_paragraphe(p, valeur):
    ancien = texte(p)
    if ancien:
        remplacer(p, 0, len(ancien), valeur)
    elif valeur:
        doc = p.ownerDocument
        run = doc.createElementNS('http://schemas.openxmlformats.org/wordprocessingml/2006/main', 'w:r')
        proprietes = p.getElementsByTagName('w:rPr')
        if proprietes:
            run.appendChild(copy.deepcopy(proprietes[0]))
        t = doc.createElementNS('http://schemas.openxmlformats.org/wordprocessingml/2006/main', 'w:t')
        t.appendChild(doc.createTextNode(valeur))
        run.appendChild(t)
        p.appendChild(run)


def _substituer(p, substitutions):
    # Modifier seulement les textes, préserver les tabulations entre colonnes.
    for ancien, nouveau in substitutions:
        contenu = texte(p)
        if contenu.count(ancien) != 1:
            raise ValueError('Repère BL non reconnu : ' + ancien)
        debut = contenu.index(ancien)
        remplacer(p, debut, debut+len(ancien), nouveau)


def preparer_bl(doc):
    zones = {int(s.getAttribute('id').rsplit(' ', 1)[-1]): s
             for s in doc.getElementsByTagName('v:shape')
             if s.getAttribute('id').startswith('Zone de texte ')}
    if not set(range(1, 26, 2)) <= zones.keys():
        raise ValueError('Les zones de la deuxième page BL sont incomplètes.')
    # Élargir uniquement les surfaces de texte à l'intérieur des cases du fond.
    # Voyage : même origine du texte. N° BL centré : même centre à 448,8 pt.
    zones[17].setAttribute('style', zones[17].getAttribute('style').replace('width:32.75pt', 'width:60pt'))
    zones[1].setAttribute('style', zones[1].getAttribute('style')
                          .replace('margin-left:417.1pt', 'margin-left:403.8pt').replace('width:63.4pt', 'width:90pt'))
    paragraphes = lambda numero: zones[numero].getElementsByTagName('w:p')
    simples = {17: '{{VOYAGE_BL}}', 1: '{{NUMERO_BL}}', 7: '{{FRET_PAYABLE_BL}}'}
    for numero, valeur in simples.items():
        _ecrire_paragraphe(paragraphes(numero)[0], valeur)
    _substituer(paragraphes(11)[0], [('JEBEL ALI', '{{LIEU_EMISSION_BL}}'),
                                   ('19 AUG 2025', '{{DATE_BL}}')])
    _substituer(paragraphes(5)[0], [('OEL SHRAVAN', '{{NAVIRE_BL}}'),
                                  ('JEBEL ALI', '{{PORT_CHARGEMENT_BL}}'),
                                  ('DAR ES SALAAM', '{{PORT_DECHARGEMENT_BL}}')])
    _substituer(paragraphes(9)[0], [('MRSU 8765546', '{{CONTENEUR}}'),
                                  ('10 X 40HC', '{{NOMBRE_CONTENEURS_BL}} X {{TYPE_CONTENEUR_BL}}'),
                                  ('1 800.00', '{{QUANTITE_BL}}'),
                                  ('240 000.000', '{{POIDS_BL}}'), ('3900', '{{TARE_BL}}')])
    descriptions = {
        0: '{{NOMBRE_CONTENEURS_BL}} X {{TYPE_CONTENEUR_BL}} CONTAINER',
        1: 'TOTAL {{QUANTITE_BL}} PACKAGES ONLY',
        2: 'TOTAL {{QUANTITE_BL_LETTRES}} ONLY', 3: 'PRODUIT',
        5: 'GOODS AS PER PACKING LIST', 6: '{{QUANTITE_BL}} {{EMBALLAGE_BL}}',
        9: 'TERMS {{CONDITIONS_FOB_BL}}',
        10: '({{QUANTITE_BL_LETTRES}})',
        12: 'INV.NO.{{NUMERO_FACTURE_BL}} DT. {{DATE_FACTURE_BL}}',
    }
    for i, p in enumerate(paragraphes(25)):
        if texte(p) or descriptions.get(i):
            _ecrire_paragraphe(p, descriptions.get(i, ''))
    for numero, prefixe in ((23, 'IMPORTATEUR'), (21, 'FOURNISSEUR'), (3, 'AGENT_BL')):
        for i, p in enumerate(paragraphes(numero)):
            if texte(p):
                _ecrire_paragraphe(p, '{{'+prefixe+'_LIGNE_'+str(i+1)+'}}')
    for i, p in enumerate(paragraphes(19)):
        _ecrire_paragraphe(p, '{{CONTENEUR_SCELLE_BL_'+str(i+1)+'}}' if i < 19 else '')
