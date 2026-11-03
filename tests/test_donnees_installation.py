from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from asydec.systeme.donnees_installation import importer


class ImportInstallationTest(TestCase):
    def test_copie_donnees_et_registre_sans_modifier_source(self):
        with TemporaryDirectory() as d:
            source=Path(d)/'OUTILS';destination=Path(d)/'nouveau'
            (source/'CONFIG_LOCAL').mkdir(parents=True)
            (source/'CONFIG_LOCAL/compte.json').write_text('{"test":true}')
            for nom in ('CONFIG_LOCAL/numeros_factures.db','DONNEES/factures.db'):
                p=source/nom;p.parent.mkdir(exist_ok=True)
                with sqlite3.connect(p) as db:
                    db.execute('CREATE TABLE exemple(valeur TEXT)')
                    db.execute('INSERT INTO exemple VALUES(?)',('conserve',))
            importer(source,destination)
            for nom in ('CONFIG_LOCAL/numeros_factures.db','DONNEES/factures.db'):
                with sqlite3.connect(destination/nom) as db:
                    self.assertEqual(db.execute('SELECT valeur FROM exemple').fetchone()[0],'conserve')
                self.assertTrue((source/nom).exists())
            with self.assertRaises(ValueError): importer(source,destination)

if __name__=='__main__':
    main()
