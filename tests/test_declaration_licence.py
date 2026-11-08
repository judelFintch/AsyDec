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
        for valeur in ('10632', '20/10/2026', '7,500.00', 'FirstBank DRC SA', '>TVF<', '22,804'):
            self.assertIn(valeur, x)
        for valeur in ('>RCC<', '>RII<', '641,367'):  # au-delà des 8 premières taxes : non affichées
            self.assertNotIn(valeur, x)
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

    def test_position_tarifaire_et_designation_de_l_article_du_dossier(self):
        sydonia = BASE.read_text(encoding='utf-8')  # XML : 8714100000
        v = D.valeurs(sydonia)
        self.assertEqual(v['CODE_SH'], '8714100000')
        licence = {'produits': [{'tarif_douanier': '8711 100000', 'designation': "Motocycles à moteur à\npiston"},
                                {'tarif_douanier': '8714109000', 'designation': 'Pièces détachées'}],
                   'repartition': {'parts': [
                       {'numero': 1, 'articles': [{'article': 1, 'designation': "Motocycles à moteur à piston, 50 cm3"}]},
                       {'numero': 2, 'articles': [{'article': 2}]},
                       {'numero': 3, 'articles': []}]}}
        donnees, controle = D.completer(sydonia, None, D.projet_part(licence, 1))
        self.assertEqual((donnees['CODE_SH'], donnees['DESIGNATION']), ('8711100000', 'Motocycles à moteur à piston, 50 cm3'))
        self.assertEqual(donnees['TAUX'], v['TAUX'])  # le reste reste celui du XML
        self.assertEqual(donnees['TAXE_MONTANT'], v['TAXE_MONTANT'])
        self.assertIn('code SH (case 33)', controle['projet'])
        donnees, _ = D.completer(sydonia, None, D.projet_part(licence, 2))
        self.assertEqual((donnees['CODE_SH'], donnees['DESIGNATION']), ('8714109000', 'Pièces détachées'))
        licence['produits'] = []
        donnees, _ = D.completer(sydonia, None, D.projet_part(licence, 3))  # dossier sans article : XML gardé
        self.assertEqual((donnees['CODE_SH'], donnees['DESIGNATION']), (v['CODE_SH'], v['DESIGNATION']))
        x = textes(D.remplir(MODELE.read_bytes(), D.completer(sydonia, None, D.projet_part(
            {'produits': [{'tarif_douanier': '8711100000'}], 'repartition': {'parts': [
                {'numero': 1, 'articles': [{'article': 1, 'designation': 'MOTOS NEUVES'}]}]}}, 1))[0]))
        self.assertIn('MOTOS NEUVES', x)
        self.assertIn('8711100000', x.replace(' ', ''))

    def test_etape_9_passe_par_l_etape_8(self):
        licence = dict(xml_genere={'contenu': '<ASYCUDA/>'}, repartition={'parts': [{'numero': 1}, {'numero': 2}]})
        with self.assertRaisesRegex(ValueError, 'étape 8'):
            D.sources(licence)
        licence['recuperation_simulation'] = dict(imports=[dict(parts=[2], fichier='s2.xml', contenu='<ASYCUDA/>')])
        self.assertEqual(D.parts_sans_sydonia(licence), [1])

    def test_parts_de_meme_montant_reprennent_le_xml_sydonia_du_groupe(self):
        article = dict(quantite=10, valeur=100)
        parts = [dict(numero=n, fob=100, articles=[article]) for n in (1, 2, 3)]
        parts.append(dict(numero=4, fob=200, articles=[dict(quantite=20, valeur=200)]))
        licence = dict(xml_genere={'contenu': '<ASYCUDA/>'}, repartition={'parts': parts},
                       recuperation_simulation=dict(imports=[dict(parts=[1], fichier='s1.xml', contenu='<ASYCUDA/>')]))
        self.assertEqual(D.parts_sans_sydonia(licence), [4])
        sources = {s['part']: s for s in D.sources(licence)}
        self.assertEqual(sorted(sources), [1, 2, 3])
        self.assertIsNone(sources[1]['partage'])
        self.assertEqual((sources[2]['partage'], sources[3]['partage']), (1, 1))
        self.assertIn('part 1, même montant', sources[3]['origine'])

    def test_xml_sydonia_modele_et_cases_propres_a_la_repartition(self):
        base = BASE.read_text(encoding='utf-8')
        reference = D.valeurs(base)['REF_SUITE']
        autre = base.replace(reference, '347/05/NCA')  # XML attendu d'une autre part du groupe
        propres = D.propre_a_la_part(base, base, autre)
        self.assertEqual(propres.get('REF_SUITE'), '347/05/NCA')
        self.assertNotIn('TOTAL_TAXES', propres)  # identique : reste celle du XML SYDONIA modèle
        self.assertEqual(D.propre_a_la_part(base, base, None), {})

    def test_case_47_huit_premieres_taxes_police_du_modele(self):
        v = D.valeurs(BASE.read_text(encoding='utf-8'))
        codes = [f'T{i:02d}' for i in range(11)]
        for cle in D.TAXES:
            v[cle] = codes if cle == 'TAXE_CODE' else ['1'] * 11
        x = document(D.remplir(MODELE.read_bytes(), v))
        for code in codes[:8]:
            self.assertIn('>' + code + '<', x)  # les 8 premières taxes du XML, comme l'original
        for code in codes[8:]:
            self.assertNotIn('>' + code + '<', x)
        def ligne(code):
            return x[x.rfind('<w:p ', 0, x.index('>' + code + '<')):x.index('>' + code + '<')]
        self.assertNotIn('w:lineRule="exact"', ligne('T07'))  # police et interligne du modèle
        v.update({cle: (codes[:3] if cle == 'TAXE_CODE' else ['1'] * 3) for cle in D.TAXES})
        x = document(D.remplir(MODELE.read_bytes(), v))
        self.assertNotIn('T03', x)
        self.assertNotIn('w:lineRule="exact"', ligne('T02'))

    def test_texte_trop_long_reduit_pour_tenir_dans_sa_case(self):
        import re
        v = D.valeurs(BASE.read_text(encoding='utf-8'))
        self.assertEqual(D.nom_banque('FirstBank DRC SA / LUBUMBASHI'), 'FirstBank DRC SA')
        v['NOM_BANQUE'] = D.nom_banque('FirstBank DRC SA / LUBUMBASHI')
        v['PAYEUR'] = ['KATANGA TVS SARL', 'AV/LUMUMBA Q/KATAKI C/LUBUMBASHI', '--', 'KATANGA']
        x = document(D.remplir(MODELE.read_bytes(), v))
        banque = x[x.rfind('<w:r>', 0, x.index('FirstBank')):x.index('FirstBank')]
        self.assertEqual(re.findall(r'<w:sz w:val="(\d+)"', banque)[-1], '16')  # nom seul, police du modèle
        self.assertNotIn('LUBUMBASHI', x[x.index('FirstBank'):x.index('FirstBank') + 40])
        self.assertIn('>KATANGA<', x)  # toutes les lignes du XML, resserrées dans la case 9
        payeur = x[x.rfind('<w:p ', 0, x.index('>KATANGA<')):x.index('>KATANGA<')]
        self.assertIn('w:lineRule="exact"', payeur)
        v['NOM_BANQUE'] = 'RAWBANK'
        x = document(D.remplir(MODELE.read_bytes(), v))
        banque = x[x.rfind('<w:r>', 0, x.index('RAWBANK')):x.index('RAWBANK')]
        self.assertEqual(re.findall(r'<w:sz w:val="(\d+)"', banque)[-1], '16')  # texte court : modèle inchangé

    def test_modele_non_prepare_refuse(self):
        with self.assertRaises(ValueError):
            D.remplir(b'pas un docx', {})


if __name__ == '__main__':
    unittest.main()
