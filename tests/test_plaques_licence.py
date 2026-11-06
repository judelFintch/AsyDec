from pathlib import Path
import tempfile
import unittest

from asydec.declarations import repartition_licence as regles, licences_ouvertes as registre
from asydec.declarations.documents_finaux import preparer_licence


class PlaquesLicenceTest(unittest.TestCase):
    def test_format_unicite_et_conservation(self):
        exemples=['T171EAK/T196EAK','T265EAK/T160EAL']
        plaques=regles.proposer_plaques(1000,exemples)
        self.assertEqual(plaques[:2],exemples)
        self.assertEqual(regles.verifier_plaques(plaques,1000),plaques)
        elements=[p for paire in plaques for p in paire.split('/')]
        self.assertEqual(len(set(elements)),2000)
        self.assertEqual(regles.proposer_plaques(1000,plaques),plaques)

    def test_refus_format_et_plaques_reutilisees(self):
        for plaques in (['ABC'],['T171EAK/T171EAK'],['T171EAK/T196EAK','T171EAK/T160EAL']):
            with self.subTest(plaques=plaques),self.assertRaises(ValueError):
                regles.verifier_plaques(plaques,len(plaques))
        corriges=regles.proposer_plaques(3,['T171EAK/T196EAK','T171EAK/T196EAK',None])
        self.assertEqual(corriges[0],'T171EAK/T196EAK')
        regles.verifier_plaques(corriges,3)

    def test_apercu_sauvegarde_et_changement_poids_sans_nouveau_tirage(self):
        with tempfile.TemporaryDirectory() as dossier:
            fichier=Path(dossier)/'licences.sqlite'
            licence=preparer_licence('DEC','168430','LICENCE','17/03/2026')
            registre.enregistrer(licence,fichier)
            plaques=regles.proposer_plaques(2)
            registre.enregistrer_repartition('LICENCE','168430',23000,fichier,plaques=plaques)
            self.assertEqual([p['plaque'] for p in registre.charger('LICENCE',fichier)['repartition']['parts']],plaques)
            registre.enregistrer_repartition('LICENCE','168430',24000,fichier)
            self.assertEqual([p['plaque'] for p in registre.lister_repartitions('LICENCE',fichier)],plaques)

    def test_anciennes_repartitions_completees_une_seule_fois(self):
        with tempfile.TemporaryDirectory() as dossier:
            fichier=Path(dossier)/'licences.sqlite'
            licence=preparer_licence('DEC','300000','LICENCE','17/03/2026')
            licence['repartition']=regles.preparer('300000')
            registre.enregistrer(licence,fichier)
            premier=registre.lister_repartitions('LICENCE',fichier)
            second=registre.lister_repartitions('LICENCE',fichier)
            self.assertEqual(premier,second)
            regles.verifier_plaques([p['plaque'] for p in premier],3)
