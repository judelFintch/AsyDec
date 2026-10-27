import unittest
from decimal import Decimal, ROUND_HALF_UP
import variantes


class VariantesTest(unittest.TestCase):
    ratios = [1.5, .1875, .25, .4, .15, .136, .419, .157]

    def test_totaux_et_ratios(self):
        for seed in range(10):
            valeurs = variantes.generer(19000, 7800, 790, self.ratios, graine=seed)
            self.assertEqual(len(valeurs), 12)
            self.assertEqual(len({tuple(v['poids']) for v in valeurs}), 12)
            for v in valeurs:
                self.assertEqual(round(sum(v['poids']), 3), 19000)
                self.assertEqual(round(sum(v['fob']), 2), 7800)
                self.assertEqual(sum(v['colis']), 790)
                self.assertTrue(all(isinstance(p,int) for p in v['poids']))
                self.assertGreaterEqual(min(v['colis']), 10)
                self.assertEqual(len(set(v['colis'])), 8)
                for p, f, r in zip(v['poids'], v['fob'], self.ratios):
                    self.assertGreater(p, 0)
                    self.assertEqual(Decimal(str(f)), (Decimal(str(p))*Decimal(str(r))).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))

    def test_entrees_impossibles(self):
        for p, f, c in [(0, 7800, 790), (19000, 1, 790), (19000, 40000, 790),
                         (19000, 7800, 7), (19000, 7800, 107), (19000, 7800, 8.5), (float('nan'), 7800, 790),
                         (19000.5, 7800, 790), (19000.0001, 7800, 790)]:
            with self.assertRaises(ValueError):
                variantes.generer(p, f, c, self.ratios)



class ControleTest(unittest.TestCase):
    def profil(self):
        r = VariantesTest.ratios
        poids = [550,280,280,7100,90,490,7050,3160]
        info = {'poids_articles':poids, 'fob_articles':[p*t for p,t in zip(poids,r)], 'colis_articles':[22,12,12,294,4,20,292,134]}
        return {'ratios':r, 'bornes':[(x,x) if k in (3,6,7) else (x*.9,x*1.1) for k,x in enumerate(r)],
                'references':[{'nom':'controle.xml','info':info}], 'exclus':[]}

    def test_classement_et_controles(self):
        profil = self.profil()
        propositions = variantes.generer(19000,7800,790,profil['ratios'],profil=profil,graine=3)
        self.assertEqual(len(propositions),12)
        self.assertEqual([v['distance'] for v in propositions], sorted(v['distance'] for v in propositions))
        for v in propositions:
            variantes.controler(v,profil)
            self.assertEqual(round(sum(v['fob']),2),7800)
            self.assertEqual(round(sum(v['poids']),3),19000)
            self.assertEqual(sum(v['colis']),790)
        v = propositions[0]
        v['fob'][3] += .01
        with self.assertRaises(ValueError):
            variantes.controler(v,profil)

    def test_fourchette_et_reference(self):
        profil = self.profil()
        ref = profil['references'][0]['info']
        v = {'poids':ref['poids_articles'], 'fob':ref['fob_articles'], 'colis':ref['colis_articles']}
        self.assertEqual(variantes.evaluer(v,profil)['proximite'],100)
        v = {c:list(x) for c,x in v.items()}
        v['fob'][0] = round(v['poids'][0]*profil['bornes'][0][1],2)+1
        with self.assertRaises(ValueError):
            variantes.controler(v,profil)


class LignesVidesTest(unittest.TestCase):
    def test_lignes_vides_ignorees(self):
        from pathlib import Path
        import tempfile
        import xml.etree.ElementTree as ET
        from unittest.mock import patch
        racine = ET.Element('ASYCUDA')
        for k in range(8):
            if k == 3:
                ET.SubElement(racine, 'Item')
            it = ET.SubElement(racine, 'Item')
            ET.SubElement(ET.SubElement(it,'Tarification'),'Item_price').text = '100'
            ET.SubElement(ET.SubElement(ET.SubElement(it,'Valuation_item'),'Weight_itm'),'Gross_weight_itm').text = '50'
        ET.SubElement(racine,'Item')
        ET.SubElement(ET.SubElement(ET.SubElement(racine,'Valuation'),'Gs_Invoice'),'Currency_rate').text = '2500'
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier)/'controle.xml'
            ET.ElementTree(racine).write(chemin)
            with patch('moteur.recalculer'):
                info = variantes.verifier_modele(chemin)
            self.assertEqual(len(info['fob_articles']),8)
            self.assertEqual(len(variantes.signature(chemin)),8)


class RegenerationTest(unittest.TestCase):
    def test_exclut_propositions_deja_vues(self):
        r = VariantesTest.ratios
        anciennes = variantes.generer(19000,7800,790,r,graine=12)
        exclus = {variantes.cle_variante(v) for v in anciennes}
        nouvelles = variantes.generer(19000,7800,790,r,nombre=1,graine=12,exclure=exclus)
        self.assertEqual(len(nouvelles),1)
        self.assertNotIn(variantes.cle_variante(nouvelles[0]),exclus)
        self.assertEqual(round(sum(nouvelles[0]['fob']),2),7800)
        self.assertEqual(round(sum(nouvelles[0]['poids']),3),19000)
        self.assertEqual(sum(nouvelles[0]['colis']),790)


class MoteurTest(unittest.TestCase):
    def test_fob_trop_bas_refuse(self):
        import moteur
        poids = [550,280,280,7100,90,490,7050,3160]
        with self.assertRaises(ValueError):
            moteur.fob_par_ratios(poids, VariantesTest.ratios, 1000)
        fob, _ = moteur.fob_par_ratios(poids, VariantesTest.ratios, 7800)
        self.assertEqual(round(sum(fob), 2), 7800)


class BibliothequeTest(unittest.TestCase):
    def test_meme_contenu_conserve_une_fois(self):
        from pathlib import Path
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as dossier:
            a, b = Path(dossier)/'a.xml', Path(dossier)/'b.xml'
            a.write_text('<ASYCUDA/>')
            b.write_text('<ASYCUDA/>')
            with patch.object(variantes, 'BIBLIOTHEQUE', Path(dossier)/'bibli'), patch('variantes.verifier_modele'):
                self.assertEqual(variantes.conserver(a), variantes.conserver(b))
                self.assertEqual(len(variantes.modeles()), 1)


if __name__ == '__main__':
    unittest.main()


class RechercheBibliothequeTest(unittest.TestCase):
    def test_absence_de_modele_expliquee(self):
        with self.assertRaisesRegex(ValueError,'Aucun modèle enregistré'):
            variantes.rechercher_modeles(19000,7800,790,chemins=[])

    def test_fichier_invalide_signale_sans_crash_xml(self):
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as dossier:
            p=Path(dossier)/'invalide.xml'
            p.write_text('<XML invalide')
            with self.assertRaisesRegex(ValueError,'Aucune proposition compatible'):
                variantes.rechercher_modeles(19000,7800,790,chemins=[p])


class RatiosAjustablesTest(unittest.TestCase):
    def test_totaux_hors_ancienne_fourchette_sont_repartis(self):
        profil=ControleTest().profil()
        profil['variables_libres']=True
        for fob in (780,40000):
            propositions=variantes.generer(19000,fob,790,profil['ratios'],profil=profil,nombre=3,graine=18)
            self.assertEqual(len(propositions),3)
            for v in propositions:
                variantes.controler(v,profil)
                self.assertEqual(sum(v['poids']),19000)
                self.assertEqual(round(sum(v['fob']),2),fob)
                self.assertEqual(sum(v['colis']),790)
                self.assertTrue(all(isinstance(p,int) and p>0 for p in v['poids']))
                self.assertGreater(min(v['fob']),0)

    def test_saisie_et_calcul_appliquent_les_memes_regles(self):
        profil=ControleTest().profil()
        profil['variables_libres']=True
        poids=[100]*8
        fob=variantes.fob_controles(poids,profil,4000)
        v={'poids':poids,'fob':fob,'colis':[10]*8}
        variantes.controler(v,profil)
        self.assertEqual(round(sum(fob),2),4000)
        self.assertTrue(any(fob[k]/poids[k]>profil['bornes'][k][1] for k in (3,6,7)))
        v['fob'][0]=10000
        with self.assertRaises(ValueError):
            variantes.controler(v,profil)
