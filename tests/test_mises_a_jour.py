import json
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo
from asydec.systeme import mises_a_jour as M


class MisesAJourTest(TestCase):
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

if __name__=='__main__':
    main()
