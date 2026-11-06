import copy
import random
import tempfile
from pathlib import Path
import unittest
from asydec.declarations import numeros_repartitions as regles, licences_ouvertes as registre
from asydec.declarations.documents_finaux import preparer_licence


class NumerosPartsTest(unittest.TestCase):
    def licence(self,nombre):
        return dict(numero_dec='DEC123',informations_declaration=dict(numero_e='E00100',numero_liquidation='L00200',numero_quittance='Q00300',plaque=''),
                    repartition={'parts':[dict(numero=i+1,plaque=f'PROPOSITION{i}') for i in range(nombre)]})

    def test_incrementations_et_deux_groupes_q(self):
        l=self.licence(12)
        regles.completer(l,random.Random(17))
        infos=[p['informations_declaration'] for p in l['repartition']['parts']]
        self.assertEqual(infos[0]['numero_e'],'E00100')
        self.assertEqual(infos[0]['numero_liquidation'],'L00200')
        for cle in ('numero_e','numero_liquidation'):
            nombres=[int(i[cle][1:]) for i in infos]
            self.assertTrue(all(1<=b-a<=6 for a,b in zip(nombres,nombres[1:])))
        self.assertEqual({i['numero_dec'] for i in infos},{'DEC123'})
        self.assertEqual({i['numero_quittance'] for i in infos[:5]},{'Q00300'})
        self.assertEqual(len({i['numero_quittance'] for i in infos}),2)
        self.assertEqual(len({i['numero_quittance'] for i in infos[5:]}),1)
        avant=copy.deepcopy(l)
        self.assertFalse(regles.completer(l))
        self.assertEqual(l,avant)

    def test_cinq_parts_un_q_et_suffixes_preserves(self):
        l=self.licence(5)
        regles.completer(l)
        self.assertEqual({p['informations_declaration']['numero_quittance'] for p in l['repartition']['parts']},{'Q00300'})
        self.assertRegex(regles.incrementer('2026/0099/NCA',random.Random(1)),r'^2026/01\d\d/NCA$')

    def test_persistence_et_revalidation_sans_nouveau_tirage(self):
        with tempfile.TemporaryDirectory() as dossier:
            fichier=Path(dossier)/'licences.sqlite'
            l=preparer_licence('DEC123','840000','LICENCE','17/03/2026')
            registre.enregistrer(l,fichier)
            registre.enregistrer_repartition('LICENCE','840000',23000,fichier)
            registre.enregistrer_informations_declaration('LICENCE',dict(numero_e='100',numero_liquidation='200',numero_quittance='300'),fichier)
            premier=registre.charger('LICENCE',fichier)
            self.assertEqual(len(premier['repartition']['parts']),7)
            self.assertEqual(registre.charger('LICENCE',fichier),premier)
            registre.enregistrer_informations_declaration('LICENCE',premier['informations_declaration'],fichier)
            self.assertEqual(registre.charger('LICENCE',fichier),premier)
            self.assertEqual(len(registre.lister_repartitions('LICENCE',fichier)),7)

    def test_manifeste_premiere_part_puis_increments(self):
        l=self.licence(4)
        l['informations_declaration']['manifeste']='MAN0050'
        regles.completer(l,random.Random(3))
        manifestes=[p['informations_declaration']['manifeste'] for p in l['repartition']['parts']]
        self.assertEqual(manifestes[0],'MAN0050')
        nombres=[int(m[3:]) for m in manifestes]
        self.assertTrue(all(1<=b-a<=6 for a,b in zip(nombres,nombres[1:])))
        avant=copy.deepcopy(l)
        self.assertFalse(regles.completer(l))
        self.assertEqual(l,avant)

    def test_ancienne_repartition_avec_manifeste_recopie(self):
        l=self.licence(3)
        l['informations_declaration']['manifeste']='MAN0050'
        regles.completer(l,random.Random(3))
        for p in l['repartition']['parts']:
            p['informations_declaration']['manifeste']='MAN0050'
        self.assertTrue(regles.completer(l,random.Random(5)))
        manifestes=[p['informations_declaration']['manifeste'] for p in l['repartition']['parts']]
        self.assertEqual(manifestes[0],'MAN0050')
        self.assertEqual(len(set(manifestes)),3)

    def test_manifeste_vide_reste_vide(self):
        l=self.licence(3)
        regles.completer(l,random.Random(3))
        self.assertEqual({p['informations_declaration'].get('manifeste','') for p in l['repartition']['parts']},{''})
