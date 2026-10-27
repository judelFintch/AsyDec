"""REF-101 / REF-102 : bibliothèque des références — consultation, import de fond, fermeture, reset."""
import gc
import os
import sqlite3
import tempfile
import threading
import time
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import base_references as B
import import_fond
import import_references as I
import service_references as S
import ui.app as app_module
import ui.references as R
from test_references import declaration, item

AsyDec = app_module.AsyDec


def fils_d_import():
    return [f for f in threading.enumerate() if f.name == import_fond.NOM_DU_FIL]


class ConnexionRetardee:
    """Enveloppe une vraie connexion SQLite ; sa fermeture attend un signal du test (ou échoue)."""

    def __init__(self, conn, liberer, commencee, echec=None):
        self._conn, self._liberer, self._commencee, self._echec = conn, liberer, commencee, echec

    def __getattr__(self, nom):
        return getattr(self._conn, nom)

    def close(self):
        self._commencee.set()
        self._liberer.wait(10)
        self._conn.close()
        if self._echec:
            raise self._echec


def ouverture_retardee(liberer, commencee, echec=None):
    original = B.ouvrir
    return lambda chemin=None: ConnexionRetardee(original(chemin), liberer, commencee, echec)


class Temporaire(unittest.TestCase):
    def setUp(self):
        # Les variables Tkinter des tests précédents sont ramassées ici, dans le fil principal ;
        # sinon le ramasse-miettes peut s'exécuter dans le fil d'import et y attendre Tcl.
        gc.collect()
        self.tmp = tempfile.TemporaryDirectory()
        self.dossier = Path(self.tmp.name)
        self.base = self.dossier / 'DONNEES' / 'asydec.db'
        patcher = patch.object(B, 'BASE', self.base)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def fichiers(self, n):
        chemins = []
        for k in range(n):
            p = self.dossier / 'xml' / f'{k}.xml'
            p.parent.mkdir(exist_ok=True)
            p.write_bytes(declaration([item()], reference=f'R{k}'))
            chemins.append(p)
        return chemins

    def attendre(self, tache, delai=10):
        tache._fil.join(delai)
        self.assertFalse(tache.en_cours())
        evenements = []
        while not tache.evenements.empty():
            evenements.append(tache.evenements.get_nowait())
        return evenements


class ConnexionTest(Temporaire):
    def double(self, **attributs):
        """Double complet de la fenêtre : tout ce que touchent les méthodes de fermeture et de reset."""
        page = SimpleNamespace(arreter_import=Mock(return_value=True))
        page.preparer_reset = lambda: R.PageReferences.preparer_reset(page)
        valeurs = dict(_base_refs=None, _fermeture=False, _minuteur_session=None, _preparations_reset=[],
                       after_cancel=Mock(), destroy=Mock(), pages={'references': page})
        valeurs.update(attributs)
        app = SimpleNamespace(**valeurs)
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
        app.pages['references'].arreter_import.assert_called_with(5.0)
        connexion.close.assert_called_once()
        self.assertIsNone(app._base_refs)
        AsyDec.preparer_reset(app)                               # second appel : sans effet ni erreur
        connexion.close.assert_called_once()
        self.assertIsInstance(app.base_refs(), sqlite3.Connection)   # rouvre au prochain besoin
        AsyDec.fermer_base_refs(app)

    def test_reset_refuse_si_l_import_ne_s_arrete_pas(self):
        connexion = Mock()
        app = self.double(_base_refs=connexion)
        app.pages['references'].arreter_import.return_value = False
        app._preparations_reset.append(lambda: AsyDec._preparer_reset_references(app))
        with self.assertRaisesRegex(ValueError, 'import'):
            AsyDec.preparer_reset(app)
        connexion.close.assert_not_called()                      # la connexion n'est pas fermée sous l'import

    def test_fermeture_refusee_si_l_import_ne_s_arrete_pas(self):
        connexion = Mock()
        app = self.double(_base_refs=connexion)
        app.pages['references'].arreter_import.return_value = False
        with patch.object(app_module, 'messagebox') as boite:
            AsyDec.fermer_sans_preferences(app)
        boite.showwarning.assert_called_once()
        app.destroy.assert_not_called()                          # pas de destruction sous une tâche active
        self.assertFalse(app._fermeture)
        connexion.close.assert_not_called()
        app.pages['references'].arreter_import.return_value = True
        AsyDec.fermer_sans_preferences(app)                      # une fois arrêtée, la fermeture passe
        app.destroy.assert_called_once()
        connexion.close.assert_called_once()

    def test_persistance_a_la_reouverture(self):
        source = self.fichiers(1)[0]
        premiere = self.double()
        I.importer_lot([source], premiere.base_refs())
        document = S.lister_documents(premiere.base_refs())[0]['id']
        S.enregistrer_statut(premiere.base_refs(), document, 'accepte', preuve='Quittance Q 1')
        AsyDec.fermer_sans_preferences(premiere)
        seconde = self.double()
        documents = S.lister_documents(seconde.base_refs(), statut='accepte')
        self.assertEqual([d['nom_initial'] for d in documents], ['0.xml'])
        detail = S.detail_document(seconde.base_refs(), document)
        self.assertEqual(detail['articles'][0]['taxes'][0]['code'], 'DDI')
        AsyDec.fermer_base_refs(seconde)


class TacheImportTest(Temporaire):
    def test_import_dans_un_fil_avec_sa_propre_connexion(self):
        ouvertes = []
        original = B.ouvrir

        def ouvrir(chemin=None):
            conn = original(chemin)
            ouvertes.append((threading.current_thread().name, conn))
            return conn

        tache = import_fond.TacheImport(self.fichiers(3) + [self.fichiers(1)[0]], self.base)
        with patch.object(B, 'ouvrir', ouvrir):
            tache.demarrer()
            evenements = self.attendre(tache)
        self.assertEqual([nom for nom, _ in ouvertes], [import_fond.NOM_DU_FIL])
        with self.assertRaises(sqlite3.ProgrammingError):        # fermée dans son fil
            ouvertes[0][1].execute('SELECT 1')
        self.assertEqual([e[0] for e in evenements], ['progression'] * 4 + ['fin'])
        bilan = evenements[-1][1]
        self.assertEqual((bilan.etat, bilan.importes, bilan.doublons), ('termine', 3, 1))
        conn = B.ouvrir(self.base)
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM status_events').fetchone()[0], 0)   # rien d'accepté
        conn.close()
        self.assertEqual(fils_d_import(), [])

    def test_fin_publiee_seulement_apres_fermeture(self):
        liberer, commencee = threading.Event(), threading.Event()
        self.addCleanup(liberer.set)
        tache = import_fond.TacheImport(self.fichiers(2), self.base)
        with patch.object(B, 'ouvrir', ouverture_retardee(liberer, commencee)):
            tache.demarrer()
            self.assertTrue(commencee.wait(5))                   # import fini, fermeture en cours
            types = []
            while not tache.evenements.empty():
                types.append(tache.evenements.get_nowait()[0])
            self.assertEqual(types, ['progression', 'progression'])   # pas encore de « fin »
            self.assertTrue(tache.en_cours())
            liberer.set()
            evenements = self.attendre(tache)
        self.assertEqual([e[0] for e in evenements], ['fin'])
        self.assertEqual(evenements[0][1].importes, 2)

    def test_echec_de_fermeture_est_une_erreur_terminale(self):
        liberer, commencee = threading.Event(), threading.Event()
        liberer.set()
        tache = import_fond.TacheImport(self.fichiers(1), self.base)
        with patch.object(B, 'ouvrir', ouverture_retardee(liberer, commencee, OSError('disque débranché'))):
            tache.demarrer()
            evenements = self.attendre(tache)
        self.assertEqual(evenements[-1][0], 'erreur')
        self.assertIn('Fermeture de la base impossible', evenements[-1][1])
        self.assertEqual([e[0] for e in evenements].count('fin'), 0)

    def test_annulation_entre_deux_documents(self):
        tache = import_fond.TacheImport(self.fichiers(4), self.base)
        original = I.importer_fichier

        def puis_annuler(*args, **kwargs):
            resultat = original(*args, **kwargs)
            tache.annuler()
            return resultat

        with patch.object(I, 'importer_fichier', puis_annuler):
            tache.demarrer()
            bilan = self.attendre(tache)[-1][1]
        self.assertEqual((bilan.etat, bilan.importes, bilan.traites), ('annule', 1, 1))
        conn = B.ouvrir(self.base)
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM documents').fetchone()[0], 1)   # déjà validé : gardé
        conn.close()

    def test_arret_borne_puis_fin_propre(self):
        libere, commence = threading.Event(), threading.Event()
        self.addCleanup(libere.set)
        original = I.importer_fichier

        def bloquant(*args, **kwargs):
            commence.set()
            libere.wait(10)
            return original(*args, **kwargs)

        tache = import_fond.TacheImport(self.fichiers(2), self.base)
        with patch.object(I, 'importer_fichier', bloquant):
            tache.demarrer()
            commence.wait(5)
            debut = time.monotonic()
            self.assertFalse(tache.arreter(0.2))                 # attente bornée, pas de blocage
            self.assertLess(time.monotonic() - debut, 2)
            self.assertTrue(tache.en_cours())
            libere.set()
            self.assertTrue(tache.arreter(5))
        self.assertEqual(self.attendre(tache)[-1][1].etat, 'annule')
        self.assertEqual(fils_d_import(), [])

    def test_erreur_rapportee_sans_fil_residuel(self):
        tache = import_fond.TacheImport(self.fichiers(1), self.dossier)   # un dossier n'est pas une base
        tache.demarrer()
        evenements = self.attendre(tache)
        self.assertEqual(evenements[-1][0], 'erreur')
        self.assertEqual(fils_d_import(), [])


class PageTest(Temporaire):
    def setUp(self):
        super().setUp()
        try:
            self.racine = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f'Tk indisponible : {exc}')
        self.racine.withdraw()
        self.addCleanup(gc.collect)                              # après destruction, dans ce fil
        self.addCleanup(self.racine.destroy)
        self.conn = None

        def base_refs():
            if self.conn is None:
                self.conn = B.ouvrir(self.base)
            return self.conn

        self.addCleanup(lambda: self.conn and self.conn.close())
        self.app = SimpleNamespace(base_refs=Mock(side_effect=base_refs), utilisateur='essai', page_active=None)
        self.page = R.PageReferences(self.racine, self.app)

    def pomper(self, condition, delai=10):
        fin = time.monotonic() + delai
        while not condition() and time.monotonic() < fin:
            self.racine.update()
            time.sleep(0.02)
        self.assertTrue(condition())

    def textes_des_boutons(self, widget):
        textes = []
        for enfant in widget.winfo_children():
            if isinstance(enfant, (tk.Button, R.ttk.Button)):
                textes.append(str(enfant.cget('text')))
            textes += self.textes_des_boutons(enfant)
        return textes

    def test_import_et_statuts_autorises_seuls(self):
        self.assertTrue(R.IMPORT_ACTIF)
        self.assertTrue(R.STATUTS_ACTIFS)
        self.assertFalse(R.ACTIONS_ACTIVES)
        boutons = self.textes_des_boutons(self.page)
        for permis in ('Importer des XML…', 'Importer un dossier…', 'Accepté dans SYDONIA…', 'Rejeter…',
                       'Exclure…', 'Remettre « non vérifié »…'):
            self.assertIn(permis, boutons)
        for interdit in ('Corriger', 'Exporter'):
            self.assertFalse([b for b in boutons if interdit in b], interdit)
        self.assertEqual([self.page.onglets.tab(i, 'text') for i in self.page.onglets.tabs()], ['Documents'])
        self.app.base_refs.assert_not_called()                   # rien d'ouvert à la construction

    def test_autres_actions_sans_effet(self):
        for methode in ('calculer_marchandises', 'exporter_marchandises', 'corriger'):
            getattr(self.page, methode)()
        self.page.changer_statut('accepte')                      # aucun document ouvert : rien
        self.app.base_refs.assert_not_called()

    # ------------------------------------------------------------- REF-103
    def ouvrir_un_document(self, n=1):
        self.page._importer(self.fichiers(n))
        self.pomper(lambda: self.page.tache is None)
        premier = self.page.liste.get_children()[-1]
        self.page.liste.selection_set(premier)
        self.page.ouvrir_document()
        return int(premier)

    def soumettre(self, statut, preuve='', commentaire='', date=''):
        """Ouvre le dialogue de statut et le valide comme le ferait l'utilisateur."""
        dialogues = []

        def remplir_et_valider(dialogue):
            dialogue.var_preuve.set(preuve)
            dialogue.var_date.set(date)
            dialogue.commentaire.insert('1.0', commentaire)
            dialogue.enregistrer()
            dialogue.texte_erreur = dialogue.erreur.cget('text') if dialogue.winfo_exists() else ''
            dialogues.append(dialogue)
            if dialogue.winfo_exists():                          # refusé : l'utilisateur annule
                dialogue.destroy()

        with patch.object(self.page, 'wait_window', remplir_et_valider):
            self.page.changer_statut(statut)
        gc.collect()                                             # variables du dialogue fermé
        return dialogues[0] if dialogues else None

    def test_acceptation_sydonia_exige_une_preuve_et_trace_l_auteur(self):
        document = self.ouvrir_un_document()
        refuse = self.soumettre('accepte', preuve='')
        self.assertIsNone(refuse.resultat)
        self.assertIn('preuve', refuse.texte_erreur)
        self.assertEqual(S.historique_statuts(self.conn, document), [])
        accepte = self.soumettre('accepte', preuve='Quittance Q 4437', date='2026-10-02')
        self.assertIsNotNone(accepte.resultat)
        evenement = S.historique_statuts(self.conn, document)[-1]
        self.assertEqual((evenement['nouveau'], evenement['preuve'], evenement['auteur']),
                         ('accepte', 'Quittance Q 4437', 'essai'))   # auteur = utilisateur connecté
        self.assertEqual(self.page.var_statut_doc.get(), 'Accepté')   # fiche rafraîchie
        self.assertIn('1 accepté(s)', self.page.var_compteurs.get())  # statistiques rafraîchies
        self.assertEqual(str(self.page.boutons_statut['accepte'].cget('state')), 'disabled')

    def test_rejet_exclusion_retour_exigent_un_motif(self):
        document = self.ouvrir_un_document()
        for statut in ('rejete', 'exclu'):
            self.assertIsNone(self.soumettre(statut).resultat)
        self.soumettre('rejete', commentaire='Valeur contestée')
        self.assertIsNone(self.soumettre('non_verifie').resultat)
        self.soumettre('non_verifie', commentaire='Erreur de saisie')
        self.soumettre('exclu', commentaire='Dossier atypique')
        self.assertEqual([e['nouveau'] for e in S.historique_statuts(self.conn, document)],
                         ['rejete', 'non_verifie', 'exclu'])         # historique en ajout seul
        self.assertEqual(len(self.page.historique.get_children()), 3)

    def test_statut_persistant_apres_reouverture_et_import_jamais_accepte(self):
        document = self.ouvrir_un_document(3)
        self.soumettre('accepte', preuve='Enregistrement E 12')
        statuts = {d['id']: d['statut'] for d in S.lister_documents(self.conn)}
        self.assertEqual(sorted(statuts.values()), ['accepte', 'non_verifie', 'non_verifie'])
        self.conn.close()
        self.conn = None                                         # relance
        self.assertEqual(S.statut(self.app.base_refs(), document), 'accepte')
        self.page._importer(self.fichiers(5))                    # nouvel import : jamais accepté
        self.pomper(lambda: self.page.tache is None)
        self.assertEqual(S.compteurs(self.conn)['acceptes'], 1)

    def test_statuts_indisponibles_pendant_un_import(self):
        self.ouvrir_un_document()
        libere, commence = threading.Event(), threading.Event()
        original = I.importer_fichier

        def bloquant(*args, **kwargs):
            commence.set()
            libere.wait(10)
            return original(*args, **kwargs)

        self.addCleanup(libere.set)                              # jamais de fil laissé bloqué
        with patch.object(I, 'importer_fichier', bloquant):
            self.page._importer([self.dossier / 'xml' / 'nouveau.xml'])
            commence.wait(5)
            self.assertTrue(all(str(b.cget('state')) == 'disabled' for b in self.page.boutons_statut.values()))
            with patch.object(R, 'DialogueStatut') as dialogue:
                self.page.changer_statut('rejete')
            dialogue.assert_not_called()
            self.assertEqual(self.page.message.titre.cget('text'), 'Import en cours')
            libere.set()
            self.pomper(lambda: self.page.tache is None)
        self.assertEqual(str(self.page.boutons_statut['rejete'].cget('state')), 'normal')

    def test_import_de_fond_depuis_la_page(self):
        self.page._importer(self.fichiers(3) + [self.dossier / 'absent.xml'])
        self.assertIsNotNone(self.page.tache)
        self.pomper(lambda: self.page.tache is None)
        self.assertEqual(self.page.message.titre.cget('text'), 'Import terminé')
        self.assertIn('3 document(s) ajouté(s)', self.page.message.lignes.cget('text'))
        self.assertIn('1 refusé(s)', self.page.message.lignes.cget('text'))
        self.assertEqual(len(self.page.liste.get_children()), 3)
        self.assertIsNone(self.page._suivi)
        self.assertEqual(fils_d_import(), [])
        self.conn.close()
        self.conn = None                                         # relance : les documents sont retrouvés
        self.assertEqual(len(S.lister_documents(self.app.base_refs())), 3)

    def test_suivi_conserve_jusqu_a_l_arret_du_fil(self):
        liberer, commencee = threading.Event(), threading.Event()
        self.addCleanup(liberer.set)
        with patch.object(B, 'ouvrir', ouverture_retardee(liberer, commencee)):
            self.page._importer(self.fichiers(2))
            self.assertTrue(commencee.wait(5))                   # le fil ferme sa connexion
            for _ in range(15):                                  # l'interface tourne pendant ce temps
                self.racine.update()
                time.sleep(0.02)
            self.assertIsNotNone(self.page.tache)                # la tâche n'est pas oubliée
            self.assertTrue(self.page.import_en_cours)
            self.assertIsNotNone(self.page._suivi)
            self.assertNotEqual(self.page.message.titre.cget('text'), 'Import terminé')
            liberer.set()
            self.pomper(lambda: self.page.tache is None)
        self.assertEqual(self.page.message.titre.cget('text'), 'Import terminé')
        self.assertEqual(fils_d_import(), [])

    def test_annulation_depuis_la_page(self):
        libere = threading.Event()
        self.addCleanup(libere.set)
        original = I.importer_fichier

        def lent(*args, **kwargs):
            libere.wait(10)
            return original(*args, **kwargs)

        with patch.object(I, 'importer_fichier', lent):
            self.page._importer(self.fichiers(3))
            self.page.annuler()
            libere.set()
            self.pomper(lambda: self.page.tache is None)
        self.assertEqual(self.page.message.titre.cget('text'), 'Import annulé')
        self.assertLessEqual(len(S.lister_documents(self.conn)), 1)

    def test_arreter_import_borne_et_suivi_annule(self):
        libere, commence = threading.Event(), threading.Event()
        self.addCleanup(libere.set)
        original = I.importer_fichier

        def bloquant(*args, **kwargs):
            commence.set()
            libere.wait(10)
            return original(*args, **kwargs)

        with patch.object(I, 'importer_fichier', bloquant):
            self.page._importer(self.fichiers(2))
            self.assertTrue(commence.wait(5))                    # le fil est occupé sur un document
            self.assertFalse(self.page.arreter_import(0.2))      # encore active : refus
            with self.assertRaisesRegex(ValueError, 'import'):
                with patch.object(self.page, 'arreter_import', return_value=False):
                    self.page.preparer_reset()
            libere.set()
            self.assertTrue(self.page.arreter_import(5))
        self.assertIsNone(self.page.tache)
        self.assertIsNone(self.page._suivi)
        self.assertEqual(fils_d_import(), [])


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


if __name__ == '__main__':
    unittest.main()
