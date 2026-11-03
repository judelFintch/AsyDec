from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import patch
from zipfile import ZipFile

from asydec.declarations import factures as F
from asydec.declarations.preparer_facture import preparer_plaque
from tests.test_factures import document
from tests.test_preparer_facture import modele


class SuggestionsFacturesTest(TestCase):
    def setUp(self):
        self.dossier = TemporaryDirectory()
        self.addCleanup(self.dossier.cleanup)
        self.base = Path(self.dossier.name)/'factures.db'

    def test_plaque_absente_ne_cree_ni_facture_ni_numero(self):
        fichier=Path(self.dossier.name)/'modele.docx'
        fichier.write_bytes(document())
        g=F.importer(fichier,self.base)
        d={'supprime':False,'plaque':'  ','importateur':'X','resultat':{}}
        with patch('asydec.declarations.modeles_generes.detail',return_value=d):
            with self.assertRaisesRegex(ValueError,'plaque est obligatoire'):
                F.generer(1,g,'alice',self.base)
        self.assertEqual(F.lister_factures(1,self.base),[])
        self.assertFalse((self.base.parent/'numeros_factures.db').exists())

    def test_zone_de_plaque_absente_bloque_avant_reservation(self):
        from tests.test_factures import document
        b = BytesIO()
        with ZipFile(BytesIO(document())) as source, ZipFile(b, 'w') as cible:
            for i in source.infolist():
                cible.writestr(i, source.read(i.filename).replace(b'{{PLAQUE}}', b'VIDE'))
        fichier = Path(self.dossier.name)/'sans-plaque.docx'
        fichier.write_bytes(b.getvalue())
        g = F.importer(fichier, self.base)
        d={'supprime':False,'plaque':'T974EBZ','importateur':'X','resultat':{
            'colis':[30],'resume':{'poids':100,'fob':60}}}
        with patch('asydec.declarations.modeles_generes.detail',return_value=d):
            with self.assertRaisesRegex(ValueError, 'aucune zone de plaque'):
                F.generer(1,g,'alice',self.base)
        self.assertFalse((self.base.parent/'numeros_factures.db').exists())

    def test_plaque_du_modele_remplace_celle_du_word(self):
        fichier=Path(self.dossier.name)/'modele.docx'
        fichier.write_bytes(modele())
        g=F.importer(fichier,self.base)
        d={'supprime':False,'plaque':'T974EBZ','importateur':'X','resultat':{
            'colis':[30],'resume':{'poids':100,'fob':60,'articles':[{'poids':100,'fob':60}]}}}
        with patch('asydec.declarations.modeles_generes.detail',return_value=d):
            f=F.generer(1,g,'alice',self.base,correspondance_confirmee=True)
        with ZipFile(BytesIO(f['contenu'])) as z:
            xml=z.read('word/document.xml').decode()
            self.assertIn('PLAQUE : T974EBZ',xml)
            self.assertNotIn('T123ABC',xml)
        self.assertTrue(F.lister_modeles(self.base)[0]['plaque_prevue'])

    def test_zone_umba_choix_et_fallback_sans_redessiner(self):
        xml=f'''<w:document xmlns:w="{F.W}" xmlns:v="urn:schemas-microsoft-com:vml"
            xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">
            <w:body><w:p><w:r><w:t>REGISTRATION NO’S MANIFEST NO:</w:t></w:r></w:p>
            <wp:anchor><wp:docPr name="Text Box 27"/><w:txbxContent><w:p><w:r><w:t>  </w:t></w:r></w:p></w:txbxContent></wp:anchor>
            <v:shape id="Text Box 27" style="position:absolute;width:166pt"><w:txbxContent><w:p><w:r><w:t>  </w:t></w:r></w:p></w:txbxContent></v:shape>
            </w:body></w:document>'''
        b=BytesIO()
        with ZipFile(b,'w') as z:
            z.writestr('[Content_Types].xml','<Types/>')
            z.writestr('word/document.xml',xml)
        r=preparer_plaque(b.getvalue())
        with ZipFile(BytesIO(r)) as z:
            texte=z.read('word/document.xml').decode()
            self.assertEqual(texte.count('{{PLAQUE}}'),2)
            self.assertIn('position:absolute;width:166pt',texte)

    def test_classement_explique_ne_se_fonde_pas_sur_le_nombre_seul(self):
        d={'importateur':'ETS ALPHA','resultat':{'info':{'designations':['USED CLOTHINGS','BEDSPREADS']},
                                            'resume':{'articles':[{},{}]}}}
        def g(i,articles,**kw):
            return dict(id=i,nom=str(i),articles=articles,plaque_prevue=True,destinataire='ETS ALPHA',**kw)
        gs=[g(1,['MACHINES','CHAIRS']), g(2,['USED CLOTHINGS','BEDSPREADS']),g(3,['USED CLOTHINGS'])]
        classement=F.classer_gabarits(gs,d)
        self.assertEqual(classement[0]['id'],2)
        self.assertTrue(classement[0]['propose'])
        self.assertFalse(next(x for x in classement if x['id']==1)['propose'])
        self.assertIn('2 dans le modèle',next(x for x in classement if x['id']==3)['raison'])
        gs[1]['destinataire']='AUTRE CLIENT'
        classement=F.classer_gabarits(gs,d)
        self.assertFalse(any(g['propose'] for g in classement))

    def test_etudie_le_destinataire_sans_creer_une_facture(self):
        contenu=modele()
        with ZipFile(BytesIO(contenu)) as source:
            sortie=BytesIO()
            with ZipFile(sortie,'w') as z:
                for i in source.infolist():
                    data=source.read(i.filename)
                    if i.filename=='word/document.xml':
                        data=data.replace(b'INV NO: OLD',b'Consignee: ETS ALPHA     INV NO: OLD')
                    z.writestr(i,data)
        analyse=F.analyser_gabarit(sortie.getvalue())
        self.assertEqual(analyse['destinataire'],'ETS ALPHA')

if __name__=='__main__':
    main()
