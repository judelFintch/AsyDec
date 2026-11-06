import copy
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from asydec.declarations import xml_licence as service


def champ(racine, chemin, texte='ANCIEN DOSSIER'):
    courant = racine
    for balise in chemin.split('/'):
        enfant = courant.find(balise)
        if enfant is None:
            enfant = ET.SubElement(courant, balise)
        courant = enfant
    courant.text = texte


class XmlLicenceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.racine = Path(self.temp.name)
        self.modele = self.racine/'modele.xml'
        r = ET.Element('ASYCUDA')
        for chemin in ('Property/Nbers/Total_number_of_items', 'Property/Nbers/Total_number_of_packages',
                'Valuation/Gs_Invoice/Currency_code', 'Valuation/Gs_Invoice/Amount_foreign_currency',
                'Valuation/Gs_Invoice/Currency_rate', 'Valuation/Total/Total_invoice',
                'Traders/Consignee/Consignee_code', 'Traders/Consignee/Consignee_name',
                'Traders/Exporter/Exporter_name', 'General_information/Comments_free_text',
                'Identification/Registration/Number', 'Financial/Amounts/Totals_taxes'):
            champ(r, chemin)
        for chemin in ('Tarification/HScode/Commodity_code', 'Tarification/HScode/Precision_1',
                       'Tarification/Item_price', 'Tarification/Supplementary_unit/Suppplementary_unit_name',
                       'Tarification/Supplementary_unit/Suppplementary_unit_quantity',
                       'Goods_description/Description_of_goods', 'Goods_description/Commercial_Description',
                       'Goods_description/Country_of_origin_code', 'Licence_number', 'Free_text_1',
                       'Valuation_item/Item_Invoice/Amount_foreign_currency',
                       'Valuation_item/Item_Invoice/Currency_code', 'Taxation/Taxation_line/Duty_tax_rate'):
            champ(r, 'Item/'+chemin)
        ET.ElementTree(r).write(self.modele)
        self.licence = dict(numero_validation='DEC123-ADD0-IB', numero_dec='DEC123', montant_fob='30',
                            date_validation='17/03/2026', date_bl='2026-03-20',
                            soussigne={'nom':'Import & Co', 'identifiants':'N° Impôt : A123'},
                            fournisseur={'nom':'Exportateur', 'adresse':'Adresse complète'},
                            produits=[dict(tarif_douanier='6505000000',designation='Chapeaux\nTextile',
                                           pays_origine='China',quantite='10',prix_unitaire='3',unite='Unite(Piece)',devise='USD')])

    def test_pre_remplissage_sans_recopier_ancien_dossier(self):
        avant = self.modele.read_bytes()
        arbre = service.preparer(self.licence, self.modele)
        r = arbre.getroot()
        self.assertNotIn('ANCIEN DOSSIER', ET.tostring(r,encoding='unicode'))
        self.assertEqual(self.modele.read_bytes(), avant)
        self.assertEqual(r.findtext('Traders/Consignee/Consignee_code'), 'A123')
        self.assertEqual(r.findtext('Traders/Financial/Financial_name'), 'Import & Co\nN° Impôt : A123')
        self.assertEqual(r.findtext('Item/Tarification/HScode/Commodity_code'), '65050000')
        self.assertEqual(r.findtext('Item/Tarification/HScode/Precision_1'), '00')
        self.assertEqual(r.findtext('Item/Licence_number'), 'DEC123-ADD0-IB')
        self.assertEqual(r.findtext('Item/Goods_description/Description_of_goods'), 'Chapeaux\nTextile')
        self.assertEqual(r.findtext('Item/Tarification/Item_price'), '30.00')
        self.assertIn('China',r.findtext('Item/Free_text_1'))
        self.assertIn('20/03/2026',r.findtext('General_information/Comments_free_text'))
        self.assertFalse(r.findtext('Valuation/Gs_Invoice/Currency_rate'))
        self.assertFalse(r.findtext('Financial/Amounts/Totals_taxes'))

    def test_nombre_articles_variable_et_articles_identiques_conserves(self):
        self.licence['produits'] *= 17
        self.licence['montant_fob']='510'
        r=service.preparer(self.licence,self.modele).getroot()
        self.assertEqual(len(r.findall('Item')),17)
        self.assertEqual(r.findtext('Property/Nbers/Total_number_of_items'),'17')

    def test_ambiguite_et_incoherence_refusees(self):
        for cle,valeur in [('montant_fob','31'),('nombre_produits_attendu',2),('produits',[])]:
            licence=copy.deepcopy(self.licence)
            licence[cle]=valeur
            with self.subTest(cle=cle), self.assertRaises(ValueError):
                service.preparer(licence,self.modele)
        for cle,valeur in [('quantite','NaN'),('devise',''),('tarif_douanier','123')]:
            licence=copy.deepcopy(self.licence)
            licence['produits'][0][cle]=valeur
            with self.subTest(cle=cle), self.assertRaises(ValueError):
                service.preparer(licence,self.modele)

    def test_export_sans_ecrasement_et_xml_reanalysable(self):
        from asydec.declarations import mise_a_jour_repartitions
        self.licence['repartition']={'parts':[{'numero':1,'fob':'30','poids_kg':23000,'plaque':'T171EAK/T196EAK',
                                               'articles':[{'quantite':'10','valeur':'30.00'}]}]}
        self.licence['informations_declaration']=dict(numero_e='100',numero_liquidation='200',numero_quittance='300')
        r=ET.parse(self.modele).getroot()
        champ(r,'Identification/Assessment/Number')
        champ(r,'Identification/receipt/Number')
        ET.ElementTree(r).write(self.modele)
        mise_a_jour_repartitions.appliquer(self.licence)
        destination=self.racine/'licence.xml'
        service.exporter(self.licence,self.modele,destination)
        ET.parse(destination)
        avant=destination.read_bytes()
        with self.assertRaises(FileExistsError):
            service.exporter(self.licence,self.modele,destination)
        self.assertEqual(destination.read_bytes(),avant)
        self.assertFalse(list(self.racine.glob('.asydec-*')))
        with self.assertRaises(ValueError):
            service.exporter(self.licence,self.modele,self.modele)

    def test_informations_declaration_reprises_dans_xml(self):
        r=ET.parse(self.modele).getroot()
        for chemin in ('Declarant/Reference/Number','Property/Date_of_declaration',
                       'Identification/Office_segment/Customs_clearance_office_code',
                       'Transport/Means_of_transport/Departure_arrival_information/Identity'):
            champ(r,chemin)
        ET.ElementTree(r).write(self.modele)
        self.licence['informations_declaration'] = dict(reference='REF/123', date_declaration='05/11/2026',
                                                       bureau_code='CODE', plaque='ABC123',numero_bl='BL-42',observations='Test déclaration')
        r=service.preparer(self.licence,self.modele).getroot()
        self.assertEqual(r.findtext('Declarant/Reference/Number'),'REF/123')
        self.assertEqual(r.findtext('Property/Date_of_declaration'),'11/05/26')
        self.assertEqual(r.findtext('Transport/Means_of_transport/Departure_arrival_information/Identity'),'ABC123')
        self.assertIn('BL-42',r.findtext('General_information/Comments_free_text'))

    def test_numeros_et_dates_e_liquidation_quittance(self):
        r=ET.parse(self.modele).getroot()
        for chemin in ('Identification/Registration/Date', 'Identification/Assessment/Number',
                       'Identification/Assessment/Date','Identification/receipt/Number','Identification/receipt/Date'):
            champ(r,chemin)
        ET.ElementTree(r).write(self.modele)
        self.licence['informations_declaration']=dict(numero_e='123',date_enregistrement='03/06/2026',
            numero_liquidation='456',date_liquidation='05/06/2026',numero_quittance='789',date_quittance='05/06/2026')
        r=service.preparer(self.licence,self.modele).getroot()
        self.assertEqual(r.findtext('Identification/Registration/Number'),'123')
        self.assertEqual(r.findtext('Identification/Registration/Date'),'06/03/26')
        self.assertEqual(r.findtext('Identification/Assessment/Number'),'456')
        self.assertEqual(r.findtext('Identification/Assessment/Date'),'06/05/26')
        self.assertEqual(r.findtext('Identification/receipt/Number'),'789')
        self.assertEqual(r.findtext('Identification/receipt/Date'),'06/05/26')

    def test_export_de_la_premiere_part_seulement(self):
        from asydec.declarations import mise_a_jour_repartitions, repartition_licence
        r=ET.parse(self.modele).getroot()
        for chemin in ('Identification/Assessment/Number','Identification/receipt/Number','Identification/Manifest_reference_number',
                       'Transport/Means_of_transport/Departure_arrival_information/Identity'):
            champ(r,chemin)
        ET.ElementTree(r).write(self.modele)
        self.licence['produits']=[dict(self.licence['produits'][0],quantite='60000',prix_unitaire='3'),
                                  dict(self.licence['produits'][0],quantite='1001',prix_unitaire='2')]
        self.licence['montant_fob']='182002'
        self.licence['repartition']=repartition_licence.preparer('182002',23000,self.licence['produits'])
        for i,part in enumerate(self.licence['repartition']['parts']):
            part['plaque']=f'T17{i}EAK/T19{i}EAK'
        self.licence['informations_declaration']=dict(numero_e='100',numero_liquidation='200',numero_quittance='300',manifeste='2026 7644')
        mise_a_jour_repartitions.appliquer(self.licence)
        destination=self.racine/'part1.xml'
        service.exporter(self.licence,self.modele,destination)
        x=ET.parse(destination).getroot()
        part=self.licence['repartition']['parts'][0]
        self.assertEqual(len(self.licence['repartition']['parts']),2)
        self.assertEqual(x.findtext('Valuation/Gs_Invoice/Amount_foreign_currency'),part['fob'])
        self.assertEqual([i.findtext('Tarification/Supplementary_unit/Suppplementary_unit_quantity') for i in x.findall('Item')],['30000','501'])
        self.assertEqual(x.findtext('Identification/Registration/Number'),'100')
        self.assertEqual(x.findtext('Identification/Manifest_reference_number'),'2026 7644')
        self.assertEqual(x.findtext('Transport/Means_of_transport/Departure_arrival_information/Identity'),'T170EAK/T190EAK')
        self.assertIn('Part 1 sur 2',x.findtext('General_information/Comments_free_text'))


class XmlParPartDifferenteTest(XmlLicenceTest):
    def test_un_xml_par_montant_de_part_different(self):
        from asydec.declarations import mise_a_jour_repartitions, repartition_licence
        r=ET.parse(self.modele).getroot()
        for chemin in ('Identification/Assessment/Number','Identification/receipt/Number'):
            champ(r,chemin)
        ET.ElementTree(r).write(self.modele)
        # 1 425,212 motos à 701,65 sur 10 parts (cas DEC0679470) : parts de montants différents.
        self.licence['produits']=[dict(self.licence['produits'][0],quantite='1425.212',prix_unitaire='701.65')]
        self.licence['montant_fob']='1000000'
        self.licence['repartition']=repartition_licence.preparer('1000000',23000,self.licence['produits'],nombre=10,plafond=False)
        self.licence['informations_declaration']=dict(numero_e='100',numero_liquidation='200',numero_quittance='300')
        mise_a_jour_repartitions.appliquer(self.licence)
        parts=self.licence['repartition']['parts']
        groupes=service.groupes_parts(self.licence)
        self.assertEqual(sorted(n for g in groupes for n in g['numeros']),list(range(1,11)))
        self.assertEqual(len(groupes),len({p['fob'] for p in parts}))  # ici, même FOB = mêmes quantités
        self.assertGreater(len(groupes),1)
        self.assertLess(len(groupes),10)
        self.assertEqual(groupes[0]['numeros'][0],1)
        for i,vue in enumerate(service.vues_a_generer(self.licence)):
            destination=self.racine/f'g{i}.xml'
            service.exporter(self.licence,self.modele,destination,vue)
            x=ET.parse(destination).getroot()
            part=next(p for p in parts if p['numero']==vue['part_generee']['numero'])
            self.assertEqual(x.findtext('Valuation/Gs_Invoice/Amount_foreign_currency'),part['fob'])
            self.assertEqual(x.findtext('Identification/Registration/Number'),part['informations_declaration']['numero_e'])
            if len(vue['part_generee']['identiques'])>1:
                self.assertIn('Même montant et mêmes quantités pour les parts',x.findtext('General_information/Comments_free_text'))
        self.assertEqual(service.libelle_parts([1]),'part 1')
        self.assertEqual(service.libelle_parts([1,2,4]),'parts 1-2-4')


class PropositionModeleTest(XmlLicenceTest):
    def licence_repartie(self):
        from asydec.declarations import mise_a_jour_repartitions, repartition_licence
        self.licence['repartition'] = repartition_licence.preparer('30', 23000, self.licence['produits'])
        self.licence['informations_declaration'] = dict(numero_e='100', numero_liquidation='200', numero_quittance='300')
        mise_a_jour_repartitions.appliquer(self.licence)
        return self.licence

    def test_modele_compatible_propose_et_modele_retenu_en_premier(self):
        from unittest.mock import patch
        from asydec.systeme import espace_travail
        locaux = self.racine / 'locaux'
        locaux.mkdir()
        (locaux / 'casse.xml').write_text('<pas-asycuda/>')
        bon = locaux / 'bon.xml'
        r = ET.parse(self.modele).getroot()
        champ(r, 'Identification/Assessment/Number')
        champ(r, 'Identification/receipt/Number')
        ET.ElementTree(r).write(bon)
        (locaux / 'incomplet.xml').write_bytes(self.modele.read_bytes())  # sans champs liquidation et Q : refusé
        licence = self.licence_repartie()
        with patch('asydec.chemins.MODELES_XML', locaux), patch('asydec.chemins.XML_LICENCES', self.racine / 'aucune'), \
                patch.object(espace_travail, 'racine', lambda fichier=None: None):
            self.assertEqual(service.proposer_modele(licence), bon)
            licence['modele_structure'] = str(self.modele)
            self.assertEqual(service.candidats_modele(licence)[0], self.modele)
            self.assertEqual(service.proposer_modele(licence), bon)  # retenu mais incompatible : suivant
            (locaux / 'bon.xml').unlink()
            licence.pop('modele_structure')
            self.assertIsNone(service.proposer_modele(licence))

    def test_apercu_part_1(self):
        lignes, produits = service.apercu(self.licence_repartie())
        valeurs = dict(lignes)
        self.assertEqual(valeurs['Part générée'], 'Part 1 sur 1')
        self.assertEqual(valeurs['Numéro E'], '100')
        self.assertEqual(len(produits), 1)


BASE_TVS = Path(__file__).resolve().parent.parent / 'XML_LICENCES' / 'PARTIE TVS2.xml'


@unittest.skipUnless(BASE_TVS.is_file(), 'déclaration réelle TVS absente')
class XmlCompletTest(XmlLicenceTest):
    def test_xml_complet_depuis_vraie_declaration(self):
        import shutil
        from unittest.mock import patch
        from asydec.declarations import mise_a_jour_repartitions, repartition_licence
        dossier = self.racine / 'XML_LICENCES'
        dossier.mkdir()
        base = dossier / 'base.xml'
        shutil.copy(BASE_TVS, base)
        self.licence['produits'] = [dict(self.licence['produits'][0], tarif_douanier='8711100000', designation='Motocycles',
                                         pays_origine='India', quantite='1425.212', prix_unitaire='701.65')]
        self.licence['montant_fob'] = '1000000'
        self.licence.update(numero_facture='INV1023', date_facture='12/06/2026')
        self.licence['repartition'] = repartition_licence.preparer('1000000', 23000, self.licence['produits'], nombre=10, plafond=False)
        for i, p in enumerate(self.licence['repartition']['parts']):
            p['plaque'] = f'T17{i}EAK/T19{i}EAK'
        self.licence['informations_declaration'] = dict(numero_e='100', numero_liquidation='200', numero_quittance='300',
                                                        manifeste='2026 7644')
        mise_a_jour_repartitions.appliquer(self.licence)
        with patch('asydec.chemins.XML_LICENCES', dossier):
            self.assertEqual(service.proposer_modele(self.licence), base)
            vue = service.vues_a_generer(self.licence)[0]
            x = service.preparer(vue, base).getroot()
        part = self.licence['repartition']['parts'][0]
        t = lambda c: x.findtext(c)
        # Gardés de la vraie déclaration
        self.assertEqual(t('Identification/Office_segment/Customs_clearance_office_code'), '725B')
        self.assertEqual(t('Declarant/Declarant_code'), '000313')
        self.assertEqual(t('Financial/Bank/Code'), '8430')
        self.assertEqual(t('Valuation/Gs_Invoice/Currency_rate'), '2262.32')
        # Remplacés par la part
        self.assertEqual(t('Valuation/Gs_Invoice/Amount_foreign_currency'), part['fob'])
        self.assertEqual(t('Valuation/Total/Total_weight'), '23000')
        self.assertEqual(t('Identification/Registration/Number'), '100')
        self.assertEqual(t('Identification/Manifest_reference_number'), '2026 7644')
        self.assertEqual(t('Transport/Means_of_transport/Border_information/Identity'), 'T170EAK/T190EAK')
        self.assertIn('Import & Co', t('Traders/Consignee/Consignee_name'))
        self.assertEqual(t('Item/Tarification/HScode/Commodity_code'), '87111000')
        self.assertEqual(t('Item/Goods_description/Country_of_origin_code'), 'IN')
        self.assertEqual(t('Item/Licence_number'), 'DEC123-ADD0-IB')
        self.assertEqual(t('Item/Tarification/Supplementary_unit/Suppplementary_unit_quantity'), part['articles'][0]['quantite'])
        fcm = next(d for d in x.iter('Attached_documents') if d.findtext('Attached_document_code') == 'FCM')
        self.assertEqual(fcm.findtext('Attached_document_reference'), 'INV1023-1')
        # Rien de l'ancien dossier
        texte = ET.tostring(x, encoding='unicode')
        self.assertEqual(len(x.findall('Item')), 1)  # seuls les articles de la licence
        for ancien in ('KATANGA TVS SARL', 'SAN-LG', '10632', 'T281BMW', '2020099972', '25-013-0000146726',
                       '87141000', 'Parties et accessoires'):
            self.assertNotIn(ancien, texte)
        # Taxes recalculées (CIF > 0, total = articles + globales)
        self.assertGreater(int(t('Financial/Amounts/Totals_taxes')), int(t('Item/Taxation/Item_taxes_amount')))


class AjoutBaseLicenceTest(XmlLicenceTest):
    def test_ajout_d_une_declaration_reelle(self):
        from unittest.mock import patch
        dossier = self.racine / 'XML_LICENCES'
        r = ET.parse(self.modele).getroot()
        champ(r, 'Valuation/Gs_Invoice/Currency_rate', '2267')
        reelle = self.racine / 'reelle.xml'
        ET.ElementTree(r).write(reelle)
        with patch('asydec.chemins.XML_LICENCES', dossier):
            copie = service.ajouter_base_licence(reelle)
            self.assertEqual(copie, dossier / 'reelle.xml')
            self.assertEqual(service.bases_licence(), [copie])
            self.assertEqual(service.ajouter_base_licence(reelle).name, 'reelle (2).xml')  # jamais écrasée
            (self.racine / 'autre.xml').write_text('<AUTRE/>')
            with self.assertRaises(ValueError):
                service.ajouter_base_licence(self.racine / 'autre.xml')
