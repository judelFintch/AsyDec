"""Factures Word : modèles archivés et remplacement ciblé des champs OOXML."""
from contextlib import contextmanager
from datetime import datetime
from io import BytesIO
from pathlib import Path
import re
import json
import sqlite3
import secrets
import string
import unicodedata
from difflib import SequenceMatcher
from xml.dom import minidom
from zipfile import ZipFile, BadZipFile
from zoneinfo import ZoneInfo

from asydec import chemins
from asydec.formats import nombre

BASE = chemins.DONNEES / 'factures.db'
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
CHAMPS = ('NUMERO_FACTURE', 'DATE_FACTURE', 'POIDS', 'COLIS', 'FOB', 'IMPORTATEUR', 'PLAQUE', 'MODELE_ID', 'FRET', 'ASSURANCE', 'CIF_USD', 'NUMERO_MANIFESTE', 'FOB_LETTRES', 'POIDS_LETTRES')
OBLIGATOIRES = {'NUMERO_FACTURE', 'POIDS', 'COLIS', 'FOB'}
BALISE = re.compile(r'\{\{([A-Z_][A-Z_0-9]*)\}\}')


@contextmanager
def connexion(base=None):
    chemin = Path(base) if base is not None else BASE
    chemin.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(chemin, timeout=10)
    try:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.executescript('''
        CREATE TABLE IF NOT EXISTS gabarits (
          id INTEGER PRIMARY KEY, nom TEXT NOT NULL, contenu BLOB NOT NULL);
        CREATE TABLE IF NOT EXISTS factures (
          id INTEGER PRIMARY KEY AUTOINCREMENT, numero TEXT UNIQUE,
          modele_id INTEGER NOT NULL, gabarit_id INTEGER NOT NULL REFERENCES gabarits(id),
          date TEXT NOT NULL, auteur TEXT NOT NULL, contenu BLOB);
        ''')
        if 'articles_json' not in {r[1] for r in db.execute('PRAGMA table_info(gabarits)')}:
            db.execute("ALTER TABLE gabarits ADD COLUMN articles_json TEXT NOT NULL DEFAULT '[]'")
        if 'prix_base' not in {r[1] for r in db.execute('PRAGMA table_info(gabarits)')}:
            db.execute("ALTER TABLE gabarits ADD COLUMN prix_base TEXT NOT NULL DEFAULT 'colis'")
        if 'manifeste' not in {r[1] for r in db.execute('PRAGMA table_info(factures)')}:
            db.execute('ALTER TABLE factures ADD COLUMN manifeste TEXT')
        if 'retire' not in {r[1] for r in db.execute('PRAGMA table_info(gabarits)')}:
            # Date de retrait de la bibliothèque ; NULL = modèle proposé.
            db.execute('ALTER TABLE gabarits ADD COLUMN retire TEXT')
        with db:
            yield db
    finally:
        db.close()


def _reserver_numeros(base=None, numero_existant=None):
    """Registre conservé lors d’un reset ; les réservations ne sont jamais libérées."""
    chemin = (Path(base).parent / 'numeros_factures.db') if base is not None else chemins.CONFIG_LOCAL / 'numeros_factures.db'
    chemin.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(chemin, timeout=10)
    try:
        db.execute('CREATE TABLE IF NOT EXISTS numeros (facture TEXT PRIMARY KEY, manifeste TEXT NOT NULL UNIQUE)')
        db.executescript("""
        CREATE TRIGGER IF NOT EXISTS numeros_sans_modification BEFORE UPDATE ON numeros
        BEGIN SELECT RAISE(ABORT,'Numéro réservé définitivement'); END;
        CREATE TRIGGER IF NOT EXISTS numeros_sans_suppression BEFORE DELETE ON numeros
        BEGIN SELECT RAISE(ABORT,'Numéro réservé définitivement'); END;
        """)
        with db:
            db.execute('BEGIN IMMEDIATE')
            if numero_existant:
                existant = db.execute('SELECT facture,manifeste FROM numeros WHERE facture=?', (numero_existant,)).fetchone()
                if existant:
                    return tuple(existant)
            for _ in range(100):
                facture = ''.join(secrets.choice(string.ascii_uppercase) for _ in range(2)) + f'-{secrets.randbelow(1000):03d}-{secrets.randbelow(1000):03d}'
                facture = numero_existant or facture
                manifeste = f'{secrets.randbelow(10000):04d}-ML{secrets.randbelow(10000):04d}'
                try:
                    db.execute('INSERT INTO numeros VALUES(?,?)', (facture, manifeste))
                    return facture, manifeste
                except sqlite3.IntegrityError:
                    continue
            raise ValueError('Aucun numéro disponible ; réessayez.')
    finally:
        db.close()


def _parties(contenu):
    try:
        archive = ZipFile(BytesIO(contenu))
        if '[Content_Types].xml' not in archive.namelist() or 'word/document.xml' not in archive.namelist():
            raise ValueError('Ce fichier n’est pas un document Word .docx.')
        if sum(i.file_size for i in archive.infolist()) > 50_000_000:
            raise ValueError('Le document Word dépasse la taille maximale de 50 Mo décompressés.')
        parties = {}
        for nom in archive.namelist():
            if nom == 'word/document.xml' or re.fullmatch(r'word/(header|footer)\d+\.xml', nom):
                xml = archive.read(nom)
                if b'<!DOCTYPE' in xml or b'<!ENTITY' in xml:
                    raise ValueError('Les déclarations DTD ne sont pas prises en charge.')
                parties[nom] = minidom.parseString(xml)
        return archive, parties
    except (BadZipFile, OSError) as exc:
        raise ValueError('Document Word illisible.') from exc


def _textes(paragraphe):
    return list(paragraphe.getElementsByTagNameNS(W, 't'))


def _texte(noeud):
    return ''.join(n.data for n in noeud.childNodes if n.nodeType == n.TEXT_NODE)


def _ecrire(noeud, texte):
    for enfant in list(noeud.childNodes):
        noeud.removeChild(enfant)
    noeud.appendChild(noeud.ownerDocument.createTextNode(texte))
    noeud.setAttribute('xml:space', 'preserve')


def serialiser(doc):
    # minidom écrit les retours de ligne des attributs littéralement ; Word
    # contient des données de dessin encodées dans ces attributs. Les préserver.
    xml = doc.toxml()
    xml = re.sub(r'="([^"]*)"', lambda m: '="' + m[1].replace('\r', '&#13;').replace('\n', '&#10;').replace('\t', '&#9;') + '"', xml)
    return xml.encode('UTF-8')


def inspecter(contenu, exiger=True):
    archive, parties = _parties(contenu)
    try:
        champs = set()
        for doc in parties.values():
            for p in doc.getElementsByTagNameNS(W, 'p'):
                champs.update(BALISE.findall(''.join(_texte(t) for t in _textes(p))))
        manquants = OBLIGATOIRES - champs
        for champ in ('FOB', 'POIDS', 'COLIS'):
            if any(re.fullmatch(champ+r'_[1-9][0-9]*', c) for c in champs):
                manquants.discard(champ)
        inconnus = {c for c in champs if c not in CHAMPS and not re.fullmatch(r'(COLIS|FOB|POIDS|PRIX_UNITAIRE)_[1-9][0-9]*', c)}
        if manquants and exiger:
            raise ValueError('Ajoutez dans votre modèle Word les champs : ' + ', '.join('{{'+c+'}}' for c in sorted(manquants)))
        if inconnus and exiger:
            raise ValueError('Champs inconnus : ' + ', '.join(sorted(inconnus)))
        return champs
    finally:
        archive.close()


def remplir(contenu, valeurs, verifier=True):
    """Garde les runs et leur style, même quand Word a fragmenté un champ."""
    if verifier:
        inspecter(contenu)
    archive, parties = _parties(contenu)
    sortie = BytesIO()
    try:
        modifies = {}
        for nom, doc in parties.items():
            change = False
            for p in doc.getElementsByTagNameNS(W, 'p'):
                if p.getElementsByTagNameNS(W, 'p'):
                    continue
                textes = _textes(p)
                texte = ''.join(_texte(t) for t in textes)
                positions, debut = [], 0
                for t in textes:
                    positions.append((debut, debut + len(_texte(t)), t))
                    debut += len(_texte(t))
                for match in reversed(list(BALISE.finditer(texte))):
                    if match[1] not in valeurs:
                        raise ValueError('Valeur absente : ' + match[1])
                    touches = [(a, b, t) for a, b, t in positions if a < match.end() and b > match.start()]
                    for i, (a, b, t) in enumerate(touches):
                        actuel = _texte(t)
                        gauche = actuel[:max(0, match.start()-a)]
                        droite = actuel[match.end()-a:] if match.end() < b else ''
                        _ecrire(t, gauche + (str(valeurs[match[1]]) if i == 0 else '') + droite)
                    change = True
            if change:
                modifies[nom] = serialiser(doc)
        with ZipFile(sortie, 'w') as cible:
            for info in archive.infolist():
                cible.writestr(info, modifies[info.filename] if info.filename in modifies else archive.read(info.filename))
        return sortie.getvalue()
    finally:
        archive.close()


def importer(chemin, base=None):
    chemin = Path(chemin)
    if chemin.suffix.lower() != '.docx':
        raise ValueError('Choisissez un modèle Word .docx.')
    contenu = chemin.read_bytes()
    from asydec.declarations.preparer_facture import base_prix
    prix_base = base_prix(contenu)
    descriptions = []
    try:
        inspecter(contenu)
    except ValueError:
        from asydec.declarations.preparer_facture import preparer
        try:
            contenu, descriptions = preparer(contenu)
        except ValueError:
            # Conserver un Word valide même si son agencement est inconnu.
            # La configuration des zones sera faite dans la bibliothèque.
            inspecter(contenu, exiger=False)
    from asydec.declarations.preparer_facture import preparer_plaque
    contenu = preparer_plaque(contenu)
    descriptions = descriptions or analyser_gabarit(contenu)['articles']
    with connexion(base) as db:
        existant = db.execute('SELECT id FROM gabarits WHERE contenu=?', (contenu,)).fetchone()
        if existant:
            # Le même Word rechargé revient dans la bibliothèque s'il en avait été retiré.
            db.execute('UPDATE gabarits SET retire=NULL WHERE id=?', (existant['id'],))
            return existant['id']
        return db.execute('INSERT INTO gabarits(nom,contenu,articles_json,prix_base) VALUES(?,?,?,?)',
            (chemin.stem, contenu, json.dumps(descriptions), prix_base)).lastrowid


def lister_modeles(base=None):
    with connexion(base) as db:
        modeles = []
        for r in db.execute('SELECT id,nom,articles_json,contenu,prix_base FROM gabarits WHERE retire IS NULL ORDER BY id DESC'):
            from asydec.declarations.preparer_facture import preparer_plaque
            contenu = preparer_plaque(r['contenu'])
            champs = inspecter(contenu, exiger=False)
            analyse = analyser_gabarit(contenu)
            modeles.append({'id': r['id'], 'nom': r['nom'], 'articles': json.loads(r['articles_json']) or analyse['articles'],
                            'prix_base': r['prix_base'], 'pret': champs_prets(champs), 'champs': sorted(champs), 'plaque_prevue': 'PLAQUE' in champs, 'fournisseur': analyse['fournisseur'], 'destinataire': analyse['destinataire']})
        return modeles


def generer(modele_id, gabarit_id, auteur, base=None, base_modeles=None, correspondance_confirmee=False):
    from asydec.declarations import modeles_generes
    modele = modeles_generes.detail(modele_id, base=base_modeles)
    if modele['supprime']:
        raise ValueError('Restaurez le modèle avant de générer sa facture.')
    plaque = (modele.get('plaque') or '').strip()
    if not plaque:
        raise ValueError('La plaque est obligatoire : renseignez et enregistrez la plaque dans Modèles générés avant de créer la facture.')
    resultat = modele['resultat']
    resume = resultat['resume']
    maintenant = datetime.now(ZoneInfo('Africa/Lubumbashi'))
    valeurs = {
        'DATE_FACTURE': maintenant.strftime('%d/%m/%Y'),
        'POIDS': nombre(resume['poids'], 2), 'FOB': nombre(resume['fob'], 2),
        'COLIS': nombre(sum(resultat.get('colis', resume.get('colis', [])))),
        'IMPORTATEUR': modele['importateur'], 'PLAQUE': modele['plaque'] or '',
        'MODELE_ID': str(modele_id),
    }
    from asydec.declarations.nombres_lettres import nombre as lettres
    valeurs.update(FOB_LETTRES=lettres(resume['fob'], monnaie=True), POIDS_LETTRES=lettres(resume['poids']))
    with connexion(base) as db:
        db.execute('BEGIN IMMEDIATE')
        existante = db.execute('SELECT id,numero,manifeste,contenu FROM factures WHERE modele_id=? AND contenu IS NOT NULL ORDER BY id DESC LIMIT 1', (modele_id,)).fetchone()
        if existante is not None:
            facture = dict(existante)
            if not facture['manifeste']:
                # Anciennes archives : conserver leur code facture et attribuer
                # une seule fois le manifeste, sans créer une autre facture.
                from asydec.declarations.preparer_facture import preparer_manifeste
                _, manifeste = _reserver_numeros(base, numero_existant=facture['numero'])
                contenu = remplir(preparer_manifeste(facture['contenu']),
                                  {'NUMERO_MANIFESTE': manifeste}, verifier=False)
                db.execute('UPDATE factures SET manifeste=?,contenu=? WHERE id=?',
                           (manifeste, contenu, facture['id']))
                facture.update(manifeste=manifeste, contenu=contenu)
            return facture
        gabarit = db.execute('SELECT contenu,articles_json,prix_base,retire FROM gabarits WHERE id=?', (gabarit_id,)).fetchone()
        if gabarit is None:
            raise ValueError('Modèle de facture introuvable.')
        if gabarit['retire']:
            raise ValueError('Ce modèle de facture a été retiré de la bibliothèque. Rechargez le Word pour l’utiliser à nouveau.')
        from asydec.declarations.preparer_facture import preparer_plaque
        contenu_gabarit = preparer_plaque(gabarit['contenu'])
        if 'PLAQUE' not in inspecter(contenu_gabarit):
            raise ValueError('Ce modèle de facture ne prévoit aucune zone de plaque reconnue. Ajoutez {{PLAQUE}} à son emplacement dans le Word, puis rechargez-le.')
        descriptions = json.loads(gabarit['articles_json']) or analyser_gabarit(contenu_gabarit)['articles']
        if descriptions:
            articles = resume.get('articles', [])
            colis = resultat.get('colis', resume.get('colis', []))
            if len(articles) != len(descriptions) or len(colis) != len(descriptions):
                raise ValueError(f'Ce modèle de facture contient {len(descriptions)} articles ; la proposition en contient {len(articles)}. Choisissez un modèle correspondant.')
            if not correspondance_confirmee:
                raise ValueError('Confirmez la correspondance et l’ordre des articles avant de générer cette facture.')
            for i, (article, quantite) in enumerate(zip(articles, colis), 1):
                if quantite <= 0:
                    raise ValueError('Chaque article doit avoir un nombre de colis positif.')
                valeurs.update({f'COLIS_{i}': nombre(quantite), f'FOB_{i}': nombre(article['fob'], 2),
                                f'POIDS_{i}': nombre(article['poids'], 2),
                                f'PRIX_UNITAIRE_{i}': nombre(article['fob']/(article['poids'] if gabarit['prix_base']=='kg' else quantite), 4)})
            fret, assurance = resume.get('fret', 0), resume.get('assurance', 0)
            valeurs.update(FRET=nombre(fret, 2), ASSURANCE=nombre(assurance, 2),
                           CIF_USD=nombre(resume['fob'] + fret + assurance, 2))
        identifiant = db.execute('INSERT INTO factures(modele_id,gabarit_id,date,auteur) VALUES(?,?,?,?)',
            (modele_id, gabarit_id, maintenant.isoformat(), auteur)).lastrowid
        numero, manifeste = _reserver_numeros(base)
        # Mise à niveau en mémoire des modèles déjà importés, sans fichier intermédiaire.
        from asydec.declarations.preparer_facture import preparer_manifeste
        gabarit_contenu = preparer_manifeste(contenu_gabarit)
        contenu = remplir(gabarit_contenu, dict(valeurs, NUMERO_FACTURE=numero, NUMERO_MANIFESTE=manifeste))
        db.execute('UPDATE factures SET numero=?,manifeste=?,contenu=? WHERE id=?', (numero, manifeste, contenu, identifiant))
    return {'id': identifiant, 'numero': numero, 'manifeste': manifeste, 'contenu': contenu}


def factures_emises(gabarit_ids, base=None):
    """{identifiant de modèle de facture: nombre de factures déjà émises avec lui}."""
    ids = [int(i) for i in gabarit_ids]
    if not ids:
        return {}
    with connexion(base) as db:
        lignes = db.execute(f"SELECT gabarit_id, COUNT(*) n FROM factures WHERE gabarit_id IN ({','.join('?' * len(ids))}) "
                            'GROUP BY gabarit_id', ids).fetchall()
    return {i: 0 for i in ids} | {r['gabarit_id']: r['n'] for r in lignes}


def retirer_modeles(gabarit_ids, base=None):
    """Retire des modèles de facture de la bibliothèque : ils ne sont plus proposés. Les factures déjà
    émises restent archivées et téléchargeables ; recharger le même Word le remet en service.
    Renvoie le nombre de modèles retirés."""
    ids = [int(i) for i in gabarit_ids]
    if not ids:
        return 0
    with connexion(base) as db:
        connus = {r['id'] for r in db.execute(f"SELECT id FROM gabarits WHERE id IN ({','.join('?' * len(ids))})", ids)}
        if connus != set(ids):
            raise ValueError('Modèle de facture introuvable : ' + ', '.join(str(i) for i in sorted(set(ids) - connus)))
        date = datetime.now(ZoneInfo('Africa/Lubumbashi')).isoformat()
        return db.executemany('UPDATE gabarits SET retire=? WHERE id=? AND retire IS NULL',
                              [(date, i) for i in ids]).rowcount


def lister_factures(modele_id, base=None):
    with connexion(base) as db:
        return [dict(r) for r in db.execute('SELECT id,numero,manifeste,date FROM factures WHERE modele_id=? ORDER BY id DESC', (modele_id,))]


def lire(identifiant, base=None):
    with connexion(base) as db:
        facture = db.execute('SELECT numero,manifeste,contenu FROM factures WHERE id=?', (identifiant,)).fetchone()
        if facture is None:
            raise ValueError('Facture introuvable.')
        return dict(facture)


def _normaliser(texte):
    texte = ''.join(c for c in unicodedata.normalize('NFKD', texte or '') if not unicodedata.combining(c))
    return ' '.join(re.findall(r'[A-Z0-9]+', texte.upper()))


def analyser_gabarit(contenu):
    archive, parties = _parties(contenu)
    try:
        from asydec.declarations.preparer_facture import paragraphes, texte
        lignes = [texte(p).strip() for p in paragraphes(parties['word/document.xml']) if texte(p).strip()]
        destinataire = ''
        for i, ligne in enumerate(lignes):
            match = re.search(r'(?i)(?:Consignee|Consignée|Invoice to)\s*:\s*(.*?)(?:\s+INV\s+(?:NO|N°)\s*:|$)', ligne)
            if match:
                destinataire = match[1].strip() or (lignes[i+1] if i+1 < len(lignes) else '')
                break
        articles = []
        for table in parties['word/document.xml'].getElementsByTagNameNS(W, 'tbl'):
            rows = [r for r in table.childNodes if r.localName == 'tr']
            if not rows or not re.search(r'(?i)description|désignation|designation', texte(rows[0])):
                continue
            for row in rows[1:]:
                cells = [c for c in row.childNodes if c.localName == 'tc']
                if len(cells) >= 2 and texte(cells[0]).strip().isdigit():
                    articles.append(texte(cells[1]).strip())
            if articles:
                break
        fournisseur = next((s for s in lignes if re.search(r'(?i)TEXTILES|GARMENTS.*FZE', s) and not s.upper().startswith('FOR ')), lignes[0] if lignes else '')
        return {'fournisseur': fournisseur, 'destinataire': destinataire, 'articles': articles}
    finally:
        archive.close()


def classer_gabarits(gabarits, modele):
    """Propositions expliquées ; le nombre seul ne vaut jamais correspondance."""
    resultat = modele['resultat']
    designations = resultat.get('info', {}).get('designations', [])
    nombre_articles = len(resultat.get('resume', {}).get('articles', []))
    classement = []
    for g in gabarits:
        articles = g['articles']
        note, propose = 0, False
        if not g.get('pret', True):
            raison = 'Champs à configurer dans la bibliothèque'
        elif not g.get('plaque_prevue'):
            raison = 'Zone de plaque à prévoir'
        elif not articles:
            note, raison = 1, 'Articles non repérés : choix manuel'
        elif len(articles) != nombre_articles:
            raison = f'{len(articles)} articles dans la facture, {nombre_articles} dans le modèle'
        else:
            fidelites = [SequenceMatcher(None, _normaliser(a), _normaliser(b)).ratio()
                         for a, b in zip(articles, designations)]
            note = 2
            raison = f'{nombre_articles} articles : libellés à vérifier'
            if len(fidelites) == nombre_articles and all(f >= .85 for f in fidelites):
                note, propose = 3 + sum(fidelites)/len(fidelites), True
                raison = 'Articles correspondants dans le même ordre'
            destinataire = nom_client(g.get('destinataire', ''))
            importateur = nom_client(modele.get('importateur', ''))
            if destinataire and importateur and destinataire != importateur:
                propose = False
                note = 1
                raison += ' ; destinataire différent à vérifier'
        classement.append(dict(g, propose=propose, raison=raison, score=note))
    return sorted(classement, key=lambda g: (g['propose'], g['score']), reverse=True)


def proposer(modele_id, base=None, base_modeles=None):
    from asydec.declarations import modeles_generes
    return classer_gabarits(lister_modeles(base), modeles_generes.detail(modele_id, base=base_modeles))


def resume_suggestion(modele, base=None):
    if not (modele.get('plaque') or '').strip():
        return 'Facture : plaque obligatoire à renseigner dans ce modèle.'
    classes = classer_gabarits(lister_modeles(base), modele)
    proposes = [g['nom'] for g in classes if g['propose']]
    if proposes:
        return 'Facture conseillée : ' + ' ; '.join(proposes[:3])
    return 'Facture : choisissez votre modèle Word dans Factures Word… (correspondance à vérifier).'


def zones_disponibles(gabarit_id, base=None):
    from asydec.declarations.preparer_facture import paragraphes, texte
    with connexion(base) as db:
        ligne = db.execute('SELECT contenu FROM gabarits WHERE id=?', (gabarit_id,)).fetchone()
    if ligne is None:
        raise ValueError('Modèle de facture introuvable.')
    archive, parties = _parties(ligne['contenu'])
    try:
        return [{'partie': nom, 'paragraphe': i, 'texte': texte(p)}
                for nom, doc in parties.items() for i, p in enumerate(paragraphes(doc)) if texte(p).strip()]
    finally:
        archive.close()


def configurer_zones(gabarit_id, zones, base=None):
    """Associe un fragment exact à un champ, sans retoucher sa mise en forme."""
    from asydec.declarations.preparer_facture import paragraphes, texte, remplacer
    with connexion(base) as db:
        db.execute('BEGIN IMMEDIATE')
        ligne = db.execute('SELECT contenu FROM gabarits WHERE id=?', (gabarit_id,)).fetchone()
        if ligne is None:
            raise ValueError('Modèle de facture introuvable.')
        archive, parties = _parties(ligne['contenu'])
        try:
            modifications = {}
            for zone in zones:
                champ, valeur = zone['champ'], zone['valeur']
                if champ not in CHAMPS and not re.fullmatch(r'(COLIS|FOB|POIDS|PRIX_UNITAIRE)_[1-9][0-9]*', champ):
                    raise ValueError('Champ inconnu : ' + champ)
                p = paragraphes(parties[zone['partie']])[zone['paragraphe']]
                s = texte(p)
                if not valeur or s.count(valeur) != 1:
                    raise ValueError('La valeur à remplacer doit apparaître exactement une fois dans la zone choisie.')
                debut = s.index(valeur)
                modifications.setdefault((zone['partie'],zone['paragraphe']), []).append((debut,debut+len(valeur),champ))
            for (nom, indice), remplacements in modifications.items():
                remplacements.sort()
                if any(b > c for (_,b,_),(c,_,_) in zip(remplacements, remplacements[1:])):
                    raise ValueError('Deux champs se chevauchent dans la même zone.')
                p = paragraphes(parties[nom])[indice]
                for debut, fin, champ in reversed(remplacements):
                    remplacer(p,debut,fin,'{{'+champ+'}}')
            sortie = BytesIO()
            with ZipFile(sortie,'w') as cible:
                for info in archive.infolist():
                    cible.writestr(info, serialiser(parties[info.filename]) if info.filename in parties else archive.read(info.filename))
            contenu = sortie.getvalue()
            inspecter(contenu, exiger=False)
            db.execute('UPDATE gabarits SET contenu=? WHERE id=?', (contenu,gabarit_id))
        finally:
            archive.close()


def champs_prets(champs):
    obligatoires = OBLIGATOIRES | {'PLAQUE'}
    return all(c in champs or (c in ('FOB','POIDS','COLIS') and
               any(re.fullmatch(c+r'_[1-9][0-9]*', v) for v in champs)) for c in obligatoires)


def nom_client(nom):
    mots = _normaliser(nom).split()
    return ''.join(m for m in mots if m not in {'ETS','STE','SOCIETE','ETABLISSEMENT','ETABLISSEMENTS'})
