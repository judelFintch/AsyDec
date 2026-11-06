import tempfile
import unittest
from pathlib import Path

from asydec.declarations import recuperation_simulation as regles, licences_ouvertes as registre, mise_a_jour_repartitions
from asydec.declarations.documents_finaux import preparer_licence

GENERE = '''<ASYCUDA><Identification><Registration><Number>5000</Number><Date>06/19/26</Date></Registration>
<Manifest_reference_number>4320</Manifest_reference_number></Identification>
<Valuation><Gs_Invoice><Amount_foreign_currency>84215.00</Amount_foreign_currency><Currency_code>USD</Currency_code></Gs_Invoice></Valuation>
<Financial><Amounts><Totals_taxes><null/></Totals_taxes></Amounts></Financial>
<Item><Licence_number>LIC</Licence_number><Tarification><Supplementary_unit><Suppplementary_unit_quantity>5000</Suppplementary_unit_quantity></Supplementary_unit></Tarification></Item>
<Item><Licence_number>LIC</Licence_number><Tarification><Supplementary_unit><Suppplementary_unit_quantity>1250</Suppplementary_unit_quantity></Supplementary_unit></Tarification></Item>
<General_information><Comments_free_text>Texte</Comments_free_text></General_information></ASYCUDA>'''


class RecuperationTest(unittest.TestCase):
    def test_identique_meme_avec_formats_numeriques_differents(self):
        sydonia = GENERE.replace('84215.00', '84215').replace('<Totals_taxes><null/></Totals_taxes>', '<Totals_taxes></Totals_taxes>')
        r = regles.comparer(GENERE, sydonia)
        self.assertEqual(r['differences'], [])
        self.assertTrue(all(c['identique'] for c in r['controles']))
        self.assertIn('Aucun changement', regles.conclusion(r['resume']))

    def test_classement_des_ecarts_et_controles_cles(self):
        sydonia = (GENERE.replace('<Number>5000</Number>', '<Number>5007</Number>')
                   .replace('<Totals_taxes><null/></Totals_taxes>', '<Totals_taxes>1234.5</Totals_taxes>')
                   .replace('<Comments_free_text>Texte</Comments_free_text>', '<Comments_free_text><null/></Comments_free_text>')
                   .replace('>1250<', '>1300<'))
        r = regles.comparer(GENERE, sydonia)
        genres = {d['chemin']: d['genre'] for d in r['differences']}
        self.assertEqual(genres['Identification/Registration/Number'], 'modifie')
        self.assertEqual(genres['Financial/Amounts/Totals_taxes'], 'complete')
        self.assertEqual(genres['General_information/Comments_free_text'], 'retire')
        self.assertEqual(genres['Item[2]/Tarification/Supplementary_unit/Suppplementary_unit_quantity'], 'modifie')
        differents = {c['libelle'] for c in r['controles'] if not c['identique']}
        self.assertEqual(differents, {'Numéro E', 'Article 2 · Quantité'})
        self.assertEqual(r['resume']['controles_differents'], 2)
        self.assertIn('2 contrôle(s)', regles.conclusion(r['resume']))

    def test_xml_invalide_refuse(self):
        for contenu in ('pas du xml', '<AUTRE/>'):
            with self.subTest(contenu=contenu), self.assertRaises(ValueError):
                regles.comparer(GENERE, contenu)

    def test_persistance_sans_invalider_l_etape_4(self):
        with tempfile.TemporaryDirectory() as dossier:
            fichier = Path(dossier) / 'licences.sqlite'
            registre.enregistrer(preparer_licence('DEC123', '840000', 'LIC', '17/03/2026'), fichier)
            registre.enregistrer_repartition('LIC', '840000', 23000, fichier)
            registre.enregistrer_informations_declaration('LIC', dict(numero_e='100', numero_liquidation='200', numero_quittance='300'), fichier)
            registre.mettre_a_jour_repartitions('LIC', fichier)
            with self.assertRaisesRegex(ValueError, 'étape 7'):
                registre.enregistrer_recuperation('LIC', GENERE, 'sydonia.xml', fichier)
            registre.enregistrer_xml_genere('LIC', GENERE, 'genere.xml', fichier)
            r = registre.enregistrer_recuperation('LIC', GENERE.replace('4320', '4321'), 'sydonia.xml', fichier)
            self.assertEqual(r['resume']['controles_differents'], 1)
            licence = registre.charger('LIC', fichier)
            self.assertTrue(mise_a_jour_repartitions.est_a_jour(licence))
            self.assertEqual(licence['recuperation_simulation']['resume']['controles_differents'], 1)
            registre.enregistrer_xml_genere('LIC', GENERE, 'genere2.xml', fichier)
            self.assertNotIn('recuperation_simulation', registre.charger('LIC', fichier))

    def test_plusieurs_xml_sydonia_associes_a_leur_part(self):
        with tempfile.TemporaryDirectory() as dossier:
            fichier = Path(dossier) / 'licences.sqlite'
            registre.enregistrer(preparer_licence('DEC123', '840000', 'LIC', '17/03/2026'), fichier)
            registre.enregistrer_repartition('LIC', '840000', 23000, fichier)
            registre.enregistrer_informations_declaration('LIC', dict(numero_e='100', numero_liquidation='200', numero_quittance='300'), fichier)
            registre.mettre_a_jour_repartitions('LIC', fichier)
            autre = GENERE.replace('4320', '9999')
            genere1, genere2 = Path(dossier) / 'p1.xml', Path(dossier) / 'p2.xml'
            genere1.write_text(GENERE, encoding='utf-8')
            genere2.write_text(autre, encoding='utf-8')
            registre.enregistrer_xml_genere('LIC', GENERE, genere1, fichier, fichiers=[
                dict(parts=[1, 2], fob='1', fichier=str(genere1)), dict(parts=[3], fob='2', fichier=str(genere2))])
            associations = registre.enregistrer_recuperations('LIC', [('s3.xml', autre), ('s1.xml', GENERE)], fichier)
            self.assertEqual([a['reference']['parts'] for a in associations], [[3], [1, 2]])
            self.assertTrue(all(a['comparaison']['resume']['controles_differents'] == 0 for a in associations))
            recuperation = registre.charger('LIC', fichier)['recuperation_simulation']
            self.assertEqual([i['fichier'] for i in recuperation['imports']], ['s3.xml', 's1.xml'])
            self.assertEqual(recuperation['resume']['controles_differents'], 0)
