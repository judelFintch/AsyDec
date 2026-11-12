from decimal import Decimal
from pathlib import Path
import random
import tempfile
import unittest

from asydec.declarations import repartition_licence as calcul, licences_ouvertes as registre
from asydec.declarations.documents_finaux import preparer_licence


class RepartitionTest(unittest.TestCase):
    def test_exemples_et_limite_incluse(self):
        for total, parts in [('120000', ['120000']), ('120000.01', ['60000.01','60000']),
                             ('300000',['100000']*3), ('168430',['84215']*2),
                             ('240000',['120000']*2), ('.01',['.01'])]:
            with self.subTest(total=total):
                self.assertEqual(calcul.repartir(total), [Decimal(p) for p in parts])

    def test_centimes_conserves_parts_egales_et_plafond(self):
        rng=random.Random(12)
        for _ in range(1000):
            total=Decimal(rng.randint(1,1000000000))/100
            parts=calcul.repartir(total)
            self.assertEqual(sum(parts),total)
            self.assertLessEqual(max(parts),Decimal('120000'))
            self.assertLessEqual(max(parts)-min(parts),Decimal('.01'))
            self.assertGreater(min(parts),0)

    def test_poids_egal_propose_et_bornes(self):
        for poids in (22000,23000,24000):
            r=calcul.preparer('300000',poids)
            self.assertEqual(r['poids_total_kg'],poids*3)
            self.assertTrue(all(p['poids_kg']==poids for p in r['parts']))
        self.assertEqual(calcul.preparer('168430')['poids_par_part_kg'],23000)
        for poids in (21999,24001,'NaN','23000.5','abc'):
            with self.subTest(poids=poids),self.assertRaises(ValueError):
                calcul.preparer('100',poids)

    def test_poids_aleatoires_par_part(self):
        poids=calcul.proposer_poids(50)
        self.assertEqual(len(poids),50)
        self.assertTrue(all(22000<=p<=24000 for p in poids))
        self.assertGreater(len(set(poids)),1)
        # Poids valides conservés, invalides ou manquants remplacés.
        conserves=calcul.proposer_poids(4,[22500,'abc',30000])
        self.assertEqual(conserves[0],22500)
        self.assertTrue(all(22000<=p<=24000 for p in conserves))
        r=calcul.preparer('300000',[22100,23900,22500])
        self.assertEqual([p['poids_kg'] for p in r['parts']],[22100,23900,22500])
        self.assertEqual(r['poids_total_kg'],68500)
        self.assertIsNone(r['poids_par_part_kg'])
        self.assertEqual(len(calcul.preparer('300000',[22100])['parts']),3)
        with self.assertRaises(ValueError):
            calcul.preparer('300000',[22100,25000,22500])

    def test_poids_par_part_enregistres(self):
        with tempfile.TemporaryDirectory() as dossier:
            fichier=Path(dossier)/'licences.sqlite'
            licence=preparer_licence('DEC9','300000','DEC9-ADD0-IB','17/03/2026')
            registre.enregistrer(licence,fichier)
            registre.enregistrer_repartition(licence['numero_validation'],'300000',[22001,23456,23999],fichier)
            relu=registre.charger(licence['numero_validation'],fichier)['repartition']
            self.assertEqual([p['poids_kg'] for p in relu['parts']],[22001,23456,23999])
            self.assertEqual(relu['poids_total_kg'],69456)

    def test_fob_invalides(self):
        for fob in ('NaN','Infinity','0','-1','1.001','abc'):
            with self.subTest(fob=fob),self.assertRaises(ValueError):
                calcul.repartir(fob)

    def test_persistence_et_recalcul_si_fob_change(self):
        with tempfile.TemporaryDirectory() as dossier:
            fichier=Path(dossier)/'licences.sqlite'
            licence=preparer_licence('DEC123','300000','DEC123-ADD0-IB','17/03/2026')
            registre.enregistrer(licence,fichier)
            registre.enregistrer_repartition(licence['numero_validation'],'300000','23000',fichier)
            relu=registre.charger(licence['numero_validation'],fichier)
            self.assertEqual(len(relu['repartition']['parts']),3)
            registre.enregistrer(licence,fichier)
            self.assertEqual(registre.charger(licence['numero_validation'],fichier)['repartition'],relu['repartition'])
            licence['montant_fob']=Decimal('100000')
            registre.enregistrer(licence,fichier)
            self.assertNotIn('repartition',registre.charger(licence['numero_validation'],fichier))
            with self.assertRaisesRegex(ValueError,'FOB a changé'):
                registre.enregistrer_repartition(licence['numero_validation'],'300000','23000',fichier)

    def test_liste_des_repartitions_enregistrees_et_filtre_par_licence(self):
        with tempfile.TemporaryDirectory() as dossier:
            fichier=Path(dossier)/'licences.sqlite'
            for numero,total in [('DEC1','300000'),('DEC2','168430'),('DEC3','1000')]:
                licence=preparer_licence(numero,total,numero+'-ADD0-IB','17/03/2026')
                registre.enregistrer(licence,fichier)
                if numero != 'DEC3':
                    registre.enregistrer_repartition(licence['numero_validation'],total,23000,fichier)
            lignes=registre.lister_repartitions(fichier=fichier)
            self.assertEqual(len(lignes),5)
            self.assertEqual(sum(Decimal(l['fob']) for l in lignes),Decimal('468430'))
            filtre=registre.lister_repartitions('DEC2-ADD0-IB',fichier)
            self.assertEqual([Decimal(l['fob']) for l in filtre],[Decimal('84215')]*2)
            self.assertEqual(sum(l['poids_kg'] for l in filtre),46000)
            self.assertEqual(registre.lister_repartitions('DEC3-ADD0-IB',fichier),[])


class ArticlesParPartTest(unittest.TestCase):
    PRODUITS=[dict(designation='Chapeaux',quantite='10000.000',unite='Unite(Piece)',prix_unitaire='0.9'),
              dict(designation='Imprimés',quantite='10000.000',unite='Kilogramme',prix_unitaire='0.45'),
              dict(designation='Aiguilles',quantite='2400.5',unite='Kilogramme',prix_unitaire='2')]

    def total(self):
        return sum(Decimal(p['quantite'])*Decimal(p['prix_unitaire']) for p in self.PRODUITS).quantize(Decimal('.01'))

    def test_quantites_identiques_et_totaux_conserves(self):
        for nombre in (1,2,3,7):
            with self.subTest(nombre=nombre):
                parts=calcul.repartir_articles(self.PRODUITS,nombre)
                self.assertEqual(len(parts),nombre)
                for i,produit in enumerate(self.PRODUITS):
                    lignes=[p[i] for p in parts]
                    quantites=[Decimal(l['quantite']) for l in lignes]
                    self.assertEqual(sum(quantites),Decimal(produit['quantite']))
                    pas=Decimal(1) if i<2 else Decimal('0.001')
                    self.assertLessEqual(max(quantites)-min(quantites),pas)
                    self.assertEqual(sum(Decimal(l['valeur']) for l in lignes),
                                     (Decimal(produit['quantite'])*Decimal(produit['prix_unitaire'])).quantize(Decimal('.01')))
                self.assertTrue(all(Decimal(l['quantite'])==Decimal(l['quantite']).to_integral_value() for p in parts for l in p[:2]))

    def test_fob_des_parts_egal_somme_des_articles(self):
        produits=[dict(p,quantite=str(Decimal(p['quantite'])*20)) for p in self.PRODUITS]
        total=sum(Decimal(p['quantite'])*Decimal(p['prix_unitaire']) for p in produits)
        r=calcul.preparer(total,23000,produits)
        self.assertGreater(len(r['parts']),1)
        self.assertEqual(sum(Decimal(p['fob']) for p in r['parts']),total)
        for part in r['parts']:
            self.assertLessEqual(Decimal(part['fob']),calcul.PLAFOND)
            self.assertEqual(Decimal(part['fob']),sum(Decimal(a['valeur']) for a in part['articles']))

    def test_sans_articles_coherents_division_du_fob_seule(self):
        r=calcul.preparer('300000',23000,self.PRODUITS)
        self.assertNotIn('articles',r['parts'][0])
        self.assertEqual([Decimal(p['fob']) for p in r['parts']],[Decimal('100000')]*3)
        r=calcul.preparer(self.total(),23000,self.PRODUITS)
        self.assertEqual(len(r['parts'][0]['articles']),3)


class EcartArrondiTest(unittest.TestCase):
    PRODUITS=[dict(designation='Motocycles',quantite='39.865',unite='Unite(Piece)',prix_unitaire='702')]

    def test_quantite_arrondie_de_la_licence_absorbee(self):
        # 39,865 × 702 = 27 985,23 pour un FOB de 27 985,00 (licence DEC0805534) : écart d'arrondi.
        self.assertEqual(calcul.ecart_arrondi(self.PRODUITS,'27985'),Decimal('-0.23'))
        for nombre in (None,3):
            with self.subTest(nombre=nombre):
                r=calcul.preparer('27985',23000,self.PRODUITS,nombre=nombre)
                self.assertTrue(all(p.get('articles') for p in r['parts']))
                self.assertEqual(sum(Decimal(p['fob']) for p in r['parts']),Decimal('27985.00'))
                self.assertEqual(sum(Decimal(p['articles'][0]['quantite']) for p in r['parts']),Decimal('39.865'))
                self.assertTrue(all(p['articles'][0]['prix_unitaire']=='702' for p in r['parts']))

    def test_articles_ajustes_quantite_fois_prix_egal_fob(self):
        (article,)=calcul.ajuster_articles(self.PRODUITS,'27985')
        q,pu=Decimal(article['quantite']),Decimal(article['prix_unitaire'])
        self.assertEqual((q*pu).quantize(Decimal('.01')),Decimal('27985.00'))
        # Motos : 39,865 devient 40 pièces, PU recalculé 699,625 (jamais de fraction de moto).
        self.assertEqual((q,pu),(Decimal(40),Decimal('699.625')))
        self.assertEqual(self.PRODUITS[0]['quantite'],'39.865')  # original intact
        # Répartition : chaque part a quantité × prix = sa valeur (au centime) et le total = FOB.
        r=calcul.preparer('27985',23000,[article],nombre=3)
        self.assertEqual(sum(Decimal(p['fob']) for p in r['parts']),Decimal('27985.00'))
        for p in r['parts']:
            a=p['articles'][0]
            self.assertLessEqual(abs((Decimal(a['quantite'])*pu).quantize(Decimal('.01'))-Decimal(a['valeur'])),Decimal('0.01'))
        # Écart réel ou aucun écart : inchangés.
        # Écart réel : quantité entière, valeur d'origine conservée par le PU.
        (reel,)=calcul.ajuster_articles(self.PRODUITS,'27000')
        self.assertEqual(Decimal(reel['quantite']),40)
        self.assertEqual((Decimal(reel['quantite'])*Decimal(reel['prix_unitaire'])).quantize(Decimal('.01')),Decimal('27985.23'))
        exact=[dict(self.PRODUITS[0],quantite='164')]
        self.assertIs(calcul.ajuster_articles(exact,'115128'),exact)

    def test_valeurs_affichees_ajustees_au_fob(self):
        self.assertEqual(calcul.valeurs_articles(self.PRODUITS,'27985'),[Decimal('27985.00')])
        self.assertEqual(calcul.valeurs_articles(self.PRODUITS,'27000'),[Decimal('27985.23')])  # écart réel : brut

    def test_ecart_reel_refuse(self):
        self.assertIsNone(calcul.ecart_arrondi(self.PRODUITS,'27000'))
        self.assertNotIn('articles',calcul.preparer('27000',23000,self.PRODUITS)['parts'][0])


class OptionsRepartitionTest(unittest.TestCase):
    def test_defaut_inchange(self):
        r=calcul.preparer('300000',23000)
        self.assertEqual(len(r['parts']),3)
        self.assertTrue(r['plafond_actif'])
        self.assertIsNone(r['nombre_parts_choisi'])
        self.assertEqual(r['plafond_usd'],'120000.00')

    def test_nombre_de_parts_choisi(self):
        r=calcul.preparer('300000',23000,nombre=5)
        self.assertEqual([p['fob'] for p in r['parts']],['60000.00']*5)
        self.assertEqual(r['nombre_parts_choisi'],5)
        self.assertEqual(calcul.repartir('100.01',3),[Decimal('33.34'),Decimal('33.34'),Decimal('33.33')])
        with self.assertRaisesRegex(ValueError,'au moins 3 parts'):
            calcul.preparer('300000',23000,nombre=2)
        for mauvais in ('0','abc','2.5','100'):
            with self.subTest(mauvais=mauvais),self.assertRaises(ValueError):
                calcul.preparer('300000',23000,nombre=mauvais)
        self.assertIsNone(calcul.preparer('300000',23000,nombre='')['nombre_parts_choisi'])

    def test_plafond_retire(self):
        r=calcul.preparer('300000',23000,plafond=False)
        self.assertEqual([p['fob'] for p in r['parts']],['300000.00'])
        r=calcul.preparer('300000',23000,nombre=2,plafond=False)
        self.assertEqual([p['fob'] for p in r['parts']],['150000.00']*2)
        self.assertIsNone(r['plafond_usd'])

    def test_articles_divises_avec_nombre_choisi(self):
        produits=[{'designation':'A','quantite':'10','prix_unitaire':'30000'},{'designation':'B','quantite':'3','prix_unitaire':'100'}]
        r=calcul.preparer('300300',23000,produits,nombre=4)
        self.assertEqual(len(r['parts']),4)
        self.assertEqual(sum(Decimal(p['fob']) for p in r['parts']),Decimal('300300'))
        with self.assertRaisesRegex(ValueError,'dépasse 120 000'):
            calcul.preparer('300300',23000,produits,nombre=3)  # 4 x 30 000 USD dans la première part
        self.assertEqual(len(calcul.preparer('300300',23000,produits,nombre=3,plafond=False)['parts']),3)

    def test_choix_enregistres_et_conserves(self):
        with tempfile.TemporaryDirectory() as dossier:
            fichier=Path(dossier)/'licences.sqlite'
            l=preparer_licence('DEC','300000','LICENCE','17/03/2026')
            registre.enregistrer(l,fichier)
            registre.enregistrer_repartition('LICENCE','300000',23000,fichier,nombre_parts=5)
            r=registre.charger('LICENCE',fichier)['repartition']
            self.assertEqual((len(r['parts']),r['nombre_parts_choisi'],r['plafond_actif']),(5,5,True))
            registre.enregistrer_repartition('LICENCE','300000',23000,fichier,plafond=False)
            r=registre.charger('LICENCE',fichier)['repartition']
            self.assertEqual((len(r['parts']),r['plafond_actif']),(1,False))
            self.assertEqual(registre.options_repartition({}),{'nombre':None,'plafond':True})


class QuantitesEntieresTest(unittest.TestCase):
    def test_unites_comptees_et_mesurees(self):
        from asydec.declarations import quantites_entieres as Q
        for u in ('Unite(Piece)', 'pcs', 'Paire', 'Nombre', 'Carton', 'Pièces'):
            self.assertTrue(Q.comptable(u), u)
        for u in ('Kilogramme', 'KG', 'Litre', 'm3', 'Tonne', ''):
            self.assertFalse(Q.comptable(u), u)

    def test_motos_fractionnaires_deviennent_entieres_fob_exact(self):
        from asydec.declarations import quantites_entieres as Q
        produits=[dict(designation='Motocycles',quantite='1425.212',unite='Unite(Piece)',prix_unitaire='701.65')]
        (a,)=calcul.ajuster_articles(produits,'1000000')
        self.assertEqual((a['quantite'],a['prix_unitaire']),('1425','701.754386'))
        r=calcul.preparer('1000000',23000,[a],nombre=10)
        self.assertEqual(sum(Decimal(p['fob']) for p in r['parts']),Decimal('1000000.00'))
        quantites=[Decimal(p['articles'][0]['quantite']) for p in r['parts']]
        self.assertTrue(all(q==q.to_integral_value() for q in quantites))
        self.assertEqual(sum(quantites),1425)
        self.assertEqual(Q.pu_texte('701.754386'),'701.754386')
        self.assertEqual(Q.pu_texte('1234.5'),'1,234.50')

    def test_article_mesure_absorbe_l_ecart_prix_des_pieces_intact(self):
        produits=[dict(designation='Chapeaux',quantite='10000.4',unite='Unite(Piece)',prix_unitaire='0.9'),
                  dict(designation='Fil',quantite='2400.5',unite='Kilogramme',prix_unitaire='2')]
        chapeaux,fil=calcul.ajuster_articles(produits,'13801.36')
        self.assertEqual((chapeaux['quantite'],chapeaux['prix_unitaire']),('10000','0.9'))
        self.assertEqual(fil['prix_unitaire'],'2')
        total=sum((Decimal(a['quantite'])*Decimal(a['prix_unitaire'])).quantize(Decimal('.01')) for a in (chapeaux,fil))
        self.assertEqual(total,Decimal('13801.36'))
