"""XML partagés persistants, sans double compte ni transfert de validation."""
import tempfile
import unittest
from pathlib import Path
import base_references as B
import catalogue_xml as C
import service_references as S
from test_references import declaration, item


class CatalogueXmlTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.racine=Path(self.tmp.name)
        self.base=self.racine/'DONNEES'/'asydec.db'
        self.conn=B.ouvrir(self.base)
        self.addCleanup(lambda:self.conn.close())
        self.source=self.racine/'dossier.xml'
        self.source.write_bytes(declaration([item()]))

    def test_meme_fichier_partage_depuis_deux_pages_un_seul_document(self):
        premiers,erreurs=C.partager(self.conn,[self.source])
        suivants,autres=C.partager(self.conn,[self.source])
        self.assertEqual(erreurs+autres,[])
        self.assertEqual(premiers,suivants)
        self.assertEqual(S.compteurs(self.conn)['documents'],1)
        self.assertEqual(C.lister(self.conn)[0]['statut'],'non_verifie')

    def test_archive_disponible_apres_suppression_original_et_reouverture(self):
        C.partager(self.conn,[self.source])
        contenu=self.source.read_bytes()
        self.source.unlink()
        self.conn.close()
        self.conn=B.ouvrir(self.base)
        documents=C.lister(self.conn)
        self.assertEqual(len(documents),1)
        self.assertEqual(documents[0]['nom'],'dossier.xml')
        self.assertEqual(Path(documents[0]['chemin']).read_bytes(),contenu)

    def test_reutilisation_conserve_statut_accepte(self):
        ids,_=C.partager(self.conn,[self.source])
        S.enregistrer_statut(self.conn,ids[0],'accepte',preuve='preuve de test')
        copie=self.racine/'autre-nom.xml'
        copie.write_bytes(self.source.read_bytes())
        ids_copie,erreurs=C.partager(self.conn,[copie])
        self.assertEqual(ids_copie,ids)
        self.assertEqual(erreurs,[])
        self.assertEqual(C.lister(self.conn)[0]['statut'],'accepte')
        self.assertEqual(len(C.lister(self.conn,[copie])),1)

    def test_rejet_exclu_generation_meme_si_copie_ancienne_disponible(self):
        ids,_=C.partager(self.conn,[self.source])
        S.enregistrer_statut(self.conn,ids[0],'rejete',commentaire='rejet test')
        self.assertEqual(C.lister(self.conn,[self.source],generation=True),[])
        self.assertEqual(len(C.lister(self.conn,[self.source])),1)

    def test_anciens_modeles_accessibles_sans_double_import(self):
        documents=C.lister(self.conn,[self.source,self.source])
        self.assertEqual(len(documents),1)
        self.assertEqual(S.compteurs(self.conn)['documents'],0)
        self.assertEqual(documents[0]['source'],'Modèle existant')

    def test_fichier_refuse_ne_bloque_pas_les_autres(self):
        invalide=self.racine/'autre.xml'
        invalide.write_text('<autre/>')
        ids,erreurs=C.partager(self.conn,[invalide,self.source])
        self.assertEqual(len(ids),1)
        self.assertEqual(len(erreurs),1)
        self.assertIn('autre.xml',erreurs[0])


if __name__=='__main__':
    unittest.main()
