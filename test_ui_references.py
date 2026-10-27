"""REF-101 : bibliothèque des références — fermeture, reset, persistance, fuseau, actions désactivées."""
import os
import sqlite3
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import base_references as B
import import_references as I
import service_references as S
import ui.app as app_module
import ui.references as R
from test_references import declaration, item

AsyDec = app_module.AsyDec


class ConnexionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name) / 'DONNEES' / 'asydec.db'
        patcher = patch.object(B, 'BASE', self.base)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def double(self, **attributs):
        """Double complet de la fenêtre : tout ce que touchent les méthodes de fermeture et de reset."""
        valeurs = dict(_base_refs=None, _fermeture=False, _minuteur_session=None, _preparations_reset=[],
                       after_cancel=Mock(), destroy=Mock(),
                       pages={'references': SimpleNamespace(import_en_cours=False, _annuler=False)})
        valeurs.update(attributs)
        app = SimpleNamespace(**valeurs)
        app.pages['references'].preparer_reset = lambda: R.PageReferences.preparer_reset(app.pages['references'])
        app.base_refs = lambda: AsyDec.base_refs(app)
        app.fermer_base_refs = lambda: AsyDec.fermer_base_refs(app)
        return app

    def test_ouverture_paresseuse_et_fermeture_idempotente_reelle(self):
        app = self.double()
        self.assertFalse(self.base.exists())                     # rien n'est ouvert avant le premier besoin
        conn = app.base_refs()
        self.assertIs(app.base_refs(), conn)                     # une seule connexion
        AsyDec.fermer_sans_preferences(app)
        AsyDec.fermer_sans_preferences(app)
        self.assertIsNone(app._base_refs)
        with self.assertRaises(sqlite3.ProgrammingError):        # vraiment fermée
            conn.execute('SELECT 1')
        app.destroy.assert_called_once()

    def test_connexion_fermee_une_seule_fois(self):
        connexion = Mock()
        app = self.double(_base_refs=connexion, _minuteur_session='session')
        AsyDec.fermer_sans_preferences(app)
        AsyDec.fermer_sans_preferences(app)
        AsyDec.fermer_base_refs(app)
        connexion.close.assert_called_once()
        app.after_cancel.assert_called_once_with('session')

    def test_callback_avant_reset_ferme_puis_reouverture(self):
        connexion = Mock()
        app = self.double(_base_refs=connexion)
        app._preparations_reset.append(lambda: AsyDec._preparer_reset_references(app))
        AsyDec.preparer_reset(app)
        connexion.close.assert_called_once()
        self.assertIsNone(app._base_refs)
        AsyDec.preparer_reset(app)                               # second appel : sans effet ni erreur
        connexion.close.assert_called_once()
        self.assertIsInstance(app.base_refs(), sqlite3.Connection)   # rouvre au prochain besoin
        AsyDec.fermer_base_refs(app)

    def test_reset_refuse_pendant_un_import(self):
        connexion = Mock()
        app = self.double(_base_refs=connexion)
        app.pages['references'].import_en_cours = True
        app._preparations_reset.append(lambda: AsyDec._preparer_reset_references(app))
        with self.assertRaisesRegex(ValueError, 'import'):
            AsyDec.preparer_reset(app)
        self.assertTrue(app.pages['references']._annuler)        # l'import est prié de s'arrêter
        connexion.close.assert_not_called()                      # la connexion n'est pas fermée sous l'import

    def test_persistance_a_la_reouverture(self):
        source = Path(self.tmp.name) / 'a.xml'
        source.write_bytes(declaration([item()]))
        premiere = self.double()
        I.importer_lot([source], premiere.base_refs())
        document = S.lister_documents(premiere.base_refs())[0]['id']
        S.enregistrer_statut(premiere.base_refs(), document, 'accepte', preuve='Quittance Q 1')
        AsyDec.fermer_sans_preferences(premiere)
        seconde = self.double()
        documents = S.lister_documents(seconde.base_refs(), statut='accepte')
        self.assertEqual([d['nom_initial'] for d in documents], ['a.xml'])
        detail = S.detail_document(seconde.base_refs(), document)
        self.assertEqual(detail['articles'][0]['taxes'][0]['code'], 'DDI')
        AsyDec.fermer_base_refs(seconde)


class FuseauTest(unittest.TestCase):
    def test_lubumbashi_quel_que_soit_le_fuseau_du_poste(self):
        ancien = os.environ.get('TZ')
        try:
            for fuseau in ('UTC', 'America/New_York', 'Asia/Tokyo'):
                os.environ['TZ'] = fuseau
                time.tzset()
                self.assertEqual(R.date_locale('2026-10-27T10:00:00+00:00'), '27/10/2026 12:00')
                self.assertEqual(R.date_locale('2026-10-27T23:30:00'), '28/10/2026 01:30')   # sans fuseau : UTC
        finally:
            if ancien is None:
                os.environ.pop('TZ', None)
            else:
                os.environ['TZ'] = ancien
            time.tzset()
        self.assertEqual(R.date_locale(''), '')
        self.assertEqual(R.date_locale('10/1/26'), '10/1/26')    # non interprétable : laissé tel quel


class ActionsDesactiveesTest(unittest.TestCase):
    def setUp(self):
        try:
            self.racine = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f'Tk indisponible : {exc}')
        self.racine.withdraw()
        self.addCleanup(self.racine.destroy)
        self.app = SimpleNamespace(base_refs=Mock(side_effect=AssertionError('base ouverte à la construction')),
                                   utilisateur='essai', page_active=None)
        self.page = R.PageReferences(self.racine, self.app)

    def textes_des_boutons(self, widget):
        textes = []
        for enfant in widget.winfo_children():
            if isinstance(enfant, (tk.Button, R.ttk.Button)):
                textes.append(str(enfant.cget('text')))
            textes += self.textes_des_boutons(enfant)
        return textes

    def test_seule_la_consultation_est_construite(self):
        self.assertFalse(R.ACTIONS_ACTIVES)
        boutons = self.textes_des_boutons(self.page)
        for interdit in ('Importer', 'Accepter', 'Rejeter', 'Exclure', 'Remettre', 'Corriger', 'Exporter',
                         "Annuler l'import"):
            self.assertFalse([b for b in boutons if interdit in b], interdit)
        self.assertIn('XML archivé', boutons)                    # consultation conservée
        self.assertEqual([self.page.onglets.tab(i, 'text') for i in self.page.onglets.tabs()], ['Documents'])
        self.assertEqual(self.page.boutons_statut, {})

    def test_aucun_raccourci_ni_appel_detourne(self):
        self.assertEqual(self.racine.bind_all('<Command-i>'), '')
        for methode in ('importer_fichiers', 'importer_dossier', 'annuler', 'calculer_marchandises',
                        'exporter_marchandises', 'corriger'):
            getattr(self.page, methode)()                        # ne fait rien, n'ouvre pas la base
        self.page._importer(['x.xml'])
        self.page.changer_statut('accepte')
        self.app.base_refs.assert_not_called()


if __name__ == '__main__':
    unittest.main()
