"""Import initial des données de l’ancien dossier OUTILS vers la version installée."""
from contextlib import closing
from pathlib import Path
import os
import shutil
import sqlite3
import tempfile

ELEMENTS = ('DONNEES','CONFIG_LOCAL','SAUVEGARDES','MODELES_XML','ETUDES_XML','SIMULATIONS','SAISIE.xlsx','registre.json')


def importer(source, destination):
    source,destination=Path(source).resolve(),Path(destination).resolve()
    if source==destination or source in destination.parents or destination in source.parents:
        raise ValueError('Les deux dossiers doivent être distincts et non imbriqués.')
    if not (source/'CONFIG_LOCAL/compte.json').is_file():
        raise ValueError('Ce dossier ne contient pas le compte AsyDec. Sélectionnez l’ancien dossier OUTILS.')
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('La destination contient déjà des données. L’import ne les remplacera pas.')
    destination.parent.mkdir(parents=True,exist_ok=True)
    temporaire=Path(tempfile.mkdtemp(prefix='.AsyDec-import-',dir=destination.parent))
    try:
        def copier(fichier,cible):
            p=Path(fichier)
            if p.suffix=='.db':
                with closing(sqlite3.connect(p.as_uri()+'?mode=ro',uri=True)) as entree, closing(sqlite3.connect(cible)) as sortie:
                    entree.backup(sortie)
            elif not p.name.endswith(('.db-wal','.db-shm','.db-journal')):
                shutil.copy2(fichier,cible)
            return cible
        for nom in ELEMENTS:
            entree=source/nom
            if entree.is_symlink():
                raise ValueError('Un dossier de données est un lien symbolique ; import automatique refusé.')
            if entree.is_dir():
                if any(p.is_symlink() for p in entree.rglob('*')):
                    raise ValueError('Un lien symbolique existe dans les données ; choisissez une copie autonome.')
                shutil.copytree(entree,temporaire/nom,copy_function=copier)
            elif entree.is_file():
                copier(str(entree),str(temporaire/nom))
        if destination.exists():
            destination.rmdir()
        os.replace(temporaire,destination)
    finally:
        if temporaire.exists():
            shutil.rmtree(temporaire)
