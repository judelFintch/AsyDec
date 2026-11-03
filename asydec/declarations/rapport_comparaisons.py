"""Rapport de toutes les comparaisons « XML généré / XML comparé » enregistrées, avec leur analyse.

Lecture seule : rien n'est écrit dans la base des modèles ni dans les fichiers comparés.
Convention partout : écart = XML comparé − XML généré (positif = le fichier comparé déclare plus).

Chaque comparaison reçoit d'abord un diagnostic, car un écart de taxes n'a pas le même sens selon
ce qui est comparé : même répartition (le calcul est en jeu), répartition différente des mêmes
totaux, ou autre dossier (seuls les ratios FOB/kg des articles restent instructifs).
"""
from decimal import Decimal
from pathlib import Path
from statistics import mean

from asydec.declarations import modeles_generes as service
from asydec.formats import nombre

IDENTIQUE, TAUX, CALCUL = 'Identique', 'Écart dû au taux', 'Écart de calcul'
REPARTITION, AUTRE, NON_VERIFIABLE = 'Répartition différente', 'Autre dossier', 'Non vérifiable'
DIAGNOSTICS = (CALCUL, TAUX, IDENTIQUE, REPARTITION, AUTRE, NON_VERIFIABLE)
MEME_REPARTITION = (IDENTIQUE, TAUX, CALCUL)

TOLERANCE_ARRONDI = Decimal(10)      # CDF : taux identique, écart dû aux seuls arrondis des lignes
TOLERANCE_TAUX = Decimal('0.02')     # % : reste admis après neutralisation du taux (effet non linéaire)
SEUIL_TAXE = 0.1                     # % hors taux : écart d'un code de taxe jugé significatif
SEUIL_ARTICLE = 5.0                  # % : écart moyen de ratio FOB/kg d'un article jugé significatif
DETAIL_ENREGISTRE, DETAIL_RECONSTITUE, TOTAUX_SEULS = 'Enregistré', 'Reconstitué', 'Totaux seuls'


def _float(valeur):
    return float(valeur) if valeur is not None else None


def _pct(ecart, base):
    return ecart / abs(base) * 100 if ecart is not None and base else None


def _signe(x, decimales=2):
    return ('+' if x > 0 else '') + nombre(x, decimales)


def _variation_taux(rapport):
    """Variation relative des montants en CDF due au seul taux : taux comparé / taux généré − 1."""
    tg, tf = (rapport or {}).get('taux_genere'), (rapport or {}).get('taux_fourni')
    return Decimal(str(tf)) / Decimal(str(tg)) - 1 if tg and tf and tg != tf else Decimal(0)


# =============================================================================
# Collecte et diagnostic
# =============================================================================
def diagnostiquer(entree):
    """(diagnostic, raisons) d'une comparaison ; raisons = phrases courtes qui le justifient."""
    rapport, ecart = entree['rapport'], entree['ecart']
    if not rapport:
        return (IDENTIQUE, []) if ecart == 0 else (NON_VERIFIABLE, ['Détail indisponible'])
    totaux = {l['metrique']: l for l in rapport['lignes'] if l['position'] == 'Total global'}
    articles = [l for l in rapport['lignes'] if l['position'] != 'Total global']
    raisons = [c.split(' :')[0] for c in rapport.get('contexte', [])
               if c.startswith(('Importateur différent', 'Devise différent'))]
    raisons += [f"{totaux[m]['libelle']} {nombre(totaux[m]['prevu'], 0)} → {nombre(totaux[m]['fourni'], 0)}"
                for m in ('poids', 'fob') if m in totaux and totaux[m]['ecart'] not in (0, None)]
    if any(l['etat'].startswith(('Article absent', 'Code différent')) for l in articles):
        raisons.append('Articles différents')
    if raisons:
        return AUTRE, raisons
    deplaces = sorted({str(l['position']) for l in articles
                       if l['metrique'] in ('poids', 'fob', 'colis') and l['ecart'] not in (0, None)})
    if deplaces or totaux.get('colis', {}).get('ecart') not in (0, None):
        return REPARTITION, [f"Article(s) {', '.join(deplaces)} répartis autrement" if deplaces else 'Colis différents']
    if ecart == 0:
        return IDENTIQUE, []
    reste = ecart - entree['effet_taux']
    if entree['effet_taux'] == 0:
        return (IDENTIQUE, ['Arrondis']) if abs(reste) <= TOLERANCE_ARRONDI else (CALCUL, ['Même taux, même répartition'])
    if entree['estime'] and abs(reste) / abs(entree['estime']) * 100 <= TOLERANCE_TAUX:
        return TAUX, [f"Taux {nombre(entree['taux_genere'], 2)} → {nombre(entree['taux_fourni'], 2)}"]
    return CALCUL, ['Reste après neutralisation du taux']


def construire_entree(modele, comparaison, rapport, origine=DETAIL_ENREGISTRE):
    """Entrée du rapport : modele = ligne de lister(), comparaison = élément de comparaisons()."""
    estime, ecart = comparaison['total_estime'], comparaison['ecart_total']
    # Les taxes suivent la valeur en CDF : à répartition égale, un autre taux les décale d'autant.
    effet_taux = estime * _variation_taux(rapport) if estime is not None else Decimal(0)
    entree = dict(
        evenement=comparaison['evenement'], modele=modele['id'], date_utc=comparaison['date_utc'],
        auteur=comparaison['auteur'], plaque=modele['plaque'], importateur=modele['importateur'],
        statut=modele['statut'], note=modele.get('note'), fichier=comparaison['fichier'], estime=estime,
        compare=comparaison['total_compare'], ecart=ecart, pourcentage=_pct(ecart, estime),
        taux_genere=(rapport or {}).get('taux_genere'), taux_fourni=(rapport or {}).get('taux_fourni'),
        effet_taux=effet_taux, ecart_hors_taux=ecart - effet_taux if ecart is not None else None,
        contexte=list((rapport or {}).get('contexte', [])), rapport=rapport, origine=origine, repetitions=1)
    entree['pourcentage_hors_taux'] = _pct(entree['ecart_hors_taux'], estime)
    entree['diagnostic'], entree['raisons'] = diagnostiquer(entree)
    return entree


def collecter(base=None, module=None):
    """Une entrée par comparaison (modèles non supprimés), la plus récente d'abord.
    Un même fichier comparé plusieurs fois au même modèle n'est compté qu'une fois."""
    entrees, vues = [], {}
    for m in service.lister(base=base, module=module):
        if not m['comparaisons']:
            continue
        d = service.detail(m['id'], base=base)
        for c in service.comparaisons(d):  # la plus récente d'abord
            cle = (m['id'], c['fichier'], c['total_compare'])
            if cle in vues:
                vues[cle]['repetitions'] += 1
                continue
            rapport, origine = c['rapport'], DETAIL_ENREGISTRE
            if not rapport:
                rapport = service.reconstituer_comparaison(d, c, base=base)
                origine = DETAIL_RECONSTITUE if rapport else TOTAUX_SEULS
            entree = vues[cle] = construire_entree(m, c, rapport, origine)
            entrees.append(entree)
    entrees.sort(key=lambda e: e['date_utc'], reverse=True)
    return entrees


# =============================================================================
# Analyse
# =============================================================================
def _sens(valeurs, tolerance=0.0):
    signes = {(v > tolerance) - (v < -tolerance) for v in valeurs}
    signes.discard(0)
    return 'aucun' if not signes else 'plus' if signes == {1} else 'moins' if signes == {-1} else 'variable'


GLOBALES = 'Taxes globales'


def _globales_non_detaillees(rapport):
    """Les XML ne donnent souvent que le montant des taxes globales, sans leurs lignes :
    ce montant devient alors une ligne « Taxes globales » à part entière."""
    if not rapport or any(l['position'] == 'Globale' for l in rapport.get('taxes_detail') or []):
        return []
    total = next((l for l in rapport['lignes'] if l['position'] == 'Total global' and l['metrique'] == 'taxes_globales'), None)
    if total is None:
        return []
    return [dict(position='Globale', taxe=GLOBALES, estime=total['prevu'], compare=total['fourni'],
                 ecart=total['ecart'], etat=total['etat'])]


def decomposition(entree):
    """{'articles': CDF, 'globales': CDF} : écart hors taux des taxes des articles et des taxes globales."""
    variation = _variation_taux(entree['rapport'])
    sortie = {}
    for l in (entree['rapport'] or {}).get('lignes', []):
        if l['position'] == 'Total global' and l['metrique'] in ('taxes_articles', 'taxes_globales') \
                and l['ecart'] is not None and l['prevu'] is not None:
            sortie[l['metrique'].split('_')[1]] = l['ecart'] - l['prevu'] * variation
    return sortie


def par_taxe(entrees):
    """Par code de taxe, sur les comparaisons à répartition identique seulement, taux neutralisé."""
    groupes = {}
    for e in entrees:
        if e['diagnostic'] not in MEME_REPARTITION:
            continue
        lignes = (e['rapport'] or {}).get('taxes_detail') or []
        variation = _variation_taux(e['rapport'])
        taux_differents = {l['taxe'] for l in lignes if l['etat'] == 'Taux différent'}
        absentes = {l['taxe'] for l in lignes if str(l['etat']).startswith('Absente')}
        for l in lignes + _globales_non_detaillees(e['rapport']):
            if l['position'] not in ('Total', 'Globale'):
                continue
            portee = 'Globale' if l['position'] == 'Globale' else 'Articles'
            g = groupes.setdefault((l['taxe'], portee), dict(
                taxe=l['taxe'], portee=portee, n=0, estime=0.0, compare=0.0, ecart=0.0, ecart_hors_taux=0.0,
                pourcentages_hors_taux=[], taux_differents=0, absentes=0))
            g['n'] += 1
            g['taux_differents'] += l['taxe'] in taux_differents
            g['absentes'] += l['taxe'] in absentes
            if l['ecart'] is None:
                continue
            hors_taux = l['ecart'] - l['estime'] * variation
            g['estime'] += float(l['estime'])
            g['compare'] += float(l['compare'])
            g['ecart'] += float(l['ecart'])
            g['ecart_hors_taux'] += float(hors_taux)
            if l['estime']:
                g['pourcentages_hors_taux'].append(float(hors_taux / abs(l['estime']) * 100))
    for g in groupes.values():
        g['pourcentage'] = _pct(g['ecart'], g['estime'])
        g['pourcentage_hors_taux'] = _pct(g['ecart_hors_taux'], g['estime'])
        g['sens'] = _sens(g['pourcentages_hors_taux'], SEUIL_TAXE)
    return sorted(groupes.values(), key=lambda g: -abs(g['ecart_hors_taux']))


def par_article(entrees):
    """Par article (code + désignation). Ratio FOB/kg : toutes les comparaisons, y compris d'autres
    dossiers ; poids, FOB et colis : répartitions différentes ; taxes : hors autres dossiers."""
    groupes = {}
    for e in entrees:
        diagnostic = e['diagnostic']
        for l in (e['rapport'] or {}).get('lignes', []):
            if l['position'] == 'Total global' or l['pourcentage'] is None:
                continue
            metrique = l['metrique']
            if (metrique in ('poids', 'fob', 'colis') and diagnostic != REPARTITION) or \
               (metrique == 'taxes' and diagnostic == AUTRE) or metrique == 'cif':
                continue
            cle = (l['code'] or '—', ' '.join(str(l['designation'] or '').upper().split()))
            g = groupes.setdefault(cle, dict(code=cle[0], designation=l['designation'] or '', comparaisons=set(),
                                             poids=[], fob=[], colis=[], ratio=[], taxes=[]))
            g['comparaisons'].add(e['evenement'])
            g[metrique].append(float(l['pourcentage']))
    for g in groupes.values():
        g['n'] = len(g.pop('comparaisons'))
        for m in ('poids', 'fob', 'colis', 'ratio', 'taxes'):
            g[m + '_moyen'] = mean(g[m]) if g[m] else None
    return sorted(groupes.values(), key=lambda g: -abs(g['ratio_moyen'] or 0))


def par_importateur(entrees):
    groupes = {}
    for e in entrees:
        g = groupes.setdefault(e['importateur'] or '—', dict(importateur=e['importateur'] or '—', n=0,
            pourcentages=[], hors_taux=[], diagnostics={}))
        g['n'] += 1
        g['diagnostics'][e['diagnostic']] = g['diagnostics'].get(e['diagnostic'], 0) + 1
        if e['pourcentage'] is not None:
            g['pourcentages'].append(float(e['pourcentage']))
        if e['diagnostic'] in MEME_REPARTITION and e['pourcentage_hors_taux'] is not None:
            g['hors_taux'].append(float(e['pourcentage_hors_taux']))
    for g in groupes.values():
        g['moyen'] = mean(g['pourcentages']) if g['pourcentages'] else None
        g['hors_taux_moyen'] = mean(g['hors_taux']) if g['hors_taux'] else None
    return sorted(groupes.values(), key=lambda g: -g['n'])


def indicateurs(entrees):
    meme = [e for e in entrees if e['diagnostic'] in MEME_REPARTITION and e['pourcentage_hors_taux'] is not None]
    hors_taux = [float(e['pourcentage_hors_taux']) for e in meme]
    p = [float(e['pourcentage']) for e in entrees if e['pourcentage'] is not None]
    return dict(
        n=len(entrees), modeles=len({e['modele'] for e in entrees}),
        diagnostics={d: sum(1 for e in entrees if e['diagnostic'] == d) for d in DIAGNOSTICS},
        moyen=mean(p) if p else None, absolu_moyen=mean(abs(x) for x in p) if p else None,
        meme_repartition=len(meme), hors_taux_moyen=mean(hors_taux) if hors_taux else None,
        hors_taux_max=max(hors_taux, key=abs) if hors_taux else None,
        taux_differents=sum(1 for e in entrees if e['effet_taux']),
        repetees=sum(e['repetitions'] - 1 for e in entrees),
        totaux_seuls=sum(1 for e in entrees if e['origine'] == TOTAUX_SEULS),
        reconstituees=sum(1 for e in entrees if e['origine'] == DETAIL_RECONSTITUE))


def _taxes_responsables(entree, combien=3):
    """Codes de taxe qui portent le plus l'écart hors taux d'une comparaison."""
    variation = _variation_taux(entree['rapport'])
    lignes = [(l['taxe'], l['ecart'] - l['estime'] * variation)
              for l in ((entree['rapport'] or {}).get('taxes_detail') or []) + _globales_non_detaillees(entree['rapport'])
              if l['position'] in ('Total', 'Globale') and l['ecart'] is not None]
    lignes = sorted((t for t in lignes if t[1]), key=lambda t: -abs(t[1]))[:combien]
    return ', '.join(f'{code} {_signe(float(e), 0)}' for code, e in lignes)


def _bases_communes(taxes):
    """Groupes d'au moins 3 taxes au même écart hors taux (±0,05 point) et de même sens :
    c'est leur base commune (valeur CIF en CDF) qui diffère, pas chacune d'elles."""
    candidates = sorted((t for t in taxes if t['pourcentage_hors_taux'] is not None
                         and abs(t['pourcentage_hors_taux']) >= SEUIL_TAXE and t['portee'] == 'Articles'),
                        key=lambda t: t['pourcentage_hors_taux'])
    groupes, courant = [], []
    for t in candidates:
        if courant and abs(t['pourcentage_hors_taux'] - courant[0]['pourcentage_hors_taux']) > 0.05:
            groupes.append(courant)
            courant = []
        courant.append(t)
    if courant:
        groupes.append(courant)
    return [g for g in groupes if len(g) >= 3]


def constats(entrees, ind=None, taxes=None, articles=None):
    """Ce qu'il faut retenir, du plus important au plus secondaire, en phrases simples."""
    if not entrees:
        return ['Aucune comparaison enregistrée. Dans « Vérifier et générer » ou « Modèles générés », '
                'utilisez « Comparer avec un XML… » : chaque comparaison apparaîtra ici.']
    ind = ind or indicateurs(entrees)
    taxes = par_taxe(entrees) if taxes is None else taxes
    articles = par_article(entrees) if articles is None else articles
    compte = ind['diagnostics']
    parts = [f"{compte[d]} {d.lower()}" for d in DIAGNOSTICS if compte[d]]
    phrases = [f"{ind['n']} comparaison(s) sur {ind['modeles']} modèle(s) : {', '.join(parts)}."]

    # 1. Le calcul lui-même : seul cas qui demande une correction du moteur ou du barème.
    calculs = [e for e in entrees if e['diagnostic'] == CALCUL]
    for e in calculs:
        parts = decomposition(e)
        detail = ' (' + ', '.join(f"taxes {k} {_signe(float(v), 0)}" for k, v in parts.items()) + ')' if parts else ''
        phrases.append(f"⚠ Modèle N° {e['modele']} ({e['plaque'] or 'sans plaque'}) : à répartition identique, il reste "
                       f"{_signe(float(e['ecart_hors_taux']), 0)} CDF ({_signe(float(e['pourcentage_hors_taux']), 3)} %) "
                       f"une fois le taux neutralisé{detail}. Principales taxes : {_taxes_responsables(e) or '—'}.")
        reste = abs(e['ecart_hors_taux'])
        if reste and abs(parts.get('globales', 0)) >= reste * Decimal('0.8'):
            phrases.append("   → L'écart vient des taxes globales. Le moteur les reprend telles quelles du XML de base, "
                           "sans les recalculer : vérifiez leur montant dans le XML de base de ce dossier.")
        elif reste and abs(parts.get('articles', 0)) >= reste * Decimal('0.8'):
            phrases.append("   → L'écart vient des taxes des articles : comparez leurs bases et taux dans « Détails des taxes… ».")
    if ind['meme_repartition'] and not calculs:
        phrases.append(f"✓ Calcul fiable : sur {ind['meme_repartition']} comparaison(s) à répartition identique, aucun écart "
                       f"ne subsiste une fois le taux neutralisé (au plus {_signe(ind['hors_taux_max'], 3)} %, arrondis).")

    # 2. Le taux de change : écart réel, mais qui ne vient pas du calcul.
    dues_au_taux = [e for e in entrees if e['diagnostic'] == TAUX]
    if dues_au_taux:
        ecart = sum(float(e['ecart']) for e in dues_au_taux)
        exemples = '; '.join(f"N° {e['modele']} : {nombre(e['taux_genere'], 2)} → {nombre(e['taux_fourni'], 2)}"
                             for e in dues_au_taux[:3])
        phrases.append(f"{len(dues_au_taux)} écart(s) s'expliquent entièrement par le taux de change ({_signe(ecart, 0)} CDF "
                       f"au total ; {exemples}). Saisissez le taux du jour de la déclaration avant de générer.")

    # 3. Taxes : barème ou base commune.
    for t in taxes:
        if t['taux_differents']:
            phrases.append(f"Taxe {t['taxe']} : taux différent dans {t['taux_differents']} comparaison(s) sur {t['n']} — "
                           "le barème du XML de base n'est peut-être plus à jour.")
    groupes = _bases_communes(taxes)
    dans_un_groupe = {(t['taxe'], t['portee']) for g in groupes for t in g}
    for g in groupes:
        p = mean(t['pourcentage_hors_taux'] for t in g)
        phrases.append(f"{len(g)} taxes ({', '.join(t['taxe'] for t in g)}) diffèrent toutes d'environ {_signe(p)} % hors taux : "
                       "c'est leur base commune (valeur CIF en CDF) qui diffère, pas leurs taux.")
    for t in taxes:
        if ((t['taxe'], t['portee']) not in dans_un_groupe and t['pourcentage_hors_taux'] is not None
                and abs(t['pourcentage_hors_taux']) >= SEUIL_TAXE and t['sens'] in ('plus', 'moins')):
            nom = 'Taxes globales' if t['taxe'] == GLOBALES else f"Taxe {t['taxe']} ({t['portee'].lower()})"
            phrases.append(f"{nom} : toujours {t['sens']} élevée(s) dans les fichiers comparés, "
                           f"{_signe(t['pourcentage_hors_taux'])} % hors taux ({_signe(t['ecart_hors_taux'], 0)} CDF).")
        if t['absentes']:
            phrases.append(f"Taxe {t['taxe']} : présente d'un seul côté dans {t['absentes']} comparaison(s).")

    # 4. Répartitions : où les déclarations comparées placent autrement le poids et le FOB.
    if compte[REPARTITION]:
        deplaces = sorted((a for a in articles if a['poids_moyen']), key=lambda a: -abs(a['poids_moyen']))[:3]
        detail = '; '.join(f"art. {a['code']} {_signe(a['poids_moyen'], 1)} % de poids" for a in deplaces)
        phrases.append(f"{compte[REPARTITION]} comparaison(s) aux mêmes totaux mais répartis autrement"
                       + (f" : {detail}." if detail else '.') + " Leurs écarts de taxes viennent de cette répartition.")

    # 5. Ratios FOB/kg : instructifs même d'un autre dossier.
    for a in articles:
        if a['ratio_moyen'] is not None and abs(a['ratio_moyen']) >= SEUIL_ARTICLE:
            phrases.append(f"Article {a['code']} · {a['designation'] or '—'} : ratio FOB/kg {_signe(a['ratio_moyen'], 1)} % "
                           f"en moyenne dans les fichiers comparés ({a['n']} comparaison(s)) — ratio "
                           f"{'plus bas' if a['ratio_moyen'] > 0 else 'plus haut'} dans les modèles générés.")
    if articles and not any(a['ratio_moyen'] is not None and abs(a['ratio_moyen']) >= SEUIL_ARTICLE for a in articles):
        ecart_max = max((a for a in articles if a['ratio_moyen'] is not None), key=lambda a: abs(a['ratio_moyen']), default=None)
        if ecart_max is not None:
            phrases.append(f"Ratios FOB/kg des articles proches des fichiers comparés : au plus "
                           f"{_signe(ecart_max['ratio_moyen'], 1)} % (art. {ecart_max['code']}).")

    # 6. Autres dossiers : on dit pourquoi ils ne jugent pas le calcul.
    autres = [e for e in entrees if e['diagnostic'] == AUTRE]
    if autres:
        raisons = {}
        for e in autres:
            for r in e['raisons']:
                raisons[r.split(' ')[0]] = raisons.get(r.split(' ')[0], 0) + 1
        phrases.append(f"{len(autres)} comparaison(s) portent sur un autre dossier ("
                       + ', '.join(f"{e['raisons'][0]}" for e in autres[:2])
                       + ") : leur écart de taxes n'évalue pas le calcul ; seuls leurs ratios FOB/kg sont exploités.")

    # 7. Qualité des données.
    if ind['repetees']:
        phrases.append(f"{ind['repetees']} comparaison(s) répétée(s) avec le même fichier : comptée(s) une seule fois.")
    if ind['reconstituees']:
        phrases.append(f"{ind['reconstituees']} ancienne(s) comparaison(s) détaillée(s) à nouveau à partir du XML exporté "
                       "archivé et du fichier comparé (inchangé).")
    if ind['totaux_seuls']:
        phrases.append(f"{ind['totaux_seuls']} ancienne(s) comparaison(s) n'ont que les totaux : le fichier comparé a été "
                       "déplacé ou modifié. Comparez à nouveau pour obtenir le détail.")
    return phrases


def analyser(entrees):
    """Toute l'analyse en une fois : indicateurs, tableaux par taxe, article et importateur, constats."""
    ind, taxes, articles = indicateurs(entrees), par_taxe(entrees), par_article(entrees)
    return dict(indicateurs=ind, taxes=taxes, articles=articles, importateurs=par_importateur(entrees),
                constats=constats(entrees, ind, taxes, articles))


# =============================================================================
# Export Excel
# =============================================================================
def _fraction(pourcentage):
    return float(pourcentage) / 100 if pourcentage is not None else None


def exporter(entrees, analyse, chemin):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from asydec.formats import date_locale
    wb = Workbook()
    synthese = wb.active
    synthese.title = 'SYNTHESE'
    synthese.append(['Ce qu’il faut retenir'])
    for p in analyse['constats']:
        synthese.append([p])
    comparaisons = wb.create_sheet('COMPARAISONS')
    comparaisons.append(['Date', 'Modèle N°', 'Plaque', 'Importateur', 'Fichier comparé', 'Diagnostic', 'Raisons',
                         'Taxes XML généré', 'Taxes XML comparé', 'Écart CDF', 'Écart %', 'Taux généré',
                         'Taux comparé', 'Effet du taux CDF', 'Écart hors taux CDF', 'Écart hors taux %', 'Détail'])
    for e in entrees:
        comparaisons.append([date_locale(e['date_utc']), e['modele'], e['plaque'], e['importateur'],
                             Path(e['fichier']).name, e['diagnostic'], ' ; '.join(e['raisons']),
                             _float(e['estime']), _float(e['compare']), _float(e['ecart']), _fraction(e['pourcentage']),
                             _float(e['taux_genere']), _float(e['taux_fourni']), _float(e['effet_taux']),
                             _float(e['ecart_hors_taux']), _fraction(e['pourcentage_hors_taux']), e['origine']])
    taxes = wb.create_sheet('TAXES')
    taxes.append(['Taxe', 'Portée', 'Comparaisons', 'Total XML générés', 'Total XML comparés', 'Écart CDF', 'Écart %',
                  'Écart hors taux CDF', 'Écart hors taux %', 'Sens', 'Taux différent', 'Absente d’un côté'])
    for t in analyse['taxes']:
        taxes.append([t['taxe'], t['portee'], t['n'], t['estime'], t['compare'], t['ecart'], _fraction(t['pourcentage']),
                      t['ecart_hors_taux'], _fraction(t['pourcentage_hors_taux']), t['sens'],
                      t['taux_differents'], t['absentes']])
    articles = wb.create_sheet('ARTICLES')
    articles.append(['Code', 'Désignation', 'Comparaisons', 'Écart ratio FOB/kg %', 'Écart poids %',
                     'Écart FOB %', 'Écart colis %', 'Écart taxes %'])
    for a in analyse['articles']:
        articles.append([a['code'], a['designation'], a['n']]
                        + [_fraction(a[m + '_moyen']) for m in ('ratio', 'poids', 'fob', 'colis', 'taxes')])
    importateurs = wb.create_sheet('IMPORTATEURS')
    importateurs.append(['Importateur', 'Comparaisons', 'Écart % moyen', 'Écart hors taux % moyen', 'Diagnostics'])
    for g in analyse['importateurs']:
        importateurs.append([g['importateur'], g['n'], _fraction(g['moyen']), _fraction(g['hors_taux_moyen']),
                             ', '.join(f'{d} : {n}' for d, n in g['diagnostics'].items())])
    entete, fond = Font(bold=True, color='FFFFFF'), PatternFill('solid', fgColor='1F4E79')
    formats = {'COMPARAISONS': {'H': '#,##0', 'I': '#,##0', 'J': '#,##0', 'K': '0.00%', 'N': '#,##0', 'O': '#,##0',
                                'P': '0.000%'},
               'TAXES': {'D': '#,##0', 'E': '#,##0', 'F': '#,##0', 'G': '0.00%', 'H': '#,##0', 'I': '0.00%'},
               'ARTICLES': {c: '0.0%' for c in 'DEFGH'},
               'IMPORTATEURS': {'C': '0.00%', 'D': '0.000%'}}
    for ws in wb:
        for cellule in ws[1]:
            cellule.font, cellule.fill = entete, fond
        ws.freeze_panes = 'A2'
        for colonne, fmt in formats.get(ws.title, {}).items():
            for c in ws[colonne][1:]:
                c.number_format = fmt
        for colonne in ws.columns:
            largeur = max(len(str(c.value)) if c.value is not None else 0 for c in colonne)
            ws.column_dimensions[colonne[0].column_letter].width = min(60, max(10, largeur + 2))
    synthese.column_dimensions['A'].width = 140
    for c in synthese['A']:
        c.alignment = Alignment(wrap_text=True, vertical='top')
    wb.save(chemin)
    return str(chemin)
