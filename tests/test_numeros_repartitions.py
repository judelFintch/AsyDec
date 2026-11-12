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
        quittances=[i['numero_quittance'] for i in infos]
        self.assertEqual(quittances[0],'Q00300')
        self.assertTrue(regles.quittances_valides(quittances,'Q00300',['']*12))
        avant=copy.deepcopy(l)
        self.assertFalse(regles.completer(l))
        self.assertEqual(l,avant)

    def test_suffixes_preserves(self):
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


class GroupesQuittanceTest(unittest.TestCase):
    def test_groupes_aleatoires_de_deux_a_six_parts(self):
        tailles_vues = set()
        for graine in range(300):
            rng = random.Random(graine)
            for nombre in range(2, 25):
                tailles = regles.tailles_groupes(nombre, rng)
                self.assertEqual(sum(tailles), nombre)
                self.assertTrue(all(2 <= t <= 6 for t in tailles), tailles)
                tailles_vues.update(tailles)
        self.assertEqual(tailles_vues, {2, 3, 4, 5, 6})

    def test_une_seule_part(self):
        self.assertEqual(regles.tailles_groupes(1, random.Random(1)), [1])

    def test_q_croissants_par_groupe_et_meme_date(self):
        quittances = regles.tirer_quittances('Q00300', ['15/05/2019'] * 10, random.Random(4))
        self.assertEqual(quittances[0], 'Q00300')
        self.assertTrue(regles.quittances_valides(quittances, 'Q00300', ['15/05/2019'] * 10))
        self.assertGreater(len(set(quittances)), 1)

    def test_changement_de_date_ouvre_un_nouveau_groupe(self):
        dates = ['15/05/2019'] * 4 + ['16/05/2019'] * 4
        quittances = regles.tirer_quittances('300', dates, random.Random(2))
        self.assertNotEqual(quittances[3], quittances[4])
        self.assertTrue(regles.quittances_valides(quittances, '300', dates))
        self.assertFalse(regles.quittances_valides(['300'] * 8, '300', dates))

    def test_ancien_tirage_conforme_conserve_sinon_retire(self):
        dates = [''] * 12
        self.assertTrue(regles.quittances_valides(['300'] * 5 + ['304'] * 5 + ['306'] * 2, '300', dates))
        # Ancienne règle « cinq puis tout le reste » : 7 parts sur un même Q, non conforme.
        self.assertFalse(regles.quittances_valides(['300'] * 5 + ['304'] * 7, '300', dates))
        self.assertFalse(regles.quittances_valides(['300'] * 2 + ['310'] * 10, '300', dates))
        self.assertFalse(regles.quittances_valides(['300'] * 6 + ['300'] * 0 + ['301'], '300', [''] * 7))
