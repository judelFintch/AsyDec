"""Factures Word : page blanche avant le manifeste, date absente du modèle, date fixée une fois par dossier."""
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import patch
from xml.dom import minidom
from zipfile import ZipFile

from asydec.declarations import factures as F
from asydec.declarations.preparer_facture import preparer_date, retirer_page_vide

RUN = '<w:r><w:rPr><w:rFonts w:ascii="Courier New"/><w:b/></w:rPr><w:t>{}</w:t></w:r>'
SECTION = '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr>'


def docx(corps):
    xml = f'<w:document xmlns:w="{F.W}"><w:body>{corps}</w:body></w:document>'
    sortie = BytesIO()
    with ZipFile(sortie, 'w') as z:
        z.writestr('[Content_Types].xml', '<Types/>')
        z.writestr('word/document.xml', xml)
    return sortie.getvalue()


def corps(contenu):
    with ZipFile(BytesIO(contenu)) as z:
        return minidom.parseString(z.read('word/document.xml')).getElementsByTagNameNS(F.W, 'body')[0]


def paragraphes(contenu):
    return [n for n in corps(contenu).childNodes if n.localName == 'p']


# Modèle du type SHABANI : ligne de date vidée au-dessus de « INV N° », packing list puis saut de section
# porté par un paragraphe vide, puis manifeste.
SHABANI = docx(
    '<w:p></w:p>'
    '<w:p>' + RUN.format('INV N°:{{NUMERO_FACTURE}}') + '</w:p>'
    '<w:p>' + RUN.format('PACKING LIST {{POIDS}} {{COLIS}} {{FOB}} {{PLAQUE}}') + '</w:p>'
    '<w:p>' + RUN.format('Signature') + '</w:p>'
    '<w:p><w:pPr><w:tabs/>' + SECTION + '</w:pPr><w:r><w:tab/></w:r></w:p>'
    '<w:p>' + RUN.format('MANIFEST') + '</w:p>' + SECTION)


class PageVideTest(TestCase):
    def test_tampon_flottant_conserve_sans_paragraphe_debordant(self):
        dessin = ('<w:r><w:drawing xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">'
                  '<wp:anchor><wp:wrapNone/></wp:anchor></w:drawing></w:r>')
        source = docx('<w:p>' + RUN.format('PACKING LIST') + '</w:p>'
                      '<w:p><w:r><w:br/></w:r></w:p>'
                      '<w:p><w:pPr>' + SECTION + '</w:pPr>' + dessin + '<w:r><w:br/></w:r></w:p>'
                      '<w:p>' + RUN.format('MANIFEST') + '</w:p>' + SECTION)
        corrige = retirer_page_vide(source)
        ps = paragraphes(corrige)
        self.assertEqual(len(ps), 3)
        self.assertEqual(len(ps[1].getElementsByTagNameNS(F.W, 'drawing')), 1)
        self.assertEqual(len(ps[1].getElementsByTagNameNS(F.W, 'sectPr')), 1)
        self.assertFalse(ps[1].getElementsByTagNameNS(F.W, 'br'))
        spacing = ps[1].getElementsByTagNameNS(F.W, 'spacing')[0]
        self.assertEqual(spacing.getAttribute('w:line'), '20')
        self.assertEqual(retirer_page_vide(corrige), corrige)

    def test_saut_de_section_remonte_et_paragraphe_vide_retire(self):
        corrige = retirer_page_vide(SHABANI)
        p = paragraphes(corrige)
        self.assertEqual(len(p), len(paragraphes(SHABANI)) - 1)
        signature = next(x for x in p if 'Signature' in x.toxml())
        self.assertTrue(signature.getElementsByTagNameNS(F.W, 'sectPr'))
        # Police et gras du texte inchangés, section finale intacte.
        self.assertEqual(len(signature.getElementsByTagNameNS(F.W, 'rFonts')), 1)
        self.assertEqual(sum(1 for n in corps(corrige).childNodes if n.localName == 'sectPr'), 1)

    def test_saut_continu_ou_paragraphe_avec_texte_inchange(self):
        continu = docx('<w:p>' + RUN.format('A') + '</w:p><w:p><w:pPr><w:sectPr><w:type w:val="continuous"/>'
                       '</w:sectPr></w:pPr></w:p>' + SECTION)
        self.assertEqual(retirer_page_vide(continu), continu)
        plein = docx('<w:p>' + RUN.format('A') + '</w:p><w:p><w:pPr>' + SECTION + '</w:pPr>' + RUN.format('B')
                     + '</w:p>' + SECTION)
        self.assertEqual(retirer_page_vide(plein), plein)


class DateAbsenteTest(TestCase):
    def test_date_ajoutee_au_dessus_du_numero_avec_sa_police(self):
        prepare = preparer_date(SHABANI)
        self.assertIn('DATE_FACTURE', F.inspecter(prepare, exiger=False))
        ligne = paragraphes(prepare)[0]
        self.assertEqual(''.join(F._texte(t) for t in ligne.getElementsByTagNameNS(F.W, 't')), 'Date: {{DATE_FACTURE}}')
        self.assertTrue(ligne.getElementsByTagNameNS(F.W, 'rFonts'))
        self.assertEqual(len(paragraphes(prepare)), len(paragraphes(SHABANI)))

    def test_modele_qui_a_deja_sa_date_inchange(self):
        avec = docx('<w:p>' + RUN.format('Date: {{DATE_FACTURE}}') + '</w:p><w:p>'
                    + RUN.format('INV N°:{{NUMERO_FACTURE}}') + '</w:p>')
        self.assertEqual(preparer_date(avec), avec)


class DateUneFoisParDossierTest(TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name) / 'factures.db'
        source = Path(temp.name) / 'shabani.docx'
        source.write_bytes(SHABANI)
        self.gabarit = F.importer(source, self.base)
        resultat = {'resume': {'poids': 20150, 'fob': 7400}, 'colis': [790]}
        self.modeles = {
            23: {'supprime': False, 'importateur': 'SHABANI SUMAILI CHARLY', 'plaque': 'T524ECQ/T620ECT', 'resultat': resultat},
            24: {'supprime': False, 'importateur': 'SHABANI SUMAILI CHARLY', 'plaque': 'T524ECQ / T620ECT', 'resultat': resultat},
            25: {'supprime': False, 'importateur': 'AUTRE', 'plaque': 'T999XYZ', 'resultat': resultat},
            26: {'supprime': False, 'importateur': 'AUTRE', 'plaque': 'T888XYZ',
                 'resultat': dict(resultat, correction={'modele_initial': 25})},
        }

    def generer(self, modele_id, quand):
        class Horloge(datetime):
            @classmethod
            def now(cls, tz=None):
                return quand.replace(tzinfo=tz)
        with patch('asydec.declarations.modeles_generes.detail', side_effect=lambda i, base=None: self.modeles[i]), \
                patch.object(F, 'datetime', Horloge):
            return F.generer(modele_id, self.gabarit, 'test', self.base)

    def test_trois_mois_avant_puis_conservee_pour_le_meme_dossier(self):
        premiere = self.generer(23, datetime(2026, 11, 11, 8, 35))
        self.assertEqual(premiere['date_facture'], '11/08/2026')
        self.assertIn(b'Date: 11/08/2026', ZipFile(BytesIO(premiere['contenu'])).read('word/document.xml'))
        # Même camion, même importateur, nouvelle répartition trois semaines plus tard : même date.
        reprise = self.generer(24, datetime(2026, 12, 2, 9, 0))
        self.assertEqual(reprise['date_facture'], '11/08/2026')
        self.assertNotEqual(reprise['numero'], premiere['numero'])
        # Régénérer le même modèle rend la même facture.
        self.assertEqual(self.generer(23, datetime(2027, 1, 20))['date_facture'], '11/08/2026')

    def test_correction_garde_la_date_meme_avec_une_autre_plaque(self):
        self.generer(25, datetime(2026, 11, 11))
        self.assertEqual(self.generer(26, datetime(2027, 3, 1))['date_facture'], '11/08/2026')

    def test_autre_dossier_nouvelle_date(self):
        self.generer(23, datetime(2026, 11, 11))
        self.assertEqual(self.generer(25, datetime(2026, 11, 20))['date_facture'], '20/08/2026')

    def test_meme_camion_bien_plus_tard_nouvelle_date(self):
        self.generer(23, datetime(2026, 11, 11))
        plus_tard = datetime(2026, 11, 11) + timedelta(days=F.DELAI_MEME_DOSSIER + 5)
        self.assertNotEqual(self.generer(24, plus_tard)['date_facture'], '11/08/2026')

    def test_ancienne_facture_sans_date_mise_a_niveau_sans_changer_ses_numeros(self):
        ancien = F.remplir(SHABANI, {'NUMERO_FACTURE': 'SX-1', 'POIDS': '1', 'COLIS': '1', 'FOB': '1', 'PLAQUE': 'P'},
                           verifier=False)
        with F.connexion(self.base) as db:
            db.execute('INSERT INTO factures(numero,manifeste,modele_id,gabarit_id,date,auteur,contenu) '
                       'VALUES(?,?,?,?,?,?,?)', ('SX-1', 'M-1', 23, self.gabarit, '2026-11-11T08:35:58+02:00', 'test', ancien))
        f = self.generer(23, datetime(2026, 11, 30))
        self.assertEqual((f['numero'], f['manifeste'], f['date_facture']), ('SX-1', 'M-1', '11/08/2026'))
        xml = ZipFile(BytesIO(f['contenu'])).read('word/document.xml')
        self.assertIn(b'Date: 11/08/2026', xml)
        self.assertEqual(len(paragraphes(f['contenu'])), len(paragraphes(ancien)) - 1)


if __name__ == '__main__':
    main()
