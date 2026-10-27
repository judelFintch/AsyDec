"""Comparaison descriptive en lecture seule d'un aperçu avec un fichier fourni."""
from decimal import Decimal
from pathlib import Path
from import_references import extraire

METRIQUES = (('poids', 'Poids kg'), ('fob', 'FOB (devise)'), ('colis', 'Colis'),
             ('ratio', 'Ratio FOB/kg'), ('cif', 'CIF CDF'), ('taxes', 'Taxes CDF'))


def _decimal(valeur):
    return Decimal(str(valeur)) if valeur is not None else None


def _ratio(fob, poids):
    return fob / poids if fob is not None and poids is not None and poids > 0 else None


def comparer(resultat, chemin_base, chemin_fourni):
    """Écart = fichier fourni moins aperçu ; aucune acceptation n'est déduite."""
    base = extraire(Path(chemin_base).read_bytes())
    fourni = extraire(Path(chemin_fourni).read_bytes())
    return _comparer(resultat, base, fourni, chemin_fourni)


def comparer_xmls(chemin_genere, chemin_fourni):
    """Compare les valeurs effectivement inscrites dans le XML généré, sans recalcul."""
    genere = extraire(Path(chemin_genere).read_bytes())
    fourni = extraire(Path(chemin_fourni).read_bytes())
    v = genere['valorisation']
    resultat = {'resume': {k: v[c] for k,c in (
        ('poids','poids_total'),('fob','fob_total'),('cif','cif_total'),('taxes_totales','taxes_totales'),
        ('taux','taux_change'),('fret','fret_externe_montant'),('assurance','assurance_montant'),('colis_total','colis_total'))},
        'colis': [a['colis'] for a in genere['articles']]}
    resultat['resume']['articles'] = [{k:a[c] for k,c in (
        ('poids','poids_brut'),('fob','fob'),('cif','cif'),('taxes','taxes_article'))} for a in genere['articles']]
    rapport = _comparer(resultat,genere,fourni,chemin_fourni,source_xml=True)
    rapport['source'] = str(Path(chemin_genere))
    return rapport


def _comparer(resultat, base, fourni, chemin_fourni, source_xml=False):
    resume = resultat['resume']
    avertissements = []
    for origine, donnees in (('Base', base), ('Fichier fourni', fourni)):
        avertissements.extend(f'{origine} : {d[2]}' for d in donnees['diagnostics'])
    contextes = []
    def contexte(libelle, avant, apres):
        if avant is None or apres is None or avant == '' or apres == '':
            contextes.append(f'{libelle} absent : contexte non vérifiable.')
        elif avant != apres:
            contextes.append(f'{libelle} différent : {avant} → {apres}.')
    contexte('Importateur', base['document']['importateur'], fourni['document']['importateur'])
    contexte('Devise', base['document']['devise'], fourni['document']['devise'])
    vb, vf = base['valorisation'], fourni['valorisation']
    for libelle, cle, cle_resume in (
        ('Taux de change', 'taux_change', 'taux'), ('Fret externe', 'fret_externe_montant', 'fret'),
        ('Assurance', 'assurance_montant', 'assurance')):
        contexte(libelle, _decimal(resume.get(cle_resume)), _decimal(vf[cle]))
    for cle in ('fret_externe_devise', 'assurance_devise', 'fret_interne_monnaie_nationale',
                'autres_couts_monnaie_nationale', 'deductions_monnaie_nationale'):
        if vb[cle] != vf[cle]:
            contextes.append(f'{cle} différent : {vb[cle]} → {vf[cle]}.')
    if [(t['code'], t['taux']) for t in base['taxes_globales']] != [(t['code'], t['taux']) for t in fourni['taxes_globales']]:
        contextes.append('Codes ou taux de taxes globales différents.')
    # Le calcul ignore les lignes sans FOB ; conserver leur position XML plutôt que renuméroter.
    sources = base['articles'] if source_xml else [a for a in base['articles'] if a['fob'] is not None and Decimal(a['fob']) != 0]
    if len(sources) != len(resume['articles']) or len(sources) != len(resultat['colis']):
        raise ValueError("Les articles de l'aperçu ne correspondent plus au XML de base. Recalculez l'aperçu.")
    predictions = {}
    for a, calcule, colis in zip(sources, resume['articles'], resultat['colis']):
        valeurs = {k: _decimal(calcule[k]) for k in ('poids', 'fob', 'cif', 'taxes')}
        valeurs.update(colis=_decimal(colis), ratio=_ratio(valeurs['fob'], valeurs['poids']))
        predictions[a['position']] = (a, valeurs)
    reels = {a['position']: a for a in fourni['articles']}
    lignes = []
    devise_identique = bool(base['document']['devise']) and base['document']['devise'] == fourni['document']['devise']
    def ajouter(position, code, nom, prevu, actuel, compatible=True, motif=''):
        for metrique, libelle in METRIQUES:
            p, f = prevu.get(metrique), actuel.get(metrique)
            comparable = compatible and (devise_identique or metrique not in ('fob', 'ratio'))
            ecart = f - p if comparable and p is not None and f is not None else None
            pourcentage = ecart / abs(p) * 100 if ecart is not None and p != 0 else None
            etat = motif if not compatible else ('Devise différente ou absente' if not comparable else
                    'Donnée absente' if ecart is None else 'Contexte différent / non vérifiable' if contextes and metrique in ('cif', 'taxes') else
                    'Identique' if ecart == 0 else 'Écart observé')
            lignes.append(dict(position=position, code=code, designation=nom, metrique=metrique,
                libelle=libelle, prevu=p, fourni=f, ecart=ecart, pourcentage=pourcentage, etat=etat))
    for position in sorted(set(predictions) | set(reels)):
        source, prevu = predictions.get(position, ({}, {}))
        actuel = reels.get(position, {})
        valeurs = {k: _decimal(actuel.get(c)) for k, c in
                   (('poids', 'poids_brut'), ('fob', 'fob'), ('colis', 'colis'), ('cif', 'cif'), ('taxes', 'taxes_article'))}
        valeurs['ratio'] = _ratio(valeurs['fob'], valeurs['poids'])
        compatible = bool(source and actuel and source['code'] and source['code'] == actuel['code'])
        motif = 'Article absent du fichier fourni' if not actuel else 'Article absent de l’aperçu' if not source else 'Code différent ou absent à cette position'
        if not compatible:
            avertissements.append(f'Position {position} : {motif}.')
        elif [(t['code'], t['taux']) for t in source['taxes']] != [(t['code'], t['taux']) for t in actuel['taxes']]:
            contextes.append(f'Position {position} : codes ou taux de taxes différents.')
        ajouter(position, actuel.get('code') or source.get('code') or '—',
                actuel.get('designation') or source.get('designation') or '', prevu, valeurs, compatible, motif)
    prevu = {k: _decimal(resume[c]) for k, c in (('poids', 'poids'), ('fob', 'fob'), ('cif', 'cif'), ('taxes', 'taxes_totales'))}
    prevu['colis'] = _decimal(resume['colis_total']) if 'colis_total' in resume else sum(_decimal(c) for c in resultat['colis'])
    prevu['ratio'] = _ratio(prevu['fob'], prevu['poids'])
    actuel = {k: _decimal(vf[c]) for k, c in (('poids', 'poids_total'), ('fob', 'fob_total'), ('colis', 'colis_total'), ('cif', 'cif_total'), ('taxes', 'taxes_totales'))}
    actuel['ratio'] = _ratio(actuel['fob'], actuel['poids'])
    ajouter('Total global', '', 'Ratio global = FOB total / poids total', prevu, actuel)
    # Un changement de contexte découvert sur un article concerne aussi ceux déjà ajoutés.
    if contextes:
        for ligne in lignes:
            if ligne['metrique'] in ('cif', 'taxes') and ligne['ecart'] is not None:
                ligne['etat'] = 'Contexte différent / non vérifiable'
    return dict(lignes=lignes, contexte=contextes, avertissements=avertissements,
                fichier=str(Path(chemin_fourni)), devise_prevue=base['document']['devise'],
                devise_fournie= fourni['document']['devise'])
