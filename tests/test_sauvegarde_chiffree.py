"""Sauvegardes chiffrées et GitHub : seulement des comptes et données temporaires."""
import hashlib
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from zipfile import ZipFile

from asydec.systeme import sauvegarde_chiffree as C, sauvegarde_github as G, transfert
from tests.test_transfert import _machine

MOT_DE_PASSE_TEST = 'phrase-secrete-de-test-2026'


class SauvegardeChiffreeTest(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.d = Path(self.temp.name)
        self.source = self.d / 'source'
        _machine(self.source)
        (self.source / 'CONFIG_LOCAL/prive.json').write_text('{"secret":"DONNEES_TRES_PRIVEES"}')

    def exporter(self, nom='sauvegarde'):
        return C.exporter(self.d / nom, MOT_DE_PASSE_TEST, racine=self.source)[0]

    def test_chiffrement_aleatoire_sans_donnees_ni_mot_de_passe_visibles(self):
        a, b = self.exporter('a'), self.exporter('b')
        self.assertNotEqual(a.read_bytes(), b.read_bytes())
        self.assertNotIn(b'DONNEES_TRES_PRIVEES', a.read_bytes())
        self.assertNotIn(MOT_DE_PASSE_TEST.encode(), a.read_bytes())
        self.assertTrue(a.name.endswith(C.EXTENSION))
        with C.ouvrir(a, MOT_DE_PASSE_TEST) as archive:
            chemin_clair = archive
            with ZipFile(archive) as z:
                self.assertIn(b'DONNEES_TRES_PRIVEES', z.read('CONFIG_LOCAL/prive.json'))
        self.assertFalse(chemin_clair.exists())

    def test_mauvais_mot_de_passe_et_fichier_altere_ne_preparent_aucun_import(self):
        fichier = self.exporter()
        contenu = bytearray(fichier.read_bytes())
        contenu[C.ENTETE + 8] ^= 1
        altere = self.d / 'altere.asydec.enc'
        altere.write_bytes(contenu)
        with patch.object(transfert, 'preparer_import_complet') as preparer:
            for source, mdp in ((fichier, 'mauvaise-phrase-longue'), (altere, MOT_DE_PASSE_TEST)):
                with self.assertRaisesRegex(ValueError, 'incorrect|endommagée'):
                    C.preparer_import(source, mdp)
            preparer.assert_not_called()

    def test_import_verifie_avant_remplacement_et_anciennes_donnees_archivees(self):
        fichier = self.exporter()
        neuve = self.d / 'neuve'
        (neuve / 'DONNEES').mkdir(parents=True)
        original = neuve / 'DONNEES/existant.txt'
        original.write_text('conserver')
        C.preparer_import(fichier, MOT_DE_PASSE_TEST, racine=neuve)
        self.assertEqual(original.read_text(), 'conserver')
        sauvegarde = transfert.appliquer_en_attente(neuve)
        self.assertEqual((sauvegarde / 'DONNEES/existant.txt').read_text(), 'conserver')
        self.assertTrue((neuve / 'CONFIG_LOCAL/prive.json').exists())

    def test_mot_de_passe_court_refuse_avant_export(self):
        with patch.object(transfert, 'exporter') as exporter:
            with self.assertRaises(ValueError):
                C.exporter(self.d / 'x', 'court', racine=self.source)
        exporter.assert_not_called()

    def test_publication_valide_le_chiffrement_et_n_envoie_jamais_le_mot_de_passe(self):
        fichier = self.exporter()

        def envoyer(copie, identifiant, nom, token):
            self.assertNotEqual(copie, fichier)
            self.assertEqual(copie.read_bytes(), fichier.read_bytes())
            self.assertTrue(nom.endswith(C.EXTENSION))
            self.assertNotIn('DONNEES_TRES_PRIVEES', nom)
            self.assertEqual(identifiant, 73)
            self.assertEqual(token, 'jeton-test')
            return {'state': 'uploaded'}

        with patch.object(G, '_api', side_effect=[{'id': 73}, {'html_url': 'https://github.com/test/release'}]) as api, \
             patch.object(G, '_envoyer', side_effect=envoyer):
            self.assertEqual(G.publier(fichier, MOT_DE_PASSE_TEST, 'jeton-test'), 'https://github.com/test/release')
        self.assertNotIn(MOT_DE_PASSE_TEST, repr(api.call_args_list))
        self.assertTrue(api.call_args_list[0].args[3]['draft'])
        self.assertEqual(api.call_args_list[1].args[3], {'draft': False, 'make_latest': 'false'})

    def test_publication_refuse_clair_et_mauvais_mot_de_passe_avant_reseau(self):
        clair = self.d / 'faux.asydec.enc'
        clair.write_bytes(b'DONNEES EN CLAIR')
        fichier = self.exporter()
        with patch.object(G, '_api') as api, patch.object(G, '_envoyer') as envoyer:
            for source, mdp in ((clair, MOT_DE_PASSE_TEST), (fichier, 'mauvaise-phrase-longue')):
                with self.assertRaises(ValueError):
                    G.publier(source, mdp, 'jeton-test')
        api.assert_not_called()
        envoyer.assert_not_called()

    def test_echec_envoi_supprime_seulement_son_nouveau_brouillon(self):
        fichier = self.exporter()
        with patch.object(G, '_api', side_effect=[{'id': 73}, None]) as api, \
             patch.object(G, '_envoyer', side_effect=OSError('réseau indisponible')):
            with self.assertRaises(OSError):
                G.publier(fichier, MOT_DE_PASSE_TEST, 'jeton-test')
        self.assertEqual(api.call_args_list[-1].args, ('/releases/73', 'jeton-test', 'DELETE'))

    def test_transport_envoie_les_octets_chiffres_uniquement_vers_github(self):
        from unittest.mock import Mock
        fichier = self.exporter()
        reponse = Mock(status=201)
        reponse.read.return_value = b'{"state":"uploaded"}'
        connexion = Mock()
        connexion.getresponse.return_value = reponse
        with patch.object(G.http.client, 'HTTPSConnection', return_value=connexion) as ouvrir:
            G._envoyer(fichier, 73, 'sauvegarde.asydec.enc', 'jeton-test')
        self.assertEqual(ouvrir.call_args.args[0], 'uploads.github.com')
        self.assertEqual(b''.join(c.args[0] for c in connexion.send.call_args_list), fichier.read_bytes())
        self.assertIn('/releases/73/assets?name=sauvegarde.asydec.enc', connexion.putrequest.call_args.args[1])
        self.assertNotIn(MOT_DE_PASSE_TEST, repr(connexion.method_calls))
        connexion.close.assert_called_once()

    def test_telechargement_et_import_avec_mot_de_passe(self):
        fichier = self.exporter()
        contenu = fichier.read_bytes()
        asset = dict(id=12, nom='sauvegarde.asydec.enc', taille=len(contenu),
                     digest='sha256:' + hashlib.sha256(contenu).hexdigest())
        neuve = self.d / 'neuve'
        with patch.object(G.github, '_ouvrir', return_value=BytesIO(contenu)) as ouvrir:
            G.recuperer(asset, MOT_DE_PASSE_TEST, racine=neuve)
        self.assertTrue((neuve / transfert.EN_ATTENTE / 'CONFIG_LOCAL/prive.json').is_file())
        self.assertNotIn(MOT_DE_PASSE_TEST, repr(ouvrir.call_args_list))
        self.assertEqual(ouvrir.call_args.args[0], G.github.API + '/releases/assets/12')

    def test_sans_mot_de_passe_aucun_telechargement(self):
        with patch.object(G.github, '_ouvrir') as ouvrir:
            with self.assertRaises(ValueError):
                G.recuperer({}, '')
        ouvrir.assert_not_called()

    def test_telechargement_incomplet_ne_touche_pas_aux_donnees(self):
        with patch.object(G.github, '_ouvrir', return_value=BytesIO(b'court')), \
             patch.object(C, 'preparer_import') as preparer:
            with self.assertRaisesRegex(ValueError, 'incomplet'):
                G.recuperer(dict(id=12, nom='s.asydec.enc', taille=100), MOT_DE_PASSE_TEST)
        preparer.assert_not_called()

    def test_liste_separe_sauvegardes_et_installateurs(self):
        asset = dict(id=12, name='sauvegarde.asydec.enc', size=100, state='uploaded')
        releases = [dict(assets=[dict(id=1, name='AsyDec.exe', state='uploaded')]),
                    dict(draft=True, assets=[asset]), dict(assets=[asset], tag_name='sauvegarde-test')]
        with patch.object(G, '_api', return_value=releases):
            self.assertEqual([s['id'] for s in G.lister()], [12])
