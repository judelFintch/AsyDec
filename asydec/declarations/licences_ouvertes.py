"""Conservation locale des dossiers de licence ouverts et validés."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal
import json
import re
from pathlib import Path
import sqlite3
import xml.etree.ElementTree as ET

from asydec import chemins
from asydec.declarations import recuperation_simulation, conteneurs, repartition_licence, informations_declaration, numeros_repartitions, mise_a_jour_repartitions

FICHIER = chemins.DONNEES / 'licences_ouvertes.sqlite'


@contextmanager
def connexion(fichier=None):
    fichier = Path(fichier or FICHIER)
    fichier.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(fichier)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('''CREATE TABLE IF NOT EXISTS licences (
            numero TEXT PRIMARY KEY, contenu TEXT NOT NULL, modifie_le TEXT NOT NULL)''')
        # Licences supprimées : gardées pour toujours afin que leurs clients, fournisseurs et
        # articles restent proposés (voir reprises_licence). Jamais affichées dans la liste.
        conn.execute('''CREATE TABLE IF NOT EXISTS licences_supprimees (
            id INTEGER PRIMARY KEY AUTOINCREMENT, numero TEXT NOT NULL, contenu TEXT NOT NULL,
            modifie_le TEXT NOT NULL, supprime_le TEXT NOT NULL)''')
        with conn:
            yield conn
    finally:
        conn.close()


def encoder(valeur):
    if isinstance(valeur, Decimal):
        return str(valeur)
    if isinstance(valeur, date):
        return valeur.isoformat()
    raise TypeError(f'Type non pris en charge : {type(valeur).__name__}')


def enregistrer(licence, fichier=None):
    numero = licence['numero_validation'].strip()
    if not numero:
        raise ValueError('Le numéro licence est obligatoire.')
    donnees = dict(licence)
    # Quantité × prix unitaire des articles = FOB exactement (écart d'arrondi corrigé dès l'enregistrement).
    donnees['produits'] = repartition_licence.ajuster_articles(licence.get('produits') or [], licence.get('montant_fob'))
    maintenant = datetime.now(timezone.utc).isoformat()
    with connexion(fichier) as conn:
        ancien = conn.execute('SELECT contenu FROM licences WHERE numero=?', (numero,)).fetchone()
        if ancien:
            ancien = json.loads(ancien['contenu'])
            if ancien.get('informations_declaration'):
                donnees['informations_declaration'] = ancien['informations_declaration']
            if Decimal(str(ancien['montant_fob'])) == Decimal(str(licence['montant_fob'])) and ancien.get('repartition'):
                donnees['repartition'] = ancien['repartition']
                if ancien.get('produits') != donnees['produits']:
                    # Articles modifiés : leur division par part sera recalculée au chargement.
                    for part in donnees['repartition'].get('parts') or []:
                        part.pop('articles', None)
            else:
                donnees.pop('repartition', None)
        contenu = json.dumps(donnees, default=encoder, ensure_ascii=False, allow_nan=False)
        conn.execute('''INSERT INTO licences VALUES (?, ?, ?)
            ON CONFLICT(numero) DO UPDATE SET contenu=excluded.contenu, modifie_le=excluded.modifie_le''',
                     (numero, contenu, maintenant))


def supprimer(numero, fichier=None):
    """Retire la licence de la liste ; son contenu est archivé, pas détruit.

    Soussigné, fournisseur et articles restent ainsi disponibles pour les autres licences.
    Le dossier DEC sur le disque n'est pas touché. Renvoie le contenu de la licence supprimée
    (date de validation au format JJ/MM/AAAA), pour pouvoir recommencer avec.
    """
    with connexion(fichier) as conn:
        ligne = conn.execute('SELECT contenu, modifie_le FROM licences WHERE numero=?', (numero,)).fetchone()
        if ligne is None:
            raise ValueError('Cette licence est introuvable.')
        conn.execute('INSERT INTO licences_supprimees (numero, contenu, modifie_le, supprime_le) VALUES (?, ?, ?, ?)',
                     (numero, ligne['contenu'], ligne['modifie_le'], datetime.now(timezone.utc).isoformat()))
        conn.execute('DELETE FROM licences WHERE numero=?', (numero,))
    licence = json.loads(ligne['contenu'])
    try:
        licence['date_validation'] = date.fromisoformat(licence['date_validation']).strftime('%d/%m/%Y')
    except (KeyError, TypeError, ValueError):
        pass
    return licence


def supprimer_toutes(fichier=None):
    """Supprime (archive) toutes les licences ouvertes ; renvoie leurs contenus."""
    with connexion(fichier) as conn:
        numeros = [l['numero'] for l in conn.execute('SELECT numero FROM licences').fetchall()]
    return [supprimer(numero, fichier) for numero in numeros]


def base_recommencer(licence):
    """Éléments d'une licence supprimée repris dans un formulaire neuf (étape 1 seulement).

    Répartition, factures, XML, CVI… ne sont pas repris : le dossier repart de zéro.
    """
    cles = ('numero_validation', 'numero_dec', 'montant_fob', 'date_validation', 'numero_facture', 'date_facture',
            'soussigne', 'fournisseur', 'produits', 'nombre_produits_attendu')
    return {c: deepcopy(licence[c]) for c in cles if c in licence}


def lister(fichier=None):
    from asydec.declarations.informations_declaration import alerte_enregistrement
    with connexion(fichier) as conn:
        lignes = conn.execute('SELECT numero, contenu, modifie_le FROM licences ORDER BY modifie_le DESC, numero').fetchall()
    resultat = []
    for ligne in lignes:
        licence = json.loads(ligne['contenu'])
        resultat.append(dict(numero=ligne['numero'], numero_dec=licence.get('numero_dec', ''),
                             soussigne=licence.get('soussigne', {}).get('nom', ''),
                             montant_fob=licence.get('montant_fob', ''),
                             articles=len(licence.get('produits', [])),
                             alerte=alerte_enregistrement(licence),
                             modifie_le=ligne['modifie_le']))
    return resultat


def _completer_plaques(licence):
    repartition = licence.get('repartition')
    if not repartition:
        return False
    parts = repartition['parts']
    anciennes = [p.get('plaque') for p in parts]
    nouvelles = repartition_licence.proposer_plaques(len(parts), anciennes)
    for part, plaque in zip(parts, nouvelles):
        part['plaque'] = plaque
    return anciennes != nouvelles


def options_repartition(repartition):
    """Choix enregistrés de l'étape 2 ; anciennes répartitions : comportement par défaut."""
    repartition = repartition or {}
    return dict(nombre=repartition.get('nombre_parts_choisi'), plafond=repartition.get('plafond_actif', True))


def _ajuster_produits(licence):
    """Licences enregistrées avant la correction : articles dont quantité × prix ne tombe pas sur le FOB
    à l'arrondi près. Corrigés tant qu'aucune facture ni XML n'a été produit à partir d'eux."""
    if licence.get('factures_parts') or licence.get('xml_genere'):
        return False
    ajustes = repartition_licence.ajuster_articles(licence.get('produits') or [], licence.get('montant_fob'))
    if ajustes is licence.get('produits') or ajustes == licence.get('produits'):
        return False
    licence['produits'] = ajustes
    for part in (licence.get('repartition') or {}).get('parts') or []:
        part.pop('articles', None)  # division par part recalculée juste après
    return True


def _articles_coherents(licence):
    """Division par part conforme aux articles de la licence : même prix, quantités qui s'additionnent."""
    produits = licence.get('produits') or []
    parts = licence['repartition']['parts']
    for i, produit in enumerate(produits):
        lignes = [(p.get('articles') or [])[i] for p in parts if len(p.get('articles') or []) > i]
        if len(lignes) != len(parts):
            return False
        try:
            if (sum(Decimal(str(l['quantite'])) for l in lignes) != Decimal(str(produit.get('quantite')).replace(',', '.'))
                    or any(Decimal(str(l['prix_unitaire'])) != Decimal(str(produit.get('prix_unitaire')).replace(',', '.'))
                           for l in lignes)):
                return False
        except (ArithmeticError, ValueError, KeyError):
            return False
    return True


def _completer_articles(licence):
    """Ajoute (ou recalcule) la division des articles des répartitions enregistrées :
    absente, ou devenue différente des articles de la licence (articles corrigés depuis)."""
    repartition = licence.get('repartition')
    if not repartition:
        return False
    if all('articles' in p for p in repartition['parts']) and (
            _articles_coherents(licence) or licence.get('factures_parts') or licence.get('xml_genere')):
        return False
    try:
        nouvelle = repartition_licence.preparer(licence['montant_fob'], [p['poids_kg'] for p in repartition['parts']], licence.get('produits'),
                                                **options_repartition(repartition))
    except ValueError:
        return False
    if len(nouvelle['parts']) != len(repartition['parts']) or 'articles' not in nouvelle['parts'][0]:
        return False
    for part, calculee in zip(repartition['parts'], nouvelle['parts']):
        part['articles'] = calculee['articles']
        part['fob'] = calculee['fob']
    return True


def _completer_conteneurs(licence):
    repartition = licence.get('repartition')
    return conteneurs.completer(repartition['parts']) if repartition else False


def charger(numero, fichier=None):
    with connexion(fichier) as conn:
        ligne = conn.execute('SELECT contenu FROM licences WHERE numero=?', (numero,)).fetchone()
        if ligne is None:
            raise ValueError('Cette licence est introuvable.')
        licence = json.loads(ligne['contenu'])
        plaques_modifiees = (_ajuster_produits(licence) | _completer_plaques(licence) | _completer_articles(licence)
                             | _completer_conteneurs(licence))
        numeros_modifies = numeros_repartitions.completer(licence)
        if plaques_modifiees or numeros_modifies:
            conn.execute('UPDATE licences SET contenu=? WHERE numero=?',
                         (json.dumps(licence, ensure_ascii=False), numero))
    licence['date_validation'] = date.fromisoformat(licence['date_validation']).strftime('%d/%m/%Y')
    return licence


def enregistrer_repartition(numero, fob_attendu, poids, fichier=None, plaques=None, paires_conteneurs=None,
                            nombre_parts=None, plafond=True):
    with connexion(fichier) as conn:
        conn.execute('BEGIN IMMEDIATE')
        ligne = conn.execute('SELECT contenu FROM licences WHERE numero=?', (numero,)).fetchone()
        if ligne is None:
            raise ValueError('Cette licence est introuvable.')
        licence = json.loads(ligne['contenu'])
        repartition = repartition_licence.preparer(fob_attendu, poids, licence.get('produits'), nombre_parts, plafond)
        if repartition_licence.montant(licence['montant_fob']) != repartition_licence.montant(fob_attendu):
            raise ValueError('Le FOB a changé. Rouvrez la répartition pour la recalculer.')
        if plaques is None:
            anciennes = [p.get('plaque') for p in licence.get('repartition', {}).get('parts', [])]
            choisies = repartition_licence.proposer_plaques(len(repartition['parts']), anciennes)
        else:
            choisies = repartition_licence.verifier_plaques(plaques, len(repartition['parts']))
        for part, plaque in zip(repartition['parts'], choisies):
            part['plaque'] = plaque
        anciennes_parts = licence.get('repartition', {}).get('parts', [])
        # Garder les conteneurs déjà proposés pour les mêmes numéros de part.
        sources = paires_conteneurs if paires_conteneurs is not None else anciennes_parts
        for part, ancienne in zip(repartition['parts'], sources):
            part['conteneur'], part['scelle'] = ancienne.get('conteneur'), ancienne.get('scelle')
        conteneurs.completer(repartition['parts'])
        for part, ancienne in zip(repartition['parts'], anciennes_parts):
            if ancienne.get('informations_declaration'):
                part['informations_declaration'] = ancienne['informations_declaration']
        licence['repartition'] = repartition
        numeros_repartitions.completer(licence)
        conn.execute('UPDATE licences SET contenu=?, modifie_le=? WHERE numero=?',
                     (json.dumps(licence, ensure_ascii=False, allow_nan=False),
                      datetime.now(timezone.utc).isoformat(), numero))
    return repartition


def lister_repartitions(numero=None, fichier=None):
    """Parts enregistrées actuellement, éventuellement limitées à une licence."""
    with connexion(fichier) as conn:
        if numero is None:
            lignes = conn.execute('SELECT numero, contenu FROM licences ORDER BY modifie_le DESC, numero').fetchall()
        else:
            lignes = conn.execute('SELECT numero, contenu FROM licences WHERE numero=?', (numero,)).fetchall()
    resultat = []
    for ligne in lignes:
        licence = charger(ligne['numero'], fichier)
        repartition = licence.get('repartition')
        if not repartition:
            continue
        for part in repartition['parts']:
            resultat.append(dict(numero_licence=ligne['numero'], numero_dec=licence.get('numero_dec', ''),
                                 soussigne=licence.get('soussigne', {}).get('nom', ''),
                                 part=part['numero'], fob=part['fob'], poids_kg=part['poids_kg'], plaque=part['plaque'],
                                 articles=part.get('articles', []),
                                 conteneur=part.get('conteneur', ''), scelle=part.get('scelle', ''),
                                 informations_declaration=part.get('informations_declaration', {})))
    return resultat


def enregistrer_informations_declaration(numero, valeurs, fichier=None):
    mise_a_jour_repartitions.exiger_numeros(valeurs)
    with connexion(fichier) as conn:
        conn.execute('BEGIN IMMEDIATE')
        ligne = conn.execute('SELECT contenu FROM licences WHERE numero=?', (numero,)).fetchone()
        if ligne is None:
            raise ValueError('Cette licence est introuvable.')
        licence = json.loads(ligne['contenu'])
        if not licence.get('repartition'):
            raise ValueError('Validez d’abord la répartition et les poids.')
        proposition = informations_declaration.proposer_date_enregistrement(licence.get('date_bl'))
        dates = {cle: valeurs.get(cle, '') for cle in informations_declaration.DATES_AUTO}
        attendu = proposition['date'].strftime('%d/%m/%Y')
        if dates['date_liquidation'] and not dates['date_cvi']:
            # Informations enregistrées avant l’ajout de la date CVI : on la calcule sans retirer les autres dates.
            dates['date_cvi'] = informations_declaration.proposer_date_cvi(dates['date_liquidation']).strftime('%d/%m/%Y')
        if not all(dates.values()):
            dates = informations_declaration.proposer_dates_declaration(licence.get('date_bl'))
        elif dates['date_enregistrement'] != attendu:
            raise ValueError('La date d’enregistrement a changé. Rouvrez les informations pour recalculer les dates.')
        informations = informations_declaration.verifier(dict(valeurs, **dates))
        licence['informations_declaration'] = informations
        numeros_repartitions.completer(licence)
        conn.execute('UPDATE licences SET contenu=?, modifie_le=? WHERE numero=?',
                     (json.dumps(licence, ensure_ascii=False, allow_nan=False),
                      datetime.now(timezone.utc).isoformat(), numero))
    return informations


def mettre_a_jour_repartitions(numero, fichier=None):
    with connexion(fichier) as conn:
        conn.execute('BEGIN IMMEDIATE')
        ligne=conn.execute('SELECT contenu FROM licences WHERE numero=?',(numero,)).fetchone()
        if ligne is None:
            raise ValueError('Cette licence est introuvable.')
        licence=json.loads(ligne['contenu'])
        _completer_plaques(licence)
        _completer_conteneurs(licence)
        mise_a_jour_repartitions.appliquer(licence)
        conn.execute('UPDATE licences SET contenu=?,modifie_le=? WHERE numero=?',
                     (json.dumps(licence,ensure_ascii=False),datetime.now(timezone.utc).isoformat(),numero))
    return licence


def _modifier(numero, fichier, action):
    with connexion(fichier) as conn:
        conn.execute('BEGIN IMMEDIATE')
        ligne = conn.execute('SELECT contenu FROM licences WHERE numero=?', (numero,)).fetchone()
        if ligne is None:
            raise ValueError('Cette licence est introuvable.')
        licence = json.loads(ligne['contenu'])
        resultat = action(licence)
        conn.execute('UPDATE licences SET contenu=?, modifie_le=? WHERE numero=?',
                     (json.dumps(licence, ensure_ascii=False, allow_nan=False),
                      datetime.now(timezone.utc).isoformat(), numero))
    return resultat


def retenir_modele_structure(numero, modele, fichier=None):
    """Mémorise le XML de structure utilisé, pour le reproposer à la prochaine génération."""
    def action(licence):
        licence['modele_structure'] = str(modele)
    _modifier(numero, fichier, action)


def enregistrer_xml_genere(numero, contenu, chemin, fichier=None, fichiers=None):
    """Conserve le XML de la part 1 comme référence de la récupération SYDONIA ; une ancienne récupération est écartée.
    fichiers : [dict(parts, fob, fichier)] de tous les XML générés (un par montant de part différent)."""
    recuperation_simulation.aplatir(contenu)

    def action(licence):
        licence['xml_genere'] = dict(contenu=contenu, fichier=str(chemin),
                                     fichiers=fichiers or [dict(parts=[1], fichier=str(chemin))],
                                     genere_le=datetime.now(timezone.utc).isoformat())
        licence.pop('recuperation_simulation', None)
    _modifier(numero, fichier, action)


def enregistrer_factures(numero, fiche, fichier=None):
    """Retient les factures et packing lists de toutes les parts (étape 5), avec l'empreinte des données utilisées."""
    def action(licence):
        if not mise_a_jour_repartitions.est_a_jour(licence):
            raise ValueError('Validez la mise à jour des répartitions avant les factures.')
        licence['factures_parts'] = dict(fiche, empreinte=mise_a_jour_repartitions.empreinte(licence))
    _modifier(numero, fichier, action)


PREFIXE_FACTURE = 'INV'
PREMIER_NUMERO_FACTURE = 'INV1001'


def proposer_numero_facture(fichier=None):
    """Numéro de facture suivant (INV + plus grand numéro INV déjà utilisé + 1), licences supprimées
    comprises : un numéro n'est jamais réutilisé."""
    motif = re.compile(rf'{PREFIXE_FACTURE}(\d+)', re.I)
    with connexion(fichier) as conn:
        contenus = [r['contenu'] for table in ('licences', 'licences_supprimees')
                    for r in conn.execute(f'SELECT contenu FROM {table}').fetchall()]
    numeros = []
    for contenu in contenus:
        try:
            m = motif.fullmatch(''.join(str(json.loads(contenu).get('numero_facture') or '').split()))
        except (ValueError, AttributeError):
            continue
        if m:
            numeros.append(m[1])
    if not numeros:
        return PREMIER_NUMERO_FACTURE
    plus_grand = max(numeros, key=int)
    return PREFIXE_FACTURE + str(int(plus_grand) + 1).zfill(len(plus_grand))


def enregistrer_references_facture(numero, numero_facture, date_facture, fichier=None):
    """Complète le numéro et la date de facture d'une licence déjà enregistrée, sans toucher aux étapes suivantes."""
    from asydec.declarations.documents_finaux import references_facture, controler_date_facture

    def action(licence):
        numero_ok, date_ok = references_facture(numero_facture, date_facture, obligatoire=True)
        controler_date_facture(date_ok, licence.get('date_validation'))
        licence['numero_facture'], licence['date_facture'] = numero_ok, date_ok
    _modifier(numero, fichier, action)


def references_xml(licence):
    """XML attendu de chaque part : [dict(parts=[n], libelle, contenu)].

    Les parts d'un même groupe (même montant) partagent un XML généré, mais chacune a ses numéros E, L, Q :
    le XML attendu de chaque part est reconstruit avec le modèle de structure retenu. À défaut de modèle,
    les XML générés eux-mêmes servent de référence (un par groupe)."""
    from asydec.declarations import xml_licence
    xml = licence.get('xml_genere') or {}
    if not xml:
        return []
    modele = licence.get('modele_structure')
    if modele and Path(modele).is_file():
        try:
            references = []
            for groupe in xml_licence.groupes_parts(licence):
                for n in groupe['numeros']:
                    part = next(p for p in licence['repartition']['parts'] if p['numero'] == n)
                    arbre = xml_licence.preparer(xml_licence.vue_part(licence, part, groupe['numeros']), modele)
                    references.append(dict(parts=[n], libelle=f'part {n}',
                                           contenu=ET.tostring(arbre.getroot(), encoding='unicode')))
            return references
        except (ValueError, OSError, ET.ParseError, KeyError, StopIteration):
            pass
    references = []
    for entree in xml.get('fichiers') or [dict(parts=[1], fichier=xml.get('fichier'))]:
        try:
            contenu = entree.get('contenu') or Path(entree['fichier']).read_text(encoding='utf-8')
        except (OSError, TypeError, KeyError):
            contenu = xml.get('contenu') if entree.get('parts') == [1] or len(xml.get('fichiers') or []) <= 1 else None
        if contenu:
            references.append(dict(parts=list(entree.get('parts') or [1]),
                                   libelle=xml_licence.libelle_parts(list(entree.get('parts') or [1])), contenu=contenu))
    return references


def enregistrer_recuperations(numero, sydonias, fichier=None):
    """Compare un ou plusieurs XML SYDONIA [(chemin, contenu)] au XML attendu de la part qui leur correspond,
    puis conserve fichiers, références et résultats. Renvoie la liste des associations (voir associer)."""
    def action(licence):
        if not licence.get('xml_genere'):
            raise ValueError('Générez d’abord le XML à l’étape 7.')
        associations = recuperation_simulation.associer(references_xml(licence), [(str(c), t) for c, t in sydonias])
        maintenant = datetime.now(timezone.utc).isoformat()
        from asydec.declarations import declaration_licence
        imports = []
        for a in associations:
            try:
                # Contenu utile à l'étape 9 : cases présentes, complétées depuis AsyDec, manquantes.
                parts = a['reference']['parts']
                projet = declaration_licence.projet_part(licence, parts[0]) if len(parts) == 1 else None
                controle = declaration_licence.completer(a['contenu'], a['reference']['contenu'], projet)[1]
            except ET.ParseError:
                controle = None
            imports.append(dict(fichier=a['fichier'], contenu=a['contenu'], importe_le=maintenant,
                                parts=a['reference']['parts'], libelle=a['reference']['libelle'],
                                reference=a['reference']['contenu'], resume=a['comparaison']['resume'],
                                controle_declaration=controle))
        licence['recuperation_simulation'] = dict(contenu=imports[0]['contenu'], fichier=imports[0]['fichier'],
                                                  importe_le=maintenant, imports=imports,
                                                  resume=recuperation_simulation.resume_global(i['resume'] for i in imports))
        return associations
    return _modifier(numero, fichier, action)


def enregistrer_recuperation(numero, contenu, chemin, fichier=None):
    """Un seul XML SYDONIA : renvoie sa comparaison."""
    return enregistrer_recuperations(numero, [(chemin, contenu)], fichier)[0]['comparaison']


def enregistrer_declarations(numero, fiche, fichier=None):
    """Retient les déclarations Word de l'étape 9 (une par part)."""
    def action(licence):
        licence['declarations'] = dict(fiche, xml_genere_le=(licence.get('xml_genere') or {}).get('genere_le'),
                                       recuperation_le=(licence.get('recuperation_simulation') or {}).get('importe_le'))
    _modifier(numero, fichier, action)


def enregistrer_cvi(numero, fiche, fichier=None):
    from asydec.declarations import cvi
    with connexion(fichier) as conn:
        conn.execute('BEGIN IMMEDIATE')
        ligne = conn.execute('SELECT contenu FROM licences WHERE numero=?', (numero,)).fetchone()
        if ligne is None:
            raise ValueError('Cette licence est introuvable.')
        licence = json.loads(ligne['contenu'])
        if fiche.get('empreinte') != cvi.empreinte(licence, fiche.get('complements')):
            raise ValueError('Les données ont changé : recommencez les CVI.')
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='cvi_references'").fetchone():
            raise ValueError('Références CVI non réservées : rouvrez le formulaire CVI.')
        references = list(cvi.REFERENCES_CVI)
        if not cvi.numero_bl_connu(licence):
            references.append('NUMERO_BL')
        for cle in references:
            reserve = conn.execute('SELECT reference FROM cvi_references WHERE licence=? AND champ=?',
                                   (numero, cle)).fetchone()
            if not reserve or (fiche.get('complements') or {}).get(cle) != reserve['reference']:
                raise ValueError('Référence CVI non réservée ou modifiée : rouvrez le formulaire CVI.')
        licence['cvi_parts'] = fiche
        conn.execute('UPDATE licences SET contenu=?, modifie_le=? WHERE numero=?',
                     (json.dumps(licence, ensure_ascii=False, allow_nan=False),
                      datetime.now(timezone.utc).isoformat(), numero))
