"""Dossier de travail : organisation, rangement des fichiers produits et des fichiers existants."""
from datetime import date
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

from asydec import chemins
from asydec.declarations import generer
from asydec.declarations import rangement_existants as R
from asydec.systeme import espace_travail as E
from tests.test_detection_reelles import variante
from tests import test_modeles_generes as TM


class EspaceTest(unittest.TestCase):
    """Configuration et anciens dossiers temporaires : rien n'est lu ni écrit chez l'utilisateur."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.temp = Path(temp.name)
        self.ancien = self.temp / 'DEC'
        self.ancien.mkdir()
        self.travail = self.temp / 'Documents' / 'AsyDec'
        patchers = [patch.object(E, 'FICHIER', self.temp / 'config' / 'espace_travail.json'),
                    patch.object(generer, 'DEC', str(self.ancien))]
        for p in patchers:
            p.start()
            self.addCleanup(p.stop)


class ChoixTest(EspaceTest):
    def test_sans_choix_ancienne_organisation(self):
        self.assertIsNone(E.racine())
        self.assertEqual(Path(generer.dossier_rangement('SOCIETE K.D.META', 'historique')),
                         self.ancien / 'KDMETA' / '1 - HISTORIQUE')
        self.assertIsNone(E.dossier_rapports())
        self.assertEqual(E.options_rapport(), {})

    def test_definir_cree_l_arborescence(self):
        racine = E.definir(self.travail)
        self.assertEqual(E.racine(), racine)
        for nom in E.DOSSIERS + ('LISEZMOI.txt',):
            self.assertTrue((racine / nom).exists(), nom)
        E.definir(self.travail)  # à nouveau : rien n'est effacé ni dupliqué
        self.assertEqual(sorted(p.name for p in racine.iterdir()), sorted(E.DOSSIERS + ('LISEZMOI.txt',)))

    def test_migration_de_l_ancienne_organisation(self):
        ancien = self.travail / '1 - IMPORTATEURS' / 'KDMETA' / '3 - XML VALIDES'
        ancien.mkdir(parents=True)
        (ancien / 'a.xml').write_text('<ASYCUDA/>')
        (self.travail / '2 - RAPPORTS' / '2026-11').mkdir(parents=True)
        (self.travail / '4 - SAUVEGARDES').mkdir()
        (self.travail / 'LISEZMOI.txt').write_text('AsyDec — dossier de travail\nancien', encoding='utf-8')
        ancien_chemin = str(ancien / 'a.xml')
        racine = E.definir(self.travail)
        nouveau = racine / E.FRIPERIE / 'KDMETA' / '3 - XML VALIDES' / 'a.xml'
        self.assertTrue(nouveau.is_file())
        self.assertFalse((racine / '1 - IMPORTATEURS').exists())
        self.assertTrue((racine / E.RAPPORTS / '2026-11').is_dir())
        self.assertEqual(sorted(p.name for p in racine.iterdir()), sorted(E.DOSSIERS + ('LISEZMOI.txt',)))
        self.assertIn('3 - DOCUMENTS FINAUX', (racine / 'LISEZMOI.txt').read_text(encoding='utf-8'))
        # Chemin enregistré avant la migration : retrouvé au nouvel emplacement.
        self.assertEqual(Path(E.chemin_actuel(ancien_chemin)).resolve(), nouveau.resolve())
        self.assertEqual(E.chemin_actuel('/nulle/part/1 - IMPORTATEURS/x.xml'), '/nulle/part/1 - IMPORTATEURS/x.xml')

    def test_migration_sans_ecraser_en_cas_de_conflit(self):
        (self.travail / '1 - IMPORTATEURS' / 'KDMETA').mkdir(parents=True)
        (self.travail / '1 - IMPORTATEURS' / 'AUTRE').mkdir()
        (self.travail / E.FRIPERIE / 'KDMETA').mkdir(parents=True)
        resultat = E.migrer(self.travail)
        self.assertEqual([c.name for c in resultat['conflits']], ['KDMETA'])
        self.assertTrue((self.travail / E.FRIPERIE / 'AUTRE').is_dir())
        self.assertTrue((self.travail / '1 - IMPORTATEURS' / 'KDMETA').is_dir())

    def test_rangement_par_module_et_dossier_dec(self):
        racine = E.definir(self.travail)
        self.addCleanup(E.definir_module, 'friperie')
        E.definir_module('divers')
        self.assertEqual(Path(generer.dossier_rangement('SOCIETE K.D.META', 'pdf')), racine / E.DIVERS / 'KDMETA' / '5 - PDF')
        E.definir_module('friperie')
        self.assertEqual(Path(generer.dossier_rangement('SOCIETE K.D.META', 'pdf')), racine / E.FRIPERIE / 'KDMETA' / '5 - PDF')
        dossier = E.dossier_dec('DEC1710304')
        self.assertEqual(dossier, racine / E.DOCUMENTS_FINAUX / 'DEC1710304')
        self.assertEqual(sorted(p.name for p in dossier.iterdir()), sorted(E.RANGEMENT_DEC.values()))
        source = self.temp / 'licence.pdf'
        source.write_bytes(b'%PDF')
        range = E.ranger_dans_dec(source, 'DEC1710304', 'licence')
        self.assertEqual(range, dossier / '1 - LICENCE' / 'licence.pdf')
        self.assertEqual(E.ranger_dans_dec(source, 'DEC1710304', 'licence'), range)  # pas de doublon
        self.assertRaises(ValueError, E.dossier_dec, '  ')

    def test_dossier_du_logiciel_refuse(self):
        self.assertRaisesRegex(ValueError, 'en dehors du logiciel', E.definir, chemins.RACINE / 'travail')
        self.assertIsNone(E.racine())

    def test_rangement_par_importateur_et_par_type(self):
        racine = E.definir(self.travail)
        for cle, nom in E.RANGEMENT.items():
            self.assertEqual(Path(generer.dossier_rangement('SOCIETE K.D.META', cle)),
                             racine / E.IMPORTATEURS / 'KDMETA' / nom)
        self.assertEqual(E.dossier_rapports(jour=date(2026, 11, 3)), racine / E.RAPPORTS / '2026-11')
        self.assertEqual(E.options_rapport(), {'initialdir': str(racine / E.RAPPORTS / f'{date.today():%Y-%m}')})
        self.assertRaises(ValueError, E.dossier_importateur, 'KDMETA', 'inconnu')

    def test_copie_rangee_sans_doublon_ni_ecrasement(self):
        racine = E.definir(self.travail)
        recu = self.temp / 'Téléchargements' / 'T1.xml'
        recu.parent.mkdir()
        recu.write_bytes(b'<a/>')
        range = Path(generer.ranger_fichier(recu, 'SOCIETE K.D.META', 'reelles'))
        self.assertEqual(range, racine / E.IMPORTATEURS / 'KDMETA' / '4 - DECLARATIONS REELLES' / 'T1.xml')
        self.assertEqual(Path(generer.ranger_fichier(recu, 'SOCIETE K.D.META', 'reelles')), range)  # déjà là
        self.assertEqual(Path(generer.ranger_fichier(range, 'SOCIETE K.D.META', 'reelles')), range)  # dans l'espace
        recu.write_bytes(b'<b/>')  # même nom, autre contenu : jamais écrasé
        self.assertEqual(Path(generer.ranger_fichier(recu, 'SOCIETE K.D.META', 'reelles')).name, 'T1 (2).xml')
        self.assertEqual(range.read_bytes(), b'<a/>')
        self.assertTrue(recu.exists())  # l'original reste en place
        interne = chemins.RACINE / 'asydec' / '__init__.py'  # fichier du logiciel : jamais copié
        self.assertEqual(Path(generer.ranger_fichier(interne, 'SOCIETE K.D.META', 'sources')), interne)

    def test_numerotation_continue_apres_changement(self):
        E.definir(self.travail)
        ancien = self.ancien / 'KDMETA' / '1 - HISTORIQUE'
        ancien.mkdir(parents=True)
        (ancien / 'KDMETA 7600USD 20800KG 07.xml').write_bytes(b'<a/>')
        self.assertEqual(generer.numero_suivant('KDMETA'), 8)
        nouveau = Path(generer.dossier_rangement('SOCIETE K.D.META', 'historique'))
        (nouveau / 'KDMETA 7600USD 20800KG 09.xml').write_bytes(b'<a/>')
        self.assertEqual(generer.numero_suivant('KDMETA'), 10)

    def test_base_cherchee_d_abord_dans_le_dossier_de_travail(self):
        E.definir(self.travail)
        for dossier in (self.ancien / 'KDMETA' / '2 - VOS FICHIERS (bases et SYDONIA)',
                        Path(generer.dossier_rangement('SOCIETE K.D.META', 'sources'))):
            dossier.mkdir(parents=True, exist_ok=True)
            (dossier / 'base.xml').write_bytes(b'<a/>')
        self.assertTrue(E.dans_espace(generer.trouver_base('base.xml')))
        self.assertEqual(E.relatif(generer.trouver_base('base.xml')),
                         str(Path(E.IMPORTATEURS) / 'KDMETA' / '1 - BASES SYDONIA' / 'base.xml'))


class RangementExistantsTest(EspaceTest):
    def setUp(self):
        super().setUp()
        TM.ModelesGeneresTest.setUp(self)  # base de modèles temporaire et XML de test
        self.base_modeles = self.base
        kd = self.ancien / 'KDMETA'
        for nom in ('1 - HISTORIQUE', '2 - VOS FICHIERS (bases et SYDONIA)', '5 - PDF'):
            (kd / nom).mkdir(parents=True)
        (kd / '1 - HISTORIQUE' / 'KDMETA 175USD 150KG 01.xml').write_bytes(self.xml)
        # Même numéro d'enregistrement que la déclaration générée : gabarit, pas déclaration réelle.
        gabarit = variante(self.xml, 12, poids=99, date='10/1/26')
        (kd / '2 - VOS FICHIERS (bases et SYDONIA)' / 'base.xml').write_bytes(gabarit)
        (kd / '2 - VOS FICHIERS (bases et SYDONIA)' / 'base copie.xml').write_bytes(gabarit)
        (kd / '5 - PDF' / 'modele.pdf').write_bytes(b'%PDF modele')
        (self.ancien / 'COMPARAISON').mkdir()
        (self.ancien / 'COMPARAISON' / 'T1.xml').write_bytes(variante(self.xml, 500, camion='T1/T2'))
        (self.ancien / 'divers.pdf').write_bytes(b'%PDF divers')
        (self.ancien / 'casse.xml').write_bytes(b'pas du xml')

    def planifier(self):
        return R.planifier(base=self.base_modeles)

    def test_sans_dossier_de_travail_refuse(self):
        self.assertRaisesRegex(ValueError, 'dossier de travail', self.planifier)

    def test_plan_puis_copie_idempotente(self):
        racine = E.definir(self.travail)
        plan = {p['source'].name: p for p in self.planifier()}
        # Même contenu dans deux fichiers : copié une seule fois.
        self.assertEqual(len({'base.xml', 'base copie.xml'} & set(plan)), 1)
        base = plan.get('base.xml') or plan['base copie.xml']
        attendu = {'KDMETA 175USD 150KG 01.xml': 'historique', 'T1.xml': 'reelles', 'modele.pdf': 'pdf',
                   'divers.pdf': 'a_trier', 'casse.xml': 'a_trier'}
        self.assertEqual(base['categorie'], 'sources')
        self.assertEqual({n: plan[n]['categorie'] for n in attendu}, attendu)
        importateur = plan['T1.xml']['importateur']
        self.assertEqual(plan['T1.xml']['destination'],
                         racine / E.IMPORTATEURS / importateur / '4 - DECLARATIONS REELLES' / 'T1.xml')
        self.assertEqual(plan['divers.pdf']['destination'], racine / E.A_TRIER / 'divers.pdf')
        avant = sorted(p for p in self.ancien.rglob('*'))
        copies, compte_rendu = R.executer(list(plan.values()))
        self.assertEqual(copies, len(plan))
        self.assertTrue(plan['T1.xml']['destination'].is_file())
        self.assertIn('Les originaux sont restés en place', compte_rendu.read_text(encoding='utf-8'))
        self.assertEqual(sorted(p for p in self.ancien.rglob('*')), avant)  # originaux intacts
        self.assertTrue(all(p['deja'] for p in self.planifier()))  # second passage : rien à copier


class FenetresTest(EspaceTest):
    def setUp(self):
        super().setUp()
        self.racine = tk.Tk()
        self.racine.withdraw()
        self.addCleanup(self.racine.destroy)

    def test_choix_du_dossier(self):
        from asydec.ui.espace_travail import FenetreEspaceTravail
        fenetre = FenetreEspaceTravail(self.racine, premier_lancement=True)
        self.assertEqual(fenetre.var_dossier.get(), str(E.DEFAUT))
        fenetre.var_dossier.set(str(chemins.RACINE / 'interdit'))
        fenetre.valider()
        self.assertIsNone(fenetre.choisi)
        fenetre.var_dossier.set(str(self.travail))
        fenetre.valider()
        self.assertEqual(E.racine(), self.travail.resolve())

    def test_fenetre_de_rangement(self):
        from asydec.ui.espace_travail import FenetreRangement
        E.definir(self.travail)
        source = self.ancien / 'divers.pdf'
        source.write_bytes(b'%PDF')
        plan = R.planifier(base=self.temp / 'modeles.db')
        fenetre = FenetreRangement(self.racine, plan)
        fenetre.copier()
        self.assertTrue((self.travail / E.A_TRIER / 'divers.pdf').is_file())
        self.assertEqual(str(fenetre.copier_bouton['state']), 'disabled')


if __name__ == '__main__':
    unittest.main()


class ArchiveDecTest(EspaceTest):
    def test_dossier_dec_deplace_jamais_efface(self):
        self.assertIsNone(E.archiver_dossier_dec('DEC1'))   # pas de dossier de travail
        E.definir(self.travail)
        self.assertIsNone(E.archiver_dossier_dec('DEC1'))   # pas encore de dossier DEC
        (E.dossier_dec('DEC1', 'licence') / 'licence.pdf').write_bytes(b'pdf')
        (E.dossier_dec('DEC1', 'xml_sydonia') / 'reel.xml').write_text('<ASYCUDA/>')
        archive = E.archiver_dossier_dec('DEC1', garder=('licence',))
        self.assertEqual(archive.parent, E.racine() / E.SAUVEGARDES / E.LICENCES_SUPPRIMEES)
        self.assertTrue((archive / '3 - XML SYDONIA' / 'reel.xml').is_file())     # rien n'est perdu
        # Nouveau dossier DEC : propre, avec seulement la licence recopiée.
        self.assertTrue((E.dossier_dec('DEC1', 'licence') / 'licence.pdf').is_file())
        self.assertEqual(list(E.dossier_dec('DEC1', 'xml_sydonia').iterdir()), [])
        # Deuxième suppression la même minute : nom distinct.
        self.assertNotEqual(E.archiver_dossier_dec('DEC1'), archive)
        self.assertFalse(E.dossier_dec('DEC1', creer=False).exists())
