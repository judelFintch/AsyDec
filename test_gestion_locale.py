"""Tests exclusivement sur des comptes et données temporaires, jamais sur le projet réel."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch
import gestion_locale as local

MDP = 'mot-de-passe-test-2026'


class GestionLocaleTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.racine = Path(self.temp.name) / 'application'
        self.racine.mkdir()
        self.config = self.racine / 'CONFIG_LOCAL'
        local.creer_compte('Administrateur', MDP, self.config)

    def test_compte_hache_et_connexion(self):
        contenu = (self.config / 'compte.json').read_text()
        self.assertNotIn(MDP, contenu)
        self.assertEqual(json.loads(contenu)['algorithme'], 'pbkdf2_sha256')
        self.assertTrue(local.authentifier('administrateur', MDP, self.config))
        self.assertFalse(local.authentifier('autre', MDP, self.config))
        self.assertFalse(local.authentifier('Administrateur', 'faux', self.config))
        self.assertEqual((self.config / 'compte.json').stat().st_mode & 0o777, 0o600)

    def test_compte_existant_non_remplace(self):
        avant = (self.config / 'compte.json').read_bytes()
        with self.assertRaises(FileExistsError):
            local.creer_compte('AutreCompte', 'autre-mot-de-passe-long', self.config)
        self.assertEqual((self.config / 'compte.json').read_bytes(), avant)

    def test_pas_de_compte_par_defaut_ni_mdp_faible(self):
        autre = self.racine / 'autre'
        self.assertFalse(local.compte_existe(autre))
        with self.assertRaises(local.ErreurCompte):
            local.creer_compte('admin', 'court', autre)
        self.assertFalse(local.compte_existe(autre))

    def test_creation_accepte_8_caracteres_et_refuse_7(self):
        autre = self.racine / 'compte-8'
        local.creer_compte('admin8', 'abcdefgh', autre)
        self.assertTrue(local.authentifier('admin8', 'abcdefgh', autre))
        with self.assertRaisesRegex(local.ErreurCompte, '8 caractères'):
            local.creer_compte('admin7', 'abcdefg', self.racine / 'compte-7')

    def test_changement_accepte_8_caracteres_et_refuse_7(self):
        with self.assertRaisesRegex(local.ErreurCompte, '8 caractères'):
            local.changer_mot_de_passe(MDP, 'abcdefg', self.config)
        local.changer_mot_de_passe(MDP, 'abcdefgh', self.config)
        self.assertTrue(local.authentifier('Administrateur', 'abcdefgh', self.config))

    def test_blocage_temporaire_persistant(self):
        for _ in range(5):
            self.assertFalse(local.authentifier('Administrateur', 'faux', self.config, maintenant=1000))
        with self.assertRaisesRegex(local.ErreurCompte, 'Attendez'):
            local.authentifier('Administrateur', MDP, self.config, maintenant=1001)
        self.assertTrue(local.authentifier('Administrateur', MDP, self.config, maintenant=1061))

    def test_changement_mot_de_passe(self):
        nouveau = 'nouveau-mot-de-passe-long'
        local.changer_mot_de_passe(MDP, nouveau, self.config)
        self.assertFalse(local.authentifier('Administrateur', MDP, self.config))
        self.assertTrue(local.authentifier('Administrateur', nouveau, self.config))

    def test_compte_corrompu_ne_devient_pas_creation_libre(self):
        (self.config / 'compte.json').write_text('[]')
        self.assertTrue(local.compte_existe(self.config))
        with self.assertRaises(local.ErreurCompte):
            local.authentifier('Administrateur', MDP, self.config)

    def test_parametres_persistants_et_validation(self):
        choix = dict(local.DEFAUTS, organisation='Agence test', memoriser_recents=False,
                     dossier_xml=str(self.racine), page_demarrage='parametres', verrouillage_minutes=3)
        local.enregistrer_reglages(choix, self.config)
        self.assertEqual(local.lire_reglages(self.config), choix)
        for mauvais in ({'verrouillage_minutes': -1}, {'verrouillage_minutes': True},
                        {'page_demarrage': 'inconnue'}, {'dossier_xml': '/dossier/inexistant'}):
            with self.assertRaises(ValueError):
                local.enregistrer_reglages(mauvais, self.config)
        self.assertEqual(local.lire_reglages(self.config), choix)

    def preparer_donnees(self):
        for nom in ('MODELES_XML/ref.xml', 'ETUDES_XML/etude.json', 'DONNEES/sources/source.xml',
                    'registre.json', 'SAISIE.xlsx', 'CONFIG_LOCAL/reglages.json', 'CONFIG_LOCAL/preferences.json',
                    'SIMULATIONS/export.xlsx', 'DONNEES/export-client.xml', 'DONNEES/sauvegardes/ancien.txt'):
            p = self.racine / nom
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('donnée de test')
        conn = sqlite3.connect(self.racine / 'DONNEES/asydec.db')
        conn.execute('CREATE TABLE exemple (valeur TEXT)')
        conn.execute("INSERT INTO exemple VALUES ('persistant')")
        conn.commit()
        conn.close()
        original = Path(self.temp.name) / 'original.xml'
        original.write_text('original à conserver')
        export = self.racine / 'declaration-exportee.xml'
        export.write_text('export à conserver')
        return original, export

    def test_reset_archive_preserve_compte_originaux_exports(self):
        original, export = self.preparer_donnees()
        hook = Mock()
        sauvegarde = local.reinitialiser(MDP, 'REINITIALISER', self.racine, avant_reset=hook)
        hook.assert_called_once_with()
        self.assertTrue(sauvegarde.is_dir())
        self.assertFalse((self.racine / 'DONNEES/asydec.db').exists())
        self.assertFalse((self.racine / 'MODELES_XML').exists())
        self.assertTrue((sauvegarde / 'DONNEES/asydec.db').exists())
        self.assertTrue((sauvegarde / 'DONNEES/sources/source.xml').exists())
        self.assertTrue((sauvegarde / 'manifest.json').exists())
        self.assertTrue(local.authentifier('Administrateur', MDP, self.config))
        self.assertEqual(local.lire_reglages(self.config), local.DEFAUTS)
        self.assertEqual(original.read_text(), 'original à conserver')
        self.assertEqual(export.read_text(), 'export à conserver')
        for nom in ('SIMULATIONS/export.xlsx', 'DONNEES/export-client.xml', 'DONNEES/sauvegardes/ancien.txt'):
            self.assertTrue((self.racine / nom).exists())
        conn = sqlite3.connect(sauvegarde / 'DONNEES/asydec.db')
        self.assertEqual(conn.execute('SELECT valeur FROM exemple').fetchone()[0], 'persistant')
        conn.close()

    def test_reset_exige_mdp_phrase_et_services_disponibles(self):
        self.preparer_donnees()
        hook = Mock()
        with self.assertRaises(ValueError):
            local.reinitialiser(MDP, 'oui', self.racine, avant_reset=hook)
        with self.assertRaises(local.ErreurCompte):
            local.reinitialiser('faux', 'REINITIALISER', self.racine, avant_reset=hook)
        hook.assert_not_called()
        with self.assertRaisesRegex(ValueError, 'import actif'):
            local.reinitialiser(MDP, 'REINITIALISER', self.racine,
                                avant_reset=Mock(side_effect=ValueError('import actif')))
        self.assertTrue((self.racine / 'MODELES_XML/ref.xml').exists())
        self.assertFalse((self.racine / 'SAUVEGARDES').exists())

    def test_reset_retour_arriere_si_deplacement_echoue(self):
        self.preparer_donnees()
        remplacer = local.os.replace
        declenche = False
        def echec(source, cible):
            nonlocal declenche
            if Path(source) == self.racine / 'ETUDES_XML' and not declenche:
                declenche = True
                raise OSError('erreur disque simulée')
            return remplacer(source, cible)
        with patch.object(local.os, 'replace', side_effect=echec):
            with self.assertRaises(OSError):
                local.reinitialiser(MDP, 'REINITIALISER', self.racine)
        self.assertTrue((self.racine / 'DONNEES/asydec.db').exists())
        self.assertTrue((self.racine / 'MODELES_XML/ref.xml').exists())
        self.assertTrue((self.racine / 'ETUDES_XML/etude.json').exists())

    def test_reset_refuse_un_lien_vers_origine_externe(self):
        externe = Path(self.temp.name) / 'source-externe'
        externe.mkdir()
        (externe / 'original.xml').write_text('conserver')
        (self.racine / 'MODELES_XML').symlink_to(externe, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'lien symbolique'):
            local.reinitialiser(MDP, 'REINITIALISER', self.racine)
        self.assertEqual((externe / 'original.xml').read_text(), 'conserver')


if __name__ == '__main__':
    unittest.main()
