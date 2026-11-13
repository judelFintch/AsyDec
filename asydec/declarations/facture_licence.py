"""Étape 5 du traitement licence : une facture et une packing list par part, en deux fichiers séparés,
plus une facture et une packing list globales qui totalisent toutes les parts.

Le numéro de facture est celui de la licence suivi du numéro de part (ORD0000013709-1,
ORD0000013709-2…) ; la facture globale porte le numéro de la licence seul (ORD0000013709).
La date est celle de la facture sur la licence.
Le modèle Word choisi garde sa structure, ses polices et ses dessins : seuls les textes
variables (articles, quantités, prix, poids, totaux, numéro, date, plaque, manifeste)
sont remplacés. Les lignes d'articles en trop sont vidées, jamais supprimées.
"""
import copy
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
import re
from xml.dom import minidom
from zipfile import ZipFile

from asydec.declarations import factures as F
from asydec.declarations import mise_a_jour_repartitions
from asydec.declarations.nombres_lettres import nombre as en_lettres
from asydec.declarations.preparer_facture import (preparer, preparer_lettres,
                                                  preparer_manifeste, preparer_plaque, remplacer, texte)
from asydec.formats import nombre

FACTURE, PACKING_LIST = 'facture', 'packing list'
INDICE = re.compile(r'(COLIS|FOB|POIDS|PRIX_UNITAIRE)_([1-9][0-9]*)')


def _decimal(valeur):
    return Decimal(str(valeur).replace(' ', '').replace(' ', '').replace(',', '.'))


def repartir_poids(quantites, total):
    """Poids entiers proportionnels aux quantités ; le reste va aux plus grandes fractions,
    pour que la somme soit exactement le poids de la part."""
    quantites = [_decimal(q) for q in quantites]
    somme = sum(quantites, Decimal(0))
    total = int(total)
    if somme <= 0:
        raise ValueError('Les quantités de la part sont nulles : impossible de répartir le poids.')
    exacts = [q * total / somme for q in quantites]
    poids = [int(e) for e in exacts]
    ordre = sorted(range(len(exacts)), key=lambda i: (exacts[i] - poids[i], quantites[i]), reverse=True)
    for i in ordre[:total - sum(poids)]:
        poids[i] += 1
    return poids


def parts(licence):
    resultat = (licence.get('repartition') or {}).get('parts') or []
    if not resultat:
        raise ValueError('Validez la répartition avant de préparer les factures.')
    return resultat


def lignes_part(part):
    """Articles d'une part : désignation, quantité, prix unitaire, valeur et poids."""
    articles = part.get('articles') or []
    if not articles:
        raise ValueError(f"Les quantités de la part {part.get('numero')} ne sont pas calculées : refaites la répartition.")
    poids = repartir_poids([a['quantite'] for a in articles], part.get('poids_kg') or 0)
    return [dict(designation=' '.join(str(a.get('designation', '')).split()), quantite=_decimal(a['quantite']),
                 prix_unitaire=_decimal(a['prix_unitaire']), valeur=_decimal(a['valeur']), poids=p)
            for a, p in zip(articles, poids)]


def avertissements_quantites(licence):
    """Signale les fractions de pièces sans altérer les données de licence."""
    from asydec.declarations.facture_simple import _unite
    alertes = []
    for part in parts(licence):
        for ligne in donnees_part(licence, part)['lignes']:
            if _unite(ligne.get('unite', '')) == 'PCS' and ligne['quantite'] != ligne['quantite'].to_integral_value():
                alertes.append(f"Part {part['numero']} : {ligne['designation']} — {ligne['quantite']} PCS.")
    return alertes


def _pu_fr(prix):
    """PU à la française, décimales utiles seulement (ex. « 701,754386 », « 702,00 »)."""
    from asydec.declarations.quantites_entieres import pu_texte
    return pu_texte(prix, ' ').replace('.', ',')


def _quantite(q):
    return nombre(q) if q == q.to_integral_value() else nombre(float(q), 3)


def references_facture(licence):
    """(numéro, date JJ/MM/AAAA) de la facture portée par la licence ; ValueError si absents."""
    numero = ''.join(str(licence.get('numero_facture') or '').split())
    date = str(licence.get('date_facture') or '').strip()
    if not numero or not date:
        raise ValueError('Le numéro et la date de facture de la licence sont requis.')
    try:
        datetime.strptime(date, '%d/%m/%Y')
    except ValueError:
        raise ValueError('Date de facture de la licence invalide : format JJ/MM/AAAA attendu.') from None
    return numero, date


def numero_part(numero_facture, part):
    return f"{numero_facture}-{part['numero']}"


def _tables_articles(doc):
    """Tableaux facture / packing list : en-tête à 5 colonnes avec DESCRIPTION, lignes numérotées."""
    for table in doc.getElementsByTagNameNS(F.W, 'tbl'):
        lignes = [n for n in table.childNodes if n.localName == 'tr']
        if not lignes:
            continue
        cellules = lambda r: [n for n in r.childNodes if n.localName == 'tc']
        entete = [texte(c).strip().upper() for c in cellules(lignes[0])]
        if len(entete) != 5 or 'DESCRIPTION' not in entete[1]:
            continue
        articles = [cellules(r) for r in lignes[1:] if len(cellules(r)) == 5 and texte(cellules(r)[0]).strip().isdigit()]
        if articles:
            yield articles


def adapter_tableaux(contenu, designations):
    """Écrit les désignations de la part et vide les lignes d'articles en trop.

    Renvoie (contenu, nombre de lignes d'articles du modèle) ; 0 si aucun tableau reconnu.
    """
    archive, parties = F._parties(contenu)
    try:
        doc = parties['word/document.xml']
        capacites = []
        for lignes in _tables_articles(doc):
            capacites.append(len(lignes))
            if len(lignes) < len(designations):
                raise ValueError(f'Le modèle de facture prévoit {len(lignes)} ligne(s) d’articles ; '
                                 f'la part en contient {len(designations)}. Choisissez un modèle avec assez de lignes.')
            for i, cellules in enumerate(lignes):
                if i < len(designations):
                    remplacer(cellules[1], 0, len(texte(cellules[1])), designations[i])
                else:
                    for cellule in cellules:
                        remplacer(cellule, 0, len(texte(cellule)), '')
        if len(set(capacites)) > 1:
            raise ValueError('La facture et la packing list du modèle n’ont pas le même nombre de lignes d’articles.')
        sortie = BytesIO()
        with ZipFile(sortie, 'w') as cible:
            for info in archive.infolist():
                cible.writestr(info, F.serialiser(doc) if info.filename == 'word/document.xml' else archive.read(info.filename))
        return sortie.getvalue(), (capacites[0] if capacites else 0)
    finally:
        archive.close()


def _type_tableau(table):
    """'facture', 'packing list' ou None pour un tableau d'articles du modèle."""
    lignes = [n for n in table.childNodes if n.localName == 'tr']
    cellules = lambda r: [n for n in r.childNodes if n.localName == 'tc']
    if not lignes or len(cellules(lignes[0])) != 5:
        return None
    entete = [texte(c).strip().upper() for c in cellules(lignes[0])]
    if 'DESCRIPTION' not in entete[1]:
        return None
    articles = [cellules(r) for r in lignes[1:] if len(cellules(r)) == 5 and texte(cellules(r)[0]).strip().isdigit()]
    if 'WEIGHT' in entete[4] or 'POIDS' in entete[4] or (articles and re.search(r'(?i)\bKGS?\b', texte(articles[0][4]))):
        return PACKING_LIST
    return FACTURE


def _saut(element):
    """Nature du saut de page porté par un élément du corps : 'br', 'avant', 'section' ou None."""
    if element.localName != 'p':
        return None
    if any(_est_saut_page(b) for b in element.getElementsByTagNameNS(F.W, 'br')):
        return 'br'
    for ppr in (n for n in element.childNodes if n.localName == 'pPr'):
        if any(n.localName == 'sectPr' for n in ppr.childNodes):
            return 'section'
        if any(n.localName == 'pageBreakBefore' for n in ppr.childNodes):
            return 'avant'
    return None


def _enfants(doc):
    corps = doc.getElementsByTagNameNS(F.W, 'body')[0]
    return corps, [n for n in corps.childNodes if n.nodeType == n.ELEMENT_NODE and n.localName != 'sectPr']


def _point_de_coupe(doc):
    """(indice, nature, facture_d_abord) : où commence le second document dans le corps du Word."""
    corps, enfants = _enfants(doc)
    positions = {}
    for table in doc.getElementsByTagNameNS(F.W, 'tbl'):
        genre = _type_tableau(table)
        if genre and genre not in positions:
            haut = table
            while haut.parentNode is not corps:
                haut = haut.parentNode
            positions[genre] = enfants.index(haut)
    if set(positions) != {FACTURE, PACKING_LIST}:
        raise ValueError('Le modèle doit contenir le tableau de la facture et celui de la packing list.')
    premier, second = sorted(positions.values())
    if premier == second:
        raise ValueError('La facture et la packing list du modèle sont dans le même bloc : impossible de les séparer.')
    facture_d_abord = positions[FACTURE] == premier
    sauts = [(k, _saut(enfants[k])) for k in range(premier + 1, second + 1) if _saut(enfants[k])]
    if sauts:
        return sauts[-1] + (facture_d_abord,)
    second_titre = 'PACKING' if facture_d_abord else 'INVOICE'
    for k in range(premier + 1, second + 1):
        if second_titre in texte(enfants[k]).upper():
            return k, 'titre', facture_d_abord
    raise ValueError('Impossible de séparer la facture et la packing list du modèle : '
                     'ajoutez un saut de page entre les deux dans le Word.')


def _est_saut_page(n):
    return n.localName == 'br' and (n.getAttributeNS(F.W, 'type') == 'page' or n.getAttribute('w:type') == 'page')


def _couper_paragraphe(paragraphe, garder_avant):
    """Garde ce qui précède (garder_avant) ou ce qui suit le saut de page du paragraphe ; le saut disparaît.
    Renvoie True s'il reste du texte ou un dessin."""
    runs = list(paragraphe.getElementsByTagNameNS(F.W, 'r'))
    indice = next(i for i, r in enumerate(runs) if any(_est_saut_page(n) for n in r.childNodes))
    for i, run in enumerate(runs):
        if (i > indice) if garder_avant else (i < indice):
            run.parentNode.removeChild(run)
    contenu = [n for n in runs[indice].childNodes if n.nodeType == n.ELEMENT_NODE and n.localName != 'rPr']
    position = next(i for i, n in enumerate(contenu) if _est_saut_page(n))
    for i, n in enumerate(contenu):
        if i == position or ((i > position) if garder_avant else (i < position)):
            runs[indice].removeChild(n)
    return bool(texte(paragraphe).strip() or paragraphe.getElementsByTagNameNS(F.W, 'drawing')
                or paragraphe.getElementsByTagName('w:pict'))


def separer(contenu):
    """Coupe le Word rempli en deux documents (facture, packing list) au début du second.

    Chaque moitié garde sa mise en page, ses styles, en-têtes et pieds de page ; rien n'est redessiné.
    """
    archive, parties = F._parties(contenu)
    try:
        source = F.serialiser(parties['word/document.xml'])
        indice, nature, facture_d_abord = _point_de_coupe(parties['word/document.xml'])
        moities = []
        for avant in (True, False):
            doc = minidom.parseString(source)
            corps, enfants = _enfants(doc)
            if nature == 'br':
                garder = range(0, indice + 1) if avant else range(indice, len(enfants))
            elif nature == 'section':
                garder = range(0, indice + 1) if avant else range(indice + 1, len(enfants))
            else:  # saut avant le paragraphe, ou titre du second document
                garder = range(0, indice) if avant else range(indice, len(enfants))
            for k, enfant in enumerate(enfants):
                if k not in garder:
                    corps.removeChild(enfant)
            frontiere = enfants[indice]
            if nature == 'br' and not _couper_paragraphe(frontiere, avant):
                corps.removeChild(frontiere)  # paragraphe qui ne portait que le saut
            elif nature == 'avant' and not avant:
                for ppr in (n for n in frontiere.childNodes if n.localName == 'pPr'):
                    for n in [n for n in ppr.childNodes if n.localName == 'pageBreakBefore']:
                        ppr.removeChild(n)
            elif nature == 'section' and avant:
                # La section de la première moitié devient la mise en page de tout son document.
                ppr = next(n for n in frontiere.childNodes if n.localName == 'pPr')
                section = next(n for n in ppr.childNodes if n.localName == 'sectPr')
                ppr.removeChild(section)
                for ancienne in [n for n in corps.childNodes if n.localName == 'sectPr']:
                    corps.removeChild(ancienne)
                corps.appendChild(section)
            sortie = BytesIO()
            with ZipFile(sortie, 'w') as cible:
                for info in archive.infolist():
                    contenu_partie = (F.serialiser(doc) if info.filename == 'word/document.xml'
                                      else archive.read(info.filename))
                    # Copie : writestr modifie le ZipInfo, relu pour la seconde moitié.
                    cible.writestr(copy.copy(info), contenu_partie)
            moities.append(sortie.getvalue())
        return tuple(moities) if facture_d_abord else (moities[1], moities[0])
    finally:
        archive.close()


def preparer_modele(contenu):
    """Balise un Word de facture brut (ou déjà balisé) sans en changer la structure."""
    try:
        F.inspecter(contenu)
    except ValueError:
        try:
            contenu, _ = preparer(contenu)
        except ValueError as exc:
            raise ValueError('Modèle non reconnu : il faut une facture et une packing list en tableaux '
                             '(N°, Description, Quantité, Prix ou Poids, Total) avec les mêmes articles.') from exc
    return preparer_lettres(preparer_manifeste(preparer_plaque(contenu)))


def _prix_au_kg(contenu):
    from asydec.declarations.preparer_facture import base_prix
    try:
        return base_prix(contenu) == 'kg'
    except (ValueError, KeyError):
        return False


def donnees_part(licence, part):
    """Données d'une part communes aux deux méthodes (modèle fourni ou facture simple AsyDec)."""
    numero_facture, date = references_facture(licence)
    lignes = lignes_part(part)
    produits = licence.get('produits') or []
    for ligne, article in zip(lignes, part.get('articles') or []):
        indice = int(article.get('article') or 0) - 1
        produit = produits[indice] if 0 <= indice < len(produits) else {}
        ligne.update(unite=article.get('unite') or produit.get('unite', ''),
                     origine=produit.get('pays_origine', ''), tarif=produit.get('tarif_douanier', ''),
                     devise=produit.get('devise') or 'USD')
    informations = part.get('informations_declaration') or licence.get('informations_declaration') or {}
    return dict(numero=numero_part(numero_facture, part), date=date, part=part['numero'],
                total_parts=len(parts(licence)), lignes=lignes,
                fob=sum((l['valeur'] for l in lignes), Decimal(0)), poids=sum(l['poids'] for l in lignes),
                quantites=sum((l['quantite'] for l in lignes), Decimal(0)),
                plaque=part.get('plaque') or informations.get('plaque') or '',
                manifeste=informations.get('manifeste') or '',
                conteneur=part.get('conteneur', ''), scelle=part.get('scelle', ''))


GLOBALE = 'global'


def _cle_article(ligne, article):
    return ('article', int(article['article'])) if article.get('article') else ('designation', ligne['designation'])


def donnees_globale(licence):
    """Facture globale : les articles de toutes les parts additionnés (quantités, FOB, poids).
    Le poids de chaque article est la somme des poids des packing lists des parts, pour que tout concorde."""
    numero_facture, date = references_facture(licence)
    toutes = parts(licence)
    cumul = {}
    for part in toutes:
        for ligne, article in zip(donnees_part(licence, part)['lignes'], part.get('articles') or []):
            cle = _cle_article(ligne, article)
            if cle not in cumul:
                cumul[cle] = dict(ligne, prix=[ligne['prix_unitaire']])
            else:
                total = cumul[cle]
                total.update(quantite=total['quantite'] + ligne['quantite'], valeur=total['valeur'] + ligne['valeur'],
                             poids=total['poids'] + ligne['poids'], prix=total['prix'] + [ligne['prix_unitaire']])
    lignes = list(cumul.values())
    for ligne in lignes:
        # Prix unitaire moyen seulement si les parts n'ont pas toutes le même prix
        # (un écart d'arrondi absorbé dans la valeur ne change pas le prix de la licence).
        if len(set(ligne.pop('prix'))) > 1 and ligne['quantite']:
            from asydec.declarations.quantites_entieres import pu_exact
            ligne['prix_unitaire'] = (pu_exact(ligne['quantite'], ligne['valeur'])
                                      or (ligne['valeur'] / ligne['quantite']).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))

    def distincts(valeurs):
        return ' - '.join(dict.fromkeys(v for v in valeurs if v))
    informations = [p.get('informations_declaration') or licence.get('informations_declaration') or {} for p in toutes]
    return dict(numero=numero_facture, date=date, part=GLOBALE, total_parts=len(toutes), lignes=lignes,
                fob=sum((l['valeur'] for l in lignes), Decimal(0)), poids=sum(l['poids'] for l in lignes),
                quantites=sum((l['quantite'] for l in lignes), Decimal(0)),
                plaque=distincts(p.get('plaque') or i.get('plaque') for p, i in zip(toutes, informations)),
                manifeste=distincts(i.get('manifeste') for i in informations),
                conteneur=distincts(p.get('conteneur') for p in toutes),
                scelle=distincts(p.get('scelle') for p in toutes))


def actualiser_coordonnees(contenu, licence):
    """Remplace les blocs commerciaux fixes du modèle par les parties de la licence.

    Les paragraphes, polices et dessins restent en place. Les lignes anciennes d'un
    bloc reconnu sont vidées, même si la licence n'a pas de contact correspondant.
    """
    from asydec.declarations.preparer_facture import paragraphes
    fournisseur = licence.get('fournisseur') or {}
    client = licence.get('soussigne') or {}
    libelle_client = re.compile(r'(?i)^\s*(?:consignee|consignée|invoice to|bill to|client|destinataire)\s*[:：]?\s*')
    limite = re.compile(r'(?i)^(?:INVOICE\b|PACKING\b|FACTURE\b|DATE\b|INV\b|N[°º]?\s*$|DESCRIPTION\b|'
                        r'GOODS\b|QUANTITY\b|QTY\b|BUYER\b|NOTIFY\b|COUNTRY\b|TERMS\b|EXPORTER\b|'
                        r'\{\{|TOTAL\b|SIGNATURE\b|FOR\s)')

    def bloc(partie):
        return '\n'.join(str(partie.get(c) or '').strip() for c in ('nom', 'adresse', 'telephone', 'email')
                         if str(partie.get(c) or '').strip())

    def ecrire(p, valeur):
        s = texte(p)
        if s:
            remplacer(p, 0, len(s), valeur)

    archive, parties = F._parties(contenu)
    try:
        for doc in parties.values():
            ps = [p for p in paragraphes(doc) if texte(p).strip()]
            occupes = set()
            for i, p in enumerate(ps):
                m = libelle_client.match(texte(p))
                if not m:
                    continue
                groupe = []
                for suivant in ps[i + 1:]:
                    s = texte(suivant).strip()
                    if libelle_client.match(s) or limite.match(s):
                        break
                    groupe.append(suivant)
                # Le nom peut suivre le libellé dans le même paragraphe.
                inline = bool(texte(p)[m.end():].strip())
                if inline:
                    remplacer(p, m.end(), len(texte(p)), bloc(client))
                elif groupe:
                    ecrire(groupe[0], bloc(client))
                for ancien in groupe if inline else groupe[1:]:
                    ecrire(ancien, '')
                occupes.update([p, *groupe])

            # En-tête fournisseur : avant le titre ou les références commerciales.
            entete = []
            for p in ps:
                if p in occupes or limite.match(texte(p).strip()):
                    break
                entete.append(p)
            if entete:
                anciens = {texte(p).strip() for p in entete}
                premier = texte(entete[0]).strip()
                ecrire(entete[0], bloc(fournisseur))
                for ancien in entete[1:]:
                    ecrire(ancien, '')
                # Même en-tête répété sur la packing list ou dans un dessin de secours.
                for p in ps:
                    if p not in entete and p not in occupes and texte(p).strip() in anciens:
                        ecrire(p, bloc(fournisseur) if texte(p).strip() == premier else '')
            # Champs explicites utilisables aussi dans les en-têtes/pieds de page.
            valeurs = {'FOURNISSEUR': fournisseur.get('nom', ''), 'ADRESSE_FOURNISSEUR': fournisseur.get('adresse', ''),
                       'TELEPHONE_FOURNISSEUR': fournisseur.get('telephone', ''), 'EMAIL_FOURNISSEUR': fournisseur.get('email', ''),
                       'IMPORTATEUR': client.get('nom', ''), 'ADRESSE_IMPORTATEUR': client.get('adresse', ''),
                       'TELEPHONE_IMPORTATEUR': client.get('telephone', ''), 'EMAIL_IMPORTATEUR': client.get('email', '')}
            for p in paragraphes(doc):
                for cle, valeur in valeurs.items():
                    for m in reversed(list(re.finditer(re.escape('{{' + cle + '}}'), texte(p)))):
                        remplacer(p, m.start(), m.end(), str(valeur or ''))
                # Word attend des sauts de ligne explicites dans les blocs multiligne.
                for t in list(p.getElementsByTagNameNS(F.W, 't')):
                    s = F._texte(t)
                    if '\n' not in s:
                        continue
                    lignes = s.splitlines()
                    F._ecrire(t, lignes[0] if lignes else '')
                    precedent = t
                    for ligne in lignes[1:]:
                        br = doc.createElementNS(F.W, 'w:br')
                        nouveau = t.cloneNode(False)
                        F._ecrire(nouveau, ligne)
                        t.parentNode.insertBefore(br, precedent.nextSibling)
                        t.parentNode.insertBefore(nouveau, br.nextSibling)
                        precedent = nouveau
        sortie = BytesIO()
        with ZipFile(sortie, 'w') as cible:
            for info in archive.infolist():
                cible.writestr(info, F.serialiser(parties[info.filename]) if info.filename in parties
                               else archive.read(info.filename))
        return sortie.getvalue()
    finally:
        archive.close()


def completer_entete_fournisseur(contenu, licence):
    """Garantit un bloc fournisseur complet dans chaque document séparé.

    Certains modèles commencent directement par INVOICE, ou ne portent leur
    identité que dans un logo. Le bloc est alors ajouté avant le corps du document.
    """
    from asydec.declarations.preparer_facture import paragraphes
    fournisseur = licence.get('fournisseur') or {}
    lignes = [str(fournisseur.get(c) or '').strip() for c in ('nom', 'adresse', 'telephone', 'email')]
    lignes = [s for s in lignes if s]
    if not lignes:
        return contenu
    archive, parties = F._parties(contenu)
    try:
        doc = parties['word/document.xml']
        normaliser = lambda s: ' '.join(s.split()).casefold()
        # Une identité complète dans un vrai en-tête Word suffit également.
        for nom, partie in parties.items():
            if nom.startswith('word/footer'):
                continue
            debut = []
            for p in paragraphes(partie):
                textes = ' '.join(F._texte(t) for t in p.getElementsByTagNameNS(F.W, 't'))
                if all(normaliser(ligne) in normaliser(textes) for ligne in lignes):
                    return contenu
                if re.search(r'(?i)\b(?:INVOICE|PACKING LIST|FACTURE|CONSIGNEE|INVOICE TO)\b', textes):
                    break
                debut.append(textes)
            if all(normaliser(ligne) in normaliser(' '.join(debut)) for ligne in lignes):
                return contenu
        corps = doc.getElementsByTagNameNS(F.W, 'body')[0]
        p = doc.createElementNS(F.W, 'w:p')
        ppr = doc.createElementNS(F.W, 'w:pPr')
        espace = doc.createElementNS(F.W, 'w:spacing')
        espace.setAttribute('w:after', '160')
        ppr.appendChild(espace)
        p.appendChild(ppr)
        for i, ligne in enumerate(lignes):
            r = doc.createElementNS(F.W, 'w:r')
            if i:
                r.appendChild(doc.createElementNS(F.W, 'w:br'))
            else:
                pr = doc.createElementNS(F.W, 'w:rPr')
                pr.appendChild(doc.createElementNS(F.W, 'w:b'))
                r.appendChild(pr)
            t = doc.createElementNS(F.W, 'w:t')
            F._ecrire(t, ligne)
            r.appendChild(t)
            p.appendChild(r)
        corps.insertBefore(p, corps.firstChild)
        sortie = BytesIO()
        with ZipFile(sortie, 'w') as cible:
            for info in archive.infolist():
                cible.writestr(info, F.serialiser(doc) if info.filename == 'word/document.xml'
                               else archive.read(info.filename))
        return sortie.getvalue()
    finally:
        archive.close()


def _generer_documents(licence, contenu_modele, donnees):
    """Facture et packing list d'une part ou de la facture globale, depuis ses données.
    Renvoie dict(documents, part, numero, date, fob, poids_kg, articles)."""
    lignes = donnees['lignes']
    resultat = dict(part=donnees['part'], numero=donnees['numero'], date=donnees['date'],
                    fob=format(donnees['fob'], '.2f'), poids_kg=donnees['poids'], articles=len(lignes))
    if contenu_modele is None:
        from asydec.declarations import facture_simple
        documents = {FACTURE: facture_simple.creer_facture(licence, donnees),
                     PACKING_LIST: facture_simple.creer_packing_list(licence, donnees)}
        return dict(resultat, documents={nom: completer_entete_fournisseur(document, licence)
                                        for nom, document in documents.items()})
    contenu = actualiser_coordonnees(preparer_modele(contenu_modele), licence)
    contenu, capacite = adapter_tableaux(contenu, [l['designation'] for l in lignes])
    champs = F.inspecter(contenu, exiger=False)
    indices = {int(m[2]) for c in champs if (m := INDICE.fullmatch(c))}
    if not capacite and indices and max(indices) != len(lignes):
        quoi = 'la facture globale' if donnees['part'] == GLOBALE else f"la part {donnees['part']}"
        raise ValueError(f'Le modèle de facture prévoit {max(indices)} article(s) ; '
                         f"{quoi} en contient {len(lignes)}.")
    prix_kg = any(c.startswith('PRIX_UNITAIRE_') for c in champs) and _prix_au_kg(contenu_modele)
    fob, poids = donnees['fob'], donnees['poids']
    valeurs = {
        'NUMERO_FACTURE': donnees['numero'], 'DATE_FACTURE': donnees['date'],
        'POIDS': nombre(poids, 2), 'FOB': nombre(float(fob), 2), 'COLIS': _quantite(donnees['quantites']),
        'IMPORTATEUR': (licence.get('soussigne') or {}).get('nom', ''),
        'PLAQUE': donnees['plaque'],
        'MODELE_ID': licence.get('numero_validation', ''),
        # Facture commerciale en FOB : fret et assurance à zéro, total = FOB.
        'FRET': nombre(0, 2), 'ASSURANCE': nombre(0, 2), 'CIF_USD': nombre(float(fob), 2),
        'NUMERO_MANIFESTE': donnees['manifeste'],
        'FOB_LETTRES': en_lettres(fob, monnaie=True), 'POIDS_LETTRES': en_lettres(poids),
    }
    for i, ligne in enumerate(lignes, 1):
        prix = (ligne['valeur'] / ligne['poids']).quantize(Decimal('.0001'), rounding=ROUND_HALF_UP) \
            if prix_kg and ligne['poids'] else ligne['prix_unitaire']
        valeurs.update({f'COLIS_{i}': _quantite(ligne['quantite']), f'FOB_{i}': nombre(float(ligne['valeur']), 2),
                        f'POIDS_{i}': nombre(ligne['poids'], 2),
                        f'PRIX_UNITAIRE_{i}': nombre(float(prix), 4) if prix_kg else _pu_fr(prix)})
    valeurs = {c: v for c, v in valeurs.items() if c in champs}
    from asydec.declarations.sceau import apposer
    facture, packing_list = (apposer(completer_entete_fournisseur(document, licence), licence) for document in
                             separer(F.remplir(contenu, valeurs, verifier=False)))
    return dict(resultat, documents={FACTURE: facture, PACKING_LIST: packing_list})


def generer_part(licence, contenu_modele, part):
    """Remplit le modèle Word (ou, sans modèle, crée la facture simple AsyDec) pour une part."""
    return _generer_documents(licence, contenu_modele, donnees_part(licence, part))


def generer_globale(licence, contenu_modele=None):
    """Facture et packing list globales : total de toutes les parts, article par article."""
    return _generer_documents(licence, contenu_modele, donnees_globale(licence))


def generer(licence, contenu_modele=None):
    """Facture et packing list de chaque part, toutes préparées avant tout enregistrement.
    contenu_modele : Word fourni par l'utilisateur ; None = facture simple créée par AsyDec."""
    references_facture(licence)
    return [generer_part(licence, contenu_modele, part) for part in parts(licence)]


def _nettoyer(texte_):
    return re.sub(r'[^A-Za-z0-9._-]', '-', texte_)


def nom_fichier(numero_licence, resultat, document=None):
    """Même organisation que le XML : « <licence> - part N - facture <numéro>.docx »
    et « <licence> - part N - packing list <numéro>.docx » ; « <licence> - global - … » pour la globale."""
    rang = GLOBALE if resultat['part'] == GLOBALE else f"part {resultat['part']}"
    return (f"{_nettoyer(numero_licence)} - {rang} - {document or FACTURE} "
            f"{_nettoyer(resultat['numero'])}.docx")


def est_a_jour(licence):
    """Factures produites pour toutes les parts, sur les données et le numéro de facture actuels."""
    factures = licence.get('factures_parts')
    if not factures or not mise_a_jour_repartitions.est_a_jour(licence):
        return False
    try:
        numero, date = references_facture(licence)
        nombre_parts = len(parts(licence))
    except ValueError:
        return False
    return (factures.get('empreinte') == mise_a_jour_repartitions.empreinte(licence)
            and (factures.get('numero_facture'), factures.get('date_facture')) == (numero, date)
            and len(factures.get('parts') or []) == nombre_parts
            # Anciennes générations en un seul fichier : à refaire en fichiers séparés.
            and all(set(p.get('fichiers') or {}) == {FACTURE, PACKING_LIST} for p in factures['parts'])
            # Générations antérieures sans facture globale : à refaire.
            and set((factures.get('globale') or {}).get('fichiers') or {}) == {FACTURE, PACKING_LIST})


FACTURE_SIMPLE = 'AsyDec · facture simple'


def _resume(resultat, fichiers):
    return dict(part=resultat['part'], numero=resultat['numero'], fichiers={d: str(c) for d, c in fichiers.items()},
                fob=resultat['fob'], poids_kg=resultat['poids_kg'], articles=resultat['articles'])


def fiche(licence, resultats, fichiers, modele=None, globale=None, fichiers_globale=None):
    """Ce qui est conservé dans la licence pour l'étape 5 (l'empreinte est ajoutée à l'enregistrement).
    modele : chemin du Word fourni ; None = facture simple AsyDec.
    globale, fichiers_globale : résultat et fichiers de la facture globale."""
    numero, date = references_facture(licence)
    return dict(globale=_resume(globale, fichiers_globale or {}) if globale else None, modele=str(modele) if modele else FACTURE_SIMPLE, methode='modele' if modele else 'simple', numero_facture=numero, date_facture=date,
                genere_le=datetime.now(timezone.utc).isoformat(),
                parts=[_resume(r, f) for r, f in zip(resultats, fichiers)])
