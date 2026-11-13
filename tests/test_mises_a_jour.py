import json
import hashlib
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo
from asydec.systeme import mises_a_jour as M


class MisesAJourTest(TestCase):
    def setUp(self):
        plateforme = patch.object(M.sys, 'platform', 'darwin')
        plateforme.start()
        self.addCleanup(plateforme.stop)

    def test_seule_construction_publiee_plus_recente_proposee(self):
        assets=[{'name':f'AsyDec-macos-arm64.{ext}','url':M.API+'/releases/assets/'+str(i)} for i,ext in enumerate(['json','zip'])]
        release={'assets':assets}
        meta={'architecture':'arm64','sha256':'a'*64,'revision':'b'*40,'build':3,'version':'1.0.3'}
        def reponses():
            return [BytesIO(json.dumps(release).encode()),BytesIO(json.dumps(meta).encode())]
        with patch.object(M.platform,'machine',return_value='arm64'),patch.object(M,'courante',return_value={'revision':'c'*40,'build':2}):
            with patch.object(M,'_ouvrir',side_effect=reponses()):
                self.assertTrue(M.verifier()['disponible'])
            meta['build']=1
            with patch.object(M,'_ouvrir',side_effect=reponses()):
                self.assertFalse(M.verifier()['disponible'])

    def test_version_intel_sous_rosetta_passe_en_arm64(self):
        class R:
            def __init__(self, code, sortie): self.returncode, self.stdout = code, sortie
        with patch.object(M.platform,'machine',return_value='x86_64'):
            with patch.object(M.subprocess,'run',return_value=R(0,'1\n')):
                self.assertEqual(M.architecture(),'arm64')  # Mac M1…M5, application Intel via Rosetta
            with patch.object(M.subprocess,'run',return_value=R(0,'0\n')):
                self.assertEqual(M.architecture(),'x86_64')
            with patch.object(M.subprocess,'run',return_value=R(1,'')):
                self.assertEqual(M.architecture(),'x86_64')  # vrai Mac Intel : clé absente
        with patch.object(M.platform,'machine',return_value='arm64'):
            self.assertEqual(M.architecture(),'arm64')

    def test_archives_traversantes_et_liens_sortants_refuses(self):
        with TemporaryDirectory() as d:
            p=Path(d)/'a.zip'
            with ZipFile(p,'w') as z: z.writestr('../secret','x')
            with self.assertRaises(ValueError): M.verifier_zip(p)
            with ZipFile(p,'w') as z:
                i=ZipInfo('AsyDec.app/link'); i.create_system=3; i.external_attr=0o120777<<16
                z.writestr(i,'../../ailleurs')
            with self.assertRaises(ValueError): M.verifier_zip(p)
            with ZipFile(p,'w') as z:
                i=ZipInfo('AsyDec.app/Contents/Frameworks/Python.framework/Versions/Current');i.create_system=3;i.external_attr=0o120777<<16
                z.writestr(i,'3.12')
            # Les chemins internes d'un ZIP restent POSIX, même lors du contrôle sous Windows.
            M.verifier_zip(p)

    def test_adresse_non_github_refusee(self):
        with self.assertRaises(ValueError): M._ouvrir('https://example.com/app.zip')
        with self.assertRaises(ValueError): M._ouvrir('http://api.github.com/repos/x')

    def test_empreinte_incorrecte_annule_et_nettoie(self):
        with TemporaryDirectory() as d:
            app=Path(d)/'AsyDec.app';app.mkdir()
            meta={'asset':{'url':M.API+'/releases/assets/1'},'sha256':'0'*64}
            with patch.object(M,'application_courante',return_value=app),patch.object(M,'_ouvrir',return_value=BytesIO(b'invalide')):
                with self.assertRaisesRegex(ValueError,'Empreinte'):
                    M.preparer(meta)
            self.assertEqual(list(Path(d).iterdir()),[app])

    def test_echec_du_remplacement_restaure_application(self):
        with TemporaryDirectory() as d:
            racine=Path(d)
            cible=racine/'AsyDec.app';cible.mkdir();(cible/'ancien').write_text('old')
            nouvelle=racine/'.AsyDec-maj-test/extraction/AsyDec.app';nouvelle.mkdir(parents=True)
            original=M.os.replace
            def remplacer(a,b):
                if Path(a).resolve()==nouvelle.resolve():
                    raise OSError('disque')
                return original(a,b)
            with patch.object(M.os,'kill',side_effect=ProcessLookupError),patch.object(M.os,'replace',side_effect=remplacer),patch.object(M.subprocess,'run'):
                with self.assertRaises(OSError): M.installer(nouvelle,cible,1234)
            self.assertTrue((cible/'ancien').exists())

    def test_installation_ne_touche_pas_aux_donnees_et_conserve_precedente(self):
        with TemporaryDirectory() as d:
            racine=Path(d)
            cible=racine/'AsyDec.app';cible.mkdir();(cible/'ancien').write_text('old')
            nouvelle=racine/'.AsyDec-maj-test/extraction/AsyDec.app';nouvelle.mkdir(parents=True);(nouvelle/'nouveau').write_text('new')
            donnees=racine/'DONNEES';donnees.mkdir();(donnees/'f.db').write_text('data')
            with patch.object(M.os,'kill',side_effect=ProcessLookupError),patch.object(M.subprocess,'run'):
                M.installer(nouvelle,cible,1234)
            self.assertTrue((cible/'nouveau').exists())
            self.assertTrue((racine/'AsyDec-version-precedente.app/ancien').exists())
            self.assertEqual((donnees/'f.db').read_text(),'data')

class MisesAJourWindowsTest(TestCase):
    def setUp(self):
        plateforme = patch.object(M.sys, 'platform', 'win32')
        plateforme.start()
        self.addCleanup(plateforme.stop)

    def test_recherche_publication_windows_meme_si_latest_est_mac(self):
        assets = [{'name': nom, 'url': M.API + '/releases/assets/' + str(i)} for i, nom in enumerate(
            ['AsyDec-windows-x64.json', 'AsyDec-Setup-windows-x64.exe'])]
        meta = dict(architecture='AMD64', sha256='a'*64, revision='b'*40, build=7, version='1.0.7')
        versions = [dict(assets=[], tag_name='macos-99'), dict(assets=assets, prerelease=True),
                    dict(assets=assets, draft=True), dict(assets=assets, tag_name='windows-7')]
        with patch.object(M.platform, 'machine', return_value='AMD64'), \
             patch.object(M, 'courante', return_value=dict(revision='c'*40, build=6)), \
             patch.object(M, '_ouvrir', side_effect=[BytesIO(json.dumps(versions).encode()),
                                                     BytesIO(json.dumps(meta).encode())]) as ouvrir, \
             patch.object(M.subprocess, 'run') as run:
            resultat = M.verifier()
        self.assertTrue(resultat['disponible'])
        self.assertEqual(resultat['asset'], assets[1])
        self.assertIn('/releases?per_page=100&page=1', ouvrir.call_args_list[0].args[0])
        run.assert_not_called()  # aucun sysctl Mac

    def test_aucune_publication_windows_message_explicite(self):
        with patch.object(M.platform, 'machine', return_value='AMD64'), \
             patch.object(M, '_ouvrir', return_value=BytesIO(b'[]')):
            with self.assertRaisesRegex(ValueError, 'Windows'):
                M.verifier()

    def test_jeton_windows_sans_trousseau_et_sans_ecriture(self):
        with patch.object(M, '_jeton_session', None), patch.object(M.subprocess, 'run') as run:
            self.assertIsNone(M.token_github())
            M.retenir_token('jeton-test')
            self.assertEqual(M.token_github(), 'jeton-test')
            run.assert_not_called()

    def test_telechargement_verifie_puis_lancement_du_setup(self):
        contenu = b'MZ-installateur-test'
        meta = dict(asset=dict(url=M.API+'/releases/assets/1'), sha256=hashlib.sha256(contenu).hexdigest())
        with TemporaryDirectory() as d:
            executable = Path(d) / 'AsyDec.exe'
            dossier = Path(d) / 'telechargement'
            dossier.mkdir()
            with patch.object(M, 'application_windows', return_value=executable), \
                 patch.object(M.tempfile, 'mkdtemp', return_value=str(dossier)), \
                 patch.object(M, '_ouvrir', return_value=BytesIO(contenu)):
                setup = M.preparer(meta)
            self.assertEqual(setup.read_bytes(), contenu)
            with patch.object(M, 'application_windows', return_value=executable), \
                 patch.object(M.subprocess, 'Popen') as lancer:
                M.lancer_installation(setup)
            self.assertEqual(lancer.call_args.args[0], [str(setup), '/NORESTART', '/DIR='+str(executable.parent)])

    def test_empreinte_incorrecte_ne_lance_rien_et_nettoie(self):
        with TemporaryDirectory() as d:
            dossier = Path(d) / 'telechargement'
            dossier.mkdir()
            with patch.object(M, 'application_windows'), \
                 patch.object(M.tempfile, 'mkdtemp', return_value=str(dossier)), \
                 patch.object(M, '_ouvrir', return_value=BytesIO(b'MZ-corrompu')), \
                 patch.object(M.subprocess, 'Popen') as lancer:
                with self.assertRaisesRegex(ValueError, 'Empreinte'):
                    M.preparer(dict(asset=dict(url=M.API+'/releases/assets/1'), sha256='0'*64))
            self.assertFalse(dossier.exists())
            lancer.assert_not_called()


if __name__=='__main__':
    main()
