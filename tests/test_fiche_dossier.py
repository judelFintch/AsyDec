from copy import deepcopy
from unittest import TestCase

import pymupdf

from asydec.declarations import fiche_dossier
from tests.test_facture_licence import licence


class FicheDossierTest(TestCase):
    def texte(self, contenu):
        return '\n'.join(p.get_text() for p in pymupdf.open('pdf', contenu))

    def test_informations_et_toutes_les_repartitions(self):
        l = licence()
        texte = self.texte(fiche_dossier.pdf(l))
        self.assertIn(l['numero_validation'], texte)
        self.assertIn('Répartitions', texte)
        document = pymupdf.open('pdf', fiche_dossier.pdf(l))
        self.assertEqual(document.page_count, 1)
        self.assertGreater(document[0].rect.width, document[0].rect.height)  # paysage
        for part in l['repartition']['parts']:
            self.assertIn(part['plaque'], texte)

    def test_beaucoup_de_parts_sur_plusieurs_pages_numerotees(self):
        l = licence()
        l = deepcopy(l)
        parts = l['repartition']['parts']
        l['repartition']['parts'] = [dict(p, numero=i + 1) for i, p in enumerate(parts * 40)]
        document = pymupdf.open('pdf', fiche_dossier.pdf(l))
        self.assertGreater(document.page_count, 1)
        self.assertIn(f'Page {document.page_count} / {document.page_count}', document[-1].get_text())

    def test_dossier_sans_repartition(self):
        l = licence()
        l.pop('repartition', None)
        l.pop('informations_declaration', None)
        texte = self.texte(fiche_dossier.pdf(l))
        self.assertIn('Répartition non encore faite', texte)

    def test_plusieurs_articles_detail_par_part(self):
        l = deepcopy(licence())
        for part in l['repartition']['parts']:
            part['articles'] = part['articles'] * 2
        self.assertIn('Détail des articles par part', self.texte(fiche_dossier.pdf(l)))
