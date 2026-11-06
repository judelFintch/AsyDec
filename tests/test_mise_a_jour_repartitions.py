from pathlib import Path
import tempfile
import unittest

from asydec.declarations import licences_ouvertes as registre, mise_a_jour_repartitions as etape
from asydec.declarations.documents_finaux import preparer_licence


class MiseAJourTest(unittest.TestCase):
    def test_numeros_obligatoires(self):
        for absent in ('numero_e','numero_liquidation','numero_quittance'):
            valeurs=dict(numero_e='100',numero_liquidation='200',numero_quittance='300')
            valeurs[absent]=' '
            with self.subTest(absent=absent),self.assertRaises(ValueError):
                etape.exiger_numeros(valeurs)

    def test_mise_a_jour_et_invalidation_des_donnees_modifiees(self):
        with tempfile.TemporaryDirectory() as dossier:
            fichier=Path(dossier)/'licences.sqlite'
            licence=preparer_licence('DEC123','840000','LICENCE','17/03/2026')
            licence['soussigne']={'nom':'Société test'}
            registre.enregistrer(licence,fichier)
            registre.enregistrer_repartition('LICENCE','840000',23000,fichier)
            with self.assertRaises(ValueError):
                registre.mettre_a_jour_repartitions('LICENCE',fichier)
            registre.enregistrer_informations_declaration('LICENCE',dict(numero_e='100',numero_liquidation='200',numero_quittance='300'),fichier)
            self.assertFalse(etape.est_a_jour(registre.charger('LICENCE',fichier)))
            registre.mettre_a_jour_repartitions('LICENCE',fichier)
            relu=registre.charger('LICENCE',fichier)
            self.assertTrue(etape.est_a_jour(relu))
            for part in relu['repartition']['parts']:
                self.assertEqual(part['contexte_licence']['soussigne']['nom'],'Société test')
                self.assertEqual(part['informations_declaration']['numero_dec'],'DEC123')
            registre.mettre_a_jour_repartitions('LICENCE',fichier)
            self.assertEqual(registre.charger('LICENCE',fichier),relu)
            infos=dict(relu['informations_declaration'],numero_e='500')
            registre.enregistrer_informations_declaration('LICENCE',infos,fichier)
            self.assertFalse(etape.est_a_jour(registre.charger('LICENCE',fichier)))
            registre.mettre_a_jour_repartitions('LICENCE',fichier)
            self.assertTrue(etape.est_a_jour(registre.charger('LICENCE',fichier)))
            registre.enregistrer_repartition('LICENCE','840000',24000,fichier)
            self.assertFalse(etape.est_a_jour(registre.charger('LICENCE',fichier)))
