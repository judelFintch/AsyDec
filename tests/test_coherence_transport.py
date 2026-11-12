from copy import deepcopy
from unittest import TestCase

from asydec.declarations import coherence_transport as C, cvi
from tests.test_facture_licence import licence


class CoherenceTransportTest(TestCase):
    def dossier(self, origine='India', complements=None):
        l = deepcopy(licence())
        for p in l.get('produits') or []:
            p['pays_origine'] = origine
        if not l.get('produits'):
            l['produits'] = [dict(designation='Motocycles', quantite='10', unite='Unite(Piece)',
                                  prix_unitaire='700', pays_origine=origine)]
        l['cvi_parts'] = {'complements': complements or {}}
        return l

    def test_origine_toujours_celle_de_la_licence(self):
        l = self.dossier('India', {'ORIGINE': 'CHINE'})
        d = cvi.donnees(l, cvi.premiere_part(l))
        self.assertEqual(d['ORIGINE'], 'INDE')
        self.assertEqual(C.origine_cvi(self.dossier('China')), 'CHINE')

    def test_port_par_defaut_et_conditions_fob_deduites(self):
        l = self.dossier('India')
        d = cvi.donnees(l, cvi.premiere_part(l), {})
        self.assertEqual(d['PORT_CHARGEMENT_BL'], 'CHENNAI')
        self.assertEqual(d['CONDITIONS_FOB_BL'], 'FOB CHENNAI PORT, INDIA')
        self.assertEqual((d['FRET_PAYABLE_BL'], d['LIEU_EMISSION_BL']), ('CHENNAI', 'CHENNAI'))

    def test_port_saisi_prime_et_alerte_si_pays_different(self):
        l = self.dossier('India', {'PORT_CHARGEMENT_BL': 'Jebel Ali', 'CONDITIONS_FOB_BL': 'FOB CHENNAI PORT, CHINA'})
        d = cvi.donnees(l, cvi.premiere_part(l))
        self.assertEqual(d['CONDITIONS_FOB_BL'], 'FOB JEBEL ALI PORT, UAE')
        self.assertTrue(C.alertes(l, 'JEBEL ALI'))
        self.assertFalse(C.alertes(l, 'CHENNAI PORT'))

    def test_facture_kinshop_reprend_le_port_du_bl(self):
        from asydec.declarations import facture_licence as F, facture_kinshop as K
        from tests.test_facture_kinshop import texte
        l = self.dossier('India', {'PORT_CHARGEMENT_BL': 'JEBEL ALI'})
        l['fournisseur'] = {'nom': 'KINSHOP GENERAL TRADING FZE'}
        contenu = texte(K.creer(l, F.donnees_part(l, l['repartition']['parts'][0])))
        self.assertIn('FOB JEBEL ALI, UAE US DOLLARS', contenu)
        self.assertNotIn('CHENNAI, INDIA', contenu)
        l['cvi_parts'] = {'complements': {}}
        self.assertIn('CHENNAI, INDIA', texte(K.creer(l, F.donnees_part(l, l['repartition']['parts'][0]))))
