import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from asydec.declarations import factures
from asydec.systeme import transfert


def _machine(racine, ancienne=None):
    """Petite installation AsyDec : compte, numéros, modèle Word, XML, chemins de l'ancienne machine."""
    ancienne = ancienne or str(racine)
    (racine / 'CONFIG_LOCAL').mkdir(parents=True)
    (racine / 'CONFIG_LOCAL/compte.json').write_text('{"identifiant":"admin"}')
    (racine / 'CONFIG_LOCAL/preferences.json').write_text(json.dumps({'recents': [ancienne + '/DONNEES/sources/a.xml']}))
    with sqlite3.connect(racine / 'CONFIG_LOCAL/numeros_factures.db') as db:
        db.execute('CREATE TABLE numeros (facture TEXT PRIMARY KEY, manifeste TEXT)')
        db.execute("INSERT INTO numeros VALUES('AB-123-456','1-ML2')")
    with factures.connexion(racine / 'DONNEES/factures.db') as db:
        g = db.execute("INSERT INTO gabarits(nom,contenu) VALUES('client A',?)", (b'WORD-A',)).lastrowid
        db.execute("INSERT INTO gabarits(nom,contenu,retire) VALUES('retire',?, 'oui')", (b'WORD-R',))
        db.execute("INSERT INTO factures(numero,modele_id,gabarit_id,date,auteur,contenu) VALUES('AB-123-456',1,?,'2026','a',x'00')", (g,))
    with sqlite3.connect(racine / 'DONNEES/modeles_generes.db') as db:
        db.execute('CREATE TABLE modeles (id INTEGER PRIMARY KEY, resultat_json TEXT, image BLOB)')
        db.execute('INSERT INTO modeles VALUES(1,?,?)', (json.dumps({'source': ancienne + '/MODELES_XML/x.xml'}), b'bin'))
    (racine / 'MODELES_XML').mkdir()
    (racine / 'MODELES_XML/ref.xml').write_text('<ASYCUDA/>')
    (racine / 'DONNEES/asydec.log').write_text('journal')


class Transfert(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def test_export_complet_puis_import_sur_autre_machine(self):
        ancienne = self.d / 'ancienne' / 'AsyDec'
        _machine(ancienne)
        fichier, resume = transfert.exporter(self.d / 'export', kit=False, racine=ancienne)
        self.assertEqual(fichier.suffix, '.asydec')
        self.assertEqual((resume['numeros_reserves'], resume['factures_emises']), (1, 1))
        with ZipFile(fichier) as z:
            self.assertNotIn('DONNEES/asydec.log', z.namelist())
        neuve = self.d / 'neuve' / 'AsyDec'
        (neuve / 'DONNEES').mkdir(parents=True)
        (neuve / 'DONNEES/existant.txt').write_text('ancien contenu')
        transfert.preparer_import_complet(fichier, neuve)
        self.assertFalse((neuve / 'CONFIG_LOCAL').exists())  # rien n'est remplacé avant le redémarrage
        mise_de_cote = transfert.appliquer_en_attente(neuve)
        self.assertEqual((mise_de_cote / 'DONNEES/existant.txt').read_text(), 'ancien contenu')
        self.assertIsNone(transfert.en_attente(neuve))
        with sqlite3.connect(neuve / 'CONFIG_LOCAL/numeros_factures.db') as db:
            self.assertEqual(db.execute('SELECT facture FROM numeros').fetchone()[0], 'AB-123-456')
        with sqlite3.connect(neuve / 'DONNEES/modeles_generes.db') as db:
            source, image = db.execute('SELECT resultat_json, image FROM modeles').fetchone()
        self.assertTrue(json.loads(source)['source'].startswith(str(neuve) + '/'))
        self.assertEqual(image, b'bin')
        self.assertIn(str(neuve), (neuve / 'CONFIG_LOCAL/preferences.json').read_text())

    def test_kit_sans_donnees_personnelles_et_fusion_sans_doublon(self):
        source = self.d / 'source'
        _machine(source)
        kit, resume = transfert.exporter(self.d / 'kit', kit=True, racine=source)
        with ZipFile(kit) as z:
            noms = z.namelist()
        self.assertFalse(any(n.startswith('CONFIG_LOCAL') for n in noms))
        self.assertNotIn(str(source), ZipFile(kit).read('manifest.json').decode())  # aucun chemin de la machine
        self.assertEqual(resume['modeles_word'], 1)
        collegue = self.d / 'collegue'
        bilan = transfert.importer_modeles(kit, collegue)
        self.assertEqual((bilan['modeles_word'], bilan['xml_reference']), (1, 1))
        with sqlite3.connect(collegue / 'DONNEES/factures.db') as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM factures').fetchone()[0], 0)
            self.assertEqual([r[0] for r in db.execute('SELECT nom FROM gabarits')], ['client A'])
        self.assertEqual(transfert.importer_modeles(kit, collegue)['modeles_word'], 0)
        with self.assertRaises(ValueError):
            transfert.preparer_import_complet(kit, self.d / 'x')

    def test_export_altere_refuse(self):
        source = self.d / 'source'
        _machine(source)
        fichier, _ = transfert.exporter(self.d / 'e', racine=source)
        altere = self.d / 'altere.asydec'
        with ZipFile(fichier) as z, ZipFile(altere, 'w') as sortie:
            for info in z.infolist():
                contenu = z.read(info)
                sortie.writestr(info, b'<modifie/>' if info.filename == 'MODELES_XML/ref.xml' else contenu)
        with self.assertRaises(ValueError):
            transfert.preparer_import_complet(altere, self.d / 'cible')
        self.assertFalse((self.d / 'cible' / transfert.EN_ATTENTE).exists())

    def test_import_depuis_ancien_dossier(self):
        outils = self.d / 'OUTILS'
        _machine(outils, ancienne='/Users/ancien/DEC FRIPERIE/OUTILS')
        (outils / 'DONNEES').mkdir(exist_ok=True)
        cible = self.d / 'AsyDec'
        transfert.preparer_import_complet(outils, cible)
        transfert.appliquer_en_attente(cible)
        self.assertTrue((cible / 'CONFIG_LOCAL/compte.json').is_file())
        self.assertTrue((outils / 'CONFIG_LOCAL/compte.json').is_file())  # source jamais modifiée

    def test_copie_datee_dans_imports(self):
        source = self.d / 'source'
        _machine(source)
        kit, _ = transfert.exporter(self.d / 'kit', kit=True, racine=source)
        imports = self.d / '7 - TRANSFERTS' / '2 - IMPORTS'
        premiere = transfert.archiver_import(kit, imports)
        seconde = transfert.archiver_import(kit, imports)
        self.assertNotEqual(premiere, seconde)
        self.assertTrue(premiere.name.endswith(' - kit.asydec'))
        self.assertEqual(transfert.archiver_import(premiere, imports), premiere)  # déjà rangé : pas de copie
        self.assertEqual(len(list(imports.iterdir())), 2)
        self.assertIsNone(transfert.archiver_import(source, imports))  # ancien dossier : pas copié


if __name__ == '__main__':
    unittest.main()
