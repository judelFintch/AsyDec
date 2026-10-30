"""Gestion dynamique des articles de l'étape Articles : une barre et l'édition dans le tableau.

« Modifier les articles » transforme la colonne Marchandise en champs de recherche (position
tarifaire ou nom), avec ✕ pour retirer une ligne et « + Ajouter » pour en ajouter une. Chaque choix
s'applique aussitôt : position, désignation, origine, taxes, ratio et contrôle de l'article sont
repris pour le calcul et la génération, dans une copie du XML du dossier.
"""
import tkinter as tk
from tkinter import ttk

from asydec.calcul import articles as gestion_articles
from asydec.ui import theme


class PanneauArticles(tk.Frame):
    def __init__(self, parent, app, quand_change):
        super().__init__(parent, bg=theme.FOND_ACTIF, highlightthickness=1, highlightbackground=theme.ACCENT,
                         padx=12, pady=6)
        self.app, self.quand_change = app, quand_change
        self.catalogue, self.cles_dossier, self.selection = {}, [], []
        self.choix, self.croix, self.noms = [], [], []
        self.edition = False

        barre = tk.Frame(self, bg=theme.FOND_ACTIF)
        barre.pack(fill="x")
        tk.Label(barre, text="Gestion dynamique des articles", bg=theme.FOND_ACTIF, fg=theme.ACCENT,
                 font=(theme.POLICE, 13, "bold")).pack(side="left")
        self.var_etat = tk.StringVar()
        tk.Label(barre, textvariable=self.var_etat, bg=theme.FOND_ACTIF, fg=theme.TEXTE_DOUX,
                 font=(theme.POLICE, 11)).pack(side="left", padx=12)
        self.bouton_composition = theme.bouton(barre, 'Composer un modèle…', self.composer_modele)
        self.bouton_composition.pack(side='right', padx=6)
        self.bouton_edition = theme.bouton(barre, "Modifier les articles", self.basculer_edition)
        self.bouton_edition.pack(side="right")
        self.bouton_dossier = theme.bouton(barre, "Revenir aux articles du dossier", self.revenir_au_dossier)
        self.ajout = ttk.Combobox(barre, width=34)
        self.ajout.bind("<KeyRelease>", lambda e: self.filtrer(self.ajout, e))
        self.ajout.bind("<<ComboboxSelected>>", lambda e: self.ajouter())
        self.ajout.bind("<Return>", lambda e: self.ajouter(saisie=True))
        self.etiquette_ajout = tk.Label(barre, text="+ Ajouter :", bg=theme.FOND_ACTIF, fg=theme.TEXTE,
                                        font=(theme.POLICE, 11, "bold"))
        self.var_detail = tk.StringVar()
        self.detail = tk.Label(self, textvariable=self.var_detail, bg=theme.FOND_ACTIF, fg=theme.TEXTE_DOUX,
                               font=(theme.POLICE, 11), anchor="w")
        self.afficher()

    # ------------------------------------------------------------- tableau
    def decorer(self, grille, noms):
        """Ajoute à chaque ligne du tableau un champ de choix et ✕, visibles en mode modification."""
        self.noms, self.choix, self.croix = list(noms), [], []
        for k in range(len(noms)):
            choix = ttk.Combobox(grille, width=34)
            choix.grid(row=k + 1, column=1, padx=5, sticky="w")
            choix.bind("<KeyRelease>", lambda e, k=k: self.filtrer(self.choix[k], e))
            choix.bind("<<ComboboxSelected>>", lambda e, k=k: self.choisir(k))
            choix.bind("<Return>", lambda e, k=k: self.choisir(k, saisie=True))
            choix.bind("<FocusIn>", lambda e, k=k: self.montrer_detail(k))
            croix = ttk.Button(grille, text="✕", width=2, command=lambda k=k: self.retirer(k))
            croix.grid(row=k + 1, column=7, padx=(0, 5))
            choix.grid_remove()
            croix.grid_remove()
            self.choix.append(choix)
            self.croix.append(croix)
        self.afficher()

    # ------------------------------------------------------------ affichage
    def disponible(self):
        """Friperie : dossiers à 8 articles. Divers : entièrement dynamique, quel que soit le nombre d'articles."""
        profil = getattr(self.app, "profil", None)
        if not (getattr(self.app, "base_dossier", None) and profil and self.cles_dossier):
            return False
        if getattr(self.app, "module_travail", "friperie") == "divers":
            return True
        return not profil.get("dynamique") and len(self.cles_dossier) == gestion_articles.NOMBRE_ARTICLES

    def preparer(self):
        """Nouveau dossier : les articles du dossier, sans modification en cours."""
        self.edition = False
        self.cles_dossier = []
        try:
            if getattr(self.app, "base_dossier", None):
                self.cles_dossier = gestion_articles.articles_du_xml(self.app.base_dossier)
                if self.disponible():
                    self.catalogue = self.app.catalogue_articles()
        except Exception as exc:  # noqa: BLE001 - la page reste utilisable sans gestion dynamique
            self.cles_dossier = []
            self.var_etat.set(f"Catalogue des articles indisponible : {exc}")
        self.selection = (gestion_articles.articles_du_xml(self.app.base)
                          if getattr(self.app, 'profil', None) and self.app.profil.get('composition_fixe')
                          else list(self.cles_dossier))
        self.afficher()

    def afficher(self):
        actif = self.disponible()
        self.bouton_composition.configure(state='normal' if getattr(self.app, 'base', None)
            and getattr(self.app, 'module_travail', 'friperie') == 'friperie' else 'disabled')
        self.edition = self.edition and actif
        changes = self.selection != self.cles_dossier
        if not actif:
            if getattr(self.app, 'profil', None) and self.app.profil.get('composition_fixe'):
                self.var_etat.set(f'{len(self.selection)} articles · composition à ratios fixes')
            elif not self.var_etat.get().startswith("Catalogue"):
                self.var_etat.set("Disponible pour les dossiers à 8 articles de la friperie")
        elif self.edition:
            self.var_etat.set(f"{len(self.selection)} article(s) · tapez une position tarifaire ou un nom · ✕ retire une ligne")
        elif changes:
            self.var_etat.set(f"{len(self.selection)} article(s) · composition modifiée par rapport au dossier")
        else:
            self.var_etat.set(f"{len(self.selection)} articles du dossier")
        self.bouton_edition.configure(state="normal" if actif else "disabled",
                                      text="Terminer" if self.edition else "Modifier les articles")
        for widget in (self.ajout, self.etiquette_ajout, self.bouton_dossier):
            widget.pack_forget()
        if self.edition:
            self.ajout.pack(side="right", padx=(4, 12))
            self.etiquette_ajout.pack(side="right")
            self.ajout.set("")
            self.ajout["values"] = [gestion_articles.libelle(e) for e in self.catalogue.values() if e["cle"] not in self.selection]
            self.detail.pack(fill="x", pady=(4, 0))
        else:
            self.detail.pack_forget()
        if changes and actif:
            self.bouton_dossier.pack(side="right", padx=8)
        tous = [gestion_articles.libelle(e) for e in self.catalogue.values()]
        for k, (nom, choix, croix) in enumerate(zip(self.noms, self.choix, self.croix)):
            if self.edition and k < len(self.selection):
                entree = self.catalogue.get(self.selection[k])
                choix.set(gestion_articles.libelle(entree) if entree else " · ".join(self.selection[k]))
                choix["values"] = tous
                nom.grid_remove()
                choix.grid()
                croix.grid()
            else:
                choix.grid_remove()
                croix.grid_remove()
                nom.grid()

    def montrer_detail(self, k):
        entree = self.catalogue.get(self.selection[k]) if k < len(self.selection) else None
        self.var_detail.set(f"Ligne {k + 1} · {entree['code']} · {gestion_articles.resume(entree)}" if entree else "")

    # ---------------------------------------------------------------- choix
    def composer_modele(self):
        if self.app.session_verrouillee or getattr(self.app, 'module_travail', 'friperie') != 'friperie':
            return
        from asydec.ui.composition import FenetreComposition
        return FenetreComposition(self)

    def basculer_edition(self):
        self.edition = not self.edition
        self.var_detail.set("")
        self.afficher()

    def filtrer(self, champ, evenement):
        if evenement.keysym in ("Return", "Up", "Down", "Escape"):
            return
        trouves = gestion_articles.rechercher(self.catalogue, champ.get())
        champ["values"] = [gestion_articles.libelle(e) for e in trouves]

    def _cle(self, champ, saisie):
        """Article désigné par le champ : choisi dans la liste, ou seul à correspondre à la saisie."""
        par_libelle = {gestion_articles.libelle(e): e["cle"] for e in self.catalogue.values()}
        if champ.get() in par_libelle:
            return par_libelle[champ.get()]
        trouves = gestion_articles.rechercher(self.catalogue, champ.get()) if saisie else []
        if len(trouves) == 1:
            return trouves[0]["cle"]
        if saisie:
            self.var_detail.set(f"{len(trouves)} article(s) correspondent : précisez ou choisissez dans la liste")
        return None

    def choisir(self, k, saisie=False):
        cle = self._cle(self.choix[k], saisie)
        if cle is None or cle == self.selection[k]:
            if not saisie:
                self.afficher()
            return
        self.appliquer(self.selection[:k] + [cle] + self.selection[k + 1:])

    def retirer(self, k):
        self.appliquer(self.selection[:k] + self.selection[k + 1:])

    def ajouter(self, saisie=False):
        cle = self._cle(self.ajout, saisie)
        if cle is not None:
            self.appliquer(self.selection + [cle])

    def revenir_au_dossier(self):
        self.appliquer(self.cles_dossier)

    def appliquer(self, cles):
        anciennes = self.selection
        if self.app.composer_articles(cles):
            self.selection = list(cles)
            self.quand_change(anciennes, self.selection)
        self.afficher()
