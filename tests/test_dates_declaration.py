from datetime import date, timedelta
import random
from pathlib import Path
import tempfile
import unittest

from asydec.declarations import dates_documents as calendrier, informations_declaration as regles, licences_ouvertes as registre
from asydec.declarations.documents_finaux import preparer_licence


class DatesDeclarationTest(unittest.TestCase):
    def test_calendrier_rdc_et_report_exceptionnel(self):
        for jour in (date(2026,1,1),date(2026,4,6),date(2026,6,30),date(2026,12,25),date(2026,1,19)):
            self.assertFalse(calendrier.est_ouvrable(jour))
        self.assertTrue(calendrier.est_ouvrable(date(2026,1,20)))
        self.assertIn(date(2026,5,16),calendrier.jours_feries(2026))

    def test_tirages_chronologie_et_jours_feries_sur_toute_annee(self):
        rng=random.Random(17)
        variations=set()
        for i in range(365):
            bl=date(2025,1,1)+timedelta(days=i)
            if not calendrier.est_ouvrable(bl):
                continue
            limite=bl+timedelta(days=120)
            for _ in range(5):
                dates=regles.proposer_dates_declaration(bl,limite,rng)
                e,l,q,cvi=[regles.lire_date(dates[c]) for c in regles.DATES_AUTO]
                self.assertTrue(e<=l<=q<=limite)
                self.assertTrue(all(calendrier.est_ouvrable(d) for d in (e,l,q)))
                self.assertIn((l-e).days,(0,2,3))
                self.assertIn((q-e).days,(0,2,3))
                self.assertTrue(calendrier.est_ouvrable(cvi))
                self.assertGreaterEqual((cvi-l).days,2)
                if (cvi-l).days>4:
                    self.assertFalse(any(calendrier.est_ouvrable(l+timedelta(days=d)) for d in (2,3,4)))
                self.assertLessEqual(e,regles.ajouter_mois(bl,2))
                variations.add(((l-e).days,(q-e).days))
        self.assertGreater(len(variations),2)

    def test_dates_enregistrees_reste_stables_et_numeros_conserves(self):
        with tempfile.TemporaryDirectory() as dossier:
            fichier=Path(dossier)/'licences.sqlite'
            l=preparer_licence('DEC','100','LICENCE','17/03/2026')
            registre.enregistrer(l,fichier)
            registre.enregistrer_repartition('LICENCE','100',23000,fichier)
            dates=regles.proposer_dates_declaration(l['date_bl'])
            valeurs=dict(dates,numero_e='E123',numero_liquidation='L456',numero_quittance='Q789')
            registre.enregistrer_informations_declaration('LICENCE',valeurs,fichier)
            relu=registre.charger('LICENCE',fichier)['informations_declaration']
            for cle,valeur in valeurs.items():
                self.assertEqual(relu[cle],valeur)
            registre.enregistrer_informations_declaration('LICENCE',relu,fichier)
            self.assertEqual(registre.charger('LICENCE',fichier)['informations_declaration'],relu)
