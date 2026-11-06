from pathlib import Path
import tempfile
import unittest
from asydec.declarations import informations_declaration as regles, licences_ouvertes as registre
from asydec.declarations.documents_finaux import preparer_licence
from asydec.declarations.dates_documents import est_ouvrable


class InformationsDeclarationTest(unittest.TestCase):
    def test_validation_date_et_donnees_vides(self):
        for valeurs in ({}, {'date_declaration':'31/02/2026'}):
            with self.assertRaises(ValueError):
                regles.verifier(valeurs)
        self.assertEqual(regles.verifier({'reference':' ABC ', 'date_declaration':'5/11/2026'})['date_declaration'],'05/11/2026')

    def test_persistence_et_ordre_des_etapes(self):
        with tempfile.TemporaryDirectory() as dossier:
            fichier=Path(dossier)/'licences.sqlite'
            licence=preparer_licence('DEC123','168430','DEC123-ADD0-IB','17/03/2026')
            registre.enregistrer(licence,fichier)
            with self.assertRaisesRegex(ValueError,'répartition'):
                registre.enregistrer_informations_declaration(licence['numero_validation'],{'reference':'REF1','numero_e':'100','numero_liquidation':'200','numero_quittance':'300'},fichier)
            registre.enregistrer_repartition(licence['numero_validation'],'168430',23000,fichier)
            registre.enregistrer_informations_declaration(licence['numero_validation'],{'reference':'REF1','date_declaration':'05/11/2026','numero_e':'100','numero_liquidation':'200','numero_quittance':'300'},fichier)
            self.assertEqual(registre.charger(licence['numero_validation'],fichier)['informations_declaration']['reference'],'REF1')
            registre.enregistrer(licence,fichier)
            self.assertEqual(registre.charger(licence['numero_validation'],fichier)['informations_declaration']['reference'],'REF1')

    def test_proposition_2_mois_maximum_puis_1(self):
        from datetime import date
        bl = date(2026, 8, 5)
        for limite, mois, attendu in [(date(2026,11,5),2,date(2026,10,5)),
                                     (date(2026,10,5),2,date(2026,10,5)),
                                     (date(2026,9,20),1,date(2026,9,18))]:
            resultat = regles.proposer_date_enregistrement(bl,limite)
            self.assertEqual(resultat['mois'],mois)
            self.assertEqual(resultat['date'],attendu)
            self.assertLessEqual(resultat['date'],regles.ajouter_mois(bl,2))
            self.assertLessEqual(resultat['date'],limite)

    def test_aucune_date_possible_et_fins_de_mois(self):
        from datetime import date
        with self.assertRaises(ValueError):
            regles.proposer_date_enregistrement('05/11/2026',date(2026,11,5))
        self.assertEqual(regles.ajouter_mois(date(2024,1,31),1),date(2024,2,29))
        self.assertEqual(regles.ajouter_mois(date(2026,12,31),2),date(2027,2,28))
        resultat=regles.proposer_date_enregistrement('27/02/2026',date(2026,4,30))
        self.assertEqual(resultat['date'],date(2026,4,27))

    def test_alerte_bl_de_moins_d_un_mois(self):
        from datetime import date
        jour = date(2026, 11, 5)
        licence = {'date_bl': '2026-10-29'}
        self.assertEqual(regles.date_enregistrement_possible_le('2026-10-29', jour), date(2026, 11, 30))
        self.assertEqual(regles.alerte_enregistrement(licence, jour),
                         'BL du 29/10/2026 : moins d’un mois, numéro E possible à partir du 30/11/2026')
        self.assertEqual(regles.alerte_enregistrement({'date_bl': '2026-09-01'}, jour), '')  # plus d'un mois
        self.assertEqual(regles.alerte_enregistrement({}, jour), '')  # BL absent : pas d'alerte
        deja = dict(licence, informations_declaration={'date_enregistrement': '05/11/2026'})
        self.assertEqual(regles.alerte_enregistrement(deja, jour), '')  # date déjà saisie

    def test_weekends_saisis_refuses(self):
        for cle in ('date_declaration','date_enregistrement'):
            with self.assertRaisesRegex(ValueError, 'jour ouvrable'):
                regles.verifier({cle:'01/11/2026'})

    def test_aucune_proposition_sur_weekend_et_plafond_deux_mois(self):
        from datetime import date, timedelta
        for i in range(365):
            bl=date(2025,1,1)+timedelta(days=i)
            if not est_ouvrable(bl):
                continue
            for delai in (31,45,60,61,75,90,120):
                limite=bl+timedelta(days=delai)
                try:
                    resultat=regles.proposer_date_enregistrement(bl,limite)
                except ValueError:
                    continue
                self.assertTrue(est_ouvrable(resultat['date']))
                self.assertLessEqual(resultat['date'],limite)
                self.assertLessEqual(resultat['date'],regles.ajouter_mois(bl,2))
                self.assertGreaterEqual(resultat['date'],regles.ajouter_mois(bl,1))

    def test_date_cvi_validation(self):
        base={'date_enregistrement':'02/11/2026','date_liquidation':'02/11/2026','date_quittance':'02/11/2026'}
        self.assertEqual(regles.verifier(dict(base,date_cvi='4/11/2026'))['date_cvi'],'04/11/2026')
        for cvi in ('03/11/2026','09/11/2026','07/11/2026'):
            with self.assertRaises(ValueError):
                regles.verifier(dict(base,date_cvi=cvi))
