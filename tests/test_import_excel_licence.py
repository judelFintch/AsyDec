from datetime import date, datetime
from pathlib import Path
import tempfile
import unittest

from openpyxl import Workbook

from asydec.declarations import import_excel_licence as excel
from asydec.declarations.documents_finaux import preparer_licence


def classeur(lignes, dossier, nom='liste.xlsx'):
    wb = Workbook()
    ws = wb.active
    for ligne in lignes:
        ws.append(ligne)
    chemin = Path(dossier) / nom
    wb.save(chemin)
    return chemin


ENTETE = [None, 'Déclaration', 'Désignation Client', 'Montant Licence', 'Devise', 'Date de validation', None, "Date d'extrême validité"]


class ImportExcelLicenceTest(unittest.TestCase):
    def test_format_liste_banque(self):
        with tempfile.TemporaryDirectory() as dossier:
            chemin = classeur([[None, None, 'd.lukwesa@tmb.cd'], [], ENTETE,
                               [None, 'DEC1837831-AE0AAEDB6212-RC', 'STE KATANGA T.V.S. SARL  ', 1900000, 'USD       ', '26/10/2026', None, '24/01/2027'],
                               [None, 'DEC1834010-CC32-RC', 'STE KATANGA T.V.S. SARL', '1 500 000,50', 'USD', datetime(2026, 10, 20), None, datetime(2027, 1, 18)],
                               [None, None, None, None, None, None, None, None]], dossier)
            lignes = excel.lire_excel(chemin)
        self.assertEqual(len(lignes), 2)
        premiere, seconde = lignes
        self.assertEqual((premiere['numero_validation'], premiere['numero_dec'], premiere['montant_fob'], premiere['devise'],
                          premiere['date_validation'], premiere['date_extreme'], premiere['soussigne']),
                         ('DEC1837831-AE0AAEDB6212-RC', 'DEC1837831', '1900000', 'USD', '26/10/2026', '24/01/2027',
                          'STE KATANGA T.V.S. SARL'))
        self.assertEqual((seconde['montant_fob'], seconde['date_validation'], seconde['date_extreme']),
                         ('1500000.50', '20/10/2026', '18/01/2027'))
        valeurs = excel.valeurs_formulaire(premiere)
        self.assertEqual(valeurs['soussigne'], {'nom': 'STE KATANGA T.V.S. SARL'})
        licence = preparer_licence(**{c: valeurs[c] for c in ('numero_dec', 'montant_fob', 'numero_validation', 'date_validation')})
        self.assertEqual(licence['numero_dec'], 'DEC1837831')

    def test_expiree_et_numero_dec(self):
        self.assertTrue(excel.expiree({'date_extreme': '10/06/2019'}, date(2026, 11, 5)))
        self.assertFalse(excel.expiree({'date_extreme': '24/01/2027'}, date(2026, 11, 5)))
        self.assertFalse(excel.expiree({'date_extreme': ''}))
        self.assertEqual(excel.numero_dec('DEC1710304-ADD0-IB'), 'DEC1710304')
        self.assertEqual(excel.numero_dec('XYZ'), '')

    def test_fichiers_refuses(self):
        with tempfile.TemporaryDirectory() as dossier:
            with self.assertRaisesRegex(ValueError, 'Aucune licence'):
                excel.lire_excel(classeur([['Nom', 'Prix'], ['A', 1]], dossier))
            with self.assertRaisesRegex(ValueError, '.xlsx'):
                excel.lire_excel(Path(dossier) / 'ancien.xls')
            faux = Path(dossier) / 'faux.xlsx'
            faux.write_text('pas un classeur')
            with self.assertRaisesRegex(ValueError, 'illisible'):
                excel.lire_excel(faux)


class OuvrirPlusieursTest(unittest.TestCase):
    def test_ouvre_toutes_sans_ecraser_ni_bloquer(self):
        from asydec.declarations import licences_ouvertes as registre
        ligne = lambda numero, date_validation, devise='USD': dict(
            numero_validation=numero, numero_dec=excel.numero_dec(numero), montant_fob='1500000',
            date_validation=date_validation, devise=devise, date_extreme='', soussigne='STE KATANGA T.V.S. SARL')
        with tempfile.TemporaryDirectory() as dossier:
            fichier = Path(dossier) / 'licences.sqlite'
            existante = preparer_licence('DEC1834010', '999', 'DEC1834010-CC32-RC', '20/10/2026')
            registre.enregistrer(existante, fichier)
            lignes = [ligne('DEC1837831-AE0AAEDB6212-RC', '26/10/2026'), ligne('DEC1834010-CC32-RC', '20/10/2026'),
                      ligne('DEC1803895-4338-RC', '31/08/2026'), ligne('DEC1000001-AAAA-RC', '01/11/2026'),
                      ligne('DEC1000002-BBBB-RC', '26/10/2026', 'EUR')]
            ouvertes, ignorees, erreurs = excel.ouvrir_plusieurs(lignes, fichier)
            self.assertEqual(ouvertes, ['DEC1837831-AE0AAEDB6212-RC', 'DEC1803895-4338-RC'])
            self.assertEqual(ignorees, ['DEC1834010-CC32-RC'])
            self.assertEqual([n for n, _ in erreurs], ['DEC1000001-AAAA-RC', 'DEC1000002-BBBB-RC'])  # dimanche, EUR
            licence = registre.charger('DEC1837831-AE0AAEDB6212-RC', fichier)
            self.assertEqual((licence['numero_dec'], licence['soussigne']['nom'], licence['date_validation']),
                             ('DEC1837831', 'STE KATANGA T.V.S. SARL', '26/10/2026'))
            self.assertEqual(str(registre.charger('DEC1834010-CC32-RC', fichier)['montant_fob']), '999')  # non écrasée


class ReprisesExistantesTest(unittest.TestCase):
    def test_importateur_et_fournisseur_repris(self):
        from asydec.declarations import licences_ouvertes as registre
        importateur = {'nom': 'ETS KATANGA TVS (CLT1064118)', 'adresse': 'AVENUE INDUSTRIELLE 2580', 'telephone': '997700700',
                       'identifiants': 'N° Impôt : A2220284Y'}
        fournisseurs = [{'nom': 'YIWU SKY TRADING COMPANY', 'adresse': 'YIWU'}, {'nom': 'KINSHOP GENERAL TRADING FZE', 'adresse': 'AJMAN'}]
        with tempfile.TemporaryDirectory() as dossier:
            fichier = Path(dossier) / 'licences.sqlite'
            for numero, f in (('DEC1710304-ADD0-IB', fournisseurs[0]), ('DEC1600886-4B1F-IB', fournisseurs[1])):
                licence = preparer_licence(numero[:10], '1000', numero, '17/03/2026')
                licence.update(soussigne=dict(importateur, email=''), fournisseur=f)
                registre.enregistrer(licence, fichier)
            importateurs, sources_f = excel.sources_existantes(fichier)
            self.assertEqual(len(importateurs), 1)  # même importateur sur les deux licences : une seule proposition
            self.assertEqual(importateurs[0]['coordonnees'], importateur)  # champs vides ignorés
            self.assertIn('(+1)', importateurs[0]['libelle'])
            self.assertEqual(sorted(s['coordonnees']['nom'] for s in sources_f), sorted(f['nom'] for f in fournisseurs))
            ligne = dict(numero_validation='DEC1837831-AE0AAEDB6212-RC', numero_dec='DEC1837831', montant_fob='1900000',
                         date_validation='26/10/2026', devise='USD', date_extreme='', soussigne='STE KATANGA T.V.S. SARL')
            valeurs = excel.valeurs_formulaire(ligne, importateur, fournisseurs[1])
            self.assertEqual((valeurs['soussigne'], valeurs['fournisseur']), (importateur, fournisseurs[1]))
            valeurs['soussigne']['nom'] = 'modifié'
            self.assertEqual(importateur['nom'], 'ETS KATANGA TVS (CLT1064118)')  # copie, pas la source
            self.assertEqual(excel.valeurs_formulaire(ligne)['soussigne'], {'nom': 'STE KATANGA T.V.S. SARL'})
            ouvertes, _, _ = excel.ouvrir_plusieurs([ligne], fichier, importateur, fournisseurs[0])
            relu = registre.charger(ouvertes[0], fichier)
            self.assertEqual((relu['soussigne'], relu['fournisseur']), (importateur, fournisseurs[0]))
