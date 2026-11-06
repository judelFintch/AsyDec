from pathlib import Path
import tempfile
import unittest

from asydec.declarations import reprises_licence as reprises, licences_ouvertes as registre
from asydec.declarations.documents_finaux import preparer_licence

ARTICLE = {'tarif_douanier': '6505000000', 'designation': 'Chapeaux\\nen bonneterie', 'pays_origine': 'China',
           'quantite': '10000.000', 'unite': 'Unite(Piece)', 'prix_unitaire': '0.9', 'devise': 'USD'}


class ReprisesLicenceTest(unittest.TestCase):
    def test_articles_et_parties_sans_doublon(self):
        with tempfile.TemporaryDirectory() as dossier:
            fichier = Path(dossier) / 'licences.sqlite'
            client = {'nom': 'ETS KATANGA TVS', 'adresse': 'AV INDUSTRIELLE'}
            for numero, produits, fournisseur in (
                    ('DEC1-ADD0-IB', [ARTICLE, dict(ARTICLE, designation='Horloges', prix_unitaire='3.8')], {'nom': 'YIWU'}),
                    ('DEC2-ADD0-IB', [dict(ARTICLE, quantite='5')], {'nom': 'KINSHOP'}),
                    ('DEC3-RC', [], {})):
                licence = preparer_licence(numero[:4], '1000', numero, '17/03/2026')
                licence.update(soussigne=client, fournisseur=fournisseur, produits=produits)
                registre.enregistrer(licence, fichier)
            articles = reprises.articles_existants(fichier)
            # Même article (quantité différente) sur deux licences : une seule proposition.
            self.assertEqual(len(articles), 2)
            chapeaux = next(a for a in articles if a['article']['designation'].startswith('Chapeaux'))
            self.assertEqual(sorted(chapeaux['licences']), ['DEC1-ADD0-IB', 'DEC2-ADD0-IB'])
            self.assertEqual(len(reprises.articles_existants(fichier, exclure='DEC1-ADD0-IB')), 1)
            importateurs, fournisseurs = reprises.parties_existantes(fichier)
            self.assertEqual([i['coordonnees'] for i in importateurs], [client])
            self.assertEqual(sorted(f['coordonnees']['nom'] for f in fournisseurs), ['KINSHOP', 'YIWU'])

    def test_copie_independante_quantite_videe(self):
        copie = reprises.copier_article(ARTICLE)
        self.assertEqual(copie['quantite'], '')
        self.assertEqual(copie['prix_unitaire'], '0.9')
        copie['designation'] = 'autre'
        self.assertEqual(ARTICLE['designation'], 'Chapeaux\\nen bonneterie')
        self.assertEqual(reprises.copier_article(ARTICLE, garder_quantite=True)['quantite'], '10000.000')


class AutomatiqueTest(unittest.TestCase):
    def test_client_rapproche_et_fournisseur_repris(self):
        self.assertEqual(reprises.cle_nom('STE KATANGA T.V.S. SARL'), reprises.cle_nom('ETS KATANGA TVS (CLT1064118)'))
        self.assertNotEqual(reprises.cle_nom('KATANGA TVS'), reprises.cle_nom('KATANGA MOTORS'))
        with tempfile.TemporaryDirectory() as dossier:
            fichier = Path(dossier) / 'licences.sqlite'
            complet = {'nom': 'ETS KATANGA TVS (CLT1064118)', 'adresse': 'AV INDUSTRIELLE', 'identifiants': 'NRC 14-A'}
            for numero, client, fournisseur in (('DEC1-ADD0-IB', complet, {'nom': 'YIWU'}),
                                                ('DEC2-ADD0-IB', complet, {'nom': 'KINSHOP', 'adresse': 'AJMAN'}),
                                                ('DEC3-RC', {'nom': 'STE KATANGA T.V.S. SARL'}, {})):
                licence = preparer_licence(numero[:4], '1000', numero, '17/03/2026')
                licence.update(soussigne=client, fournisseur=fournisseur)
                registre.enregistrer(licence, fichier)
            r = reprises.completer_parties({'nom': 'STE KATANGA T.V.S. SARL'}, {}, fichier, exclure='DEC3-RC')
            self.assertEqual((r['soussigne'], r['source_soussigne']), (complet, 'DEC2-ADD0-IB'))
            self.assertEqual((r['fournisseur']['nom'], r['source_fournisseur']), ('KINSHOP', 'DEC2-ADD0-IB'))  # le plus récent
            # Fournisseur déjà saisi et client inconnu : rien n'est remplacé.
            r = reprises.completer_parties({'nom': 'STE KATANGA T.V.S. SARL'}, {'nom': 'AUTRE'}, fichier)
            self.assertEqual((r['fournisseur'], r['source_fournisseur']), ({'nom': 'AUTRE'}, None))
            r = reprises.completer_parties({'nom': 'INCONNU SARL'}, {}, fichier)
            self.assertEqual((r['source_soussigne'], r['source_fournisseur']), (None, None))

    def test_quantites_exactes_sur_le_fob_et_acceptees_par_la_repartition(self):
        from decimal import Decimal
        from asydec.declarations import repartition_licence
        articles = [dict(ARTICLE, quantite='10000'), dict(ARTICLE, designation='Horloges', prix_unitaire='3.8', quantite='2500'),
                    dict(ARTICLE, designation='Motos', prix_unitaire='702', quantite='10')]
        for fob in ('1450000', '800000.37', '11000'):
            with self.subTest(fob=fob):
                produits, ecart = reprises.repartir_quantites(articles, fob, reprises.poids_origine(articles))
                self.assertEqual(ecart, 0)
                total = sum((Decimal(p['quantite']) * Decimal(p['prix_unitaire'])).quantize(Decimal('.01')) for p in produits)
                self.assertEqual(total, Decimal(fob))
                self.assertTrue(all(Decimal(p['quantite']) > 0 for p in produits))
                r = repartition_licence.preparer(fob, 23000, produits)
                self.assertIn('articles', r['parts'][0])  # étape 2 : articles divisés car total = FOB
        # Proportions d'origine conservées (à l'arrondi près).
        produits, _ = reprises.repartir_quantites(articles, '1450000', reprises.poids_origine(articles))
        valeurs = [Decimal(p['quantite']) * Decimal(p['prix_unitaire']) for p in produits]
        self.assertAlmostEqual(float(valeurs[0] / valeurs[1]), 9000 / 9500, places=2)
        # Article unique à prix élevé : prix ajusté de quelques centimes pour tomber exactement sur le FOB.
        for fob in ('1500000', '27985', '50000'):
            with self.subTest(fob=fob):
                (produit,), ecart = reprises.repartir_quantites([dict(ARTICLE, prix_unitaire='702')], fob)
                self.assertEqual(ecart, 0)
                q, pu = Decimal(produit['quantite']), Decimal(produit['prix_unitaire'])
                self.assertEqual((q * pu).quantize(Decimal('.01')), Decimal(fob))
                self.assertLessEqual(abs(pu - 702), 1)  # au plus près du prix d'origine
        # Prix inchangé quand la quantité suffit à tomber juste.
        (produit,), _ = reprises.repartir_quantites([dict(ARTICLE, prix_unitaire='702')], '115128')
        self.assertEqual((produit['quantite'], produit['prix_unitaire']), ('164.000', '702'))
        for mauvais in ('', '0'):
            with self.assertRaisesRegex(ValueError, 'FOB'):
                reprises.repartir_quantites(articles, mauvais)
        with self.assertRaisesRegex(ValueError, 'Prix'):
            reprises.repartir_quantites([dict(ARTICLE, prix_unitaire='')], '1000')


class PropositionArticlesTest(unittest.TestCase):
    def _base(self, dossier):
        fichier = Path(dossier) / 'licences.sqlite'
        textiles = [dict(ARTICLE, designation=f'Article {i}', prix_unitaire=str(p), quantite=str(q))
                    for i, (p, q) in enumerate([(0.9, 10000), (3.8, 2500), (2.5, 15000), (0.45, 10000), (5.8, 3000), (0.19, 7000)])]
        for numero, produits, client in (('DEC1-ADD0-IB', textiles, 'ETS KATANGA TVS'),
                                         ('DEC2-ADD0-IB', [dict(ARTICLE, designation='Motos', prix_unitaire='702', quantite='1800')], 'ETS KATANGA TVS'),
                                         ('DEC3-RC', [], 'STE KATANGA T.V.S. SARL')):
            licence = preparer_licence(numero[:4], '1000', numero, '17/03/2026')
            licence.update(soussigne={'nom': client}, produits=produits)
            registre.enregistrer(licence, fichier)
        return fichier

    def test_total_egal_au_fob_et_article_seul_repris_seul(self):
        import random
        from decimal import Decimal, ROUND_HALF_UP
        from asydec.declarations import repartition_licence
        with tempfile.TemporaryDirectory() as dossier:
            fichier = self._base(dossier)
            sources = set()
            for graine in range(40):
                for fob in ('1500000', '1404000', '27985.37'):
                    p = reprises.proposer_articles(fob, 'STE KATANGA T.V.S. SARL', fichier, exclure='DEC3-RC',
                                                   hasard=random.Random(graine))
                    total = sum((Decimal(a['quantite']) * Decimal(a['prix_unitaire'])).quantize(Decimal('.01'), ROUND_HALF_UP)
                                for a in p['produits'])
                    self.assertEqual((total, p['ecart']), (Decimal(fob), 0))
                    self.assertTrue(all(Decimal(a['quantite']) >= 1 for a in p['produits']))
                    if p['source'] == 'DEC2-ADD0-IB':
                        # Article utilisé seul sur le modèle : repris seul.
                        self.assertEqual([a['designation'] for a in p['produits']], ['Motos'])
                    else:
                        self.assertTrue(2 <= len(p['produits']) <= 6)
                    sources.add((p['source'], len(p['produits'])))
                    self.assertIn('articles', repartition_licence.preparer(fob, 23000, p['produits'])['parts'][0])
            self.assertIn(('DEC2-ADD0-IB', 1), sources)   # 1 404 000 = 2 000 motos
            self.assertGreater(len({n for s, n in sources if s == 'DEC1-ADD0-IB'}), 2)  # nombre d'articles varié

    def test_sans_modele_ou_sans_fob(self):
        with tempfile.TemporaryDirectory() as dossier:
            fichier = Path(dossier) / 'licences.sqlite'
            with self.assertRaisesRegex(ValueError, 'FOB'):
                reprises.proposer_articles('', fichier=fichier)
            with self.assertRaisesRegex(ValueError, 'modèle'):
                reprises.proposer_articles('1000', fichier=fichier)


class SuppressionLicenceTest(unittest.TestCase):
    def test_parties_et_articles_conserves_apres_suppression(self):
        with tempfile.TemporaryDirectory() as dossier:
            fichier = Path(dossier) / 'licences.sqlite'
            licence = preparer_licence('DEC1', '1000', 'DEC1-ADD0-IB', '17/03/2026')
            licence.update(soussigne={'nom': 'ETS KATANGA TVS', 'adresse': 'AV INDUSTRIELLE'},
                           fournisseur={'nom': 'YIWU'}, produits=[ARTICLE], repartition={'parts': []})
            registre.enregistrer(licence, fichier)
            supprimee = registre.supprimer('DEC1-ADD0-IB', fichier)
            self.assertEqual(registre.lister(fichier), [])
            with self.assertRaisesRegex(ValueError, 'introuvable'):
                registre.charger('DEC1-ADD0-IB', fichier)
            # Client, fournisseur et articles toujours proposés.
            importateurs, fournisseurs = reprises.parties_existantes(fichier)
            self.assertEqual([i['coordonnees']['nom'] for i in importateurs], ['ETS KATANGA TVS'])
            self.assertEqual([f['coordonnees']['nom'] for f in fournisseurs], ['YIWU'])
            self.assertEqual(len(reprises.articles_existants(fichier)), 1)
            self.assertEqual(reprises.completer_parties({'nom': 'STE KATANGA T.V.S.'}, {}, fichier)['source_fournisseur'],
                             'DEC1-ADD0-IB')
            self.assertEqual(len(reprises.modeles_articles(fichier)), 1)
            # Recommencer : étape 1 seulement, puis la licence peut être réenregistrée.
            base = registre.base_recommencer(supprimee)
            self.assertNotIn('repartition', base)
            self.assertEqual((base['date_validation'], base['produits']), ('17/03/2026', [ARTICLE]))
            registre.enregistrer(dict(licence, produits=base['produits']), fichier)
            self.assertEqual(len(registre.lister(fichier)), 1)
            self.assertEqual(len(reprises.modeles_articles(fichier)), 1)        # pas de doublon ouverte/archivée
            self.assertEqual(len(reprises.articles_existants(fichier, exclure='DEC1-ADD0-IB')), 1)  # archive gardée
            with self.assertRaisesRegex(ValueError, 'introuvable'):
                registre.supprimer('INCONNUE', fichier)

    def test_tout_supprimer(self):
        with tempfile.TemporaryDirectory() as dossier:
            fichier = Path(dossier) / 'licences.sqlite'
            for numero in ('DEC1-ADD0-IB', 'DEC2-ADD0-IB'):
                licence = preparer_licence(numero[:4], '1000', numero, '17/03/2026')
                licence.update(soussigne={'nom': 'CLIENT ' + numero}, produits=[ARTICLE])
                registre.enregistrer(licence, fichier)
            self.assertEqual(len(registre.supprimer_toutes(fichier)), 2)
            self.assertEqual(registre.lister(fichier), [])
            self.assertEqual(len(reprises.parties_existantes(fichier)[0]), 2)
            self.assertEqual(len(reprises.articles_existants(fichier)), 1)
            self.assertEqual(registre.supprimer_toutes(fichier), [])


class ArticlesDeclarationsTest(unittest.TestCase):
    def test_articles_des_vraies_declarations(self):
        with tempfile.TemporaryDirectory() as dossier:
            Path(dossier, 'tvs.xml').write_text(
                '<ASYCUDA><Item><Tarification><HScode><Commodity_code>87141000</Commodity_code><Precision_1>00</Precision_1>'
                '</HScode><Supplementary_unit><Suppplementary_unit_name>Unité</Suppplementary_unit_name>'
                '<Suppplementary_unit_quantity>100</Suppplementary_unit_quantity></Supplementary_unit>'
                '<Item_price>7500</Item_price></Tarification><Goods_description><Country_of_origin_code>IN</Country_of_origin_code>'
                '<Description_of_goods>Parties et accessoires de motocycles</Description_of_goods></Goods_description>'
                '<Valuation_item><Item_Invoice><Amount_foreign_currency>7500</Amount_foreign_currency>'
                '<Currency_code>USD</Currency_code></Item_Invoice></Valuation_item></Item>'
                '<Item><Tarification><HScode><Commodity_code></Commodity_code></HScode></Tarification></Item></ASYCUDA>',
                encoding='utf-8')
            (source,) = reprises.articles_declarations(dossier)
            self.assertEqual(source['licences'], ['XML tvs'])
            a = source['article']
            self.assertEqual((a['tarif_douanier'], a['pays_origine'], a['prix_unitaire'], a['quantite']),
                             ('8714100000', 'IN', '75.00', '100'))
            # Déjà présent sur une licence (même code, désignation, origine) : pas de doublon.
            self.assertEqual(reprises.articles_declarations(dossier, connus=[source]), [])
