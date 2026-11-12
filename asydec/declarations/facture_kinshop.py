"""Remplissage ciblé des deux Word KINSHOP fournis, sans reconstruire leur forme.

Les tableaux, lignes, dessins, variantes des zones de texte, styles, relations,
en-têtes, pieds de page et paramètres d'impression sont conservés.
"""
from datetime import datetime
from io import BytesIO
from pathlib import Path
import re
import sys
from zipfile import ZipFile

from asydec.declarations import factures as F, ajustement_word as A
from asydec.declarations.preparer_facture import paragraphes, texte, remplacer
from asydec.declarations.quantites_entieres import pu_texte
from asydec.declarations.nombres_lettres import dollars_us, nombre as en_lettres


def correspond(licence):
    nom = (licence.get('fournisseur') or {}).get('nom', '')
    return re.sub(r'[^A-Z0-9]', '', nom.upper()) == 'KINSHOPGENERALTRADINGFZE'


def modele(packing=False):
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))
    return base / 'ressources/factures/kinshop' / ('packing.docx' if packing else 'facture.docx')


def _ecrire(element, valeur):
    if texte(element):
        remplacer(element, 0, len(texte(element)), str(valeur))
    elif valeur:
        # Une cellule initialement vide reçoit du texte dans son paragraphe existant.
        ps = element.getElementsByTagNameNS(F.W, 'p')
        if not ps:
            raise ValueError('Le modèle KINSHOP ne comporte pas de paragraphe pour cette valeur.')
        p = ps[0]
        run = p.ownerDocument.createElementNS(F.W, 'w:r')
        t = p.ownerDocument.createElementNS(F.W, 'w:t')
        F._ecrire(t, str(valeur))
        run.appendChild(t)
        p.appendChild(run)


# Colonnes dessinées du modèle (twips depuis la marge gauche), mesurées sur le rendu Word :
# la colonne « Quantity » va de 6372 à 7106, alors que la cellule Word commence 6 mm plus à gauche.
QUANTITE_RETRAIT_GAUCHE = 640   # retrait qui place le nombre à droite du trait de la colonne
QUANTITE_TOTAL_DEBUT, QUANTITE_TOTAL_LARGEUR = 6396, 680
LARGEUR_BLOC_GAUCHE = 3884      # texte libre à gauche du tampon (colonne « PACKING… »)
PAYS_RDC = re.compile(r',?\s*(?:Congo,?\s*The\s+Democratic\s+Republic\s+of\s+the|(?:The\s+)?Democratic\s+Republic\s+of\s+(?:the\s+)?Congo'
                      r'|R\.?\s*D\.?\s*C(?:ongo)?\.?|DR\s*Congo)\s*$', re.I)


def _adresse_client(adresse):
    """(rue et ville, pays) : le pays occupe sa propre ligne comme dans le modèle (« RD.CONGO »)."""
    adresse = ' '.join(str(adresse or '').split())
    m = PAYS_RDC.search(adresse)
    if m:
        return adresse[:m.start()].strip(' ,'), 'RD.CONGO'
    if ',' in adresse:
        rue, pays = adresse.rsplit(',', 1)
        return rue.strip(' ,'), pays.strip()
    return adresse, ''


def _cadrer(p, gauche=None, droite=None, alignement=None):
    A.cadrer(p, gauche, droite, alignement)


def _saut_avant(p, mot):
    """Place « mot » en début de ligne (ex. « Other Reference(s) » après une date raccourcie)."""
    for t in p.getElementsByTagNameNS(F.W, 't'):
        contenu = F._texte(t)
        i = contenu.find(mot)
        if i < 0:
            continue
        run = t.parentNode
        if contenu[:i].strip():
            copie = run.cloneNode(True)
            for n in [n for n in copie.childNodes if n.localName == 't'][1:]:
                copie.removeChild(n)
            F._ecrire(next(n for n in copie.childNodes if n.localName == 't'), contenu[:i])
            run.parentNode.insertBefore(copie, run)
            F._ecrire(t, contenu[i:])
        saut = p.ownerDocument.createElementNS(F.W, 'w:r')
        saut.appendChild(p.ownerDocument.createElementNS(F.W, 'w:br'))
        run.parentNode.insertBefore(saut, run)
        return


def _section_suivante(p):
    n = p
    while n is not None:
        if n.localName == 'p' and n.getElementsByTagNameNS(F.W, 'sectPr'):
            return n.getElementsByTagNameNS(F.W, 'sectPr')[0]
        n = n.nextSibling
    return None


def _elargir_total_quantite(p):
    """Élargit la colonne de section du total des quantités jusqu'aux traits dessinés."""
    sect = _section_suivante(p)
    cols = [c for c in sect.getElementsByTagNameNS(F.W, 'col')] if sect is not None else []
    if len(cols) != 4:
        return
    l0, e0 = int(cols[0].getAttribute('w:w')), int(cols[0].getAttribute('w:space') or 0)
    l1, e1 = int(cols[1].getAttribute('w:w')), int(cols[1].getAttribute('w:space') or 0)
    debut_suivante = l0 + e0 + l1 + e1
    if not l0 < QUANTITE_TOTAL_DEBUT < QUANTITE_TOTAL_DEBUT + QUANTITE_TOTAL_LARGEUR < debut_suivante:
        return
    cols[0].setAttribute('w:space', str(QUANTITE_TOTAL_DEBUT - l0))
    cols[1].setAttribute('w:w', str(QUANTITE_TOTAL_LARGEUR))
    cols[1].setAttribute('w:space', str(debut_suivante - QUANTITE_TOTAL_DEBUT - QUANTITE_TOTAL_LARGEUR))
    _cadrer(p, gauche=0, alignement='center')


def _voisin(n, sens):
    n = getattr(n, sens)
    while n is not None and n.localName != 'p':
        n = getattr(n, sens)
    return n


def _saut_colonne(p):
    return next((r for r in p.getElementsByTagNameNS(F.W, 'r')
                 if any(b.getAttribute('w:type') == 'column' for b in r.getElementsByTagNameNS(F.W, 'br'))), None)


def _deplacer_nom_consignataire(doc, styles, nom, rue, une_ligne):
    """Nom trop long pour l'étroite colonne « Consignee » : il passe en tête du bloc d'adresse, plus
    large, dont la rue tient alors sur une ligne. Le bloc garde ainsi sa hauteur et ses traits."""
    nom = ' '.join(str(nom or '').split())
    candidats = [p for p in paragraphes(doc) if texte(p) == nom and A._style(p, styles).get('sz') is None]
    if not nom or not candidats:
        return
    p = candidats[0]
    largeur = A.largeurs(doc, styles).get(p)
    if not largeur or A.nombre_lignes(p, largeur, styles) <= 1:
        return
    fin = p
    while fin is not None and not fin.getElementsByTagNameNS(F.W, 'sectPr'):
        fin = _voisin(fin, 'nextSibling')
    adresse = _voisin(fin, 'nextSibling') if fin is not None else None
    if adresse is None or texte(adresse) != rue:
        return
    adresse.parentNode.insertBefore(p, adresse)
    _cadrer(adresse, droite=0)
    une_ligne.add(adresse)


DECALAGE_TOTAUX_PACKING = 440  # twips : la section des totaux de la packing list commence 22 pt plus haut
ESPACE_APRES_POIDS = 315       # twips : le bloc « PACKING… / Signature » retrouve la hauteur de la facture


def _espacer(p, supplement):
    espacement = A.propriete_paragraphe(p, 'spacing')
    espacement.setAttribute('w:before', str(int(espacement.getAttribute('w:before') or 0) + supplement))


def _aligner_totaux_packing(p_quantite):
    """Packing list : la section des totaux reprend exactement la disposition de la facture
    (poids en lettres à gauche, total des quantités, « TOTAL » et poids sur une même ligne, dans les
    cases dessinées). Le modèle d'origine les plaçait de part et d'autre des traits."""
    precedent = _voisin(p_quantite, 'previousSibling')
    premier = _voisin(precedent, 'previousSibling') if precedent is not None else None
    total = _voisin(p_quantite, 'nextSibling')
    espaceur = _voisin(total, 'nextSibling') if total is not None else None
    vide = _voisin(espaceur, 'nextSibling') if espaceur is not None else None
    valeur = _voisin(vide, 'nextSibling') if vide is not None else None
    fin = _voisin(valeur, 'nextSibling') if valeur is not None else None
    poids = _voisin(fin, 'nextSibling') if fin is not None else None
    saut = _saut_colonne(p_quantite)
    if (None in (premier, precedent, total, espaceur, vide, valeur, fin, poids, saut)
            or texte(premier).strip() or _saut_colonne(premier) is not None
            or texte(precedent).strip() or _saut_colonne(precedent) is None
            or texte(total).strip() != 'TOTAL' or _saut_colonne(espaceur) is None or texte(espaceur).strip()
            or texte(vide).strip() or not texte(valeur).strip()
            or not fin.getElementsByTagNameNS(F.W, 'sectPr') or 'Chargeable' not in texte(poids)):
        return False
    parent = p_quantite.parentNode
    parent.insertBefore(poids, precedent)          # colonne 1, comme « Amount Chargeable »
    _cadrer(poids, droite=0)
    parent.removeChild(precedent)
    saut.parentNode.removeChild(saut)
    p_quantite.insertBefore(saut, next((r for r in p_quantite.childNodes if r.localName == 'r'), None))
    parent.insertBefore(espaceur.cloneNode(True), total)
    parent.removeChild(vide)
    for p in (premier, p_quantite, _voisin(p_quantite, 'nextSibling'), espaceur):
        _espacer(p, DECALAGE_TOTAUX_PACKING)
    # Section suivante (« PACKING… » | « Signature ») : la ligne du poids a quitté son flux ;
    # ses deux colonnes descendent d'autant pour rester dans leurs cases.
    suivant = _voisin(fin, 'nextSibling')
    if suivant is not None:
        _espacer(suivant, ESPACE_APRES_POIDS)
    n = suivant
    while n is not None and not n.getElementsByTagNameNS(F.W, 'sectPr'):
        if _saut_colonne(n) is not None:
            colonne2 = _voisin(n, 'nextSibling')
            if colonne2 is not None:
                _espacer(colonne2, ESPACE_APRES_POIDS)
            break
        n = _voisin(n, 'nextSibling')
    return True


def _dessins_derriere_le_texte(doc):
    """Cadre, tampon et signature passent sous le texte : aucune valeur ne peut être masquée."""
    for ancre in doc.getElementsByTagNameNS('http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing', 'anchor'):
        ancre.setAttribute('behindDoc', '1')
    for groupe in doc.getElementsByTagNameNS('urn:schemas-microsoft-com:vml', 'group'):
        groupe.setAttribute('style', re.sub(r'z-index:\s*\d+', 'z-index:-251658240', groupe.getAttribute('style')))


def _cellules(ligne):
    return [c for c in ligne.childNodes if c.localName == 'tc']


def _tables_articles(doc):
    for table in doc.getElementsByTagNameNS(F.W, 'tbl'):
        lignes = [r for r in table.childNodes if r.localName == 'tr']
        if lignes and len(_cellules(lignes[0])) == 4 and 'TVS HLX' in texte(_cellules(lignes[0])[0]):
            yield lignes


def creer(licence, donnees, packing=False):
    source = modele(packing).read_bytes()
    archive, parties = F._parties(source)
    try:
        doc = parties['word/document.xml']
        styles = A.styles(archive.read('word/styles.xml') if 'word/styles.xml' in archive.namelist() else None)
        origine = A.instantane(doc, styles, paragraphes(doc))
        une_ligne = set()
        quantite_totale = None
        tableaux = list(_tables_articles(doc))
        if not tableaux:
            raise ValueError('Le tableau d’articles du modèle KINSHOP est introuvable.')
        for lignes in tableaux:
            if len(donnees['lignes']) > len(lignes):
                raise ValueError(f"Votre modèle KINSHOP comporte {len(lignes)} lignes d’articles, "
                                 f"mais cette facture en contient {len(donnees['lignes'])}. "
                                 'Fournissez un modèle avec suffisamment de lignes pour conserver sa forme.')
            for i, ligne in enumerate(lignes):
                cellules = _cellules(ligne)
                if i < len(donnees['lignes']):
                    article = donnees['lignes'][i]
                    q = article['quantite']
                    quantite = f'{q:,.0f}' if q == q.to_integral_value() else f'{q:,.3f}'
                    valeurs = [article['designation'], quantite,
                               '' if packing else '$ ' + pu_texte(article['prix_unitaire']),
                               f"{article['poids']:,.2f}" if packing else f"$ {article['valeur']:,.2f}"]
                else:
                    valeurs = [''] * 4
                for colonne, (cellule, valeur) in enumerate(zip(cellules, valeurs)):
                    _ecrire(cellule, valeur)
                    contenus = [p for p in cellule.childNodes if p.localName == 'p']
                    if colonne > 0:
                        une_ligne.update(contenus)  # quantité, taux et montant : toujours une ligne
                    if colonne == 1:
                        for p in contenus:
                            _cadrer(p, gauche=QUANTITE_RETRAIT_GAUCHE, droite=0, alignement='center')
        mois = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')
        jour = datetime.strptime(donnees['date'], '%d/%m/%Y')
        date = f'{jour.day:02d}-{mois[jour.month-1]}-{jour.year}'
        expedition = (f"All {donnees['total_parts']} parts" if donnees['part'] == 'global'
                      else f"Part {donnees['part']} of {donnees['total_parts']}")
        profil = (licence.get('fournisseur') or {}).get('facturation') or {}
        client = licence.get('soussigne') or {}
        rue, pays = _adresse_client(client.get('adresse'))
        # Port de chargement du dossier (Infos BL), le même que sur le BL et le CVI.
        from asydec.declarations import cvi as cvi_dossier, coherence_transport
        port = coherence_transport.normaliser_port(cvi_dossier.port_chargement(licence))
        lieu = coherence_transport.lieu_chargement(port)
        for p in paragraphes(doc):
            s = texte(p)
            if 'ORD0000013709' in s:
                _ecrire(p, f"{donnees['numero']} & {date} / {expedition}")
            elif 'Email Dtd:' in s:
                # Retire uniquement les références propres à l’ancienne opération.
                for ancien, nouveau in [('14-06-2025', profil.get('date_commande', '—')),
                                         ('22060190', profil.get('commande', '—'))]:
                    for m in reversed(list(re.finditer(re.escape(ancien), texte(p)))):
                        remplacer(p, m.start(), m.end(), nouveau)
                if 'Other' in texte(p):
                    _saut_avant(p, 'Other')
            elif s.strip() == '22060190':
                _ecrire(p, profil.get('reference_exportateur', '—'))
            elif s.endswith('70504'):
                remplacer(p, len(s)-5, len(s), profil.get('reference_exportateur', '—'))
            elif s.strip() == 'CHENNAI, INDIA' and lieu and lieu != 'CHENNAI, INDIA':
                _ecrire(p, lieu)
                une_ligne.add(p)
            elif s.startswith('FOB CHENNAI, INDIA') and lieu and lieu != 'CHENNAI, INDIA':
                m = re.search(re.escape('CHENNAI, INDIA'), s)
                remplacer(p, m.start(), m.end(), lieu)
            elif s.strip() == 'ETS KATANGA TVS' and client.get('nom'):
                _ecrire(p, ' '.join(client['nom'].split()))
                une_ligne.add(p)
            elif s.strip() == 'AV.INDUSTRIEL No.: 2580 LUBUMBASHI' and client.get('adresse'):
                _ecrire(p, rue)
            elif s.strip() == 'RD.CONGO' and client.get('adresse'):
                _ecrire(p, pays)
                une_ligne.add(p)
            elif s.strip() == '1,800':
                q = donnees['quantites']
                _ecrire(p, f'{q:,.0f}' if q == q.to_integral_value() else f'{q:,.3f}')
                _elargir_total_quantite(p)
                quantite_totale = p
                une_ligne.add(p)
            elif s.strip() in ('1,263,600.00', '24,000.00'):
                _ecrire(p, f"{donnees['poids'] if packing else donnees['fob']:,.2f}")
                une_ligne.add(p)
            elif s.startswith('Amount Chargeable (US DOLLAR)'):
                _ecrire(p, 'Amount Chargeable (US DOLLAR) ' + dollars_us(donnees['fob']))
                une_ligne.add(p)
            elif 'Height' in s:
                if 'Chargeable' in s:
                    _ecrire(p, 'Weight Chargeable (KGS) ' + en_lettres(donnees['poids']) + ' KILOGRAMS')
                    # Reste à gauche du tampon, comme le bloc « PACKING… » situé dessous.
                    actuelle = A.largeurs(doc, styles).get(p)
                    if actuelle and actuelle > LARGEUR_BLOC_GAUCHE:
                        _cadrer(p, droite=A.retraits(p, styles)[1] + actuelle - LARGEUR_BLOC_GAUCHE)
                    une_ligne.add(p)
                else:
                    _ecrire(p, s.replace('Height', 'Weight'))
        if packing and quantite_totale is not None:
            _aligner_totaux_packing(quantite_totale)
        if client.get('nom') and client.get('adresse'):
            _deplacer_nom_consignataire(doc, styles, client['nom'], rue, une_ligne)
        A.respecter(doc, styles, origine, une_ligne, taille_min=11)
        _dessins_derriere_le_texte(doc)
        sortie = BytesIO()
        with ZipFile(sortie, 'w') as cible:
            for info in archive.infolist():
                cible.writestr(info, F.serialiser(doc) if info.filename == 'word/document.xml' else archive.read(info.filename))
        return sortie.getvalue()
    finally:
        archive.close()
