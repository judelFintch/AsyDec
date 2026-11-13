from unittest import TestCase, skipUnless
from unittest.mock import patch
from pathlib import Path
from asydec.declarations import facture_licence as F, facture_kinshop as K
from tests.test_facture_licence import licence

def texte(contenu):
    from io import BytesIO
    from zipfile import ZipFile
    from xml.dom import minidom
    from asydec.declarations.preparer_facture import paragraphes, texte as contenu_texte
    with ZipFile(BytesIO(contenu)) as z:
        doc = minidom.parseString(z.read("word/document.xml"))
        return " ".join(contenu_texte(p) for p in paragraphes(doc))


MODELES_PRESENTS = all(K.modele(p).is_file() for p in (False, True))


class DistributionPubliqueTest(TestCase):
    def test_factures_generees_sans_les_word_prives(self):
        l = licence(parts=1)
        l['fournisseur'] = dict(nom='KINSHOP GENERAL TRADING FZE', adresse='Adresse licence')
        with patch.object(K, 'modele', return_value=Path('/modele-absent.docx')):
            self.assertFalse(K.disponible(l))
            resultats = F.generer(l) + [F.generer_globale(l)]
        for resultat in resultats:
            for document in resultat['documents'].values():
                self.assertIn(l['fournisseur']['nom'], texte(document))
                self.assertIn(l['fournisseur']['adresse'], texte(document))


@skipUnless(MODELES_PRESENTS, 'Références Word privées non distribuées ; génération autonome testée séparément')
class KinshopTest(TestCase):
    def test_modele_fournisseur_sans_references_de_l_ancienne_operation(self):
        l = licence()
        l['fournisseur'] = {'nom': 'KINSHOP GENERAL TRADING FZE', 'email': 'contact@kgtfze.com'}
        self.assertTrue(K.correspond(l))
        part = F.generer(l)[0]
        globale = F.generer_globale(l)
        facture = texte(part['documents']['facture'])
        packing = texte(part['documents']['packing list'])
        for t in (facture, packing):
            self.assertIn('Part 1 of 2', t)
            self.assertIn('Country of Origin of Goods', t)
            self.assertNotIn('22060190', t)
            self.assertNotIn('14-06-2025', t)
            self.assertIn('AE 400351191323991345021', t)
        self.assertIn('Weight', packing)
        self.assertNotIn('Height', packing)
        self.assertIn('115,128.00', facture)
        self.assertIn('All 2 parts', texte(globale['documents']['facture']))

    def test_structure_et_tous_les_medias_du_word_original_conserves(self):
        from io import BytesIO
        from zipfile import ZipFile
        from xml.etree import ElementTree as E
        l = licence()
        l['fournisseur'] = {'nom': 'KINSHOP GENERAL TRADING FZE'}
        donnees = F.donnees_part(l, l['repartition']['parts'][0])
        for packing in (False, True):
            resultat = K.creer(l, donnees, packing)
            with ZipFile(K.modele(packing)) as source, ZipFile(BytesIO(resultat)) as cible:
                self.assertEqual(source.namelist(), cible.namelist())
                for nom in source.namelist():
                    if nom != 'word/document.xml':
                        self.assertEqual(source.read(nom), cible.read(nom), nom)
                a = E.fromstring(source.read('word/document.xml'))
                b = E.fromstring(cible.read('word/document.xml'))
                # Cadres, tableaux, dessins et sections identiques ; seuls la typographie, les retraits
                # et la répartition des colonnes de section s'ajustent aux valeurs.
                for nom in ('tbl', 'tr', 'tc', 'drawing', 'sectPr', 'anchor'):
                    self.assertEqual(sum(1 for n in a.iter() if n.tag.endswith('}' + nom)),
                                     sum(1 for n in b.iter() if n.tag.endswith('}' + nom)), nom)

    def test_trop_d_articles_refuse_sans_changer_le_modele(self):
        l = licence()
        l['fournisseur'] = {'nom': 'KINSHOP GENERAL TRADING FZE'}
        donnees = F.donnees_part(l, l['repartition']['parts'][0])
        donnees['lignes'] *= 4
        with self.assertRaisesRegex(ValueError, '3 lignes'):
            K.creer(l, donnees)

    def test_grandes_quantites_conservent_valeur_et_largeur(self):
        from asydec.declarations.preparer_facture import texte as lire
        from asydec.declarations import factures as outils
        from decimal import Decimal
        l = licence(parts=1)
        donnees = F.donnees_part(l, l['repartition']['parts'][0])
        donnees['lignes'][0]['quantite'] = Decimal('1234567.891')
        donnees['quantites'] = Decimal('1234567.891')
        for packing in (False, True):
            resultat = K.creer(l, donnees, packing)
            archive, parties = outils._parties(resultat)
            try:
                doc = parties['word/document.xml']
                lignes = next(t for t in doc.getElementsByTagNameNS(outils.W, 'tbl')
                              if '1,234,567.891' in lire(t))
                cellule = K._cellules([r for r in lignes.childNodes if r.localName == 'tr'][0])[1]
                self.assertEqual(lire(cellule), '1,234,567.891')
                self.assertEqual(cellule.getElementsByTagNameNS(outils.W, 'tcW')[0].getAttribute('w:w'), '1271')
                self.assertFalse(cellule.getElementsByTagNameNS(outils.W, 'fitText'))
                self.assertLess(int(cellule.getElementsByTagNameNS(outils.W, 'sz')[-1].getAttribute('w:val')), 17)
                # Une seule ligne dans la colonne dessinée « Quantity ».
                from asydec.declarations import ajustement_word as A
                styles = A.styles(archive.read('word/styles.xml'))
                p = cellule.getElementsByTagNameNS(outils.W, 'p')[0]
                self.assertEqual(A.nombre_lignes(p, A.largeurs(doc, styles)[p], styles), 1)
            finally:
                archive.close()


@skipUnless(MODELES_PRESENTS, 'Références Word privées non distribuées ; génération autonome testée séparément')
class MiseEnPageKinshopTest(TestCase):
    def _document(self, packing=False, quantite=None, nom='ETS KATANGA TVS (CLT1064118)'):
        from decimal import Decimal
        from asydec.declarations import factures as outils, ajustement_word as A
        l = licence(parts=1)
        l['fournisseur'] = {'nom': 'KINSHOP GENERAL TRADING FZE'}
        l['soussigne'] = {'nom': nom, 'adresse': 'AVENUE INDUSTRIELLE 2580, Lubumbashi, Katanga, Congo, The Democratic Republic of the'}
        donnees = F.donnees_part(l, l['repartition']['parts'][0])
        if quantite:
            donnees['lignes'][0]['quantite'] = donnees['quantites'] = Decimal(quantite)
        archive, parties = outils._parties(K.creer(l, donnees, packing))
        try:
            return parties['word/document.xml'], A.styles(archive.read('word/styles.xml'))
        finally:
            archive.close()

    def test_valeurs_numeriques_sur_une_seule_ligne(self):
        from asydec.declarations import ajustement_word as A
        from asydec.declarations.preparer_facture import paragraphes, texte
        for packing in (False, True):
            doc, styles = self._document(packing, quantite='1425.212')
            largeurs = A.largeurs(doc, styles)
            nombres = [p for p in paragraphes(doc) if p in largeurs and texte(p).strip().startswith(('1,425.212', '$'))]
            self.assertTrue(nombres)
            for p in nombres:
                self.assertEqual(A.nombre_lignes(p, largeurs[p], styles), 1, texte(p))

    def test_adresse_client_et_pays_sur_leurs_lignes(self):
        from asydec.declarations.preparer_facture import paragraphes, texte
        doc, _ = self._document()
        textes = [texte(p) for p in paragraphes(doc)]
        self.assertIn('AVENUE INDUSTRIELLE 2580, Lubumbashi, Katanga', textes)
        self.assertGreaterEqual(textes.count('RD.CONGO'), 2)
        self.assertEqual(K._adresse_client('12 RUE X, Kinshasa, RDC'), ('12 RUE X, Kinshasa', 'RD.CONGO'))
        self.assertEqual(K._adresse_client('ZONE 3, Lusaka, Zambia'), ('ZONE 3, Lusaka', 'Zambia'))

    def test_nom_long_du_consignataire_dans_le_bloc_adresse(self):
        from asydec.declarations import ajustement_word as A
        from asydec.declarations.preparer_facture import paragraphes, texte
        doc, styles = self._document()
        largeurs = A.largeurs(doc, styles)
        noms = [p for p in paragraphes(doc) if texte(p) == 'ETS KATANGA TVS (CLT1064118)']
        self.assertEqual(len(noms), 2)
        for p in noms:
            self.assertEqual(A.nombre_lignes(p, largeurs[p], styles), 1)
            tailles = [int(n.getAttribute('w:val')) for r in p.getElementsByTagNameNS(A.W, 'r')
                       for n in r.getElementsByTagNameNS(A.W, 'sz')]
            self.assertGreaterEqual(min(tailles or [15]), 13)  # lisible : pas de réduction extrême

    def test_totaux_sur_la_ligne_de_la_facture_et_dessins_sous_le_texte(self):
        from asydec.declarations import ajustement_word as A
        from asydec.declarations.preparer_facture import paragraphes, texte
        for packing in (False, True):
            doc, _ = self._document(packing)
            self.assertTrue(all(a.getAttribute('behindDoc') == '1'
                                for a in doc.getElementsByTagNameNS(
                                    'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing', 'anchor')))
            cols = [c for s in doc.getElementsByTagNameNS(A.W, 'cols')
                    for c in s.getElementsByTagNameNS(A.W, 'col') if c.getAttribute('w:w') == str(K.QUANTITE_TOTAL_LARGEUR)]
            self.assertEqual(len(cols), 1)
            ps = paragraphes(doc)
            i = next(i for i, p in enumerate(ps) if texte(p) == 'TOTAL')
            # Même suite que la facture : espace, TOTAL, espace, valeur.
            self.assertEqual(texte(ps[i - 1]).strip(), '')
            self.assertEqual(texte(ps[i + 1]).strip(), '')
            self.assertTrue(texte(ps[i + 2]).strip())
            if packing:
                self.assertIn('Weight Chargeable', texte(ps[i - 4]) + texte(ps[i - 3]))
