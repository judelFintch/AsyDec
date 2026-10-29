"""Bibliothèque persistante et variantes contrôlées, sans écriture de déclaration."""
import hashlib
import math
from pathlib import Path
import random
import xml.etree.ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP

from asydec import chemins
from asydec.calcul import moteur

BIBLIOTHEQUE = chemins.MODELES_XML
# 10 + 11 + ... + 17 : plus petit total possible avec 8 articles gradués.
COLIS_MINIMUM = sum(range(10, 18))


def verifier_modele(chemin):
    arbre = moteur.charger(chemin)
    info = moteur.infos_dossier(arbre.getroot())
    if not info['poids_articles']:
        raise ValueError(f"Le générateur exige au moins un article valorisé ; ce XML en contient {len(info['poids_articles'])}. Les lignes vides sont ignorées.")
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
    bibli = list(BIBLIOTHEQUE.glob('*.xml')) if BIBLIOTHEQUE.exists() else []
    etudes = chemins.ETUDES_XML
    return sorted(set(bibli + list(etudes.glob('*.xml'))))


def signature(chemin):
    return signature_racine(moteur.charger(chemin).getroot())


def signature_racine(r):
    """Codes, désignations normalisées et devise de chaque article d'un XML déjà lu."""
    return [(moteur._txt(i, 'Tarification/HScode/Commodity_code'),
             ' '.join(moteur._txt(i, 'Goods_description/Description_of_goods').casefold().split()),
             moteur._txt(r, 'Valuation/Gs_Invoice/Currency_code')) for i in moteur.articles(r)]


def generer(poids_total, fob_total, colis_total, ratios, nombre=12, graine=None, profil=None, exclure=None):
    """Ratios fixes : FOB arrondis au centime, poids en kilogrammes entiers, totaux exacts."""
    if not all(math.isfinite(float(v)) and float(v) > 0 for v in [poids_total, fob_total, colis_total, *ratios]):
        raise ValueError('Les totaux et ratios doivent être finis et strictement positifs.')
    n = len(ratios)
    if profil and profil.get('variables_libres'):
        n = len(ratios)
        if not n or poids_total != int(poids_total) or Decimal(str(fob_total))*100 != (Decimal(str(fob_total))*100).to_integral_value():
            raise ValueError('Poids entiers et FOB au centime requis.')
        if int(colis_total) != colis_total or colis_total < sum(range(10, 10+n)):
            raise ValueError(f'Il faut au moins {sum(range(10, 10+n))} colis entiers pour {n} articles.')
        return generer_equilibres(int(poids_total), int(Decimal(str(fob_total))*100), colis_total, profil, nombre, graine, exclure)
    if not n or int(colis_total) != colis_total:
        raise ValueError('Il faut un ratio par article et un nombre de colis entier.')
    if colis_total < sum(range(10, 10+n)):
        raise ValueError(f'Il faut au moins {sum(range(10, 10+n))} colis (minimum 10 par article, tous différents).')
    D = Decimal
    q = lambda v: int(D(str(v)).quantize(D('1'), rounding=ROUND_HALF_UP))
    W = q(D(str(poids_total)))
    F = q(D(str(fob_total)) * 100)
    if D(str(poids_total)) != W or D(str(fob_total))*100 != F:
        raise ValueError('Saisissez le poids en kilogrammes entiers et le FOB au centime au maximum.')
    if profil and profil.get('variables_libres'):
        return generer_equilibres(W,F,colis_total,profil,nombre,graine,exclure)
    if (not profil or profil.get('dynamique')) and len({D(str(r)) for r in ratios}) == 1:
        if W < n:
            raise ValueError(f'Il faut au moins {n} kg pour conserver {n} articles de poids entier positif.')
        if F < n:
            raise ValueError(f'Il faut au moins {n/100:.2f} USD pour {n} articles à FOB strictement positif.')
        ratio = D(str(ratios[0]))
        cible_cents = D(F)
        total_theorique = D(W) * ratio * 100
        # Half-up rounding puts each positive line error in (-0.5, 0.5] cents.
        ecart_cents = cible_cents - total_theorique
        if ecart_cents <= -D(n)/2 or ecart_cents > D(n)/2:
            raise ValueError('FOB total mathématiquement incompatible avec des ratios identiques et les arrondis au centime.')

        base, reste = divmod(W, n)
        poids = [base + (i < reste) for i in range(n)]
        def centimes(kg):
            return [q(D(p) * ratio * 100) for p in kg]

        base_cents = centimes(poids)
        propositions, vus_poids = [], {tuple(poids)}
        exclues = set(exclure or ())
        erreurs_colis = []

        def ajouter(kg, montants):
            if any(c <= 0 for c in montants):
                return
            proposition = {'poids': kg, 'fob': [c / 100 for c in montants]}
            try:
                proposition['colis'] = moteur.colis_gradues(kg, proposition['fob'], int(colis_total))
            except ValueError as exc:
                erreurs_colis.append(exc)
                return
            cle = cle_variante(proposition)
            if cle in exclues or cle in {cle_variante(v) for v in propositions}:
                return
            if profil:
                controler(proposition, profil)
                proposition.update(evaluer(proposition, profil))
            propositions.append(proposition)

        if sum(base_cents) == F:
            ajouter(poids, base_cents)
        if len(propositions) < nombre and W <= 100000:
            for i in range(n):
                for j in range(i + 1, 8):
                    autres = sum(poids[k] for k in range(n) if k not in (i, j))
                    total_paire = W - autres
                    milieu = total_paire // 2
                    for ecart in range(total_paire):
                        candidats = (milieu - ecart, (total_paire + 1) // 2 + ecart)
                        for premier in candidats:
                            second = total_paire - premier
                            if premier <= 0 or second <= 0:
                                continue
                            essais = list(poids)
                            essais[i], essais[j] = premier, second
                            cle_poids = tuple(essais)
                            if cle_poids in vus_poids:
                                continue
                            vus_poids.add(cle_poids)
                            fob_premier = q(D(premier) * ratio * 100)
                            fob_second = q(D(second) * ratio * 100)
                            nouveau_total = (sum(base_cents) - base_cents[i] - base_cents[j] +
                                             fob_premier + fob_second)
                            if nouveau_total == F:
                                montants = list(base_cents)
                                montants[i], montants[j] = fob_premier, fob_second
                                ajouter(essais, montants)
                                if len(propositions) >= nombre:
                                    break
                        if len(propositions) >= nombre:
                            break
                    if len(propositions) >= nombre:
                        break
                if len(propositions) >= nombre:
                    break

        if not propositions:
            if erreurs_colis:
                raise ValueError(f'Ratios identiques : répartition des colis impossible avec ce total. {erreurs_colis[-1]}') from erreurs_colis[-1]
            if W == n:
                raise ValueError('Aucune répartition entière ne peut atteindre ce FOB : chaque article doit peser au moins 1 kg.')
            raise ValueError('Aucune répartition exacte au centime avec des FOB strictement positifs trouvée pour ces ratios identiques.')
        return propositions
    cible = float(fob_total) / float(poids_total)
    limites = [x for paire in profil['bornes'] for x in paire] if profil else ratios
    if not min(limites) < cible < max(limites):
        raise ValueError(f'FOB/poids doit être entre {min(limites):g} et {max(limites):g} pour garder les articles positifs.')
    exclus = set(exclure or ())
    rng = random.Random(graine)
    resultats, vus = [], set()
    paires = [(i,j) for i in range(n) for j in range(n) if ratios[i] < cible < ratios[j]]
    for _ in range(20000):
        if profil:
            ratios = [profil['ratios'][k] if k in articles_ajustables(profil) else
                      rng.uniform(*profil['bornes'][k]) for k in range(n)]
            paires = [(i,j) for i in range(n) for j in range(n) if ratios[i] < cible < ratios[j]]
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
        kg = [q(D(str(p))) for p in poids]
        kg[j] += W - sum(kg)
        if min(kg) <= 0 or tuple(kg) in vus:
            continue
        cents = [q(D(w)*D(str(r))*100) for w,r in zip(kg,ratios)]
        if sum(cents) != F or min(cents) <= 0:
            continue
        # Colis gradués : minimum 10, petits articles 10/11/12..., tous différents.
        try:
            colis = moteur.colis_gradues(kg, cents, int(colis_total))
        except ValueError:
            continue
        vus.add(tuple(kg))
        v = {'poids':list(kg), 'fob':[f/100 for f in cents], 'colis':colis}
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


def construire_profil(choisi, chemins=None, dynamique=None):
    info = verifier_modele(choisi)
    sig = signature(choisi)
    references, exclus = [], []
    chemins = list(chemins if chemins is not None else modeles())
    if str(choisi) not in [str(p) for p in chemins]:
        chemins.append(choisi)
    empreintes = set()
    for chemin in chemins:
        try:
            empreinte = hashlib.sha256(Path(chemin).read_bytes()).hexdigest()
            if empreinte in empreintes:
                continue
            autre = verifier_modele(chemin)
            if signature(chemin) != sig:
                raise ValueError('articles incompatibles')
            references.append({'nom': Path(chemin).name, 'info': autre})
            empreintes.add(empreinte)
        except Exception as exc:
            exclus.append(f'{Path(chemin).name} : {exc}')
    ratios = [f/p for f,p in zip(info['fob_articles'],info['poids_articles'])]
    dynamique = len(ratios) != 8 if dynamique is None else dynamique
    ajustables = () if dynamique else moteur.ARTICLES_VARIABLES
    bornes = []
    for k in range(len(ratios)):
        observes = [r['info']['fob_articles'][k]/r['info']['poids_articles'][k] for r in references]
        bornes.append((ratios[k],ratios[k]) if dynamique or k in ajustables else (min(observes),max(observes)))
    return {'ratios':ratios, 'bornes':bornes, 'references':references, 'exclus':exclus, 'signature':sig, 'variables_libres':not dynamique, 'ajustables':ajustables, 'dynamique':dynamique}


def articles_ajustables(profil):
    """Les positions spéciales 4/7/8 appartiennent uniquement au profil classique."""
    return tuple(profil.get('ajustables', moteur.ARTICLES_VARIABLES))


def controler(v, profil):
    if any(len(v.get(c, [])) != len(profil['ratios']) for c in ('poids','fob','colis')):
        raise ValueError('Le contrôle exige une ligne complète pour chaque article du modèle.')
    for k,(p,f,c) in enumerate(zip(v['poids'],v['fob'],v['colis'])):
        if any(x is None for x in (p,f,c)) or not all(math.isfinite(float(x)) and x > 0 for x in (p,f,c)) or int(c) != c:
            raise ValueError(f'Art. {k+1} : poids, FOB et colis positifs requis, colis entiers.')
        if Decimal(str(p)) != Decimal(str(p)).to_integral_value() or Decimal(str(f))*100 != (Decimal(str(f))*100).to_integral_value():
            raise ValueError(f'Art. {k+1} : poids en kg entiers, sans décimales, et FOB au centime au maximum.')
        if profil.get('variables_libres') and k in articles_ajustables(profil):
            continue
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
        if profil.get('variables_libres'):
            ecart=sum(abs(v['fob'][k]/v['poids'][k]-profil['ratios'][k]) /
                      (v['fob'][k]/v['poids'][k]+profil['ratios'][k]) for k in articles_ajustables(profil))/max(1, len(articles_ajustables(profil)))
            distance=.8*distance+.2*ecart
        if meilleur is None or distance < meilleur['distance']:
            meilleur = {'distance':distance, 'proximite':round(100*(1-distance),2), 'reference_proche':ref['nom']}
    return meilleur


def distance_parts(v, ref):
    """Écart moyen des parts de poids, FOB et colis entre deux répartitions (0 = mêmes proportions)."""
    distance = 0
    for cle in ('poids', 'fob', 'colis'):
        a, b = v[cle], ref[cle]
        if sum(a) <= 0 or sum(b) <= 0:
            distance += 1/3
        else:
            distance += sum(abs(x/sum(a)-y/sum(b)) for x, y in zip(a, b))/6
    return distance


def plus_proche(propositions, modeles):
    """Proposition la plus proche d'un des modèles retenus : (proposition, modèle, proximité %)."""
    choix = min(((distance_parts(p, m), i, p, m) for i, p in enumerate(propositions) for m in modeles),
                key=lambda t: (t[0], t[1]))
    return choix[2], choix[3], round(100*(1-choix[0]), 2)


def cle_variante(v):
    """Identifie une proposition aux précisions de sortie XML."""
    return (tuple(v['poids']),
            tuple(round(f*100) for f in v['fob']), tuple(v['colis']))


def fob_controles(poids, profil, total=None):
    """Répartit au centime dans les bornes ; les ratios fixes ne sont jamais ajustés."""
    if len(poids)!=len(profil['ratios']) or any(p is None or not math.isfinite(p) or p<=0 or p!=int(p) for p in poids):
        raise ValueError('Les poids de chaque article doivent être des kilogrammes entiers strictement positifs.')
    if profil.get('variables_libres'):
        return fob_equilibres(poids,profil,total)
    def cents(p,r):
        return int((Decimal(str(p))*Decimal(str(r))*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    bas=[cents(p,b[0]) for p,b in zip(poids,profil['bornes'])]
    haut=[cents(p,b[1]) for p,b in zip(poids,profil['bornes'])]
    valeurs=[min(h,max(b,cents(p,r))) for p,r,b,h in zip(poids,profil['ratios'],bas,haut)]
    if total is None:
        return [x/100 for x in valeurs]
    if not math.isfinite(total):
        raise ValueError('Le FOB total doit être fini.')
    cible=int((Decimal(str(total))*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    if not math.isfinite(total) or Decimal(str(total))*100!=cible:
        raise ValueError('Le FOB total doit être fini et exprimé au centime.')
    if not sum(bas)<=cible<=sum(haut):
        raise ValueError(f'FOB incompatible avec ces poids et les ratios : intervalle autorisé {sum(bas)/100:.2f} à {sum(haut)/100:.2f}. Utilisez « Proposer des répartitions » pour faire varier les poids.')
    reste=cible-sum(valeurs)
    for k in range(len(poids)):
        deplacement=min(reste,haut[k]-valeurs[k]) if reste>0 else max(reste,bas[k]-valeurs[k])
        valeurs[k]+=deplacement
        reste-=deplacement
    return [x/100 for x in valeurs]


def rechercher_modeles(poids, fob, colis, chemins=None, nombre=12, exclure=None, dynamique=None):
    """Recherche uniquement dans les références conservées, sans XML de dossier."""
    if any(v is None or not math.isfinite(float(v)) or v<=0 for v in (poids,fob,colis)):
        raise ValueError('Les trois totaux doivent être finis et strictement positifs.')
    if int(colis)!=colis or colis<10:
        raise ValueError('Le total des colis doit être entier et au moins égal à 10 ; le minimum requis dépend du nombre d’articles.')
    chemins=list(chemins if chemins is not None else modeles())
    if not chemins:
        raise ValueError('Aucun modèle enregistré. Ajoutez des XML de contrôle ou des études avant la simulation.')
    propositions,ecartes=[],[]
    empreintes=set()
    for chemin in chemins:
        try:
            empreinte=hashlib.sha256(Path(chemin).read_bytes()).hexdigest()
            if empreinte in empreintes:
                continue
            empreintes.add(empreinte)
            info=verifier_modele(chemin)
            devise=moteur._txt(moteur.charger(chemin).getroot(),'Valuation/Gs_Invoice/Currency_code')
            if devise and devise!='USD':
                raise ValueError('La saisie FOB est en USD : modèle de devise différente.')
            profil=construire_profil(chemin,chemins,dynamique=dynamique)
            valeurs=generer(poids,fob,colis,profil['ratios'],nombre=3,profil=profil,exclure=exclure)
            for v in valeurs:
                v['profil']=profil
                v['controle']=str(chemin)
                v['modele']=Path(chemin).name
                propositions.append(v)
        except (ValueError,OSError,ArithmeticError,ET.ParseError) as exc:
            ecartes.append(f'{Path(chemin).name} : {exc}')
    if not propositions:
        raise ValueError('Aucune proposition compatible trouvée dans les modèles enregistrés.\n'+'\n'.join(ecartes))
    propositions.sort(key=lambda v:v['distance'])
    return propositions[:nombre],ecartes


def fob_equilibres(poids,profil,total=None):
    """Les variables absorbent l'écart, proportionnellement à leur FOB de référence."""
    if len(poids)!=len(profil['ratios']) or any(p is None or not math.isfinite(p) or p<=0 or p!=int(p) for p in poids):
        raise ValueError('Les poids de chaque article doivent être des kilogrammes entiers strictement positifs.')
    def cent(p,r):
        return int((Decimal(str(p))*Decimal(str(r))*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    valeurs=[max(1,cent(p,r)) for p,r in zip(poids,profil['ratios'])]
    if total is None:
        return [v/100 for v in valeurs]
    if not math.isfinite(total) or total<=0 or Decimal(str(total))*100!=(Decimal(str(total))*100).to_integral_value():
        raise ValueError('Le FOB doit être positif, fini et exprimé au centime.')
    cible=int(Decimal(str(total))*100)
    variables=list(articles_ajustables(profil))
    autres=[k for k in range(len(poids)) if k not in variables]
    minimum={k:max(1,cent(poids[k],profil['bornes'][k][0])) for k in autres}
    for k in autres:
        valeurs[k]=max(minimum[k],min(valeurs[k],cent(poids[k],profil['bornes'][k][1])))
    if cible<sum(minimum.values())+len(variables):
        raise ValueError(f'FOB trop faible avec ces poids : minimum { (sum(minimum.values())+len(variables))/100:.2f} USD, même en ajustant les articles variables. Réduisez les poids des autres articles.')
    a_reduire=max(0,sum(valeurs[k] for k in autres)+len(variables)-cible)
    # Ne réduit que les articles non variables ayant une marge dans leur fourchette.
    for k in autres:
        baisse=min(a_reduire,valeurs[k]-minimum[k])
        valeurs[k]-=baisse
        a_reduire-=baisse
    reste=cible-sum(valeurs[k] for k in autres)
    bases=[Decimal(str(poids[k]))*Decimal(str(profil['ratios'][k])) for k in variables]
    brut=[Decimal(reste-len(variables))*b/sum(bases) for b in bases]
    parts=[1+int(x) for x in brut]
    for j in sorted(range(len(parts)),key=lambda j:brut[j]-int(brut[j]),reverse=True)[:reste-sum(parts)]:
        parts[j]+=1
    for k,v in zip(variables,parts):
        valeurs[k]=v
    return [x/100 for x in valeurs]


def generer_equilibres(W,F,colis,profil,nombre=12,graine=None,exclure=None):
    n = len(profil['ratios'])
    if W<n:
        raise ValueError(f'Il faut au moins {n} kg pour conserver {n} articles de poids entier positif.')
    rng=random.Random(graine)
    exclus=set(exclure or ())
    vus=set()
    resultats=[]
    variables=set(articles_ajustables(profil))
    for tentative in range(10000):
        ref=rng.choice(profil['references'])['info']['poids_articles']
        parts=[p*rng.uniform(.75,1.25) for p in ref]
        # Explore aussi des poids faibles sur les articles bornés, pour les petits FOB.
        if tentative%3==0:
            facteur=10**rng.uniform(-4,0)
            parts=[p if k in variables else p*facteur for k,p in enumerate(parts)]
        brut=[(W-n)*p/sum(parts) for p in parts]
        poids=[1+int(p) for p in brut]
        for k in sorted(range(n),key=lambda k:brut[k]-int(brut[k]),reverse=True)[:W-sum(poids)]:
            poids[k]+=1
        try:
            fob=fob_equilibres(poids,profil,F/100)
            paquets=moteur.colis_gradues(poids,fob,int(colis))
            v={'poids':poids,'fob':fob,'colis':paquets}
            controler(v,profil)
        except ValueError:
            continue
        cle=cle_variante(v)
        if cle in vus or cle in exclus:
            continue
        vus.add(cle)
        v.update(evaluer(v,profil))
        resultats.append(v)
        if len(resultats)>=nombre*10:
            break
    if not resultats:
        raise ValueError('Aucune nouvelle répartition trouvée avec poids entiers, FOB positifs et bornes des articles non variables. Vérifiez les totaux et les articles du modèle.')
    return sorted(resultats,key=lambda v:v['distance'])[:nombre]
