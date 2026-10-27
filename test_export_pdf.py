"""Impression PDF des modèles validés et des comparaisons, sur données temporaires."""
import hashlib
import re
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import comparaison_prediction
import export_pdf as P
import modeles_generes as M
import test_modeles_generes as TM
import ui.modeles_generes as U


def structure_valide(test, octets):
    """En-tête, fin, startxref et positions de chaque objet cohérents."""
    test.assertTrue(octets.startswith(b'%PDF-1.4'))
    test.assertTrue(octets.rstrip().endswith(b'%%EOF'))
    debut = int(re.search(rb'startxref\n(\d+)', octets).group(1))
    test.assertEqual(octets[debut:debut + 4], b'xref')
    positions = re.findall(rb'(\d{10}) 00000 n ', octets)
    for numero, position in enumerate(positions, 1):
        test.assertTrue(octets[int(position):].startswith(b'%d 0 obj' % numero))


class ExportPdfTest(unittest.TestCase):
    def setUp(self):
        # Même dossier de déclaration temporaire que les tests des modèles générés.
        TM.ModelesGeneresTest.setUp(self)
        self.identifiant = M.enregistrer(self.resultat, self.source, 'alice', base=self.base)
        self.pdf = self.racine / 'sortie.pdf'

    def empreintes(self):
        return [hashlib.sha256(p.read_bytes()).hexdigest() for p in (self.source, self.base)]

    def test_modele_non_valide_refuse(self):
        self.assertRaisesRegex(ValueError, 'Validé localement', P.pdf_modele,
                               M.detail(self.identifiant, base=self.base), self.pdf, 'alice')
        M.changer_statut(self.identifiant, 'rejete', 'alice', 'motif', base=self.base)
        self.assertRaises(ValueError, P.pdf_modele, M.detail(self.identifiant, base=self.base), self.pdf, 'alice')
        self.assertFalse(self.pdf.exists())

    def test_modele_valide_pdf_lisible_sans_modifier_les_donnees(self):
        M.changer_statut(self.identifiant, 'valide', 'alice', base=self.base)
        avant = self.empreintes()
        P.pdf_modele(M.detail(self.identifiant, base=self.base), self.pdf, 'bob')
        octets = self.pdf.read_bytes()
        structure_valide(self, octets)
        self.assertIn('Modèle validé'.encode('cp1252'), octets)
        self.assertIn('ne vaut pas acceptation douanière'.encode('cp1252'), octets)
        self.assertIn(b'par bob', octets)
        self.assertIn(b'Total', octets)
        self.assertEqual(self.empreintes(), avant)
        self.assertFalse(list(self.racine.glob('*.tmp')))

    def test_comparaison_pdf(self):
        rapport = comparaison_prediction.comparer_xmls(self.source, self.source)
        rapport['source'] = 'Modèle n° 1 : XML exporté archivé'
        avant = self.empreintes()
        P.pdf_comparaison(rapport, self.pdf, 'alice')
        octets = self.pdf.read_bytes()
        structure_valide(self, octets)
        self.assertIn(b'Taxes globales', octets)
        self.assertIn('Écart'.encode('cp1252'), octets)
        self.assertEqual(self.empreintes(), avant)

    def test_pagination_et_entete_repete(self):
        doc = P.Document()
        doc.tableau([('Colonne', 1, 'w'), ('Valeur', 1, 'e')], [((f'ligne {i}', i), False) for i in range(200)])
        octets = doc.octets('pied')
        nombre = len(doc.pages)
        self.assertGreater(nombre, 2)
        self.assertIn(b'/Count %d' % nombre, octets)
        self.assertEqual(octets.count(b'(Colonne)'), nombre)
        self.assertIn(b'page %d/%d' % (nombre, nombre), octets)
        structure_valide(self, octets)

    def test_caracteres_hors_winansi_et_echappement(self):
        doc = P.Document()
        doc.paragraphe('a − b ≠ (c) \\ « é »')
        flux = '\n'.join(doc.pages[0]).encode('latin-1')
        self.assertIn(b'a - b != \\(c\\) \\\\ \xab \xe9 \xbb', flux)

    def test_cellule_trop_longue_coupee(self):
        texte = P._couper('x' * 500, 8, 50)
        self.assertTrue(texte.endswith('…'))
        self.assertLessEqual(P.largeur(texte, 8), 50)


class BoutonPdfTest(unittest.TestCase):
    def page(self, statut, verrouillee=False):
        return SimpleNamespace(selection=lambda: 7, modeles={'7': {'statut': statut, 'exporte': False}},
            app=SimpleNamespace(session_verrouillee=verrouillee, utilisateur='alice'),
            comparer_bouton=Mock(), pdf_bouton=Mock(), xml_bouton=Mock())

    def test_bouton_actif_seulement_si_valide_et_session_libre(self):
        for statut, verrouillee, attendu in (('valide', False, 'normal'), ('en_attente', False, 'disabled'),
                                             ('rejete', False, 'disabled'), ('valide', True, 'disabled')):
            page = self.page(statut, verrouillee)
            U.PageModelesGeneres.actualiser_comparaison(page)
            page.pdf_bouton.configure.assert_called_with(state=attendu)

    def test_garde_relit_le_statut_meme_si_bouton_contourne(self):
        page = self.page('valide')
        with patch.object(U.service, 'detail', return_value={'statut': 'en_attente'}), \
                patch.object(U.messagebox, 'showerror') as erreur, \
                patch('ui.comparaison.enregistrer_pdf') as enregistrer:
            U.PageModelesGeneres.imprimer(page)
        erreur.assert_called_once()
        enregistrer.assert_not_called()

    def test_session_verrouillee_aucune_action(self):
        page = self.page('valide', True)
        with patch.object(U.service, 'detail') as detail:
            U.PageModelesGeneres.imprimer(page)
        detail.assert_not_called()


if __name__ == '__main__':
    unittest.main()
