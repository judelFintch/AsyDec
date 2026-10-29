"""Reprise d'une copie de travail archivée, sans modifier le modèle ou son statut."""
from decimal import Decimal
import hashlib
from pathlib import Path
import tempfile
from tkinter import messagebox

from asydec.calcul import variantes
from asydec.references.import_references import extraire


def reprendre(app, contenu, nom='reprise.xml', parent=None, repartition=None):
    if app.session_verrouillee:
        return False
    parent=parent or app
    try:
        donnees=extraire(contenu)
        actifs=[a for a in donnees['articles'] if a['fob'] is not None and Decimal(a['fob'])!=0]
        if not actifs or [a['position'] for a in actifs]!=list(range(1,len(actifs)+1)):
            raise ValueError('La reprise exige des articles valorisés avec des positions consécutives. Les XML partiels restent réservés aux études.')
        valeurs=repartition if repartition is not None else {
            'poids':[a['poids_brut'] for a in actifs], 'fob':[a['fob'] for a in actifs],
            'colis':[a['colis'] for a in actifs]}
        if any(len(valeurs[k])!=len(actifs) for k in ('poids','fob','colis')):
            raise ValueError('La répartition conservée doit contenir les poids, FOB et colis de chaque article.')
        nombres={k:[Decimal(str(v)) if v is not None else None for v in valeurs[k]] for k in valeurs}
        if any(v is None or not v.is_finite() or v<=0 or v!=v.to_integral_value() for v in nombres['poids']):
            raise ValueError('Les poids repris doivent être des kilogrammes entiers strictement positifs. Aucun poids décimal ne sera arrondi.')
        if any(v is None or not v.is_finite() or v<=0 or v!=v.quantize(Decimal('.01')) for v in nombres['fob']):
            raise ValueError('Les FOB repris doivent être strictement positifs et exprimés au centime.')
        if any(v is None or not v.is_finite() or v<0 or v!=v.to_integral_value() for v in nombres['colis']):
            raise ValueError('Les colis repris doivent être des entiers renseignés, sans arrondi.')
        if getattr(app,'base',None) and not messagebox.askyesno('Reprendre pour modifier',
            'Les saisies du dossier actif seront remplacées. Continuer ?\n\n'
            'Le XML et le modèle conservés restent intacts, ainsi que leur validation locale. '
            'Une répartition modifiée pourra être enregistrée comme une autre proposition.',parent=parent):
            return False
        if app.session_verrouillee:
            return False
        with tempfile.TemporaryDirectory(prefix='asydec-reprise-') as dossier:
            source=Path(dossier)/(Path(nom).name or 'reprise.xml')
            source.write_bytes(contenu)
            variantes.verifier_modele(source)
            erreurs=app.partager_xml([source])
            if erreurs:
                raise ValueError('\n'.join(erreurs))
        empreinte=hashlib.sha256(contenu).hexdigest()
        archive=next((d['chemin'] for d in app.xml_disponibles(generation=True) if d['empreinte']==empreinte),None)
        if archive is None:
            raise ValueError('Le XML archivé ne peut pas servir de base de génération (rejeté, exclu ou incomplet).')
        if not app.ouvrir_base(archive):
            return False
        app.pages['articles'].remplir([int(v) for v in nombres['poids']],
            [float(v) for v in nombres['fob']],[int(v) for v in nombres['colis']],mode='SAISI')
        app.montrer('articles')
        return True
    except Exception as exc:
        messagebox.showerror('Reprise impossible',str(exc),parent=parent)
        return False
