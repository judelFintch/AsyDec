"""Étape 9 : déclaration Word de chaque part, remplie depuis son XML sans changer la forme du modèle."""
from io import BytesIO
from pathlib import Path
import re
import unittest
from zipfile import ZipFile

from asydec.declarations import declaration_licence as D

RACINE = Path(__file__).resolve().parent.parent
MODELE = RACINE / 'ressources' / 'declaration' / 'Declaration-modele.docx'
BASE = RACINE / 'XML_LICENCES' / 'PARTIE TVS2.xml'


def document(contenu):
    return ZipFile(BytesIO(contenu)).read('word/document.xml').decode()


def textes(contenu):
    """Texte visible du document (contenu des <w:t>), sans les identifiants internes du Word."""
    return ' | '.join(re.findall(r'<w:t(?: [^>]*)?>([^<]*)</w:t>', document(contenu)))


class FormatsTest(unittest.TestCase):
    def test_formats_du_formulaire(self):
        self.assertEqual(D.montant('126360', 2), '126,360.00')
        self.assertEqual(D.montant('2262.32', 4), '2,262.3200')
        self.assertEqual(D.montant('285488130'), '285,488,130')
        self.assertEqual(D.montant(''), '')
        self.assertEqual(D.date_dcu('10/20/26'), '20/10/2026')


@unittest.skipUnless(MODELE.is_file() and BASE.is_file(), 'modèle ou déclaration réelle absents')
class DeclarationTest(unittest.TestCase):
    def test_valeurs_et_remplissage_sans_changer_la_forme(self):
        contenu = BASE.read_text(encoding='utf-8')
        v = D.valeurs(contenu)
        self.assertEqual((v['NUMERO_E'], v['DATE_E'], v['NUMERO_Q']), ('10632', '20/10/2026', '4911'))
        self.assertEqual(v['TOTAL_FACTURE'], '7,500.00')
        self.assertEqual(v['TAUX'], '2,262.3200')
        self.assertEqual(v['CODE_SH'], '8714100000')
        self.assertEqual(len(v['TAXE_CODE']), 13)
        self.assertEqual(v['TAXE_MONTANT'][0], '2,850,523')
        self.assertEqual(v['DESTINATAIRE'][0], 'KATANGA TVS SARL')
        modele = MODELE.read_bytes()
        rempli = D.remplir(modele, v)
        x = document(rempli)
        self.assertEqual(re.findall(r'\{\{[A-Z_]+\}\}', x), [])
        for valeur in ('10632', '20/10/2026', '7,500.00', 'FirstBank DRC SA / LUBUMBASHI', 'RII', '641,367'):
            self.assertIn(valeur, x)
        for ancien in ('9797', 'DEC1500886', 'RAWBANK', 'T443FFV', '135,703,015'):
            self.assertNotIn(ancien, x)
        # Forme conservée : mêmes fichiers (image de fond, styles), même nombre de zones de texte.
        self.assertEqual(sorted(ZipFile(BytesIO(rempli)).namelist()), sorted(ZipFile(BytesIO(modele)).namelist()))
        self.assertEqual(ZipFile(BytesIO(rempli)).read('word/media/image1.png'), ZipFile(BytesIO(modele)).read('word/media/image1.png'))
        self.assertEqual(x.count('<w:txbxContent'), document(modele).count('<w:txbxContent'))

    def test_adresse_limitee_aux_lignes_de_la_case(self):
        v = D.valeurs(BASE.read_text(encoding='utf-8'))
        v['DESTINATAIRE'] = [f'LIGNE {i}' for i in range(1, 8)]
        x = document(D.remplir(MODELE.read_bytes(), v))
        self.assertIn('LIGNE 4', x)
        self.assertNotIn('LIGNE 5', x)

    def test_cases_vides_du_xml_sydonia_completees_depuis_asydec(self):
        sydonia = BASE.read_text(encoding='utf-8')
        for balise in ('<Number>10632</Number>', '<Number>10490</Number>', '<Number>4911</Number>'):
            sydonia = sydonia.replace(balise, '<Number/>')  # simulation : E, L, Q pas encore attribués
        donnees, controle = D.completer(sydonia)
        self.assertIn('N° E (case A)', controle['manquantes'])
        donnees, controle = D.completer(sydonia, BASE.read_text(encoding='utf-8'))
        self.assertEqual(donnees['NUMERO_E'], '10632')
        self.assertIn('N° E (case A)', controle['completees'])
        self.assertNotIn('N° E (case A)', controle['manquantes'])
        self.assertIn('complété depuis AsyDec', D.texte_controle(controle))
        self.assertEqual(donnees['TAXE_MONTANT'][0], '2,850,523')  # case 47 : celle du XML SYDONIA

    def test_e_l_q_manifeste_plaques_toujours_de_l_etape_3(self):
        sydonia = BASE.read_text(encoding='utf-8')  # porte E 10632, manifeste 2026 7628, plaques T281BMW…
        licence = {'repartition': {'parts': [{'numero': 1, 'plaque': 'T104JHN/T622SMI', 'informations_declaration': dict(
            numero_e='4567', date_enregistrement='15/05/2026', numero_liquidation='4462', date_liquidation='15/05/2026',
            numero_quittance='2564', date_quittance='18/05/2026', manifeste='3879')}]}}
        donnees, controle = D.completer(sydonia, None, D.projet_part(licence, 1))
        self.assertEqual((donnees['NUMERO_E'], donnees['DATE_E'], donnees['NUMERO_L'], donnees['NUMERO_Q'], donnees['DATE_Q']),
                         ('4567', '15/05/2026', '4462', '2564', '18/05/2026'))
        self.assertEqual(donnees['MANIFESTE'], '3879')
        self.assertEqual((donnees['PLAQUE_ARRIVEE'], donnees['PLAQUE_FRONTIERE']), ('T104JHN/T622SMI',) * 2)
        self.assertEqual(donnees['TAUX'], '2,262.3200')  # le reste vient du XML
        self.assertIn('N° E (case A)', controle['projet'])
        x = textes(D.remplir(MODELE.read_bytes(), donnees))
        self.assertIn('4567', x)
        for ancien in ('10632', '7628', 'T281BMW', '10490', '4911'):
            self.assertNotIn(ancien, x)
        # Étape 3 incomplète : signalé
        licence['repartition']['parts'][0]['informations_declaration']['manifeste'] = ''
        self.assertIn('manifeste (case 40) (étape 3)', D.completer(sydonia, None, D.projet_part(licence, 1))[1]['manquantes'])

    def test_etape_9_passe_par_l_etape_8(self):
        licence = dict(xml_genere={'contenu': '<ASYCUDA/>'}, repartition={'parts': [{'numero': 1}, {'numero': 2}]})
        with self.assertRaisesRegex(ValueError, 'étape 8'):
            D.sources(licence)
        licence['recuperation_simulation'] = dict(imports=[dict(parts=[2], fichier='s2.xml', contenu='<ASYCUDA/>')])
        self.assertEqual(D.parts_sans_sydonia(licence), [1])

    def test_modele_non_prepare_refuse(self):
        with self.assertRaises(ValueError):
            D.remplir(b'pas un docx', {})


if __name__ == '__main__':
    unittest.main()
