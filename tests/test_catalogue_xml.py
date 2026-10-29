"""XML partagés persistants, sans double compte ni transfert de validation."""
import tempfile
import unittest
from unittest.mock import patch

from asydec.systeme import gestion_locale as L
from pathlib import Path

from asydec.references import base_references as B
from asydec.references import catalogue_xml as C
from asydec.references import service_references as S
from tests.test_references import declaration, item


class CatalogueXmlTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.racine=Path(self.tmp.name)
        patcher=patch.object(L,'CONFIGURATION',self.racine/'CONFIG_LOCAL')
        patcher.start()
        self.addCleanup(patcher.stop)
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

    def test_retrait_persistant_sans_effacer_origine_archive_ni_statut(self):
        ids,_=C.partager(self.conn,[self.source])
        S.enregistrer_statut(self.conn,ids[0],'accepte',preuve='preuve test')
        document=C.lister(self.conn)[0]
        archive=Path(document['chemin'])
        C.retirer([document],auteur='admin test')
        self.assertEqual(C.lister(self.conn,[self.source]),[])
        self.conn.close()
        self.conn=B.ouvrir(self.base)
        self.assertEqual(C.lister(self.conn),[])
        self.assertTrue(self.source.exists())
        self.assertTrue(archive.exists())
        self.assertEqual(S.statut(self.conn,ids[0]),'accepte')
        self.assertTrue(S.historique_statuts(self.conn,ids[0]))
        self.assertEqual(C.retraits()[document['empreinte']]['auteur'],'admin test')

    def test_rechargement_volontaire_restaure_sans_dupliquer(self):
        ids,_=C.partager(self.conn,[self.source])
        C.retirer(C.lister(self.conn))
        self.assertTrue(C.est_retire(self.source))
        ids_recharges,erreurs=C.partager(self.conn,[self.source])
        self.assertEqual(ids_recharges,ids)
        self.assertEqual(erreurs,[])
        self.assertFalse(C.est_retire(self.source))
        self.assertEqual(len(C.lister(self.conn)),1)

    def test_retrait_ancien_modele_bloque_toutes_les_copies(self):
        document=C.lister(self.conn,[self.source])[0]
        C.retirer([document])
        copie=self.racine/'copie.xml'
        copie.write_bytes(self.source.read_bytes())
        self.assertEqual(C.lister(self.conn,[self.source,copie]),[])
        self.assertTrue(copie.exists())

    def test_xml_partiel_positions_conservees_et_generation_interdite(self):
        self.source.write_bytes(declaration([item(), '<Item/>', '<Item/>', item(code='6304')]))
        C.partager(self.conn, [self.source])
        document = C.lister(self.conn)[0]
        self.assertEqual(document['positions'], [1, 4])
        self.assertEqual(document['usage'], 'Étude uniquement')
        self.assertEqual(C.lister(self.conn, [self.source], generation=True), [])
        observations = S.observations(self.conn, statuts=('non_verifie',))
        self.assertEqual([o['position'] for o in observations], [1, 4])

    def test_xml_un_article_desormais_propose_pour_generation(self):
        documents = C.lister(self.conn, [self.source], generation=True)
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0]['articles'], 1)

    def test_xml_complet_reutilisable_depuis_archive(self):
        self.source.write_bytes(declaration([item(code=str(k)) for k in range(8)]))
        C.partager(self.conn, [self.source])
        self.source.unlink()
        documents = C.lister(self.conn, generation=True)
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0]['positions'], list(range(1, 9)))
        self.assertEqual(documents[0]['usage'], 'Génération et étude')


if __name__=='__main__':
    unittest.main()
