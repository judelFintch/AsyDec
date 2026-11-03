"""Factures : fidélité des composants Word et numérotation archivée."""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import patch
from xml.dom import minidom
from zipfile import ZipFile

from asydec.declarations import factures as F


def document(texte=None):
    if texte is None:
        texte = ('<w:r><w:rPr><w:b/></w:rPr><w:t>{{NUMERO_</w:t></w:r>'
                 '<w:r><w:t>FACTURE}} / {{POIDS}} kg / {{COLIS}} / {{FOB}} USD</w:t></w:r>')
    xml = f'<w:document xmlns:w="{F.W}"><w:body><w:p>{texte}</w:p></w:body></w:document>'
    sortie = BytesIO()
    with ZipFile(sortie, 'w') as z:
        z.writestr('[Content_Types].xml', '<Types/>')
        z.writestr('word/document.xml', xml)
        z.writestr('word/header1.xml', f'<w:hdr xmlns:w="{F.W}"><w:p><w:r><w:t>{{{{IMPORTATEUR}}}}</w:t></w:r></w:p><w:p><w:r><w:t>{{{{PLAQUE}}}}</w:t></w:r></w:p></w:hdr>')
        z.writestr('word/media/logo.png', 'logo inchangé'.encode())
        z.writestr('word/styles.xml', b'<styles/>')
    return sortie.getvalue()


class FacturesTest(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)/'factures.db'
        self.modele = {'supprime': False, 'importateur': 'A & B', 'plaque': 'ABC123',
                       'resultat': {'resume': {'poids': 1234.5, 'fob': 5678.9}, 'colis': [10, 20]}}
        self.source = Path(self.temp.name)/'facture.docx'
        self.source.write_bytes(document())
        self.gabarit = F.importer(self.source, self.base)

    def generer(self, modele_id=42):
        return F.generer(modele_id, self.gabarit, 'test', self.base)

    def test_champs_fragmentes_et_composants_preserves(self):
        valeurs = dict.fromkeys(F.CHAMPS, 'x')
        valeurs.update(NUMERO_FACTURE='FAC-001', POIDS='1 234,50', COLIS='30', FOB='5 678,90', IMPORTATEUR='A & B')
        resultat = F.remplir(document(), valeurs)
        with ZipFile(BytesIO(resultat)) as z:
            doc = minidom.parseString(z.read('word/document.xml'))
            texte = ''.join(F._texte(t) for t in doc.getElementsByTagNameNS(F.W, 't'))
            self.assertEqual(texte, 'FAC-001 / 1 234,50 kg / 30 / 5 678,90 USD')
            self.assertEqual(len(doc.getElementsByTagNameNS(F.W, 'b')), 1)
            self.assertIn(b'A &amp; B', z.read('word/header1.xml'))
            self.assertEqual(z.read('word/media/logo.png'), 'logo inchangé'.encode())
            self.assertEqual(z.read('word/styles.xml'), b'<styles/>')

    def test_refuse_modele_incomplet_et_champs_inconnus(self):
        with self.assertRaisesRegex(ValueError, 'Ajoutez'):
            F.inspecter(document('<w:r><w:t>{{FOB}}</w:t></w:r>'))
        with self.assertRaisesRegex(ValueError, 'inconnus'):
            F.inspecter(document('<w:r><w:t>{{NUMERO_FACTURE}}{{POIDS}}{{COLIS}}{{FOB}}{{INCONNU}}</w:t></w:r>'))

    def test_totaux_numero_unique_et_retelechargement(self):
        with patch('asydec.declarations.modeles_generes.detail', return_value=self.modele):
            a, b = self.generer(), self.generer(43)
        self.assertNotEqual(a['numero'], b['numero'])
        self.assertEqual(F.lire(a['id'], self.base)['contenu'], a['contenu'])
        self.assertEqual(len(F.lister_factures(42, self.base)), 1)
        self.assertEqual(self.source.read_bytes(), document())
        with ZipFile(BytesIO(a['contenu'])) as z:
            xml = z.read('word/document.xml').decode()
            self.assertIn('1 234,50', xml)
            self.assertIn('5 678,90', xml)
            self.assertIn('30', xml)
            self.assertIn(a['numero'], xml)

    def test_concurrence_sans_doublon(self):
        with patch('asydec.declarations.modeles_generes.detail', return_value=self.modele):
            with ThreadPoolExecutor(max_workers=3) as pool:
                factures = list(pool.map(lambda i: self.generer(i), range(6)))
        self.assertEqual(len({f['numero'] for f in factures}), 6)

    def test_echec_ne_cree_pas_de_facture(self):
        with patch('asydec.declarations.modeles_generes.detail', return_value=self.modele):
            with patch.object(F, 'remplir', side_effect=ValueError('erreur')):
                with self.assertRaises(ValueError):
                    self.generer()
        self.assertEqual(F.lister_factures(42, self.base), [])
        import sqlite3
        with sqlite3.connect(self.base.parent / 'numeros_factures.db') as db:
            self.assertEqual(db.execute('SELECT count(*) FROM numeros').fetchone()[0], 1)

    def test_integration_modele_reel_archive(self):
        from tests.test_modeles_generes import ModelesGeneresTest
        fixture = ModelesGeneresTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        identifiant = fixture.enregistrer()
        from asydec.declarations import modeles_generes
        modeles_generes.definir_plaque(identifiant, 'T974EBZ', 'alice', base=fixture.base)
        facture = F.generer(identifiant, self.gabarit, 'alice', self.base, fixture.base)
        with ZipFile(BytesIO(facture['contenu'])) as z:
            doc = minidom.parseString(z.read('word/document.xml'))
            texte = ''.join(F._texte(t) for t in doc.getElementsByTagNameNS(F.W, 't'))
        self.assertIn('150,00 kg / 21 / 175,00 USD', texte)
        self.assertEqual(F.lister_factures(identifiant, self.base)[0]['numero'], facture['numero'])

    def test_meme_modele_meme_facture_meme_manifeste(self):
        with patch('asydec.declarations.modeles_generes.detail', return_value=self.modele):
            with ThreadPoolExecutor(max_workers=3) as pool:
                factures = list(pool.map(lambda _: self.generer(), range(5)))
        self.assertEqual(len({f['numero'] for f in factures}), 1)
        self.assertEqual(len({f['manifeste'] for f in factures}), 1)
        self.assertEqual(len(F.lister_factures(42, self.base)), 1)
        self.assertTrue(all(f['contenu'] == factures[0]['contenu'] for f in factures))

    def test_numeros_restent_reserves_apres_reset_des_factures(self):
        with patch('asydec.declarations.modeles_generes.detail', return_value=self.modele):
            premiere = self.generer()
        import sqlite3
        registre = self.base.parent / 'numeros_factures.db'
        self.base.unlink()
        self.gabarit = F.importer(self.source, self.base)
        with patch('asydec.declarations.modeles_generes.detail', return_value=self.modele):
            seconde = self.generer()
        self.assertNotEqual(premiere['numero'], seconde['numero'])
        self.assertNotEqual(premiere['manifeste'], seconde['manifeste'])
        with sqlite3.connect(registre) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM numeros').fetchone()[0], 2)
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('DELETE FROM numeros')

    def test_ancienne_facture_garde_son_code(self):
        import sqlite3
        with F.connexion(self.base) as db:
            db.execute('INSERT INTO factures(numero,modele_id,gabarit_id,date,auteur,contenu) VALUES(?,?,?,?,?,?)',
                       ('FAC-2026-000001',42,self.gabarit,'2026-11-03','test', F.remplir(document(), dict.fromkeys(F.CHAMPS, '1'))))
        with patch('asydec.declarations.modeles_generes.detail', return_value=self.modele):
            a = self.generer()
            b = self.generer()
        self.assertEqual(a['numero'], 'FAC-2026-000001')
        self.assertEqual(a['manifeste'], b['manifeste'])
        self.assertEqual(len(F.lister_factures(42,self.base)), 1)

    def test_collision_aleatoire_rejetee(self):
        with patch.object(F.secrets, 'choice', return_value='A'), patch.object(F.secrets, 'randbelow',
                side_effect=[1,2,3,4, 1,2,3,4, 5,6,7,8]):
            a = F._reserver_numeros(self.base)
            b = F._reserver_numeros(self.base)
        self.assertEqual(a, ('AA-001-002', '0003-ML0004'))
        self.assertEqual(b, ('AA-005-006', '0007-ML0008'))

    def test_import_ne_cree_pas_de_facture_ni_de_fichier_word(self):
        self.assertEqual(F.lister_factures(42, self.base), [])
        self.assertEqual(list(Path(self.temp.name).glob('*.docx')), [self.source])
        self.assertFalse((self.base.parent / 'numeros_factures.db').exists())

    def test_modele_supprime_refuse(self):
        with patch('asydec.declarations.modeles_generes.detail', return_value=dict(self.modele, supprime=True)):
            with self.assertRaisesRegex(ValueError, 'Restaurez'):
                self.generer()


if __name__ == '__main__':
    main()
