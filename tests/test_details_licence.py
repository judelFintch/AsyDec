import unittest
from asydec.declarations.details_licence import extraire_details, COLONNES_PRODUITS


class DetailsLicenceTest(unittest.TestCase):
    def test_soussigne_et_fournisseur_distincts(self):
        texte = '''Je soussigné SOCIETE IMPORTATRICE (CLT123)
Avenue du Commerce 10, Ville
Tel: 123456 - import@example.com
N° N.R.C. : ABC - N° Impôt : XYZ
 déclare réaliser l’importation
3) Nom du fournisseur Etranger EXPORT COMPANY
Détails du fournisseur Une adresse étrangère
N° de téléphone(s) 987654
Liste Des Produits (2)'''
        tableaux = [[['Données', 'A remplir'],
                     ['3) Nom du fournisseur Etranger', None, 'EXPORT COMPANY', None],
                     ['Détails du fournisseur', None, 'Room 1\nBuilding B', None],
                     ['', None, 'N° de téléphone(s)', '987654'],
                     ['', None, 'E-Mail', 'export@example.com'],
                     ['', None, 'Fax', '.'],
                     ['4) Monnaie de la transaction', None, 'USD', None],
                     ['8) Nom du Bénéficiaire du paiement', None, 'AUTRE SOCIETE', None]]]
        v = extraire_details(texte, tableaux)
        self.assertEqual(v['soussigne']['nom'], 'SOCIETE IMPORTATRICE (CLT123)')
        self.assertEqual(v['soussigne']['telephone'], '123456')
        self.assertEqual(v['soussigne']['email'], 'import@example.com')
        self.assertEqual(v['soussigne']['adresse'], 'Avenue du Commerce 10, Ville')
        self.assertIn('N° Impôt : XYZ', v['soussigne']['identifiants'])
        self.assertEqual(v['fournisseur']['nom'], 'EXPORT COMPANY')
        self.assertEqual(v['fournisseur']['adresse'], 'Room 1\nBuilding B')
        self.assertEqual(v['fournisseur']['email'], 'export@example.com')
        self.assertEqual(v['nombre_produits_attendu'], 2)

    def test_articles_sur_plusieurs_pages_sans_perdre_les_retours_ligne(self):
        entete = ['Tarif Douanier', 'Désignation', "Pays d’Origine", 'Quantité', 'Unité stat.', 'Prix Unit.', 'Devise']
        premier = ['6505000000', 'Chapeaux\nen bonneterie', 'China', '10000.000', 'Unite(Piece)', '0.9', 'USD']
        dernier = ['4819400000', 'Sacs et\nsachets', 'China', '7000.000', 'Unite(Piece)', '0.19', 'USD']
        v = extraire_details('Liste Des Produits (2)', [[entete, premier], [entete, dernier]])
        self.assertEqual(v['produits'], [dict(zip(COLONNES_PRODUITS, premier)), dict(zip(COLONNES_PRODUITS, dernier))])

    def test_absence_ne_cree_pas_d_articles(self):
        v = extraire_details('Liste Des Produits (11)')
        self.assertEqual(v['produits'], [])
        self.assertEqual(v['nombre_produits_attendu'], 11)
