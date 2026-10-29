"""Analyse des anomalies d'un modèle : ce qui l'écarte des dossiers connus.

Indicatif : aucune référence n'apporte la preuve d'un rejet SYDONIA. Chaque alerte est
expliquée et chiffrée pour que l'utilisateur juge lui-même. Les seuils sont regroupés
dans SEUILS pour être revus (domaine calcul).
"""
from collections import defaultdict
import statistics

from asydec.calcul.variantes import distance_parts
from asydec.formats import nombre

NIVEAUX = ('eleve', 'moyen', 'info')
AJUSTABLES = (4, 7, 8)  # positions dont le ratio est ajusté par le moteur (moteur.ARTICLES_VARIABLES + 1)
LIBELLES = {'eleve': 'Risque élevé', 'moyen': 'À vérifier', 'info': 'Information', None: 'Aucun signal'}
SEUILS = {
    'references_marge': 5,        # nombre minimal de dossiers pour juger la marge (déciles)
    'quantile_bas': 0.10, 'quantile_haut': 0.90,
    'comparaison_moyen': 1.0, 'comparaison_eleve': 5.0,   # écart du total des taxes, en %
    'proche_rejete': 0.02,        # distance des parts (0 = mêmes proportions)
}


def _alerte(niveau, message, article=None):
    return {'niveau': niveau, 'article': article, 'message': message}


def references_par_groupe(observations):
    """Ratios et parts de poids observés, par article (devise, code, désignation) : {groupe: [(ratio, part, doc)]}."""
    totaux = defaultdict(float)
    for o in observations:
        totaux[o['document_id']] += o['poids']
    groupes = defaultdict(list)
    for o in observations:
        part = o['poids'] / totaux[o['document_id']] if totaux[o['document_id']] > 0 else None
        groupes[o['groupe']].append((o['ratio'], part, o['document_id']))
    return groupes


def _quantile(valeurs, q):
    valeurs = sorted(valeurs)
    if len(valeurs) == 1:
        return valeurs[0]
    return statistics.quantiles(valeurs, n=100, method='inclusive')[round(q * 100) - 1]


def analyser(modele, groupes, autres=(), seuils=SEUILS):
    """Alertes d'un modèle.

    modele : {'id', 'statut', 'articles': [{'position','code','groupe','poids','fob','colis'}],
              'ecart_comparaison_pct': None|nombre}
    groupes : references_par_groupe(observations) ; autres : autres modèles au même format.
    """
    alertes = []
    articles = modele['articles']
    total_poids = sum(a['poids'] for a in articles)
    for a in articles:
        nom = f"Art. {a['position']} · {a['code'] or '—'}"
        refs = groupes.get(a['groupe'], [])
        documents = {d for _, _, d in refs}
        if not refs:
            alertes.append(_alerte('info', 'Aucune référence connue pour cet article : rien à comparer.', nom))
            continue
        ratio = a['fob'] / a['poids'] if a['poids'] > 0 else None
        ratios = [r for r, _, _ in refs]
        bas, haut = min(ratios), max(ratios)
        if ratio is not None:
            if round(ratio, 4) < round(bas, 4) or round(ratio, 4) > round(haut, 4):
                ajustable = ' Article ajustable : son ratio absorbe l’écart de FOB.' if a['position'] in AJUSTABLES else ''
                alertes.append(_alerte('eleve', f'Ratio FOB/kg {nombre(ratio, 4)} jamais observé : les {len(documents)} '
                    f'dossier(s) connu(s) vont de {nombre(bas, 4)} à {nombre(haut, 4)}.{ajustable}', nom))
            elif len(documents) >= seuils['references_marge']:
                q_bas, q_haut = _quantile(ratios, seuils['quantile_bas']), _quantile(ratios, seuils['quantile_haut'])
                if ratio < q_bas or ratio > q_haut:
                    alertes.append(_alerte('moyen', f'Ratio FOB/kg {nombre(ratio, 4)} en marge des dossiers connus '
                        f'(la plupart entre {nombre(q_bas, 4)} et {nombre(q_haut, 4)}).', nom))
        parts = [p for _, p, _ in refs if p is not None]
        if parts and total_poids > 0:
            part = a['poids'] / total_poids
            if part < min(parts) - 1e-9 or part > max(parts) + 1e-9:
                alertes.append(_alerte('moyen', f'Part du poids {nombre(100 * part, 1)} % jamais vue : '
                    f'{nombre(100 * min(parts), 1)} % à {nombre(100 * max(parts), 1)} % dans les dossiers connus.', nom))
    repartition = {k: [a[k] for a in articles] for k in ('poids', 'fob', 'colis')}
    signature = [a['groupe'] for a in articles]
    for autre in autres:
        if autre['id'] == modele['id'] or [a['groupe'] for a in autre['articles']] != signature:
            continue
        sienne = {k: [a[k] for a in autre['articles']] for k in ('poids', 'fob', 'colis')}
        if autre['statut'] == 'rejete' and distance_parts(repartition, sienne) <= seuils['proche_rejete']:
            motif = f" (motif : {autre['motif']})" if autre.get('motif') else ''
            alertes.append(_alerte('eleve', f"Très proche du modèle n° {autre['id']} rejeté localement{motif}."))
        elif repartition['poids'] == sienne['poids'] and repartition['fob'] == sienne['fob']:
            alertes.append(_alerte('moyen', f"Poids et FOB identiques au modèle n° {autre['id']} : "
                                            'une répartition recopiée se remarque.'))
    ecart = modele.get('ecart_comparaison_pct')
    if ecart is not None:
        if abs(ecart) > seuils['comparaison_eleve']:
            alertes.append(_alerte('eleve', f'Dernière comparaison : total des taxes à {nombre(ecart, 2)} % du fichier comparé.'))
        elif abs(ecart) > seuils['comparaison_moyen']:
            alertes.append(_alerte('moyen', f'Dernière comparaison : total des taxes à {nombre(ecart, 2)} % du fichier comparé.'))
    if modele.get('statut') == 'rejete':
        alertes.append(_alerte('info', 'Ce modèle est déjà rejeté localement.'))
    alertes.sort(key=lambda a: NIVEAUX.index(a['niveau']))
    return alertes


def niveau(alertes):
    """Niveau le plus grave parmi les alertes, hors informations ; None si aucun signal."""
    graves = [a['niveau'] for a in alertes if a['niveau'] != 'info']
    return min(graves, key=NIVEAUX.index) if graves else None
