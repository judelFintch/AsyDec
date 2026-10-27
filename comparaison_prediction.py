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
        ('taxes_globales','taxes_globales'),('taux','taux_change'),('fret','fret_externe_montant'),('assurance','assurance_montant'),('colis_total','colis_total'))},
        'colis': [a['colis'] for a in genere['articles']]}
    resultat['resume']['articles'] = [{k:a[c] for k,c in (
        ('poids','poids_brut'),('fob','fob'),('cif','cif'),('taxes','taxes_article'))} for a in genere['articles']]
    rapport = _comparer(resultat,genere,fourni,chemin_fourni,source_xml=True)
    rapport['source'] = str(Path(chemin_genere))
    rapport['plaque'] = genere['document']['camion'] or ''
    rapport['importateur'] = genere['document']['importateur'] or ''
    rapport['plaque_fournie'] = fourni['document']['camion'] or ''
    rapport['taxes_detail'] = detail_taxes(genere, fourni)
    return rapport


def _lignes_par_code(taxes):
    """Clé (code, n-ième occurrence) : un code répété reste distinct, sans fusion silencieuse."""
    vues, sortie = {}, {}
    for t in taxes:
        n = vues[t['code']] = vues.get(t['code'], 0) + 1
        sortie[(t['code'], n)] = t
    return sortie


def detail_taxes(genere, fourni):
    """Chaque ligne de taxe estimée (XML généré) face à la comparée (fichier fourni), écart = comparé − estimé."""
    lignes, totaux = [], {}
    def ajouter(position, article, taxe, e, c, cumuler=True):
        me, mc = _decimal(e.get('montant')), _decimal(c.get('montant'))
        ecart = mc - me if me is not None and mc is not None else None
        if not e:
            etat = 'Absente du XML généré'
        elif not c:
            etat = 'Absente du fichier fourni'
        elif ecart is None:
            etat = 'Donnée absente'
        elif _decimal(e.get('taux')) != _decimal(c.get('taux')):
            etat = 'Taux différent'
        else:
            etat = 'Identique' if ecart == 0 else 'Écart observé'
        lignes.append(dict(position=position, article=article, taxe=taxe,
            base_estimee=_decimal(e.get('base')), base_comparee=_decimal(c.get('base')),
            taux_estime=_decimal(e.get('taux')), taux_compare=_decimal(c.get('taux')),
            estime=me, compare=mc, ecart=ecart,
            pourcentage=ecart / abs(me) * 100 if ecart is not None and me != 0 else None, etat=etat))
        if cumuler:
            total = totaux.setdefault(taxe, [Decimal(0), Decimal(0), True, True])
            for i, m in ((0, me), (1, mc)):
                if m is None:
                    total[2 + i] = False
                else:
                    total[i] += m
    articles_g = {a['position']: a for a in genere['articles']}
    articles_f = {a['position']: a for a in fourni['articles']}
    for position in sorted(set(articles_g) | set(articles_f)):
        ag, af = articles_g.get(position, {}), articles_f.get(position, {})
        tg, tf = _lignes_par_code(ag.get('taxes', [])), _lignes_par_code(af.get('taxes', []))
        article = ag.get('code') or af.get('code') or '—'
        for cle in list(tg) + [k for k in tf if k not in tg]:
            ajouter(position, article, cle[0], tg.get(cle, {}), tf.get(cle, {}))
    for code, (e, c, complet_e, complet_c) in totaux.items():
        ajouter('Total', 'Articles', code, {'montant': e} if complet_e else {'montant': None},
                {'montant': c} if complet_c else {'montant': None}, cumuler=False)
    gg, gf = _lignes_par_code(genere['taxes_globales']), _lignes_par_code(fourni['taxes_globales'])
    for cle in list(gg) + [k for k in gf if k not in gg]:
        ajouter('Globale', '', cle[0], gg.get(cle, {}), gf.get(cle, {}), cumuler=False)
    return lignes


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
                libelle='Total déclaration CDF' if position == 'Total global' and metrique == 'taxes' else libelle, prevu=p, fourni=f, ecart=ecart, pourcentage=pourcentage, etat=etat))
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
    def somme_complete(valeurs):
        valeurs = list(valeurs)
        return sum(valeurs, Decimal(0)) if valeurs and all(v is not None for v in valeurs) else None
    taxes_articles_prevues = _decimal(resume.get('taxes_articles')) if 'taxes_articles' in resume else somme_complete(
        _decimal(a['taxes']) for a in resume['articles'])
    taxes_articles_fournies = somme_complete(_decimal(a['taxes_article']) for a in fourni['articles'])
    for metrique,libelle,p,f in (
        ('taxes_articles','Taxes articles CDF',taxes_articles_prevues,taxes_articles_fournies),
        ('taxes_globales','Taxes globales CDF',_decimal(resume.get('taxes_globales')), _decimal(vf['taxes_globales']))):
        ecart = f-p if p is not None and f is not None else None
        lignes.append(dict(position='Total global',code='',designation=libelle,metrique=metrique,libelle=libelle,
            prevu=p,fourni=f,ecart=ecart,pourcentage=ecart/abs(p)*100 if ecart is not None and p!=0 else None,
            etat='Donnée absente' if ecart is None else 'Identique' if ecart==0 else 'Écart observé'))
    # Un changement de contexte découvert sur un article concerne aussi ceux déjà ajoutés.
    if contextes:
        for ligne in lignes:
            if ligne['metrique'] in ('cif', 'taxes', 'taxes_articles', 'taxes_globales') and ligne['ecart'] is not None:
                ligne['etat'] = 'Contexte différent / non vérifiable'
    return dict(lignes=lignes, contexte=contextes, avertissements=avertissements,
                taux_genere=_decimal(resume.get('taux')), taux_fourni=_decimal(vf['taux_change']),
                fichier=str(Path(chemin_fourni)), devise_prevue=base['document']['devise'],
                devise_fournie= fourni['document']['devise'])


def _fr(valeur, decimales=0):
    """Format français : 1234567.5 -> « 1 234 567,50 »."""
    return f'{valeur:,.{decimales}f}'.replace(',', ' ').replace('.', ',')


def synthese_taxes(rapport):
    """Totaux de taxes (estimé, comparé, écart, %) et explication en phrases simples."""
    ligne = lambda metrique: next((l for l in rapport['lignes']
                                   if l['position'] == 'Total global' and l['metrique'] == metrique), None)
    total = ligne('taxes')
    sortie = {'estime': None, 'compare': None, 'ecart': None, 'pourcentage': None, 'phrases': []}
    if total is None or total['prevu'] is None or total['fourni'] is None:
        sortie['phrases'].append("Le total des taxes manque dans l'un des deux XML : la comparaison du total est impossible.")
        return sortie
    estime, compare, ecart = total['prevu'], total['fourni'], total['ecart']
    sortie.update(estime=estime, compare=compare, ecart=ecart, pourcentage=total['pourcentage'])
    phrases = sortie['phrases']
    if ecart == 0:
        phrases.append('Le fichier comparé déclare exactement le même total de taxes que l’estimation.')
        return sortie
    sens = 'plus' if ecart > 0 else 'moins'
    pourcentage = f" ({_fr(total['pourcentage'], 2)} %)" if total['pourcentage'] is not None else ''
    phrases.append(f'Le fichier comparé déclare {_fr(abs(ecart))} CDF de {sens} que l’estimation{pourcentage}.')
    taux_g, taux_f = rapport.get('taux_genere'), rapport.get('taux_fourni')
    if taux_g and taux_f and taux_g != taux_f:
        # Approximation : les taxes suivent surtout la valeur en CDF, donc le taux de change.
        effet = estime * (taux_f / taux_g - 1)
        phrase = (f'Le taux de change n’est pas le même ({_fr(taux_g, 2)} → {_fr(taux_f, 2)} CDF par unité de devise). '
                  f'À lui seul, il représente environ {_fr(effet)} CDF')
        reste = ecart - effet
        if abs(reste) <= abs(ecart) / 10:
            phrases.append(phrase + ' : presque tout l’écart vient du taux.')
        else:
            phrases.append(phrase + '.')
            phrases.append(f'Le reste, environ {_fr(reste)} CDF, vient d’autres différences : voir « Détails des taxes… ».')
    else:
        phrases.append('Le taux de change est le même : l’écart vient des montants des articles ou des taxes globales. '
                       'Voir « Détails des taxes… ».')
    globales = ligne('taxes_globales')
    if globales and globales['ecart']:
        phrases.append(f"Taxes globales : {_fr(globales['ecart'])} CDF d'écart.")
    articles = [l for l in rapport['lignes'] if l['metrique'] == 'taxes' and l['position'] != 'Total global'
                and l['ecart'] is not None]
    if articles:
        pire = max(articles, key=lambda l: abs(l['ecart']))
        if pire['ecart']:
            phrases.append(f"Plus gros écart par article : art. {pire['position']} ({pire['code']}), {_fr(pire['ecart'])} CDF.")
    return sortie
