import unittest
from io import BytesIO
from zipfile import ZipFile
from xml.dom import minidom
from asydec.declarations import cvi


def modele(texte):
    sortie = BytesIO()
    with ZipFile(sortie, 'w') as z:
        z.writestr('word/document.xml', '<w:document xmlns:w="'+cvi.W+'"><w:body>'+texte+'</w:body></w:document>')
        z.writestr('word/styles.xml', b'styles originaux')
        z.writestr('word/media/image1.png', b'image originale')
    return sortie.getvalue()


class TestCVI(unittest.TestCase):
    def test_zones_et_polices_et_balise_fragmentee(self):
        xml = '<w:p><w:r><w:rPr><w:rFonts w:ascii="Arial"/><w:sz w:val="20"/></w:rPr><w:t>{{NUMERO_</w:t></w:r><w:r><w:t>E}}</w:t></w:r></w:p>'
        for cle in ('NUMERO_LIQUIDATION', 'NUMERO_QUITTANCE', 'DATE_CVI'):
            xml += '<w:p><w:r><w:t>{{'+cle+'}}</w:t></w:r></w:p>'
        valeurs = dict(NUMERO_E='E 0001', NUMERO_LIQUIDATION='L 002', NUMERO_QUITTANCE='Q 3', DATE_CVI='05/11/2026')
        resultat = cvi.remplir(modele(xml), valeurs)
        with ZipFile(BytesIO(resultat)) as z:
            contenu = z.read('word/document.xml').decode()
            self.assertIn('E 0001', contenu)
            self.assertIn('w:ascii="Arial"', contenu)
            self.assertIn('w:val="20"', contenu)
            self.assertNotIn('{{', contenu)
            self.assertEqual(z.read('word/media/image1.png'), b'image originale')
            self.assertEqual(z.read('word/styles.xml'), b'styles originaux')

    def test_refuse_modele_non_prepare(self):
        with self.assertRaisesRegex(ValueError, 'non préparé'):
            cvi.remplir(modele('<w:p><w:r><w:t>E 9796</w:t></w:r></w:p>'), {})

    def test_refuse_donnee_manquante(self):
        with self.assertRaisesRegex(ValueError, 'manquante'):
            cvi.remplir(modele('<w:p><w:r><w:t>{{DATE_CVI}}</w:t></w:r></w:p>'), {})

    def test_numeros_de_la_part_sans_incrementation_supplementaire(self):
        licence = {'numero_facture': 'INV1', 'date_facture': '05/11/2026', 'numero_dec': 'DEC1'}
        part = {'numero': 2, 'informations_declaration': {'numero_e': '00125', 'numero_quittance': '46'}}
        valeurs = cvi.donnees(licence, part)
        self.assertEqual(valeurs['NUMERO_E'], 'E 00125')
        self.assertEqual(valeurs['NUMERO_QUITTANCE'], 'Q 46')
        self.assertEqual(valeurs['NUMERO_FACTURE'], 'INV1-2')

    def test_un_seul_cvi_de_la_part_1_meme_si_liste_desordonnee(self):
        from unittest.mock import patch
        licence = {'repartition': {'parts': [{'numero': 2}, {'numero': 1}]}}
        with patch.object(cvi.mise_a_jour_repartitions, 'est_a_jour', return_value=True), \
             patch.object(cvi.facture_licence, 'est_a_jour', return_value=True), \
             patch.object(cvi, 'donnees', side_effect=lambda l, p, complements=None: {'PART': str(p['numero'])}), \
             patch.object(cvi, 'remplir', return_value=b'cvi') as remplir:
            self.assertEqual(cvi.generer(licence, b'modele'), [(1, b'cvi')])
            remplir.assert_called_once_with(b'modele', {'PART': '1'}, avec_bl=True)

    def test_part_1_absente_refusee(self):
        with self.assertRaisesRegex(ValueError, 'part 1'):
            cvi.premiere_part({'repartition': {'parts': [{'numero': 2}]}})

    def test_complements_ne_peuvent_pas_ecraser_la_premiere_part(self):
        licence = {'numero_facture': 'INV1', 'date_facture': '05/11/2026'}
        part = {'numero': 1, 'fob': '1200', 'poids_kg': 23000,
                'articles': [{'designation': 'FRIPERIE', 'quantite': '12'}],
                'informations_declaration': {'numero_e': '100'}}
        v = cvi.donnees(licence, part, {'NUMERO_E': '999', 'FOB': '0', 'FRET': '10', 'ASSURANCE': '5'})
        self.assertEqual(v['NUMERO_E'], 'E 100')
        self.assertEqual(v['FOB'], '1 200,00')
        self.assertEqual(v['CIF'], '1 215,00')
        self.assertEqual(v['QUANTITE_ARTICLE'], '12,000')

    def test_references_incrementent_maximum_et_restent_stables(self):
        import tempfile
        import json
        from pathlib import Path
        from asydec.declarations import licences_ouvertes
        with tempfile.TemporaryDirectory() as dossier:
            fichier = Path(dossier)/'licences.sqlite'
            with licences_ouvertes.connexion(fichier) as conn:
                for numero, valeur, date in [('A','2026-725B-CAE-1250','2026-01-01'),
                                               ('B','2026-725B-CAE-1235','2026-02-01')]:
                    conn.execute('INSERT INTO licences VALUES (?, ?, ?)', (numero, json.dumps(
                        {'cvi_parts': {'complements': {'NUMERO_CVI': valeur}}}), date))
            licence = {'numero_validation':'NOUVELLE', 'repartition': {'parts': [{'numero': 1, 'informations_declaration': {'date_cvi': '05/11/2026'}}]}}
            proposition = cvi.proposer_complements(licence, fichier)
            self.assertEqual(proposition['NUMERO_CVI'], '2026-725B-CAE-1251')
            self.assertEqual(proposition['RAPPORT_INSPECTION'], '09899671')
            licence['cvi_parts'] = {'complements': proposition}
            self.assertEqual(cvi.proposer_complements(licence, fichier), proposition)

    def test_modele_fourni_styles_et_positions_conserves(self):
        from asydec.declarations.modele_cvi import preparer, ZONES
        from pathlib import Path
        original = cvi.modele_defaut().parent/'CVI.docx'
        if not original.is_file():
            self.skipTest('Modèle commercial privé absent')
        contenu = preparer(original.read_bytes())
        with ZipFile(BytesIO(contenu)) as z, ZipFile(original) as source:
            d = minidom.parseString(z.read('word/document.xml'))
            ancien = minidom.parseString(source.read('word/document.xml'))
            positions = {s.getAttribute('id'): s.getAttribute('style') for s in ancien.getElementsByTagName('v:shape')}
            for s in d.getElementsByTagName('v:shape'):
                self.assertEqual(s.getAttribute('style'), positions[s.getAttribute('id')])
            self.assertNotIn('BL TVS CMA CGM', d.toxml())
            self.assertNotIn('w:type="page"', d.toxml())
            self.assertNotIn('MOTOCYCLES', cvi.texte(d))
            self.assertNotIn('KINSHOP', cvi.texte(d))
            self.assertEqual(z.read('word/styles.xml'), source.read('word/styles.xml'))

    def test_modele_deux_pages_bl_sans_anciennes_donnees_et_positions_identiques(self):
        from asydec.declarations.modele_cvi import preparer
        from pathlib import Path
        original = cvi.modele_defaut().parent/'CVI.docx'
        if not original.is_file():
            self.skipTest('Modèle commercial privé absent')
        from io import BytesIO
        with ZipFile(original) as source, ZipFile(BytesIO(preparer(original.read_bytes(), inclure_bl=True))) as cible:
            doc = minidom.parseString(cible.read('word/document.xml'))
            ancien = minidom.parseString(source.read('word/document.xml'))
            self.assertEqual(len(doc.getElementsByTagName('w:br')), 1)
            positions = {s.getAttribute('id'):s.getAttribute('style') for s in ancien.getElementsByTagName('v:shape')}
            positions['Zone de texte 17'] = positions['Zone de texte 17'].replace('width:32.75pt','width:60pt')
            positions['Zone de texte 1'] = positions['Zone de texte 1'].replace('margin-left:417.1pt','margin-left:403.8pt').replace('width:63.4pt','width:90pt')
            self.assertEqual({s.getAttribute('id'):s.getAttribute('style') for s in doc.getElementsByTagName('v:shape')}, positions)
            contenu = cvi.texte(doc)
            for ancien_texte in ('G9124587','MRSU 6842391','ORD0000013709','FREIGHT AFRICA','KINSHOP','994334','AI54398465543322'):
                self.assertNotIn(ancien_texte, contenu)
            for cle in ('CONTENEUR_SCELLE_BL_1','CONTENEUR','NUMERO_BL','DATE_BL','NAVIRE_BL','POIDS_BL'):
                self.assertIn('{{'+cle+'}}', contenu)
            self.assertEqual(cible.read('word/media/image2.png'), source.read('word/media/image2.png'))
            self.assertEqual(cible.read('word/styles.xml'), source.read('word/styles.xml'))

    def test_bl_reprend_date_facture_poids_et_paire_de_la_part_1(self):
        licence = {'numero_facture': 'INV1', 'date_facture': '05/11/2026', 'date_bl': '19/08/2026',
                   'fournisseur': {'nom': 'VENDEUR', 'adresse': 'RUE 1\nVILLE'}}
        part = {'numero': 1, 'poids_kg': 23000, 'conteneur':'MRSU 1234567','scelle':'G9150001',
                'articles':[{'designation':'FRIPERIE','quantite':'123'}],
                'informations_declaration': {'numero_bl':'BL123'}}
        v = cvi.donnees(licence,part,{'AGENT_BL':'AGENT | RUE | VILLE', 'TARE_BL':'3900'})
        self.assertEqual(v['NUMERO_BL'], 'BL123')
        self.assertEqual(v['DATE_BL'], '19 AUG 2026')
        self.assertEqual(v['POIDS_BL'], '23 000.00')
        self.assertEqual(v['CONTENEUR'], 'MRSU 1234567')
        self.assertEqual(v['SCELLE'], 'G9150001')
        self.assertEqual(v['FOURNISSEUR_LIGNE_3'], 'VILLE')
        self.assertEqual(v['AGENT_BL_LIGNE_2'], 'RUE')
        self.assertEqual(v['AGENT_BL_LIGNE_4'], '')
        self.assertEqual(v['NUMERO_FACTURE'], 'INV1-1')
        self.assertEqual(v['DATE_FACTURE_BL'], '05.11.2026')


    def test_refuse_un_modele_cvi_seul_pour_generation_cvi_et_bl(self):
        champs = ('NUMERO_E','NUMERO_LIQUIDATION','NUMERO_QUITTANCE','DATE_CVI')
        contenu = modele(''.join('<w:p><w:r><w:t>{{'+c+'}}</w:t></w:r></w:p>' for c in champs))
        with self.assertRaisesRegex(ValueError, 'NUMERO_BL'):
            cvi.remplir(contenu, {c:'test' for c in champs}, avec_bl=True)

    def test_numero_voyage_trop_long_refuse_sans_reduire_police(self):
        licence = {'numero_facture': 'INV1', 'date_facture': '05/11/2026'}
        with self.assertRaisesRegex(ValueError, 'VOYAGE_BL'):
            cvi.donnees(licence, {'numero': 1}, {'VOYAGE_BL': 'X'*80})

    def test_quantite_cvi_garde_sa_colonne_avec_designation_courte(self):
        modele = cvi.modele_defaut()
        if not modele.is_file():
            self.skipTest('Modèle commercial privé absent')
        with ZipFile(modele) as archive:
            d = minidom.parseString(archive.read('word/document.xml'))
            zone = next(z for z in d.getElementsByTagName('v:shape') if z.getAttribute('id') == 'Zone de texte 49')
            self.assertIn('4320', [t.getAttribute('w:pos') for t in zone.getElementsByTagName('w:tab')])


    def test_infos_bl_preremplies_depuis_modele_et_saisies_conservees(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as dossier:
            fichier = Path(dossier)/'licences.sqlite'
            licence = {'repartition': {'parts': [{'numero': 1}]}}
            valeurs = cvi.proposer_complements(licence, fichier)
            self.assertEqual(valeurs['NAVIRE_BL'], 'OEL SHRAVAN')
            self.assertEqual(valeurs['VOYAGE_BL'], '994334')
            self.assertEqual(valeurs['PORT_CHARGEMENT_BL'], 'JEBEL ALI')
            self.assertEqual(valeurs['PORT_DECHARGEMENT_BL'], 'DAR ES SALAAM')
            self.assertEqual(valeurs['TARE_BL'], '3900')
            self.assertTrue(all(valeurs[c] for c in cvi.CHAMPS_BL))
            licence['cvi_parts'] = {'complements': {'NAVIRE_BL': 'NAVIRE MODIFIE', 'PORT_CHARGEMENT_BL': ''}}
            valeurs = cvi.proposer_complements(licence, fichier)
            self.assertEqual(valeurs['NAVIRE_BL'], 'NAVIRE MODIFIE')
            self.assertEqual(valeurs['PORT_CHARGEMENT_BL'], 'JEBEL ALI')

    def test_description_bl_uniquement_produit(self):
        from asydec.declarations.modele_cvi import preparer
        original = cvi.modele_defaut().parent/'CVI.docx'
        if not original.is_file():
            self.skipTest('Modèle commercial privé absent')
        with ZipFile(BytesIO(preparer(original.read_bytes(), inclure_bl=True))) as z:
            d = minidom.parseString(z.read('word/document.xml'))
            zone = next(s for s in d.getElementsByTagName('v:shape') if s.getAttribute('id') == 'Zone de texte 25')
            self.assertEqual(cvi.texte(zone).count('PRODUIT'), 1)
            self.assertNotIn('{{DESIGNATION}}', cvi.texte(zone))
            self.assertIn('GOODS AS PER PACKING LIST', cvi.texte(zone))
            self.assertIn('INV.NO.{{NUMERO_FACTURE_BL}}', cvi.texte(zone))
            self.assertIn('{{DESIGNATION}}', cvi.texte(d))

    def test_defaults_cvi_completent_uniquement_les_informations_absentes(self):
        import tempfile
        from pathlib import Path
        licence = {'numero_validation':'TEST', 'numero_facture':'INV1','date_facture':'05/11/2026',
                   'soussigne':{'nom':'IMPORTATEUR DU DOSSIER'}}
        part = {'numero':1,'fob':'1200','poids_kg':23000,
                'articles':[{'designation':'FRIPERIE','quantite':'12'}],
                'informations_declaration':{'origine':'JAPON','numero_e':'100'}}
        licence['repartition']={'parts':[part]}
        with tempfile.TemporaryDirectory() as dossier:
            complements = cvi.proposer_complements(licence, Path(dossier)/'base.sqlite')
        self.assertEqual(complements['ORIGINE'],'JAPON')
        self.assertEqual(complements['PROVENANCE'],'INDIA')
        self.assertEqual(complements['CONSTAT'],'TVS')
        self.assertEqual(complements['FRET'],'0,00')
        self.assertTrue(all(str(complements[c]).strip() for c in cvi.CHAMPS_COMPLEMENTAIRES))
        valeurs = cvi.donnees(licence,part,complements)
        self.assertEqual(valeurs['IMPORTATEUR'],'IMPORTATEUR DU DOSSIER')
        self.assertEqual(valeurs['ADRESSE_IMPORTATEUR'],cvi.DEFAUTS_CVI['ADRESSE_IMPORTATEUR'])
        self.assertEqual(valeurs['POSTE_ENTREE'],'KASUMBALESA FRONTIERE')
        self.assertEqual(valeurs['FOB'],'1 200,00')
        self.assertEqual(valeurs['POIDS_KG'],'23 000,00')
        self.assertEqual(valeurs['CIF'],'1 200,00')
        self.assertEqual(valeurs['NUMERO_E'],'E 100')

    def test_reservations_uniques_meme_avec_deux_formulaires_concurrents(self):
        import tempfile
        from pathlib import Path
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as dossier:
            fichier = Path(dossier)/'base.sqlite'
            licences = [{'numero_validation':n,'repartition':{'parts':[{'numero':1}]}} for n in ('A','B')]
            with ThreadPoolExecutor(max_workers=2) as executeur:
                resultats = list(executeur.map(lambda l: cvi.reserver_references(l, fichier), licences))
            for cle in cvi.REFERENCES_CVI:
                self.assertNotEqual(resultats[0][cle],resultats[1][cle])
            self.assertEqual(cvi.reserver_references(licences[0],fichier),resultats[0])
            self.assertEqual(cvi.reserver_references(licences[1],fichier),resultats[1])
            troisieme = cvi.reserver_references({'numero_validation':'C','repartition':{'parts':[{'numero':1}]}},fichier)
            self.assertEqual(troisieme['BORDEREAU'],'23')

    def test_enregistrement_refuse_reference_non_reservee(self):
        import tempfile
        from pathlib import Path
        from asydec.declarations import licences_ouvertes as registre
        from asydec.declarations.documents_finaux import preparer_licence
        with tempfile.TemporaryDirectory() as dossier:
            fichier = Path(dossier)/'base.sqlite'
            licence = preparer_licence('DEC123','1000','A','17/03/2026','INV1','17/03/2026')
            registre.enregistrer(licence,fichier)
            registre.enregistrer_repartition('A','1000',23000,fichier)
            licence = registre.charger('A',fichier)
            complements = cvi.proposer_complements(licence,fichier)
            faux = dict(complements,NUMERO_CVI='2026-725B-CAE-9999')
            fiche = dict(complements=faux,fichiers=[],empreinte=cvi.empreinte(licence,faux))
            with self.assertRaisesRegex(ValueError,'non réservée'):
                registre.enregistrer_cvi('A',fiche,fichier)
            fiche = dict(complements=complements,fichiers=[],empreinte=cvi.empreinte(licence,complements))
            registre.enregistrer_cvi('A',fiche,fichier)
            relu = registre.charger('A',fichier)
            self.assertEqual(relu['cvi_parts']['complements'],complements)
            self.assertEqual(cvi.proposer_complements(relu,fichier),complements)

    def test_une_seule_designation_premier_article_premiere_part(self):
        licence = {'numero_facture':'INV1','date_facture':'05/11/2026'}
        part = {'numero':1,'articles':[{'designation':'CHEMISES','quantite':'10'},
                                      {'designation':'CHAUSSURES','quantite':'20'}]}
        self.assertEqual(cvi.donnees(licence,part)['DESIGNATION'],'CHEMISES')
        self.assertEqual(cvi.donnees(licence,part,{'DESIGNATION':'CHEMISES ; CHAUSSURES'})['DESIGNATION'],'CHEMISES')

    def test_designation_longue_tient_sur_une_ligne_sans_changer_police(self):
        import pymupdf
        originale = 'Chapeaux et autres coiffures en bonneteries ou confectionnés à l’aide de dentelles, de feutre ou d’autres produits textiles'
        resultat = cvi.adapter_designation(originale)
        self.assertTrue(resultat.endswith('…'))
        self.assertTrue(originale.startswith(resultat[:-1]))
        self.assertLessEqual(pymupdf.get_text_length(resultat,fontname='helv',fontsize=9),174)
        self.assertNotIn('\n',resultat)
        self.assertEqual(cvi.adapter_designation('FRIPERIE'),'FRIPERIE')
        self.assertLessEqual(pymupdf.get_text_length(cvi.adapter_designation('W'*200),fontname='helv',fontsize=9),174)

    def test_bl_absent_reserve_unique_et_generation_du_modele_reussit(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as dossier:
            fichier=Path(dossier)/'base.sqlite'
            licence={'numero_validation':'A','numero_dec':'DEC123','numero_facture':'INV1','date_facture':'05/11/2026',
                     'date_bl':'19/08/2026', 'repartition':{'parts':[{'numero':1,
                     'poids_kg':23000,'plaque':'T907CUL/T543DWE','conteneur':'MRSU 8765546','scelle':'G9159034',
                     'informations_declaration':{'numero_e':'100','numero_liquidation':'200','numero_quittance':'300'}}]}}
            complements=cvi.proposer_complements(licence,fichier)
            self.assertEqual(complements['NUMERO_BL'],'E 008948900')
            self.assertEqual(cvi.proposer_complements(licence,fichier)['NUMERO_BL'],complements['NUMERO_BL'])
            valeurs=cvi.donnees(licence,cvi.premiere_part(licence),complements)
            self.assertEqual(valeurs['NUMERO_BL'],complements['NUMERO_BL'])
            autre=dict(licence,numero_validation='B')
            self.assertEqual(cvi.proposer_complements(autre,fichier)['NUMERO_BL'],'E 008948901')
            if cvi.modele_defaut().is_file():
                rempli=cvi.remplir(cvi.modele_defaut().read_bytes(),valeurs,avec_bl=True)
                with ZipFile(BytesIO(rempli)) as z:
                    texte=cvi.texte(minidom.parseString(z.read('word/document.xml')))
                    self.assertEqual(texte.count('E 008948900'),2)

    def test_bl_present_sur_licence_repris_si_absent_de_la_part(self):
        import tempfile
        from pathlib import Path
        licence={'numero_validation':'A','numero_facture':'INV1','date_facture':'05/11/2026',
                 'informations_declaration':{'numero_bl':'BL-SOURCE-123'},
                 'repartition':{'parts':[{'numero':1,'poids_kg':23000,'informations_declaration':{'numero_bl':''}}]}}
        with tempfile.TemporaryDirectory() as dossier:
            complements=cvi.proposer_complements(licence,Path(dossier)/'base.sqlite')
        self.assertEqual(complements['NUMERO_BL'],'BL-SOURCE-123')
        v=cvi.donnees(licence,cvi.premiere_part(licence),dict(complements,NUMERO_BL='AUTRE'))
        self.assertEqual(v['NUMERO_BL'],'BL-SOURCE-123')

    def test_cvi_numero_licence_complet_et_somme_des_poids_des_parts(self):
        licence={'numero_validation':'DEC1710304-ADD0-IB','numero_dec':'DEC1710304',
                 'numero_facture':'INV1','date_facture':'05/11/2026',
                 'repartition':{'poids_total_kg':999999,'parts':[
                     {'numero':1,'poids_kg':23000},{'numero':2,'poids_kg':22000},{'numero':3,'poids_kg':24000}]}}
        valeurs=cvi.donnees(licence,cvi.premiere_part(licence))
        self.assertEqual(valeurs['NUMERO_LICENCE'],'DEC1710304-ADD0-IB')
        self.assertEqual(valeurs['POIDS_GLOBAL_CVI'],'69 000,00')
        self.assertEqual(valeurs['POIDS_BL'],'69 000.00')
        if cvi.modele_defaut().is_file():
            with ZipFile(cvi.modele_defaut()) as z:
                doc=minidom.parseString(z.read('word/document.xml'))
                zones={s.getAttribute('id'):cvi.texte(s) for s in doc.getElementsByTagName('v:shape')}
                self.assertEqual(zones['Zone de texte 29'],'{{NUMERO_LICENCE}}')
                self.assertEqual(zones['Zone de texte 33'],'{{POIDS_GLOBAL_CVI}}')

    def test_poids_global_cvi_refuse_une_part_au_poids_manquant(self):
        licence={'repartition':{'parts':[{'numero':1,'poids_kg':23000},{'numero':2}]}}
        with self.assertRaisesRegex(ValueError,'chaque répartition'):
            cvi.poids_global_cvi(licence,licence['repartition']['parts'][0])

    def test_bl_liste_toutes_les_paires_et_mentions_avec_totaux(self):
        licence={'numero_validation':'LICENCE','numero_facture':'INV123','date_facture':'05/11/2026',
                 'numero_dec':'DEC123','date_bl':'19/08/2026','informations_declaration':{'numero_bl':'BL123'}}
        parts=[]
        for i, poids in enumerate((23000,22000,24000),1):
            parts.append({'numero':i,'poids_kg':poids,'conteneur':f'TEST {i:07}', 'scelle':f'SCELLE{i}',
                          'plaque':'T907CUL/T543DWE','fob':'1000',
                          'articles':[{'designation':'FRIPERIE','quantite':str(i*10)}],
                          'informations_declaration':{'numero_e':'100','numero_liquidation':'200','numero_quittance':'300'}})
        licence['repartition']={'parts':parts}
        v=cvi.donnees(licence,parts[0],{'NUMERO_CVI':'CVI123','DOSSIER_OCC':'DOS123','RAPPORT_INSPECTION':'RAP123','BORDEREAU':'21'})
        self.assertEqual(v['CONTENEUR'],'TEST 0000001')
        self.assertEqual([v[c] for c in cvi.CHAMPS_LISTE_BL][:5],
                         ['SEAL SCELLE1','TEST 0000002','SEAL SCELLE2','TEST 0000003','SEAL SCELLE3'])
        self.assertEqual(v['NOMBRE_CONTENEURS_BL'],'3')
        self.assertEqual(v['QUANTITE_BL'],'60.00')
        self.assertEqual(v['QUANTITE_BL_LETTRES'],'SIXTY')
        self.assertEqual(v['POIDS_BL'],'69 000.00')
        self.assertEqual(v['NUMERO_FACTURE_BL'],'INV123')
        if cvi.modele_defaut().is_file():
            rempli=cvi.remplir(cvi.modele_defaut().read_bytes(),v,avec_bl=True)
            with ZipFile(BytesIO(rempli)) as z:
                d=minidom.parseString(z.read('word/document.xml'))
                zones={s.getAttribute('id'):cvi.texte(s) for s in d.getElementsByTagName('v:shape')}
                self.assertIn('TEST 0000001',zones['Zone de texte 9'])
                for texte in ('SEAL SCELLE1','TEST 0000002','SEAL SCELLE2','TEST 0000003','SEAL SCELLE3'):
                    self.assertIn(texte,zones['Zone de texte 19'])
                desc=zones['Zone de texte 25']
                for texte in ('3 X 40HC CONTAINER','TOTAL 60.00 PACKAGES ONLY','TOTAL SIXTY ONLY',
                              'PRODUIT','GOODS AS PER PACKING LIST','TERMS FOB CHENNAI PORT, CHINA',
                              'INV.NO.INV123 DT. 05.11.2026'):
                    self.assertIn(texte,desc)
                self.assertNotIn('{{',cvi.texte(d))

    def test_bl_refuse_omission_scelle_ou_trop_de_conteneurs(self):
        licence={'numero_facture':'INV1','date_facture':'05/11/2026','repartition':{'parts':[
            {'numero':1,'poids_kg':23000,'conteneur':'C1','scelle':'S1'},
            {'numero':2,'poids_kg':23000,'conteneur':'C2'}]}}
        with self.assertRaisesRegex(ValueError,'répartition 2'):
            cvi.donnees(licence,cvi.premiere_part(licence))
        licence['repartition']['parts']=[{'numero':i,'poids_kg':23000,'conteneur':f'C{i}','scelle':f'S{i}'} for i in range(1,12)]
        with self.assertRaisesRegex(ValueError,'sans omission'):
            cvi.donnees(licence,cvi.premiere_part(licence))
