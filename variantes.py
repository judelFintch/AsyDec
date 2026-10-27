"""Bibliothèque persistante et variantes contrôlées, sans écriture de déclaration."""
import hashlib
import math
from pathlib import Path
import random
from decimal import Decimal, ROUND_HALF_UP
import moteur

BIBLIOTHEQUE = Path(__file__).resolve().parent / 'MODELES_XML'
# 10 + 11 + ... + 17 : plus petit total possible avec 8 articles gradués.
COLIS_MINIMUM = sum(range(10, 18))


def verifier_modele(chemin):
    arbre = moteur.charger(chemin)
    info = moteur.infos_dossier(arbre.getroot())
    if len(info['poids_articles']) != 8:
        raise ValueError(f"Le générateur actuel exige 8 articles valorisés ; ce XML en contient {len(info['poids_articles'])}. Les lignes vides sont ignorées.")
    if not all(math.isfinite(x) and x > 0 for x in [info['taux'], *info['poids_articles'], *info['fob_articles']]):
        raise ValueError('Le modèle doit avoir un taux et des poids strictement positifs.')
    # Vérifie les champs et les règles de calcul sans enregistrer.
    moteur.recalculer(arbre, list(zip(info['fob_articles'], info['poids_articles'])), info['colis_articles'])
    return info


def conserver(chemin):
    verifier_modele(chemin)
    contenu = Path(chemin).read_bytes()
    BIBLIOTHEQUE.mkdir(exist_ok=True)
    empreinte = hashlib.sha256(contenu).hexdigest()[:12]
    # Même contenu déjà conservé sous un autre nom : on ne le duplique pas.
    for existant in BIBLIOTHEQUE.glob(f'*-{empreinte}.xml'):
        if existant.read_bytes() == contenu:
            return str(existant)
    destination = BIBLIOTHEQUE / (Path(chemin).stem + '-' + empreinte + '.xml')
    if not destination.exists():
        with destination.open('xb') as fichier:
            fichier.write(contenu)
    return str(destination)


def modeles():
    return sorted(BIBLIOTHEQUE.glob('*.xml')) if BIBLIOTHEQUE.exists() else []


def signature(chemin):
    r = moteur.charger(chemin).getroot()
    return [(moteur._txt(i, 'Tarification/HScode/Commodity_code'),
             moteur._txt(i, 'Goods_description/Description_of_goods').casefold()) for i in moteur.articles(r)]


def generer(poids_total, fob_total, colis_total, ratios, nombre=12, graine=None, profil=None, exclure=None):
    """Ratios fixes : FOB arrondis au centime, poids au gramme, totaux exacts."""
    if not all(math.isfinite(float(v)) and float(v) > 0 for v in [poids_total, fob_total, colis_total, *ratios]):
        raise ValueError('Les totaux et ratios doivent être finis et strictement positifs.')
    if len(ratios) != 8 or int(colis_total) != colis_total:
        raise ValueError('Il faut 8 ratios et un nombre de colis entier.')
    if colis_total < COLIS_MINIMUM:
        raise ValueError(f'Il faut au moins {COLIS_MINIMUM} colis (minimum 10 par article, tous différents).')
    D = Decimal
    q = lambda v: int(D(str(v)).quantize(D('1'), rounding=ROUND_HALF_UP))
    W = q(D(str(poids_total)) * 1000)
    F = q(D(str(fob_total)) * 100)
    if D(str(poids_total))*1000 != W or D(str(fob_total))*100 != F:
        raise ValueError('Saisissez le poids au gramme et le FOB au centime au maximum.')
    cible = float(fob_total) / float(poids_total)
    limites = [x for paire in profil['bornes'] for x in paire] if profil else ratios
    if not min(limites) < cible < max(limites):
        raise ValueError(f'FOB/poids doit être entre {min(limites):g} et {max(limites):g} pour garder les 8 articles positifs.')
    exclus = set(exclure or ())
    rng = random.Random(graine)
    resultats, vus = [], set()
    paires = [(i,j) for i in range(8) for j in range(8) if ratios[i] < cible < ratios[j]]
    for _ in range(20000):
        if profil:
            ratios = [profil['ratios'][k] if k in moteur.ARTICLES_VARIABLES else
                      rng.uniform(*profil['bornes'][k]) for k in range(8)]
            paires = [(i,j) for i in range(8) for j in range(8) if ratios[i] < cible < ratios[j]]
            if not paires:
                continue
        i,j = rng.choice(paires)
        if profil:
            reference = rng.choice(profil['references'])['info']['poids_articles']
            parts = [p * rng.uniform(.8, 1.2) for p in reference]
        else:
            parts = [rng.expovariate(1) for _ in ratios]
        echelle = rng.uniform(.02,.8) * float(poids_total) / sum(parts)
        poids = [v * echelle for v in parts]
        reste = float(poids_total) - sum(poids)
        valeur = float(fob_total) - sum(p*r for p,r in zip(poids,ratios))
        pi = (reste * ratios[j] - valeur) / (ratios[j] - ratios[i])
        pj = reste - pi
        if min(pi,pj) <= 0:
            continue
        poids[i] += pi
        poids[j] += pj
        mg = [q(D(str(p))*1000) for p in poids]
        mg[j] += W - sum(mg)
        if min(mg) <= 0 or tuple(mg) in vus:
            continue
        cents = [q(D(w)*D(str(r))/10) for w,r in zip(mg,ratios)]
        if sum(cents) != F or min(cents) <= 0:
            continue
        # Colis gradués : minimum 10, petits articles 10/11/12..., tous différents.
        try:
            colis = moteur.colis_gradues(mg, cents, int(colis_total))
        except ValueError:
            continue
        vus.add(tuple(mg))
        v = {'poids':[w/1000 for w in mg], 'fob':[f/100 for f in cents], 'colis':colis}
        if cle_variante(v) in exclus:
            continue
        if profil:
            try:
                controler(v, profil)
            except ValueError:
                continue
            v.update(evaluer(v, profil))
        resultats.append(v)
        if len(resultats) >= (nombre * 10 if profil else nombre):
            break
    if not resultats:
        raise ValueError('Aucune nouvelle variante compatible trouvée dans la limite de recherche. La proposition actuelle est conservée.' if exclus else 'Aucune variante trouvée aux précisions XML demandées. Ajustez les totaux.')
    return sorted(resultats, key=lambda v: v.get("distance", 0))[:nombre]


def construire_profil(choisi, chemins=None):
    info = verifier_modele(choisi)
    sig = signature(choisi)
    references, exclus = [], []
    chemins = list(chemins if chemins is not None else modeles())
    if str(choisi) not in [str(p) for p in chemins]:
        chemins.append(choisi)
    for chemin in chemins:
        try:
            autre = verifier_modele(chemin)
            if signature(chemin) != sig:
                raise ValueError('articles incompatibles')
            references.append({'nom': Path(chemin).name, 'info': autre})
        except Exception as exc:
            exclus.append(f'{Path(chemin).name} : {exc}')
    ratios = [f/p for f,p in zip(info['fob_articles'],info['poids_articles'])]
    bornes = []
    for k in range(8):
        observes = [r['info']['fob_articles'][k]/r['info']['poids_articles'][k] for r in references]
        bornes.append((ratios[k],ratios[k]) if k in moteur.ARTICLES_VARIABLES else (min(observes),max(observes)))
    return {'ratios':ratios, 'bornes':bornes, 'references':references, 'exclus':exclus, 'signature':sig}


def controler(v, profil):
    if any(len(v.get(c, [])) != 8 for c in ('poids','fob','colis')):
        raise ValueError('Le contrôle exige 8 articles complets.')
    for k,(p,f,c) in enumerate(zip(v['poids'],v['fob'],v['colis'])):
        if not all(math.isfinite(float(x)) and x > 0 for x in (p,f,c)) or int(c) != c:
            raise ValueError(f'Art. {k+1} : poids, FOB et colis positifs requis, colis entiers.')
        bas,haut = profil['bornes'][k]
        montant = Decimal(str(f))
        minimum = (Decimal(str(p))*Decimal(str(bas))).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
        maximum = (Decimal(str(p))*Decimal(str(haut))).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
        if not minimum <= montant <= maximum:
            raise ValueError(f'Art. {k+1} : FOB hors contrôle, attendu entre {minimum} et {maximum} USD (ratios {bas:.6g} à {haut:.6g}).')


def evaluer(v, profil):
    # Distance moyenne entre les parts de poids, de FOB et de colis (0 = identiques).
    meilleur = None
    for ref in profil['references']:
        distance = 0
        for cle, champ in [('poids','poids_articles'),('fob','fob_articles'),('colis','colis_articles')]:
            a,b = v[cle],ref['info'][champ]
            if sum(b) <= 0:
                distance += 1/3
            else:
                distance += sum(abs(x/sum(a)-y/sum(b)) for x,y in zip(a,b))/6
        if meilleur is None or distance < meilleur['distance']:
            meilleur = {'distance':distance, 'proximite':round(100*(1-distance),2), 'reference_proche':ref['nom']}
    return meilleur


def cle_variante(v):
    """Identifie une proposition aux précisions de sortie XML."""
    return (tuple(round(p*1000) for p in v['poids']),
            tuple(round(f*100) for f in v['fob']), tuple(v['colis']))
