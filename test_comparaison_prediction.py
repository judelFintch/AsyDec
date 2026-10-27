"""Comparer des données déclarées sans écrire, recalculer ni renuméroter les XML."""
import copy
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import comparaison_prediction as C
from test_references import declaration, item
import ui.etapes as E


class ComparaisonPredictionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)/'base.xml'
        self.fourni = Path(self.tmp.name)/'fourni.xml'
        contenu = declaration([item(), '<Item/>', item(code='6304',poids='50',fob='25',colis='11')],
                              fob='175',poids='150',colis='21',totales='250')
        self.base.write_bytes(contenu)
        self.fourni.write_bytes(contenu)
        self.resultat = {'resume':{'poids':150,'fob':175,'cif':28312500,'taxes_totales':250,
            'taux':2265.5,'fret':0,'assurance':0,'articles':[
                {'poids':100,'fob':150,'cif':200,'taxes':100},
                {'poids':50,'fob':25,'cif':100,'taxes':100}]}, 'colis':[10,11]}

    def rapport(self):
        return C.comparer(self.resultat,self.base,self.fourni)

    def ligne(self,rapport,position,metrique):
        return next(l for l in rapport['lignes'] if l['position']==position and l['metrique']==metrique)

    def modifier(self,chemin,valeur):
        arbre=ET.parse(self.fourni)
        arbre.getroot().find(chemin).text=valeur
        arbre.write(self.fourni)

    def test_ecarts_exacts_et_positions_non_renumerotees(self):
        self.modifier('Item/Tarification/Item_price','165')
        rapport=self.rapport()
        l=self.ligne(rapport,1,'fob')
        self.assertEqual((l['prevu'],l['fourni'],l['ecart'],l['pourcentage']),
                         (Decimal(150),Decimal(165),Decimal(15),Decimal(10)))
        self.assertEqual(self.ligne(rapport,3,'poids')['ecart'],0)
        self.assertEqual({l['position'] for l in rapport['lignes']},{1,3,'Total global'})
        self.assertEqual(self.ligne(rapport,1,'ratio')['fourni'],Decimal('1.65'))

    def test_lecture_seule(self):
        fichiers=[p.read_bytes() for p in (self.base,self.fourni)]
        resultat=copy.deepcopy(self.resultat)
        self.rapport()
        self.assertEqual(fichiers,[p.read_bytes() for p in (self.base,self.fourni)])
        self.assertEqual(resultat,self.resultat)

    def test_article_absent_pas_decalage_ni_zero_invente(self):
        self.modifier('Item/Tarification/HScode/Commodity_code','')
        self.modifier('Item/Goods_description/Description_of_goods','')
        for chemin in ('Item/Tarification/Item_price','Item/Packages/Number_of_packages',
                       'Item/Valuation_item/Weight_itm/Gross_weight_itm'):
            self.modifier(chemin,'0')
        rapport=self.rapport()
        self.assertIsNone(self.ligne(rapport,1,'poids')['fourni'])
        self.assertIsNone(self.ligne(rapport,1,'poids')['ecart'])
        self.assertEqual(self.ligne(rapport,3,'poids')['fourni'],50)

    def test_code_different_pas_de_comparaison_forcee(self):
        self.modifier('Item/Tarification/HScode/Commodity_code','9999')
        l=self.ligne(self.rapport(),1,'fob')
        self.assertIsNone(l['ecart'])
        self.assertIn('Code différent',l['etat'])

    def test_contexte_devise_taux_importateur_et_taxes(self):
        self.modifier('Traders/Consignee/Consignee_name','AUTRE')
        self.modifier('Valuation/Gs_Invoice/Currency_code','EUR')
        self.modifier('Valuation/Gs_Invoice/Currency_rate','100')
        rapport=self.rapport()
        self.assertTrue(any('Importateur différent' in c for c in rapport['contexte']))
        self.assertTrue(any('Taux de change différent' in c for c in rapport['contexte']))
        self.assertIsNone(self.ligne(rapport,1,'fob')['ecart'])
        self.assertEqual(self.ligne(rapport,'Total global','taxes')['etat'],'Contexte différent / non vérifiable')

    def test_division_zero_pourcentage_et_ratio(self):
        self.resultat['resume']['articles'][0].update(fob=0,poids=0)
        rapport=self.rapport()
        self.assertIsNone(self.ligne(rapport,1,'fob')['pourcentage'])
        self.assertIsNone(self.ligne(rapport,1,'ratio')['prevu'])

    def test_frais_fournis_differents_signales(self):
        arbre=ET.parse(self.fourni)
        fret=ET.SubElement(arbre.getroot().find('Valuation'),'Gs_external_freight')
        ET.SubElement(fret,'Amount_foreign_currency').text='42'
        arbre.write(self.fourni)
        rapport=self.rapport()
        self.assertTrue(any('Fret externe différent' in c for c in rapport['contexte']))

    def test_valeur_numerique_absente_non_remplacee_par_zero(self):
        self.modifier('Item/Tarification/Item_price','')
        l=self.ligne(self.rapport(),1,'fob')
        self.assertIsNone(l['fourni'])
        self.assertIsNone(l['ecart'])

    def test_xml_invalide(self):
        for contenu in ('<faux/>','<ASYCUDA>'):
            self.fourni.write_text(contenu)
            with self.assertRaises(ValueError):
                self.rapport()

    def test_resume_non_aligne_refuse(self):
        self.resultat['resume']['articles'].pop()
        with self.assertRaises(ValueError):
            self.rapport()


class ActionComparaisonTest(unittest.TestCase):
    def test_annulation_et_absence_apercu_ou_verrouillage(self):
        for resultat,verrouille in ((None,False),({'resume':{}},True),({'resume':{}},False)):
            page=SimpleNamespace(resultat=resultat, app=SimpleNamespace(session_verrouillee=verrouille))
            with patch.object(E.filedialog,'askopenfilename',return_value='') as choisir, \
                 patch('ui.comparaison.afficher') as afficher:
                E.PageVerifier.comparer_xml(page)
                self.assertEqual(choisir.call_count,int(bool(resultat) and not verrouille))
                afficher.assert_not_called()

    def test_ouvre_fichier_local_et_rapport_sans_import(self):
        page=SimpleNamespace(resultat={'resume':{}},app=SimpleNamespace(base='base.xml',session_verrouillee=False))
        with patch.object(E.filedialog,'askopenfilename',return_value='fourni.xml'), \
             patch('comparaison_prediction.comparer',return_value={'lignes':[]}) as comparer, \
             patch('ui.comparaison.afficher') as afficher:
            E.PageVerifier.comparer_xml(page)
        comparer.assert_called_once_with(page.resultat,'base.xml','fourni.xml')
        afficher.assert_called_once_with(page,{'lignes':[]})


if __name__=='__main__':
    unittest.main()
