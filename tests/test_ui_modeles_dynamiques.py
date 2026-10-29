"""Les tableaux Tkinter s'adaptent au XML et affichent les positions tarifaires."""
from types import SimpleNamespace
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from asydec.calcul import moteur, variantes
from asydec.declarations import generer
from asydec.ui.etapes import PageArticles
from asydec.ui.outils import PageRepartitions
from tests import test_modeles_dynamiques as fixtures


class TableauxDynamiquesTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ModelesDynamiquesTest(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.racine = tk.Tk()
        self.racine.withdraw()
        self.addCleanup(self.racine.destroy)

    def test_saisie_propositions_et_tarifs_sur_douze_articles(self):
        source = self.fixture.source(12)
        info = moteur.infos_dossier(moteur.charger(source).getroot())
        profil = variantes.construire_profil(source, [])
        app = SimpleNamespace(base=source, info=info, profil=profil, table_imp=[],
                              session_verrouillee=False, montrer=Mock())
        with patch.object(generer, 'DEC', str(self.fixture.fixture.racine/'exports')):
            articles = PageArticles(self.racine, app)
            articles.nouvelle_base()
            articles.remplir(info['poids_articles'], info['fob_articles'], info['colis_articles'], mode='SAISI')
            self.assertEqual(len(articles.e_poids), 12)
            self.assertEqual(articles.valeurs()['poids'], [100]*12)
            self.assertIn('63000011', articles.noms[-1].cget('text'))
            resultat = generer.produire(source, [100]*12, profil['ratios'], [], {},
                mode='SAISI', fob_saisis=[150]*12, colis_saisis=info['colis_articles'],
                enregistrer=False, profil=profil)
            page = PageRepartitions(self.racine, app)
            page.propositions = [dict(poids=[100]*12, fob=[150]*12, colis=info['colis_articles'],
                                     profil=profil, resultat=resultat, empreinte='abc',
                                     proximite=100, modele='douze.xml')]
            page._remplir_liste()
            page.liste.selection_set('0')
            page.detailler()
            lignes = page.detail.get_children()
            self.assertEqual(len(lignes), 13)
            self.assertIn('63000011', page.detail.item(lignes[-2], 'values')[0])
            self.assertIn('CDF', page.var_total_declaration.get())
            # Un autre XML reconstruit la grille au lieu de garder douze lignes.
            app.info = {**info, 'poids_articles':[100]*3, 'fob_articles':[150]*3,
                        'colis_articles':[10,11,12], 'positions_tarifaires':info['positions_tarifaires'][:3],
                        'designations':info['designations'][:3], 'fob':450, 'colis':33}
            app.profil = None
            articles.nouvelle_base()
            self.assertEqual(len(articles.e_poids), 3)

    def test_mediatheque_commune_filtre_et_classement(self):
        from asydec.references import base_references as B, catalogue_xml as C
        from asydec.systeme import gestion_locale as L
        from asydec.ui.mediatheque import PageMediatheque
        source = self.fixture.source(3)
        autre = source.parent/'divers.xml'
        autre.write_bytes(source.read_bytes()+b'<!-- divers -->')
        conn = B.ouvrir(source.parent/'catalogue-ui.db')
        self.addCleanup(conn.close)
        with patch.object(L, 'CONFIGURATION', source.parent/'configuration-test'), \
             patch('asydec.ui.mediatheque.modeles_generes.usages_references', return_value={}):
            C.partager(conn, [source, autre])
            sha = variantes.hashlib.sha256(autre.read_bytes()).hexdigest()
            C.classer(conn, [sha], 'divers')
            app = SimpleNamespace(session_verrouillee=False, base=None, reference=None,
                base_refs=lambda:conn, xml_disponibles=lambda tous_modules=False:C.lister(conn),
                pages={'repartitions':Mock()}, montrer=Mock())
            app.pages['repartitions'].liste.get_children.return_value = ()
            app.pages['repartitions'].detail.get_children.return_value = ()
            page = PageMediatheque(self.racine, app)
            app.montrer.side_effect = lambda cle:page.afficher()
            page.afficher()
            self.assertEqual(len(page.table.get_children()), 2)
            page.var_filtre.set('Divers')
            page.afficher()
            self.assertEqual(len(page.table.get_children()), 1)
            self.assertEqual(page.table.item('0', 'values')[1], 'Divers')
            page.table.selection_set('0')
            page.var_type.set('Friperie')
            page.classer()
            self.assertEqual(C.module_document(conn, sha), 'friperie')
            self.assertEqual(len(page.table.get_children()), 0)
