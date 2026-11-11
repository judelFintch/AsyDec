from unittest import TestCase
from asydec.declarations.factures import _parties
from asydec.declarations.preparer_facture import cadrer_immatriculation, texte
from tests.test_factures import document


class CadragePlaqueTest(TestCase):
    def test_libelle_et_plaque_reunis_dans_les_deux_vues(self):
        for gauche, largeur, offset in [('53.1', '166.15', '674370'), ('104', '70', '1320800'),
                                        ('250', '100', '3175000')]:
            def p(t):
                return '<w:p><w:r><w:rPr><w:sz w:val="21"/></w:rPr><w:t>' + t + '</w:t></w:r></w:p>'
            vml = ('<w:r><w:pict xmlns:v="urn:schemas-microsoft-com:vml">'
                   '<v:shape style="margin-left:-32.75pt;width:135pt;"><v:textbox>' + p('REGISTRATION NO’S') + '</v:textbox></v:shape>'
                   f'<v:shape style="margin-left:{gauche}pt;width:{largeur}pt;"><v:textbox>' + p('T524ECQ/T620ECT') + '</v:textbox></v:shape></w:pict></w:r>')
            def anchor(t, x):
                return ('<wp:anchor><wp:positionH><wp:posOffset>' + x + '</wp:posOffset></wp:positionH>'
                        '<wp:extent cx="100" cy="100"/>' + p(t) + '</wp:anchor>')
            drawings = ('<w:r><w:drawing xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">'
                        + anchor('REGISTRATION NO’S', '-415925') + anchor('T524ECQ/T620ECT', offset) + '</w:drawing></w:r>')
            source = document(vml + drawings)
            result = cadrer_immatriculation(source)
            archive, parts = _parties(result)
            try:
                doc = parts['word/document.xml']
                for tag in ('v:shape', 'wp:anchor'):
                    shapes = list(doc.getElementsByTagName(tag))
                    self.assertEqual(texte(shapes[0]), 'REGISTRATION NO’S  T524ECQ/T620ECT')
                    self.assertEqual(texte(shapes[1]), '')
                self.assertEqual(archive.read('word/media/logo.png'), 'logo inchangé'.encode())
                self.assertEqual(cadrer_immatriculation(result), result)
            finally:
                archive.close()

    def test_case_bornee_par_le_trailer_et_plaque_non_tanzanienne(self):
        source = document('<w:r><w:pict xmlns:v="urn:schemas-microsoft-com:vml">'
                          '<v:shape id="client-A" style="margin-left:10pt;margin-top:20pt;width:120pt;">'
                          '<v:textbox><w:p><w:r><w:t>REGISTRATION NO:</w:t></w:r></w:p></v:textbox></v:shape>'
                          '<v:shape id="autre-zone" style="margin-left:70pt;margin-top:21pt;width:200pt;">'
                          '<v:textbox><w:p><w:r><w:t>AB-123-CD / XY-456-ZZ</w:t></w:r></w:p></v:textbox></v:shape>'
                          '<v:shape style="margin-left:230pt;margin-top:20pt;width:120pt;">'
                          '<v:textbox><w:p><w:r><w:t>TRAILER (1)</w:t></w:r></w:p></v:textbox></v:shape>'
                          '</w:pict></w:r>')
        result = cadrer_immatriculation(source, plaque='AB-123-CD / XY-456-ZZ')
        archive, parts = _parties(result)
        try:
            shapes = list(parts['word/document.xml'].getElementsByTagName('v:shape'))
            self.assertEqual(texte(shapes[0]), 'REGISTRATION NO:  AB-123-CD / XY-456-ZZ')
            self.assertIn('width:214.25pt;', shapes[0].getAttribute('style'))
            self.assertEqual(texte(shapes[1]), '')
            self.assertEqual(texte(shapes[2]), 'TRAILER (1)')
            self.assertEqual(cadrer_immatriculation(result, plaque='AB-123-CD / XY-456-ZZ'), result)
        finally:
            archive.close()
