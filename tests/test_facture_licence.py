"""Étape 5 : facture et packing list de la part 1, structure du modèle Word conservée."""
import copy
from io import BytesIO
from unittest import TestCase, main
from xml.dom import minidom
from zipfile import ZipFile

from asydec.declarations import factures as F
from asydec.declarations import facture_licence, mise_a_jour_repartitions


def modele(lignes=2, separation='br'):
    def p(t):
        return '<w:p><w:r><w:rPr><w:rFonts w:ascii="Arial Black"/><w:b/></w:rPr><w:t>' + t + '</w:t></w:r></w:p>'

    def row(cs):
        return '<w:tr>' + ''.join('<w:tc>' + p(c) + '</w:tc>' for c in cs) + '</w:tr>'
    tables = []
    for facture in (True, False):
        corps = ''.join(row([str(i), f'ANCIEN ARTICLE {i}', '80', '$2.00' if facture else '',
                             '$160.00' if facture else 'KGS 100.00']) for i in range(1, lignes + 1))
        tables.append('<w:tbl>' + row(['N°', 'Goods Description', 'Quantity', 'U. Price' if facture else 'Unit W',
                                       'Total Price' if facture else 'Total Weight']) + corps
                      + row(['TOTAL FOB' if facture else 'TOTAL WEIGHT', '$320.00' if facture else 'KGS 200 KG'])
                      + '</w:tbl>')
    coupe = {'br': '<w:p><w:r><w:t>Signature</w:t><w:br w:type="page"/><w:t>PACKING LIST</w:t></w:r></w:p>',
             'titre': p('PACKING LIST'),
             'avant': '<w:p><w:pPr><w:pageBreakBefore/></w:pPr><w:r><w:t>PACKING LIST</w:t></w:r></w:p>',
             'section': '<w:p><w:pPr><w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr></w:pPr></w:p>' + p('PACKING LIST'),
             'aucune': ''}[separation]
    xml = (f'<w:document xmlns:w="{F.W}"><w:body>' + p('INV NO: OLD DATE:27–07–2026') + p('PLAQUE : T123ABC')
           + tables[0] + p('160 PKG') + coupe + tables[1] + p('MANIFEST NO: 0499-ML1757')
           + '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/></w:sectPr></w:body></w:document>')
    b = BytesIO()
    with ZipFile(b, 'w') as z:
        z.writestr('[Content_Types].xml', '<Types/>')
        z.writestr('word/document.xml', xml)
        z.writestr('word/media/logo.png', b'logo')
    return b.getvalue()


def licence(articles=None, parts=2):
    articles = articles or [dict(article=1, designation='Motocycles 50 cm3', unite='Unite(Piece)',
                                 prix_unitaire='702', quantite='164', valeur='115128.00')]
    infos = {'numero_e': '4900', 'numero_liquidation': '1200', 'numero_quittance': '700', 'manifeste': '4900'}
    return {'numero_validation': 'DEC1-IB', 'soussigne': {'nom': 'ETS KATANGA'}, 'informations_declaration': infos,
            'numero_facture': 'ORD0000013709', 'date_facture': '16/06/2025',
            'repartition': {'parts': [dict(numero=n, fob='115128.00', poids_kg=23000 - n, plaque=f'T30{n}XDH/T908ZPJ',
                                           articles=articles, informations_declaration=dict(infos, manifeste=f'49{n:02d}'))
                                      for n in range(1, parts + 1)]}}


def document(contenu):
    with ZipFile(BytesIO(contenu)) as z:
        return z.read('word/document.xml').decode()


def facture_document(contenu):
    return document(contenu)


def texte(contenu):
    d = minidom.parseString(document(contenu))
    return ' | '.join(''.join(n.data for n in t.childNodes) for t in d.getElementsByTagNameNS(F.W, 't'))


class FactureLicenceTest(TestCase):
    def test_facture_et_packing_list_separees_pour_chaque_part(self):
        resultats = facture_licence.generer(licence(), modele())
        self.assertEqual([r['numero'] for r in resultats], ['ORD0000013709-1', 'ORD0000013709-2'])
        for n, r in enumerate(resultats, 1):
            facture, colisage = texte(r['documents']['facture']), texte(r['documents']['packing list'])
            self.assertIn(f'INV NO: ORD0000013709-{n}', facture)
            self.assertIn('16/06/2025', facture)
            self.assertIn('Motocycles 50 cm3', facture)
            self.assertIn('115 128,00', facture)
            self.assertIn(f'T30{n}XDH/T908ZPJ', facture)
            self.assertIn('Signature', facture)
            self.assertNotIn('PACKING LIST', facture)
            self.assertNotIn('Total Weight', facture)
            self.assertIn('PACKING LIST', colisage)
            self.assertIn(f'{23000 - n:,}'.replace(',', ' ') + ',00', colisage)
            self.assertIn(f'MANIFEST NO: 49{n:02d}', colisage)
            self.assertNotIn('Total Price', colisage)
            self.assertNotIn('Signature', colisage)
            for t in (facture, colisage):
                self.assertNotIn('ANCIEN ARTICLE', t)
                self.assertNotIn('{{', t)
            for document in r['documents'].values():
                self.assertNotIn('w:type="page"', facture_document(document))
        self.assertEqual(facture_licence.nom_fichier('DEC1-IB', resultats[1], 'facture'),
                         'DEC1-IB - part 2 - facture ORD0000013709-2.docx')
        self.assertEqual(facture_licence.nom_fichier('DEC1-IB', resultats[1], 'packing list'),
                         'DEC1-IB - part 2 - packing list ORD0000013709-2.docx')

    def test_separation_selon_le_modele(self):
        for separation in ('br', 'titre', 'avant', 'section'):
            with self.subTest(separation=separation):
                r = facture_licence.generer(licence(parts=1), modele(separation=separation))[0]
                facture, colisage = (document(r['documents'][d]) for d in ('facture', 'packing list'))
                self.assertEqual((facture.count('<w:tbl>'), colisage.count('<w:tbl>')), (1, 1))
                self.assertIn('Total Price', facture)
                self.assertIn('Total Weight', colisage)
                self.assertNotIn('pageBreakBefore', colisage)
                # Une seule mise en page par document, à la fin du corps.
                self.assertEqual((facture.count('<w:sectPr>'), colisage.count('<w:sectPr>')), (1, 1))
        r = facture_licence.generer(licence(parts=1), modele(separation='section'))[0]
        self.assertIn('11906', document(r['documents']['facture']))
        self.assertIn('12240', document(r['documents']['packing list']))
        with self.assertRaisesRegex(ValueError, 'saut de page'):
            facture_licence.generer(licence(parts=1), modele(separation='aucune'))

    def test_structure_polices_et_medias_conserves(self):
        source = modele()
        r = facture_licence.generer(licence(parts=1), source)[0]
        moities = [document(c) for c in r['documents'].values()]
        for balise in ('<w:tbl>', '<w:tr>', '<w:tc>', 'Arial Black'):
            self.assertEqual(document(source).count(balise), sum(m.count(balise) for m in moities), balise)
        for contenu in r['documents'].values():
            with ZipFile(BytesIO(contenu)) as z:
                self.assertEqual(z.read('word/media/logo.png'), b'logo')

    def test_poids_reparti_selon_les_quantites(self):
        self.assertEqual(facture_licence.repartir_poids(['1', '1', '1'], 23000), [7667, 7667, 7666])
        self.assertEqual(facture_licence.repartir_poids(['300', '100'], 23000), [17250, 5750])

    def test_modele_trop_court_refuse(self):
        articles = [dict(article=i, designation=f'A{i}', unite='', prix_unitaire='10', quantite='5', valeur='50.00')
                    for i in (1, 2, 3)]
        with self.assertRaisesRegex(ValueError, '2 ligne'):
            facture_licence.generer(licence(articles), modele(2))

    def test_numero_de_facture_de_la_licence_obligatoire(self):
        l = licence()
        l['numero_facture'] = ''
        with self.assertRaisesRegex(ValueError, 'numéro et la date de facture'):
            facture_licence.generer(l, modele())

    def test_factures_hors_empreinte_et_perimees_si_donnees_changent(self):
        l = licence()
        l['mise_a_jour_repartitions'] = {'empreinte': mise_a_jour_repartitions.empreinte(l)}
        resultats = facture_licence.generer(l, modele())
        fichiers = [{'facture': f'f{i}.docx', 'packing list': f'p{i}.docx'} for i in (1, 2)]
        sans_globale = dict(facture_licence.fiche(l, resultats, fichiers, 'modele.docx'),
                            empreinte=mise_a_jour_repartitions.empreinte(l))
        self.assertFalse(facture_licence.est_a_jour(dict(l, factures_parts=sans_globale)))  # globale requise
        globale = facture_licence.generer_globale(l, modele())
        l['factures_parts'] = dict(facture_licence.fiche(
            l, resultats, fichiers, 'modele.docx', globale, {'facture': 'g.docx', 'packing list': 'gp.docx'}),
                                   empreinte=mise_a_jour_repartitions.empreinte(l))
        self.assertTrue(mise_a_jour_repartitions.est_a_jour(l))
        self.assertTrue(facture_licence.est_a_jour(l))
        poids = copy.deepcopy(l)
        poids['repartition']['parts'][0]['poids_kg'] = 22000
        self.assertFalse(facture_licence.est_a_jour(poids))
        numero = copy.deepcopy(l)
        numero['numero_facture'] = 'ORD0000099999'
        self.assertTrue(mise_a_jour_repartitions.est_a_jour(numero))  # l'étape 4 reste validée
        self.assertFalse(facture_licence.est_a_jour(numero))


class FactureGlobaleTest(TestCase):
    def licence_deux_articles(self):
        l = licence(parts=2)
        p1, p2 = l['repartition']['parts']
        p1['articles'] = [dict(article=1, designation='Motos', unite='Piece', prix_unitaire='700', quantite='100', valeur='70000.00'),
                          dict(article=2, designation='Pneus', unite='Piece', prix_unitaire='50', quantite='300', valeur='15000.00')]
        p2['articles'] = [dict(article=1, designation='Motos', unite='Piece', prix_unitaire='700', quantite='60', valeur='42000.00'),
                          dict(article=2, designation='Pneus', unite='Piece', prix_unitaire='50', quantite='100', valeur='5000.00')]
        return l

    def test_totaux_de_toutes_les_parts_par_article(self):
        l = self.licence_deux_articles()
        parts = facture_licence.generer(l)
        globale = facture_licence.generer_globale(l)
        self.assertEqual(globale['numero'], 'ORD0000013709')
        self.assertEqual(globale['part'], 'global')
        self.assertEqual(globale['articles'], 2)
        self.assertEqual(globale['fob'], '132000.00')
        self.assertEqual(globale['poids_kg'], sum(p['poids_kg'] for p in parts))
        donnees = facture_licence.donnees_globale(l)
        self.assertEqual([(str(x['quantite']), str(x['valeur'])) for x in donnees['lignes']],
                         [('160', '112000.00'), ('400', '20000.00')])
        facture, colisage = texte(globale['documents']['facture']), texte(globale['documents']['packing list'])
        for attendu in ('ORD0000013709', '112,000.00', '20,000.00', '132,000.00'):
            self.assertIn(attendu, facture)
        self.assertNotIn('ORD0000013709-', facture)
        self.assertIn('All 2 parts', colisage)
        self.assertIn('All 2 parts', facture)
        self.assertEqual(facture_licence.nom_fichier('LIC 1', globale),
                         'LIC-1 - global - facture ORD0000013709.docx')

    def test_avec_modele(self):
        l = self.licence_deux_articles()
        globale = facture_licence.generer_globale(l, modele())
        facture = texte(globale['documents']['facture'])
        self.assertIn('ORD0000013709', facture)
        self.assertIn('132', facture)

    def test_prix_moyen_si_les_prix_different(self):
        l = self.licence_deux_articles()
        l['repartition']['parts'][1]['articles'][0].update(prix_unitaire='710', valeur='42600.00')
        ligne = facture_licence.donnees_globale(l)['lignes'][0]
        self.assertEqual(str(ligne['prix_unitaire']), '703.75')


class FactureSimpleTest(TestCase):
    def test_facture_et_packing_list_creees_sans_modele(self):
        l = licence()
        l['fournisseur'] = {'nom': 'EXEMPLE GENERAL TRADING FZE', 'adresse': 'AJMAN FREE ZONE'}
        l['produits'] = [{'tarif_douanier': '8711100000', 'pays_origine': 'India', 'devise': 'USD'}]
        l['repartition']['parts'][1].update(conteneur='MRSU 3816289', scelle='G9152292')
        resultats = facture_licence.generer(l)
        self.assertEqual([r['numero'] for r in resultats], ['ORD0000013709-1', 'ORD0000013709-2'])
        documents = resultats[1]['documents']
        self.assertEqual(set(documents), {'facture', 'packing list'})
        for contenu in documents.values():
            with ZipFile(BytesIO(contenu)) as z:
                self.assertEqual(sorted(z.namelist()), ['[Content_Types].xml', '_rels/.rels', 'word/_rels/document.xml.rels',
                                                        'word/document.xml', 'word/media/asydec-sceau-1.png'])
                minidom.parseString(z.read('word/document.xml'))  # XML bien formé
        facture, colisage = texte(documents['facture']), texte(documents['packing list'])
        communs = ('ORD0000013709-2', '16/06/2025', 'EXEMPLE GENERAL TRADING FZE', 'ETS KATANGA',
                   'Motocycles 50 cm3', 'Consignee:', 'INV NO', 'TOTAL FOB IN WORDS',
                   'ONE HUNDRED FIFTEEN THOUSAND ONE HUNDRED TWENTY EIGHT US DOLLARS')
        douane = ('LICENCE NO', 'DEC1-IB', 'DEC NO', 'TRUCK / TRAILER', 'T302XDH/T908ZPJ', 'CONTAINER', 'MRSU 3816289',
                  'SEAL', 'G9152292', 'MANIFEST NO', '4902')
        for absent in douane:
            self.assertNotIn(absent, facture)  # retirés de la facture commerciale
            self.assertNotIn(absent, colisage)  # et de la packing list
        self.assertIn('Part 2 of 2', facture)
        self.assertIn('Part 2 of 2', colisage)
        for attendu in communs + ('INVOICE', 'TOTAL FOB', 'FREIGHT', 'INSURANCE', 'TOTAL CIF', '115,128.00'):
            self.assertIn(attendu, facture)
        for absent in ('8711100000', 'India', 'HS CODE', 'ORIGIN', 'WEIGHT IN WORDS', 'TERMS'):
            self.assertNotIn(absent, facture)  # comme la facture commerciale réelle (FCM)
        for attendu in communs + ('PACKING LIST', '22,998.00', 'TWENTY TWO THOUSAND NINE HUNDRED NINETY EIGHT KILOGRAMS'):
            self.assertIn(attendu, colisage)
        self.assertNotIn('PACKING LIST', facture)
        self.assertNotIn('INVOICE', colisage.replace('INV NO', ''))

    def test_fiche_indique_la_methode(self):
        l = licence(parts=1)
        resultats = facture_licence.generer(l)
        self.assertEqual(facture_licence.fiche(l, resultats, [{}])['methode'], 'simple')
        self.assertEqual(facture_licence.fiche(l, resultats, [{}], 'm.docx')['methode'], 'modele')


class ReferencesFactureLicenceTest(TestCase):
    def test_lues_sur_la_licence_ib(self):
        from asydec.declarations.import_licence import extraire_champs
        texte_licence = ('10.2 Titre de transport n°      N° Facture            ORD0000013709\n'
                         '                                Date Facture           16 Juin 2025\n')
        champs = extraire_champs(texte_licence)
        self.assertEqual((champs['numero_facture'], champs['date_facture']), ('ORD0000013709', '16/06/2025'))

    def test_normalisees_et_facultatives_a_l_etape_1(self):
        from asydec.declarations.documents_finaux import references_facture
        self.assertEqual(references_facture(' ORD 0000013709 ', '16-06-2025'), ('ORD0000013709', '16/06/2025'))
        self.assertEqual(references_facture('', ''), ('', ''))
        with self.assertRaises(ValueError):
            references_facture('ORD1', '31/02/2025')
        with self.assertRaises(ValueError):
            references_facture('', '', obligatoire=True)


if __name__ == '__main__':
    main()
