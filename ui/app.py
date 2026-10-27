"""Fenêtre principale d'AsyDec : bandeau du dossier, navigation et pages."""
import json
import os
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import generer
import moteur
import variantes
import catalogue_xml
from ui.selection_xml import choisir as choisir_xml_partage
from ui import theme
import gestion_locale as local
from ui.connexion import demander_connexion
from ui.parametres import PageParametres
from ui.etapes import PageArticles, PageDossier, PageVerifier
from ui.outils import PageEtude, PageHistorique, PageRatios, PageRepartitions
from ui.references import PageReferences
from ui.mediatheque import PageMediatheque
from ui.modeles_generes import PageModelesGeneres
import base_references

PREFERENCES = local.CONFIGURATION / "preferences.json"
ETAPES = [("dossier", "1   Dossier"), ("articles", "2   Articles"), ("verifier", "3   Vérifier et générer")]
OUTILS = [("modeles_generes", "Modèles générés"), ("mediatheque", "Médiathèque XML"), ("references", "Bibliothèque des références"),
          ("repartitions", "Répartitions"), ("ratios", "Récupération des ratios"),
          ("etude", "Étude des XML"), ("historique", "Historique"), ("parametres", "Paramètres")]


def lire_preferences():
    try:
        return json.loads(PREFERENCES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


class AsyDec(tk.Tk):
    def __init__(self, utilisateur):
        super().__init__()
        self.utilisateur = utilisateur
        self.reconnexion = False
        self._fermeture = False
        self._preparations_reset = []
        self.session_verrouillee = False
        self.derniere_activite = time.monotonic()
        self._minuteur_session = None
        erreur_reglages = None
        try:
            self.reglages = local.lire_reglages()
        except ValueError as exc:
            self.reglages = dict(local.DEFAUTS)
            erreur_reglages = str(exc)
        self.title("AsyDec – Déclarations ASYCUDA")
        self.prefs = lire_preferences()
        if not self.reglages['memoriser_recents']:
            self.prefs.pop('recents', None)
            self.prefs.pop('dernier_dossier', None)
        if self.reglages['dossier_xml']:
            self.prefs['dernier_dossier'] = self.reglages['dossier_xml']
        self.geometry(self.prefs.get("geometrie", "1220x800"))
        self.minsize(1040, 700)
        self.configure(bg=theme.FOND)
        theme.appliquer(self)

        self.ratios, self.table_imp = generer.charger_reglages()
        self.base = self.info = self.reference = self.profil = None

        self._bandeau()
        corps = tk.Frame(self, bg=theme.FOND)
        corps.pack(fill="both", expand=True)
        self._navigation(corps)
        contenu = ttk.Frame(corps, padding=(28, 20, 28, 16))
        contenu.pack(side="left", fill="both", expand=True)
        contenu.rowconfigure(0, weight=1)
        contenu.columnconfigure(0, weight=1)
        self.pages = {}
        self._base_refs = None  # connexion SQLite des références, ouverte au premier besoin
        for cle, classe in [("dossier", PageDossier), ("articles", PageArticles), ("verifier", PageVerifier),
                            ("modeles_generes", PageModelesGeneres), ("mediatheque", PageMediatheque), ("references", PageReferences),
                            ("repartitions", PageRepartitions), ("ratios", PageRatios), ("etude", PageEtude),
                            ("historique", PageHistorique), ("parametres", PageParametres)]:
            page = classe(contenu, self)
            page.grid(row=0, column=0, sticky="nsew")
            self.pages[cle] = page

        self.bind_all("<Command-o>", lambda e: self.pages["dossier"].parcourir() if not self.session_verrouillee else None)
        self.bind_all("<Command-Key-1>", lambda e: self.montrer("dossier"))
        self.bind_all("<Command-Key-2>", lambda e: self.montrer("articles"))
        self.bind_all("<Command-Key-3>", lambda e: self.montrer("verifier"))
        self.protocol("WM_DELETE_WINDOW", self.quitter)
        self.enregistrer_preparation_reset(self._preparer_reset_references)
        self.montrer("parametres" if erreur_reglages else self.reglages['page_demarrage'])
        self.appliquer_reglages(self.reglages)
        self.bind_all('<KeyPress>', self._activite, add='+')
        self.bind_all('<ButtonPress>', self._activite, add='+')
        self.bind_all('<Motion>', self._activite, add='+')
        self._minuteur_session = self.after(1000, self._surveiller_session)
        if erreur_reglages:
            self.after_idle(lambda: messagebox.showwarning('Paramètres à vérifier', erreur_reglages, parent=self))

    # ------------------------------------------------------------ structure
    def _bandeau(self):
        bandeau = tk.Frame(self, bg=theme.TEXTE, padx=20, pady=10)
        bandeau.pack(fill="x")
        tk.Label(bandeau, text="AsyDec", font=(theme.POLICE, 17, "bold"), fg="white",
                 bg=theme.TEXTE).pack(side="left")
        theme.bouton(bandeau, 'Verrouiller', self.verrouiller).pack(side='right', padx=4)
        theme.bouton(bandeau, 'Paramètres', lambda: self.montrer('parametres')).pack(side='right', padx=4)
        self.var_bandeau = tk.StringVar(value="Aucun dossier ouvert  ·  ⌘O pour ouvrir un XML de base")
        tk.Label(bandeau, textvariable=self.var_bandeau, font=(theme.POLICE, 12), fg="#D1D5DB",
                 bg=theme.TEXTE).pack(side="left", padx=24)

    def _navigation(self, parent):
        nav = tk.Frame(parent, bg=theme.FOND_LATERAL, width=230, padx=12, pady=18)
        nav.pack(side="left", fill="y")
        nav.pack_propagate(False)
        self.liens = {}
        for titre, liste in (("DÉCLARATION", ETAPES), ("OUTILS", OUTILS)):
            tk.Label(nav, text=titre, font=(theme.POLICE, 10, "bold"), fg=theme.TEXTE_DOUX,
                     bg=theme.FOND_LATERAL, anchor="w").pack(fill="x", pady=(10, 4), padx=8)
            for cle, texte in liste:
                lien = tk.Label(nav, text=texte, font=(theme.POLICE, 13), anchor="w", padx=10, pady=7,
                                bg=theme.FOND_LATERAL, fg=theme.TEXTE, cursor="hand2")
                lien.pack(fill="x", pady=1)
                lien.bind("<Button-1>", lambda e, c=cle: self.montrer(c))
                self.liens[cle] = (lien, texte)
        tk.Label(nav, text="⌘1 ⌘2 ⌘3 : étapes   ·   ⌘O : ouvrir", font=(theme.POLICE, 10),
                 fg=theme.TEXTE_DOUX, bg=theme.FOND_LATERAL).pack(side="bottom", anchor="w", padx=8)

    def montrer(self, cle):
        if self.session_verrouillee:
            return
        if cle in ("articles", "verifier") and not self.base:
            messagebox.showinfo("AsyDec", "Ouvrez d'abord le XML de base du dossier (étape 1).")
            cle = "dossier"
        self.page_active = cle
        for c, (lien, texte) in self.liens.items():
            actif = c == cle
            fait = c == "dossier" and self.base
            lien.configure(text=texte + ("   ✓" if fait else ""),
                           bg=theme.FOND_ACTIF if actif else theme.FOND_LATERAL,
                           fg=theme.ACCENT if actif else theme.TEXTE,
                           font=(theme.POLICE, 13, "bold" if actif else "normal"))
        page = self.pages[cle]
        page.tkraise()
        if hasattr(page, "afficher"):
            page.afficher()

    # ----------------------------------------------------------------- état
    def ouvrir_base(self, chemin):
        """Charge le XML du dossier ; la référence des ratios redevient ce XML."""
        if self.session_verrouillee:
            return False
        try:
            chemin = generer.trouver_base(chemin)
            info = moteur.infos_dossier(moteur.charger(chemin).getroot())
            self.partager_xml([chemin])
            profil = variantes.construire_profil(chemin, self.chemins_xml_disponibles(generation=True))
        except Exception as exc:  # noqa: BLE001 - message montré à l'utilisateur
            messagebox.showerror("XML de base", str(exc))
            return False
        self.base, self.info, self.reference, self.profil = chemin, info, chemin, profil
        recents = [chemin] + [p for p in self.prefs.get("recents", []) if p != chemin]
        if self.reglages['memoriser_recents']:
            self.prefs["recents"] = recents[:8]
            self.prefs["dernier_dossier"] = os.path.dirname(chemin)
        self._ecrire_prefs()
        self.var_bandeau.set(
            f"{info['importateur']}  ·  réf. {info['reference'] or '—'}  ·  camion {info['camion'] or '—'}"
            f"  ·  {theme.nombre(info['fob'], 2)} USD  ·  {theme.nombre(info['poids'])} kg  ·  {info['colis']} colis")
        self.pages["articles"].nouvelle_base()
        return True

    def fermer_dossier(self, confirmer=True):
        """Décharge le dossier actif ; les originaux, archives et exports restent intacts."""
        if self.session_verrouillee:
            return False
        if confirmer and self.base and not messagebox.askyesno('Fermer le XML chargé',
            'Fermer ce dossier et vider les saisies non enregistrées ?\n\n'
            'Le XML reste disponible dans la bibliothèque. Les originaux et fichiers exportés sont conservés.', parent=self):
            return False
        self.base = self.info = self.reference = self.profil = None
        articles = self.pages['articles']
        if articles._attente:
            articles.after_cancel(articles._attente)
            articles._attente = None
        articles.var_fob_total.set('')
        articles.var_colis_total.set('')
        articles.remplir(None, mode='RATIOS')
        articles.message.vider()
        for label in articles.ratios:
            label.configure(text='')
        for label in articles.etats:
            label.configure(text='')
        for label in articles.totaux:
            label.configure(text='')
        verifier = self.pages['verifier']
        verifier.resultat = verifier.fichier = None
        verifier.finder.pack_forget()
        verifier.tableau.delete(*verifier.tableau.get_children())
        verifier.generer.configure(state='disabled')
        verifier.regenerer_bouton.configure(state='disabled')
        verifier.var_fichier.set('')
        for carte in verifier.cartes.values():
            carte.definir('—')
        self.var_bandeau.set('Aucun dossier ouvert · choisissez un XML déjà disponible ou ouvrez un nouveau fichier')
        self.montrer('dossier')
        return True

    def partager_xml(self, chemins):
        """Conserve les fichiers pour les autres pages, sans leur attribuer une acceptation."""
        if self.session_verrouillee:
            return
        try:
            _, erreurs = catalogue_xml.partager(self.base_refs(), chemins)
        except Exception as exc:
            erreurs = [str(exc)]
        if erreurs:
            messagebox.showwarning('Partage XML incomplet',
                'Certains fichiers ne sont pas disponibles dans la bibliothèque :\n'+'\n'.join(erreurs[:8]), parent=self)
        return erreurs

    def xml_disponibles(self, generation=False):
        supplementaires = ([self.base] if self.base else []) + list(variantes.modeles())
        documents = catalogue_xml.lister(self.base_refs(), supplementaires, generation=generation)
        return [d for d in documents if d['articles'] in (None, 8)] if generation else documents

    def chemins_xml_disponibles(self, generation=False):
        return [d['chemin'] for d in self.xml_disponibles(generation)]

    def choisir_xml_disponibles(self, multiple=False, generation=False):
        try:
            documents = self.xml_disponibles(generation)
        except Exception as exc:
            messagebox.showerror('XML disponibles', str(exc), parent=self)
            return []
        if not documents:
            messagebox.showinfo('XML disponibles', 'Aucun XML disponible. Chargez un dossier ou importez des XML dans la bibliothèque.', parent=self)
            return []
        return choisir_xml_partage(self, documents, multiple=multiple, retirer=self.retirer_xml)

    def retirer_xml(self, documents):
        if self.session_verrouillee:
            raise ValueError('La session est verrouillée.')
        catalogue_xml.retirer(documents,self.utilisateur)
        self.prefs['recents'] = [p for p in self.prefs.get('recents', []) if not catalogue_xml.est_retire(p)]
        self._ecrire_prefs()
        if any(p and catalogue_xml.est_retire(p) for p in (self.base,self.reference)):
            self.fermer_dossier(confirmer=False)
        elif self.base:
            self.choisir_reference(self.reference)
        # Les sélections dérivées ne doivent pas continuer à utiliser un XML retiré.
        repartitions=self.pages['repartitions']
        repartitions.propositions=[]
        repartitions.liste.delete(*repartitions.liste.get_children())
        repartitions.detail.delete(*repartitions.detail.get_children())
        repartitions.selection_modeles=None
        ratios=self.pages['ratios']
        ratios.chemins=[p for p in ratios.chemins if not catalogue_xml.est_retire(p)]
        if ratios.chemins:
            ratios.calculer()
        else:
            ratios.vider()
        self.pages['etude'].afficher()

    def choisir_reference(self, chemin, profil=None):
        try:
            if catalogue_xml.est_retire(chemin):
                raise ValueError('Ce XML a été retiré de la liste. Rechargez-le volontairement pour le réutiliser.')
            profil = profil or variantes.construire_profil(chemin, self.chemins_xml_disponibles(generation=True))
            if variantes.signature(self.base) != profil["signature"]:
                raise ValueError("Ce modèle n'a pas les mêmes articles (codes et désignations) que le dossier.")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Référence des ratios", str(exc))
            return False
        self.reference, self.profil = chemin, profil
        self.pages["articles"].actualiser()
        return True

    def calculer(self, enregistrer=False):
        """Calcule la déclaration avec les valeurs de l'étape 2. Lève ValueError si impossible."""
        if self.session_verrouillee:
            raise ValueError('La session est verrouillée.')
        v = self.pages["articles"].valeurs()
        registre = generer.lire_registre()
        res = generer.produire(
            self.base, v["poids"], self.profil["ratios"], self.table_imp, registre,
            mode=v["mode"], fob_total=v["fob_total"], fob_saisis=v["fob"],
            colis_total=v["colis_total"], colis_saisis=v["colis"],
            enregistrer=enregistrer, profil=self.profil)
        if enregistrer:
            generer.ecrire_registre(registre)
        return res

    def _ecrire_prefs(self):
        try:
            if not self.reglages['memoriser_recents']:
                self.prefs.pop('recents', None)
                self.prefs.pop('dernier_dossier', None)
            local._ecrire_json(PREFERENCES, self.prefs)
        except OSError:
            pass

    def quitter(self):
        if self._fermeture:
            return
        self.prefs["geometrie"] = self.geometry()
        self._ecrire_prefs()
        self.fermer_sans_preferences()

    def fermer_sans_preferences(self):
        if self._fermeture:
            return
        if not AsyDec._arreter_import_references(self):
            messagebox.showwarning("Import en cours", "Un import de références ne s'est pas arrêté dans les "
                                   "5 secondes. Fermeture annulée : réessayez dans un instant.", parent=self)
            return
        self._fermeture = True
        if self._minuteur_session is not None:
            self.after_cancel(self._minuteur_session)
            self._minuteur_session = None
        AsyDec.fermer_base_refs(self)  # appel explicite : fonctionne aussi sur un objet de test minimal
        self.destroy()

    def _arreter_import_references(self):
        """Avant de détruire la fenêtre : arrête la tâche d'import (5 s au plus). False si elle tourne encore."""
        page = getattr(self, "pages", {}).get("references")
        return page is None or page.arreter_import(5.0)

    def base_refs(self):
        """Connexion à la base des références, ouverte au premier besoin dans le fil Tkinter."""
        if self._base_refs is None:
            self._base_refs = base_references.ouvrir()
        return self._base_refs

    def fermer_base_refs(self):
        """Fermeture idempotente ; la base se rouvrira au prochain besoin."""
        if getattr(self, "_base_refs", None) is not None:
            self._base_refs.close()
            self._base_refs = None

    def _preparer_reset_references(self):
        """Callback de reset (CFG-001 / REF-001) : refuse si un import tourne, sinon ferme la base."""
        self.pages["references"].preparer_reset()
        self.fermer_base_refs()

    def enregistrer_preparation_reset(self, callback):
        """Raccordement pour les services : arrêter les tâches et fermer les connexions."""
        if not callable(callback):
            raise TypeError('La préparation du reset doit être une fonction.')
        self._preparations_reset.append(callback)

    def preparer_reset(self):
        for callback in self._preparations_reset:
            if callback() is False:
                raise ValueError('Un service refuse le reset : arrêtez ses opérations en cours.')

    def appliquer_reglages(self, reglages):
        self.reglages = dict(reglages)
        nom = reglages['organisation']
        self.title('AsyDec' + (' — ' + nom if nom else '') + ' — ' + self.utilisateur)
        if not reglages['memoriser_recents']:
            self.prefs.pop('recents', None)
            self.prefs.pop('dernier_dossier', None)
        if reglages['dossier_xml']:
            self.prefs['dernier_dossier'] = reglages['dossier_xml']
        self._ecrire_prefs()

    def _activite(self, event=None):
        if not self.session_verrouillee:
            self.derniere_activite = time.monotonic()

    def _surveiller_session(self):
        self._minuteur_session = None
        minutes = self.reglages['verrouillage_minutes']
        if not self.session_verrouillee and minutes and time.monotonic()-self.derniere_activite >= minutes*60:
            self.verrouiller()
        if not self._fermeture:
            self._minuteur_session = self.after(1000, self._surveiller_session)

    def verrouiller(self):
        if self.session_verrouillee:
            return
        self.session_verrouillee = True
        parametres = self.pages['parametres']
        for variable in (parametres.ancien, parametres.nouveau, parametres.confirmer, parametres.mdp_reset):
            variable.set('')
        self.withdraw()
        try:
            utilisateur = demander_connexion(self)
        except Exception:
            self.quitter()
            raise
        if utilisateur is None:
            self.quitter()
            return
        self.session_verrouillee = False
        self.derniere_activite = time.monotonic()
        self.deiconify()
        self.lift()

    def deconnecter(self):
        if messagebox.askyesno('Se déconnecter', 'Fermer la session ? Les saisies non enregistrées seront perdues.', parent=self):
            self.reconnexion = True
            self.quitter()


def main():
    while True:
        utilisateur = demander_connexion()
        if utilisateur is None:
            return
        app = AsyDec(utilisateur)
        app.mainloop()
        if not app.reconnexion:
            return
