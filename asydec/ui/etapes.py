"""Les trois étapes d'une déclaration : dossier, articles, vérification et génération."""
import os
import subprocess
import tkinter as tk
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from asydec.calcul import moteur
from asydec.calcul import variantes
from asydec.declarations import generer
from asydec.ui import theme
from asydec.ui.modeles_generes import classer_propositions, texte_risque
from asydec.ui.articles_dynamiques import PanneauArticles
from asydec.ui.importateurs import importateur_choisi, selecteur
from asydec.ui import intentions
from asydec.ui.intentions import intention_choisie
from asydec.ui import compteur
from asydec.ui import plaque
from asydec.ui import taux_change
from asydec.ui.taux_change import taux_choisi
from asydec.ui.theme import nombre
from asydec.systeme.journal import erreur_ignoree
from asydec.systeme import espace_travail

REFERENCE_DOSSIER = "Le XML du dossier (par défaut)"


def lire(entree):
    texte = entree.get().strip()
    return generer.nombre(texte) if texte else None


def remplir(entree, valeur):
    etat = str(entree.cget("state"))
    entree.configure(state="normal")
    entree.delete(0, "end")
    if valeur is not None:
        entree.insert(0, f"{valeur:.15g}" if isinstance(valeur, float) else str(valeur))
    entree.configure(state=etat)


def plaque_saisie(app):
    """Plaque facultative de l'étape Dossier (vide si absente, y compris sur une application de test)."""
    lire = getattr(app, "plaque_saisie", None)
    return lire() if callable(lire) else ""


def tirages(intention):
    """Nombre de répartitions tirées : davantage quand une intention doit les départager."""
    return 8 if intention == "proche" else 30


def declarations_reelles(profil):
    """Répartitions des déclarations réelles (XML comparés) retenues comme références du profil."""
    return [{'id': r['nom'], 'poids': r['info']['poids_articles'], 'fob': r['info']['fob_articles'],
             'colis': r['info']['colis_articles']}
            for r in (profil or {}).get('references', ()) if r.get('confiance') == variantes.CONFIANCE_REELLE]


def texte_inspiration(proposition):
    """« Inspirée de … » : la référence dont la proposition est la plus proche, et sa nature."""
    if not proposition.get('reference_proche'):
        return ""
    return (f" Inspirée de : {proposition.get('source_proche', 'référence').lower()} "
            f"« {proposition['reference_proche']} » ({nombre(proposition.get('proximite'), 1)} % de ressemblance).")


def choisir_proposition(app, propositions, profil, total_fob, total_colis, bons=()):
    """(proposition, alertes, guide) : parmi les moins risquées, la meilleure pour l'intention choisie ;
    pour « le plus proche », la plus ressemblante aux déclarations réelles comparées, sinon aux bons
    modèles ★ s'il y en a."""
    from asydec.calcul import anomalies
    intention = intention_choisie(app)
    if intention == "proche":
        classees = classer_propositions(app, propositions, base=app.base, profil=profil)
        meilleur = anomalies.niveau(classees[0][1])
        moins_risquees = [v for v, a in classees if anomalies.niveau(a) == meilleur]
        alertes = {id(v): a for v, a in classees}
        reelles = declarations_reelles(profil)
        if reelles:
            proposition, modele, proximite = variantes.plus_proche(moins_risquees, reelles)
            guide = (f"Guidée par vos déclarations réelles ({len(reelles)}) : la plus proche de « {modele['id']} » "
                     f"({nombre(proximite, 1)} % de ressemblance).")
        elif bons:
            proposition, modele, proximite = variantes.plus_proche(moins_risquees, bons)
            guide = f"Guidée par vos bons modèles ★ : la plus proche du n° {modele['id']} ({nombre(proximite, 1)} % de ressemblance)."
        else:
            proposition = moins_risquees[0]
            guide = "Aucune déclaration réelle comparée ni bon modèle ★ pour ces articles : tirage libre."
        return proposition, alertes[id(proposition)], guide

    def taxes(v):
        try:
            return generer.produire(app.base, v["poids"], profil["ratios"], app.table_imp, {}, mode="SAISI",
                fob_total=total_fob, fob_saisis=v["fob"], colis_total=int(total_colis), colis_saisis=v["colis"],
                enregistrer=False, profil=profil, taux=taux_choisi(app))["resume"]["taxes_totales"]
        except Exception:  # noqa: BLE001 - une répartition incalculable passe en dernier
            return float("inf")

    def cle(v):
        return variantes.score_intention(v, profil, intention, taxes(v) if intention == "taxes_basses" else None)

    proposition, alertes = classer_propositions(app, propositions, base=app.base, profil=profil, cle=cle)[0]
    guide = (f"Intention « {variantes.INTENTIONS[intention]} » : la meilleure de {len(propositions)} "
             "répartitions valides, parmi les moins risquées." + texte_inspiration(proposition))
    return proposition, alertes, guide


def pied(page):
    """Barre du bas : boutons de navigation alignés à droite."""
    barre = ttk.Frame(page)
    barre.pack(side="bottom", fill="x", pady=(14, 0))
    ttk.Separator(page).pack(side="bottom", fill="x", pady=(10, 0))
    return barre


# ==========================================================================
# 1. Dossier
# ==========================================================================
class PageDossier(ttk.Frame):
    CHAMPS = [("importateur", "Importateur"), ("code", "Code"), ("reference", "Référence"),
              ("manifeste", "Manifeste"), ("camion", "Camion"), ("taux", "Taux USD → CDF"),
              ("fob", "FOB total"), ("poids", "Poids total"), ("colis", "Colis"), ("articles", "Articles")]

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        theme.entete_page(self, "Dossier", "Ouvrez le XML SYDONIA du dossier : il fournit l'importateur, "
                          "les articles, le taux et les frais. Il n'est jamais modifié.")
        haut = ttk.Frame(self)
        haut.pack(fill="x")
        theme.bouton(haut, "Ouvrir un nouveau XML…", self.parcourir, principal=True).pack(side="left")
        theme.bouton(haut, "XML déjà disponibles…", self.choisir_disponible).pack(side="left", padx=8)
        ttk.Label(haut, text="  ou double-cliquez un fichier récent ci-dessous", style="Doux.TLabel").pack(side="left")

        ligne_importateur = ttk.Frame(self)
        ligne_importateur.pack(fill="x", pady=(12, 0))
        self.choix_importateur = selecteur(ligne_importateur, app)
        ttk.Label(ligne_importateur, text="Avant ou après l'ouverture. Base tenue à jour depuis vos XML.",
                  style="Doux.TLabel").pack(side="left")

        ttk.Label(self, text="Dossier ouvert", style="Section.TLabel").pack(anchor="w", pady=(20, 6))
        grille = ttk.Frame(self)
        grille.pack(fill="x")
        self.valeurs = {}
        for k, (cle, libelle) in enumerate(self.CHAMPS):
            ligne, colonne = divmod(k, 2)
            ttk.Label(grille, text=libelle, style="Doux.TLabel", width=16).grid(row=ligne, column=colonne * 2, sticky="w", pady=2)
            var = tk.StringVar(value="—")
            ttk.Label(grille, textvariable=var, font=(theme.POLICE, 12)).grid(
                row=ligne, column=colonne * 2 + 1, sticky="w", padx=(0, 40), pady=2)
            self.valeurs[cle] = var

        ligne_plaque = ttk.Frame(self)
        ligne_plaque.pack(fill="x", pady=(12, 0))
        ttk.Label(ligne_plaque, text="Plaque à inscrire (facultatif)", style="Doux.TLabel").pack(side="left")
        self.var_plaque = plaque.variable(app)
        ttk.Entry(ligne_plaque, textvariable=self.var_plaque, width=28).pack(side="left", padx=10)
        ttk.Label(ligne_plaque, text="Vide : le XML garde la plaque du dossier. Exemple : T546ECQ/T618ECT. "
                  "Modifiable aussi aux étapes Articles et Vérifier, et dans Répartitions.",
                  style="Doux.TLabel").pack(side="left")

        ttk.Label(self, text="Référence des ratios", style="Section.TLabel").pack(anchor="w", pady=(20, 4))
        ttk.Label(self, text="Base classique à 8 articles ou modèle dynamique selon le XML et le module. Références : "
                  "modèles aux mêmes positions tarifaires et marchandises.", style="Doux.TLabel").pack(anchor="w")
        self.var_reference = tk.StringVar(value=REFERENCE_DOSSIER)
        self.choix = ttk.Combobox(self, textvariable=self.var_reference, state="readonly", width=70)
        self.choix.pack(anchor="w", pady=6)
        self.choix.bind("<<ComboboxSelected>>", self.changer_reference)

        barre = pied(self)
        self.suivant = theme.bouton(barre, "Continuer  →  Articles", lambda: app.montrer("articles"), principal=True)
        self.suivant.pack(side="right")
        self.fermer = theme.bouton(barre, "Fermer le XML chargé", app.fermer_dossier)
        self.fermer.pack(side="left")

        ttk.Label(self, text="Fichiers récents", style="Section.TLabel").pack(anchor="w", pady=(16, 6))
        cadre, self.recents = theme.tableau(self, [("fichier", "Fichier", 420, "w"), ("dossier", "Dossier", 380, "w")], 5)
        cadre.pack(fill="both", expand=True)
        self.recents.bind("<Double-1>", self.ouvrir_recent)

    def afficher(self):
        self.recents.delete(*self.recents.get_children())
        for chemin in self.app.prefs.get("recents", []):
            if os.path.exists(chemin):
                self.recents.insert("", "end", iid=chemin, values=(Path(chemin).name, Path(chemin).parent.name))
        documents = self.app.xml_disponibles(generation=True)
        self.modeles = [Path(d['chemin']) for d in documents]
        self.choix.configure(values=[REFERENCE_DOSSIER] + [d['nom'] for d in documents])
        self.suivant.configure(state="normal" if self.app.base else "disabled")
        self.fermer.configure(state="normal" if self.app.base else "disabled")
        self.choix_importateur.configure(values=self.app.importateurs_proposes())
        self.remplir_infos()

    def remplir_infos(self):
        i = self.app.info
        if not i:
            for valeur in self.valeurs.values():
                valeur.set('—')
            self.var_reference.set(REFERENCE_DOSSIER)
            return
        textes = {"importateur": i["importateur"], "code": i["code"], "reference": i["reference"],
                  "manifeste": i["manifeste"], "camion": i["camion"], "taux": nombre(i["taux"], 2),
                  "fob": f"{nombre(i['fob'], 2)} USD", "poids": f"{nombre(i['poids'])} kg",
                  "colis": str(i["colis"]), "articles": str(len(i["fob_articles"]))}
        choisi = importateur_choisi(self.app)
        if choisi and choisi["code"] != i["code"]:
            textes.update(importateur=f"{choisi['nom']}  (XML : {i['importateur'] or '—'})", code=choisi["code"])
        for cle, var in self.valeurs.items():
            var.set(textes[cle] or "—")

    def choisir_disponible(self):
        chemins = self.app.choisir_xml_disponibles()
        if chemins:
            self._ouvrir(chemins[0])

    def parcourir(self):
        chemin = filedialog.askopenfilename(
            initialdir=self.app.prefs.get("dernier_dossier", espace_travail.dossier_ouverture()), title="XML de base du dossier",
            filetypes=[("Déclarations XML", "*.xml"), ("Tous", "*.*")])
        if chemin:
            self._ouvrir(chemin)

    def ouvrir_recent(self, _evenement=None):
        if self.recents.selection():
            self._ouvrir(self.recents.selection()[0])

    def _ouvrir(self, chemin):
        if self.app.ouvrir_base(chemin):
            self.var_reference.set(REFERENCE_DOSSIER)
            self.app.montrer("dossier")

    def changer_reference(self, _evenement=None):
        if not self.app.base:
            self.var_reference.set(REFERENCE_DOSSIER)
            return
        k = self.choix.current()
        chemin = self.app.base if k <= 0 else str(self.modeles[k - 1])
        if not self.app.choisir_reference(chemin):
            self.var_reference.set(REFERENCE_DOSSIER)
            self.app.choisir_reference(self.app.base)


# ==========================================================================
# 2. Articles
# ==========================================================================
class PageArticles(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._attente = None
        self.deja_vues, self.compteurs = {}, {}
        theme.entete_page(self, "Articles", "Saisissez ou importez les poids du colisage. Le FOB est calculé "
                          "par les ratios, ou saisi article par article. Colis vides = répartition automatique.")

        outils = ttk.Frame(self)
        outils.pack(fill="x")
        theme.bouton(outils, "Importer un Excel…", self.importer_excel).pack(side="left")
        theme.bouton(outils, "Reprendre la base", self.reprendre_base).pack(side="left", padx=6)
        theme.bouton(outils, "Ajuster au poids total…", self.ajuster_poids).pack(side="left")
        self.regenerer_bouton = theme.bouton(outils, "Générer une autre répartition", self.regenerer, principal=True)
        self.regenerer_bouton.pack(side="left", padx=6)
        intentions.selecteur(outils, app)
        theme.bouton(outils, "Vider", self.vider).pack(side="right")
        self.var_possibles = tk.StringVar()
        ttk.Label(self, textvariable=self.var_possibles, style="Doux.TLabel", wraplength=1100).pack(anchor="w", pady=(6, 0))

        reglages = ttk.Frame(self)
        reglages.pack(fill="x", pady=(16, 8))
        self.var_mode = tk.StringVar(value="RATIOS")
        ttk.Radiobutton(reglages, text="FOB calculé par les ratios", value="RATIOS", variable=self.var_mode,
                        command=self.changer_mode).pack(side="left")
        ttk.Radiobutton(reglages, text="FOB saisis", value="SAISI", variable=self.var_mode,
                        command=self.changer_mode).pack(side="left", padx=(12, 30))
        self.var_fob_total, self.var_colis_total = tk.StringVar(), tk.StringVar()
        for texte, var in (("FOB total (USD)", self.var_fob_total), ("Colis total", self.var_colis_total)):
            ttk.Label(reglages, text=texte).pack(side="left", padx=(12, 4))
            e = ttk.Entry(reglages, textvariable=var, width=11, justify="right")
            e.pack(side="left")
            e.bind("<KeyRelease>", self.planifier)

        inscrits = ttk.Frame(self)
        inscrits.pack(fill="x", pady=(0, 8))
        plaque.selecteur(inscrits, app)
        taux_change.selecteur(inscrits, app).bind("<KeyRelease>", self.planifier, add="+")

        self.panneau = PanneauArticles(self, app, self.articles_changes)
        self.panneau.pack(fill="x", pady=(4, 6))

        zone = ttk.Frame(self)
        zone.pack(fill='both', expand=True, pady=(6, 0))
        canvas = tk.Canvas(zone, height=260, highlightthickness=0, bg=theme.FOND)
        defil = ttk.Scrollbar(zone, orient='vertical', command=canvas.yview)
        horizontal = ttk.Scrollbar(zone, orient='horizontal', command=canvas.xview)
        canvas.configure(yscrollcommand=defil.set, xscrollcommand=horizontal.set)
        horizontal.pack(side='bottom', fill='x')
        defil.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        self.grille = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=self.grille, anchor='nw')
        self.grille.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        self.construire_lignes(8)

        # Synthèse de la répartition affichée : totaux et taxes estimées, comparées à la précédente.
        synthese = ttk.Frame(self)
        synthese.pack(fill="x", pady=(14, 0))
        self.cartes = {}
        for k, (cle, libelle) in enumerate((("poids", "Poids total · kg"), ("fob", "FOB total · USD"),
                                            ("colis", "Colis"), ("taxes", "Total taxes estimé · CDF"))):
            synthese.columnconfigure(k, weight=2 if cle == "taxes" else 1, uniform="synthese")
            carte = theme.Carte(synthese, libelle, detail=True,
                                style_valeur="ValeurAccent.TLabel" if cle == "taxes" else "Valeur.TLabel")
            carte.grid(row=0, column=k, sticky="nsew", padx=(0 if k == 0 else 8, 0))
            self.cartes[cle] = carte
        self.var_taxes = tk.StringVar(value="Total taxes estimé : —")
        self._taxes_precedentes = self._taxes_affichees = None

        self.message = theme.Message(self)
        self.message.pack(fill="x", pady=(14, 0))

        barre = pied(self)
        theme.bouton(barre, "Vérifier  →", lambda: app.montrer("verifier"), principal=True).pack(side="right")
        theme.bouton(barre, "←  Dossier", lambda: app.montrer("dossier")).pack(side="right", padx=8)
        self.bind_all("<Command-Return>", lambda e: app.montrer("verifier") if app.page_active == "articles" else None)
        self.changer_mode()

    def construire_lignes(self, n):
        for enfant in self.grille.winfo_children():
            enfant.destroy()
        grille = self.grille
        for c, (texte, largeur) in enumerate([("Art.", 4), ("Position tarifaire · Marchandise", 30), ("Poids (kg)", 11), ("FOB (USD)", 11),
                                               ("Colis", 8), ("Ratio", 9), ("Contrôle", 24)]):
            ttk.Label(grille, text=texte, style="Entete.TLabel", width=largeur,
                      anchor="e" if 2 <= c <= 5 else "w").grid(row=0, column=c, padx=5, pady=(0, 4), sticky="ew")
        self.noms, self.ratios, self.etats = [], [], []
        for k in range(n):
            ttk.Label(grille, text=str(k + 1), style="Doux.TLabel").grid(row=k + 1, column=0, padx=5)
            nom = ttk.Label(grille, text="—", width=30)
            nom.grid(row=k + 1, column=1, padx=5, sticky="w")
            ratio = ttk.Label(grille, text="", width=9, anchor="e")
            ratio.grid(row=k + 1, column=5, padx=5)
            etat = ttk.Label(grille, text="", width=24)
            etat.grid(row=k + 1, column=6, padx=5, sticky="w")
            self.noms.append(nom)
            self.ratios.append(ratio)
            self.etats.append(etat)
        # Créés colonne par colonne : la touche Tab descend dans la colonne des poids.
        self.e_poids, self.e_fob, self.e_colis = [], [], []
        for liste, colonne, largeur in ((self.e_poids, 2, 11), (self.e_fob, 3, 11), (self.e_colis, 4, 8)):
            for k in range(n):
                e = ttk.Entry(grille, width=largeur, justify="right")
                e.grid(row=k + 1, column=colonne, padx=5, pady=2)
                e.bind("<KeyRelease>", self.planifier)
                liste.append(e)
        self.etiquettes_totaux = [ttk.Label(grille, text="", style="Total.TLabel", anchor="e") for _ in range(3)]
        ttk.Label(grille, text="Total", style="Total.TLabel").grid(row=n+1, column=1, padx=5, pady=(8, 0), sticky="w")
        for c, label in enumerate(self.etiquettes_totaux):
            label.grid(row=n+1, column=2 + c, padx=5, pady=(8, 0), sticky="e")
        self.panneau.decorer(grille, self.noms)

    # -------------------------------------------------------------- valeurs
    def valeurs(self):
        colis = [lire(e) for e in self.e_colis]
        saisi = self.var_mode.get() == "SAISI"
        return {"mode": self.var_mode.get(), "poids": [lire(e) for e in self.e_poids],
                "fob": [lire(e) for e in self.e_fob] if saisi else None,
                "fob_total": generer.nombre(self.var_fob_total.get()) if self.var_fob_total.get().strip() else None,
                "colis": colis if any(c is not None for c in colis) else None,
                "colis_total": generer.nombre(self.var_colis_total.get()) if self.var_colis_total.get().strip() else None}

    def remplir(self, poids, fob=None, colis=None, mode=None):
        if mode:
            self.var_mode.set(mode)
        self.changer_mode()
        for k in range(len(self.e_poids)):
            remplir(self.e_poids[k], poids[k] if poids else None)
            remplir(self.e_fob[k], fob[k] if fob else None)
            remplir(self.e_colis[k], int(colis[k]) if colis and colis[k] is not None else None)
        if fob and self.var_mode.get() == "SAISI":
            self.var_fob_total.set(f"{round(sum(fob), 2):g}")
        if colis and all(c is not None for c in colis):
            self.var_colis_total.set(str(int(sum(colis))))
        self.actualiser()

    def nouvelle_base(self):
        info = self.app.info
        self.construire_lignes(len(info["poids_articles"]))
        self._nommer_articles()
        self.var_fob_total.set(f"{info['fob']:g}")
        self.var_colis_total.set(str(info["colis"]))
        self.remplir(None, mode="RATIOS")
        self.panneau.preparer()

    def _nommer_articles(self):
        info = self.app.info
        for k in range(len(self.e_poids)):
            designation = info["designations"][k] if k < len(info["designations"]) else ""
            code = info.get("positions_tarifaires", [])[k] if info.get("positions_tarifaires") else "—"
            self.noms[k].configure(text=f"{code} · {designation or f'Article {k+1}'}", wraplength=250)

    def articles_changes(self, anciennes, nouvelles):
        """Gestion dynamique : poids, FOB et colis saisis suivent leur article ; une ligne ajoutée est vide."""
        saisis = {cle: (lire(p), lire(f), lire(c))
                  for cle, p, f, c in zip(anciennes, self.e_poids, self.e_fob, self.e_colis)}
        if len(nouvelles) != len(self.e_poids):
            self.construire_lignes(len(nouvelles))
        self._nommer_articles()
        reprise = [saisis.get(cle, (None, None, None)) for cle in nouvelles]
        for k, (poids, fob, colis) in enumerate(reprise):
            remplir(self.e_poids[k], poids)
            remplir(self.e_fob[k], fob)
            remplir(self.e_colis[k], int(colis) if colis is not None else None)
        if all(c is not None for _, _, c in reprise):
            self.var_colis_total.set(str(int(sum(c for _, _, c in reprise))))
        self.changer_mode()

    # --------------------------------------------------------------- actions
    def changer_mode(self):
        etat = "normal" if self.var_mode.get() == "SAISI" else "disabled"
        for e in self.e_fob:
            e.configure(state=etat)
        self.actualiser()

    def reprendre_base(self):
        i = self.app.info
        self.var_fob_total.set(f"{i['fob']:g}")
        self.remplir(i["poids_articles"], i["fob_articles"], i["colis_articles"], mode="SAISI")

    def vider(self):
        self.remplir(None)

    def estimer_taxes(self, v, poids, fob, bloque=False):
        """Total des taxes de la répartition affichée, par le calcul complet de l'aperçu ; rien n'est écrit."""
        if bloque or any(p is None for p in poids) or not fob or None in fob:
            self.var_taxes.set("Total taxes estimé : —  (tableau incomplet ou hors fourchettes)")
            self.cartes["taxes"].definir("—", "Tableau incomplet ou hors fourchettes")
            return
        try:
            res = generer.produire(self.app.base, poids, self.app.profil["ratios"], getattr(self.app, "table_imp", []),
                {}, mode="SAISI", fob_saisis=fob, colis_total=v["colis_total"], colis_saisis=v["colis"],
                enregistrer=False, profil=self.app.profil, plaque=plaque_saisie(self.app),
                importateur=importateur_choisi(self.app),
                taux=taux_choisi(self.app))
        except Exception as exc:  # noqa: BLE001 - affiché comme estimation impossible
            self.var_taxes.set(f"Total taxes estimé : —  ({exc})")
            self.cartes["taxes"].definir("—", str(exc))
            return
        r = res["resume"]
        total = r["taxes_totales"]
        self.var_taxes.set(f"Total taxes estimé : {nombre(total)} CDF   ·   articles "
                           f"{nombre(r.get('taxes_articles'))} + globales {nombre(r.get('taxes_globales'))}")
        # Écart avec la dernière répartition différente, pour comparer pendant la régénération.
        if total != self._taxes_affichees:
            self._taxes_precedentes, self._taxes_affichees = self._taxes_affichees, total
        avant = self._taxes_precedentes
        if avant is None or avant == total:
            ecart = ""
        else:
            ecart = f"   {'▲' if total > avant else '▼'} {nombre(abs(total - avant))} CDF de {'plus' if total > avant else 'moins'} que la précédente"
        self.cartes["taxes"].definir(nombre(total), f"articles {nombre(r.get('taxes_articles'))} + globales "
                                     f"{nombre(r.get('taxes_globales'))}{ecart}")

    def bons_modeles(self):
        """Modèles cochés ★ ayant les mêmes articles que le dossier ; liste vide en cas de problème de lecture."""
        try:
            from asydec.declarations import modeles_generes
            return modeles_generes.bons_modeles(variantes.signature(self.app.base),
                module=getattr(self.app, 'module_travail', 'friperie'))
        except Exception:  # noqa: BLE001 - l'aide est facultative, le tirage libre reste possible
            erreur_ignoree('propositions des bons modèles')
            return []

    def regenerer(self):
        """Nouvelle répartition aux mêmes totaux (poids entiers), jamais déjà proposée ; rien n'est exporté."""
        if not self.app.base or self.app.session_verrouillee:
            return
        from asydec.ui.taux_change import confirmer
        info, profil, v = self.app.info, self.app.profil, self.valeurs()
        poids = v["poids"]
        total_poids = sum(poids) if all(p is not None for p in poids) else info["poids"]
        total_fob = v["fob_total"] if v["fob_total"] is not None else info["fob"]
        total_colis = v["colis_total"] if v["colis_total"] is not None else info["colis"]
        if total_poids != int(total_poids):
            messagebox.showinfo("Générer une autre répartition",
                f"Le poids total ({total_poids:g} kg) doit être un nombre entier de kilogrammes. "
                "Corrigez les poids ou utilisez « Ajuster au poids total… ».", parent=self)
            return
        try:
            if not confirmer(self.app, [self.app.base], parent=self):
                return
        except Exception as exc:
            messagebox.showinfo("Répartition actuelle conservée", str(exc), parent=self)
            return
        cle = (self.app.base, self.app.reference, int(total_poids), round(total_fob, 2), int(total_colis),
               tuple(profil["bornes"]), bool(profil.get("variables_libres")))
        vues = self.deja_vues.setdefault(cle, set())
        if all(p is not None for p in poids) and v["fob"] and v["colis"] and None not in v["fob"]:
            vues.add(variantes.cle_variante({"poids": poids, "fob": v["fob"], "colis": v["colis"]}))
        self.regenerer_bouton.configure(state="disabled")
        self.configure(cursor="watch")
        self.update_idletasks()
        try:
            bons = self.bons_modeles()
            # Plusieurs répartitions valides sont tirées : les moins risquées d'abord, puis la meilleure
            # pour l'intention choisie parmi elles.
            propositions = variantes.generer(int(total_poids), total_fob, int(total_colis), profil["ratios"],
                nombre=tirages(intention_choisie(self.app)), profil=profil, exclure=vues)
            propositions = [p for p in propositions if variantes.cle_variante(p) not in vues] or propositions
            proposition, alertes, guide = choisir_proposition(self.app, propositions, profil, total_fob,
                                                              int(total_colis), bons)
            risque = texte_risque(alertes)
            if variantes.cle_variante(proposition) in vues:
                raise ValueError("La recherche n'a pas trouvé de nouvelle répartition pour ces totaux.")
            variantes.controler(proposition, profil)
            # Vérification complète (taxes comprises) avant de remplacer le tableau.
            generer.produire(self.app.base, proposition["poids"], profil["ratios"], self.app.table_imp,
                generer.lire_registre(), mode="SAISI", fob_total=total_fob, fob_saisis=proposition["fob"],
                colis_total=int(total_colis), colis_saisis=proposition["colis"], enregistrer=False,
                profil=profil, plaque=plaque_saisie(self.app), importateur=importateur_choisi(self.app),
                taux=taux_choisi(self.app))
        except Exception as exc:
            messagebox.showinfo("Répartition actuelle conservée", str(exc), parent=self)
            return
        finally:
            self.regenerer_bouton.configure(state="normal")
            self.configure(cursor="")
        vues.add(variantes.cle_variante(proposition))
        self.compteurs[cle] = self.compteurs.get(cle, 0) + 1
        self.actualiser_compteur()
        self.remplir(proposition["poids"], proposition["fob"], proposition["colis"], mode="SAISI")
        self.message.afficher("ok", f"Répartition n° {self.compteurs[cle]} proposée : mêmes totaux, poids entiers, rien d'exporté",
            [guide, risque, "Cliquez à nouveau sur « Générer une autre répartition » autant de fois que nécessaire, "
             "puis « Vérifier → » quand elle vous convient."])

    def ajuster_poids(self):
        poids = [lire(e) for e in self.e_poids]
        if any(p is None for p in poids):
            messagebox.showinfo("Ajuster", "Saisissez d'abord les poids de chaque article.")
            return
        total = simpledialog.askfloat("Ajuster au poids total", "Poids total voulu (kg) :", parent=self,
                                      initialvalue=sum(poids), minvalue=1)
        if total:
            for e, p in zip(self.e_poids, moteur.ajuster_poids(poids, total)):
                remplir(e, p)
            self.actualiser()

    def importer_excel(self):
        chemin = filedialog.askopenfilename(initialdir=os.path.expanduser("~/Downloads"), title="Tableau Excel",
                                            filetypes=[("Excel", "*.xlsx *.xlsm"), ("Tous", "*.*")])
        if not chemin:
            return
        try:
            from asydec.declarations.tableau_excel import lire_tableau_excel
            t = lire_tableau_excel(chemin)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Import Excel", str(exc))
            return
        n = len(t["poids"])
        attendu = len(self.e_poids)
        if n != attendu:
            messagebox.showwarning("Import Excel", f"Le tableau contient {n} articles au lieu de {attendu} : choisissez un tableau compatible avec le XML.")
            return
        complet = lambda liste: n == attendu and all(x is not None for x in liste)
        self.remplir(t["poids"], t["fob"] if complet(t["fob"]) else None,
                     t["colis"] if complet(t["colis"]) else None, mode="SAISI" if complet(t["fob"]) else "RATIOS")

    # ------------------------------------------------------ contrôle direct
    def planifier(self, _evenement=None):
        if self._attente:
            self.after_cancel(self._attente)
        self._attente = self.after(250, self.actualiser)

    def totaux(self):
        """Totaux de la répartition : ceux du tableau s'il est complet, sinon ceux du XML du dossier."""
        info, v = self.app.info, self.valeurs()
        poids = v["poids"]
        return (sum(poids) if all(p is not None for p in poids) else info["poids"],
                v["fob_total"] if v["fob_total"] is not None else info["fob"],
                v["colis_total"] if v["colis_total"] is not None else info["colis"])

    def cle_session(self, total_poids, total_fob, total_colis):
        profil = self.app.profil
        return (self.app.base, self.app.reference, int(total_poids), round(total_fob, 2), int(total_colis),
                tuple(profil["bornes"]), bool(profil.get("variables_libres")))

    def actualiser_compteur(self):
        """Modèles possibles pour les totaux affichés et modèles déjà générés pour eux."""
        if not getattr(self, "var_possibles", None):
            return
        try:
            poids, fob, colis = self.totaux()
            session = len(self.deja_vues.get(self.cle_session(poids, fob, colis), ()))
            self.var_possibles.set(compteur.calculer(self.app, self.app.base, self.app.profil, poids, fob, colis, session))
        except Exception:  # noqa: BLE001 - le compteur est une aide
            erreur_ignoree('compteur des modèles possibles')
            self.var_possibles.set("")

    def actualiser(self):
        """Recalcule à chaque frappe : FOB par ratios, ratio obtenu et contrôle des fourchettes."""
        self._attente = None
        profil = self.app.profil
        if not profil:
            return
        self.actualiser_compteur()
        v = self.valeurs()
        poids, fob, probleme = v["poids"], None, None
        try:
            if all(p is not None for p in poids):
                if v["mode"] == "RATIOS":
                    fob = variantes.fob_controles(poids, profil, v["fob_total"])
                    for e, f in zip(self.e_fob, fob):
                        remplir(e, f)
                else:
                    fob = v["fob"]
        except ValueError as exc:
            probleme = str(exc)
        if v["mode"] == "RATIOS" and fob is None:
            for e in self.e_fob:
                remplir(e, None)

        hors = ecarts = 0
        for k in range(len(self.e_poids)):
            bas, haut = profil["bornes"][k]
            regle = f"fixe {bas:.4g}" if bas == haut else f"{bas:.4g} – {haut:.4g}"
            p, f = poids[k], fob[k] if fob else None
            if profil.get("variables_libres") and k in variantes.articles_ajustables(profil):
                # Articles 4/7/8 : ajustables, signal au-delà de 10 % de la référence.
                if p and f is not None:
                    ecart = f / p / profil["ratios"][k] - 1
                    signal = abs(ecart) > 0.10
                    ecarts += signal
                    self.ratios[k].configure(text=f"{f / p:.4f}")
                    self.etats[k].configure(text=f"{'⚠' if signal else '✓'}  ajustable, {ecart:+.0%} / réf.",
                                            style="Alerte.TLabel" if signal else "Ok.TLabel")
                else:
                    self.ratios[k].configure(text="")
                    self.etats[k].configure(text=f"ajustable · réf. {profil['ratios'][k]:.4g}", style="Doux.TLabel")
                continue
            if p and f is not None:
                cents = lambda r: (Decimal(str(p)) * Decimal(str(r))).quantize(Decimal(".01"), ROUND_HALF_UP)
                dedans = cents(bas) <= Decimal(str(f)) <= cents(haut)
                hors += not dedans
                self.ratios[k].configure(text=f"{f / p:.4f}")
                self.etats[k].configure(text=("✓  " if dedans else "⚠  hors ") + regle,
                                        style="Ok.TLabel" if dedans else "Alerte.TLabel")
            else:
                self.ratios[k].configure(text="")
                self.etats[k].configure(text=regle, style="Doux.TLabel")

        somme = lambda liste: sum(x for x in liste if x is not None)
        colis = v["colis"]
        self.etiquettes_totaux[0].configure(text=nombre(somme(poids)))
        self.etiquettes_totaux[1].configure(text=nombre(somme(fob), 2) if fob and None not in fob else "—")
        self.etiquettes_totaux[2].configure(text=str(int(somme(colis))) if colis else "auto")
        complet = all(p is not None for p in poids)
        self.cartes["poids"].definir(nombre(somme(poids)) if complet else "—",
                                     "" if complet else "poids incomplets")
        self.cartes["fob"].definir(nombre(somme(fob), 2) if fob and None not in fob else "—",
                                   "calculé par les ratios" if v["mode"] == "RATIOS" else "saisi article par article")
        self.cartes["colis"].definir(str(int(somme(colis))) if colis else "auto",
                                     "saisis" if colis else "répartition automatique")

        self.estimer_taxes(v, poids, fob, bloque=probleme or hors)
        if probleme:
            self.message.afficher("alerte", "Le FOB ne peut pas être calculé", [probleme])
        elif any(p is None for p in poids):
            self.message.vider()
        elif hors:
            self.message.afficher("alerte", f"{hors} article(s) hors des fourchettes de contrôle",
                                  ["La génération sera refusée tant que ces FOB ne sont pas corrigés."])
        elif ecarts:
            self.message.afficher("alerte", f"{ecarts} ratio(s) ajustable(s) à plus de 10 % de la référence",
                                  ["Autorisé, mais à examiner avant de générer."])
        else:
            self.message.afficher("ok", "Tableau cohérent  ·  ⌘↵ pour vérifier")


# ==========================================================================
# 3. Vérifier et générer
# ==========================================================================
class PageVerifier(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.resultat = self.fichier = None
        self.deja_vues = {}
        theme.entete_page(self, "Vérifier et générer", "Aperçu complet de la déclaration. Rien n'est enregistré "
                          "avant « Générer le XML ».")
        self.message = theme.Message(self)
        self.message.pack(fill="x", pady=(0, 12))

        ligne_plaque = ttk.Frame(self)
        ligne_plaque.pack(fill="x", pady=(0, 10))
        self._plaque_affichee = None
        plaque.selecteur(ligne_plaque, app, apres=self.changer_plaque)
        theme.bouton(ligne_plaque, "Appliquer", self.changer_plaque).pack(side="left", padx=8)

        cartes = ttk.Frame(self)
        cartes.pack(fill="x")
        self.cartes = {}
        for k, (cle, libelle) in enumerate((("poids", "Poids total · kg"), ("fob", "FOB total · USD"),
                                            ("colis", "Colis"), ("taxes", "Taxes totales · CDF"))):
            cartes.columnconfigure(k, weight=1, uniform="cartes")
            carte = theme.Carte(cartes, libelle)
            carte.grid(row=0, column=k, sticky="nsew", padx=(0 if k == 0 else 8, 0))
            self.cartes[cle] = carte
        self.var_fichier = tk.StringVar()
        self.var_taux = tk.StringVar()
        ttk.Label(self, textvariable=self.var_taux, style="Doux.TLabel").pack(anchor="w", pady=(8, 0))
        self.var_possibles = tk.StringVar()
        ttk.Label(self, textvariable=self.var_possibles, style="Doux.TLabel", wraplength=1100).pack(anchor="w", pady=(4, 0))
        ttk.Label(self, textvariable=self.var_fichier, style="Doux.TLabel").pack(anchor="w", pady=(12, 6))

        barre = pied(self)
        self.generer = theme.bouton(barre, "Générer le XML", self.enregistrer, principal=True)
        self.generer.pack(side="right")
        self.regenerer_bouton = theme.bouton(barre, "Régénérer un autre modèle", self.regenerer)
        self.regenerer_bouton.pack(side="left")
        self.comparer_bouton = theme.bouton(barre, "Comparer avec un XML…", self.comparer_xml, state="disabled")
        self.comparer_bouton.pack(side="left", padx=8)
        self.finder = theme.bouton(barre, "Afficher dans le Finder", self.afficher_fichier)
        theme.bouton(barre, "←  Modifier les articles", lambda: app.montrer("articles")).pack(side="right", padx=8)

        theme.bouton(self, "Enregistrer la proposition", self.conserver_proposition).pack(anchor="w", pady=(0, 8))
        # Note du modèle qui vient d'être généré, montrée après « Générer le XML ».
        from asydec.ui.notation import BarreNotation
        self.modele_id = None
        self.notation = BarreNotation(self, self.noter)

        cadre, self.tableau = theme.tableau(self, [
            ("art", "Art.", 50, "center"), ("nom", "Marchandise", 260, "w"), ("poids", "Poids kg", 100, "e"),
            ("fob", "FOB USD", 110, "e"), ("ratio", "Ratio FOB/kg", 110, "e"),
            ("colis", "Colis", 70, "e"), ("cif", "CIF CDF", 140, "e"),
            ("taxes", "Taxes CDF", 130, "e")], 10)
        cadre.pack(fill="both", expand=True)

    def changer_plaque(self):
        """Nouvelle plaque saisie : l'aperçu est recalculé pour qu'elle soit inscrite et contrôlée."""
        if self.resultat is not None and plaque.lire(self.app) != self._plaque_affichee:
            self.afficher()

    def afficher(self):
        self._plaque_affichee = plaque.lire(self.app)
        self.fichier = None
        self.comparer_bouton.configure(state="disabled")
        self.finder.pack_forget()
        if getattr(self, "notation", None) is not None:
            self.notation.pack_forget()
        self.tableau.delete(*self.tableau.get_children())
        try:
            res = self.app.calculer(enregistrer=False)
        except Exception as exc:  # noqa: BLE001 - toute erreur bloque la génération
            self.resultat = None
            self.message.afficher("erreur", "Déclaration impossible en l'état", [str(exc)])
            self.generer.configure(state="disabled")
            self.regenerer_bouton.configure(state="disabled")
            for carte in self.cartes.values():
                carte.definir("—")
            self.var_fichier.set("")
            self.var_taux.set("")
            return
        self._presenter(res)

    def _presenter(self, res):
        self.fichier = None
        self.comparer_bouton.configure(state="disabled")
        self.resultat = res
        self.tableau.delete(*self.tableau.get_children())
        self._montrer(res)
        vues = self.deja_vues.setdefault(self._contexte_regeneration(res), set())
        vues.add(variantes.cle_variante(self._repartition(res)))
        if getattr(self, "var_possibles", None):
            r = res["resume"]
            self.var_possibles.set(compteur.calculer(self.app, self.app.base, self.app.profil,
                                                     r["poids"], r["fob"], sum(res["colis"]), len(vues)))
        self.regenerer_bouton.configure(state="normal")
        self.generer.configure(state="normal", text="Générer le XML")
        if res["alertes"]:
            self.message.afficher("alerte", f"{len(res['alertes'])} point(s) à vérifier avant de générer",
                                  ["•  " + a for a in res["alertes"]])
        else:
            self.message.afficher("ok", "Aucune alerte  ·  la déclaration peut être générée")

    @staticmethod
    def _repartition(res):
        return {"poids": [a["poids"] for a in res["resume"]["articles"]],
                "fob": res["fob"], "colis": res["colis"]}

    def _contexte_regeneration(self, res):
        profil = self.app.profil
        return (self.app.base, self.app.reference, res["resume"]["poids"],
                round(res["resume"]["fob"], 2), sum(res["colis"]),
                tuple(profil["bornes"]), bool(profil.get("variables_libres")))

    def regenerer(self):
        """Propose un autre aperçu avec les mêmes totaux, sans exporter de fichier."""
        if not self.resultat or self.app.session_verrouillee:
            return
        from asydec.ui.taux_change import confirmer
        try:
            if not confirmer(self.app, [self.app.base], parent=self):
                return
        except Exception as exc:
            messagebox.showinfo("Proposition actuelle conservée", str(exc), parent=self)
            return
        ancien = self.resultat
        self.regenerer_bouton.configure(state="disabled")
        self.update_idletasks()
        try:
            cle = self._contexte_regeneration(ancien)
            vues = self.deja_vues.setdefault(cle, set())
            vues.add(variantes.cle_variante(self._repartition(ancien)))
            profil = self.app.profil
            total_poids, total_fob = ancien["resume"]["poids"], ancien["resume"]["fob"]
            total_colis = sum(ancien["colis"])
            propositions = variantes.generer(total_poids, total_fob, total_colis, profil["ratios"],
                nombre=tirages(intention_choisie(self.app)), profil=profil, exclure=vues)
            bons_modeles = getattr(getattr(self.app, "pages", {}).get("articles"), "bons_modeles", None)
            v, alertes, guide = choisir_proposition(self.app, propositions, profil, total_fob, total_colis,
                                                    bons_modeles() if bons_modeles else [])
            if variantes.cle_variante(v) in vues:
                raise ValueError("La recherche n'a pas trouvé de nouvelle répartition.")
            if (sum(v["poids"]) != total_poids or round(sum(v["fob"]), 2) != round(total_fob, 2)
                    or sum(v["colis"]) != total_colis):
                raise ValueError("La proposition ne respecte pas les totaux demandés.")
            variantes.controler(v, profil)
            # Vérification complète avant de toucher aux valeurs du tableau.
            res = generer.produire(self.app.base, v["poids"], profil["ratios"], self.app.table_imp,
                generer.lire_registre(), mode="SAISI", fob_total=total_fob, fob_saisis=v["fob"],
                colis_total=total_colis, colis_saisis=v["colis"], enregistrer=False, profil=profil,
                plaque=plaque_saisie(self.app), importateur=importateur_choisi(self.app),
                taux=taux_choisi(self.app))
        except Exception as exc:
            messagebox.showinfo("Proposition actuelle conservée", str(exc), parent=self)
            return
        finally:
            self.regenerer_bouton.configure(state="normal")
        self.app.pages["articles"].remplir(v["poids"], v["fob"], v["colis"], mode="SAISI")
        self.fichier = None
        self.finder.pack_forget()
        if getattr(self, "notation", None) is not None:
            self.notation.pack_forget()
        self._presenter(res)
        if not res["alertes"]:
            self.message.afficher("ok", "Nouvelle proposition calculée — mêmes totaux, rien d'exporté",
                [guide + " " + texte_risque(alertes),
                 "Vérifiez les articles et les taxes. Vous pouvez régénérer ou choisir « Générer le XML »."])

    def _montrer(self, res):
        r = res["resume"]
        origine = (f"Taux saisi appliqué (CDF par unité de devise) : {nombre(r.get('taux'), 4)}, "
                   f"au lieu de {nombre(res['taux_xml'], 4)} dans le XML du dossier"
                   if res.get("taux_choisi") else
                   f"Taux XML du dossier (CDF par unité de devise) : {nombre(r.get('taux'), 4)}")
        self.var_taux.set(f"{origine} · Taxes globales reprises du XML de base : {nombre(r.get('taxes_globales'))} CDF")
        self.cartes["poids"].definir(nombre(r["poids"]))
        self.cartes["fob"].definir(nombre(r["fob"], 2))
        self.cartes["colis"].definir(str(int(sum(res["colis"]))))
        self.cartes["taxes"].definir(nombre(r["taxes_totales"]))
        dossier = espace_travail.relatif(os.path.dirname(res["chemin"]))
        self.var_fichier.set(f"Fichier :  {res['nom']}     dans  {dossier}")
        noms = res["info"]["designations"]
        for k, a in enumerate(r["articles"]):
            nom = (noms[k] if k < len(noms) else "") or f"Article {k+1}"
            code = res["info"].get("positions_tarifaires", [])
            nom = f"{code[k]} · {nom}" if k < len(code) else nom
            ratio = nombre(a["fob"] / a["poids"], 4) if a["poids"] > 0 else "—"
            self.tableau.insert("", "end", values=(k + 1, nom, nombre(a["poids"]), nombre(a["fob"], 2),
                                                   ratio, int(res["colis"][k]), nombre(a["cif"]), nombre(a["taxes"])))
        self.tableau.insert("", "end", tags=("total",), values=(
            "", "Total articles", nombre(r["poids"]), nombre(r["fob"], 2), "", int(sum(res["colis"])),
            nombre(r["cif"]), nombre(r["taxes_articles"])))
        self.tableau.insert("", "end", tags=("total",), values=(
            "", "Taxes globales", "", "", "", "", "", nombre(r["taxes_globales"])))

    def conserver_proposition(self):
        if not self.resultat or self.app.session_verrouillee:
            return
        try:
            from asydec.declarations import modeles_generes
            identifiant = modeles_generes.enregistrer(self.resultat, self.app.base, self.app.utilisateur,
                                                       reference=self.app.reference, module=getattr(self.app, 'module_travail', 'friperie'))
        except Exception as exc:
            messagebox.showerror("Proposition non conservée", str(exc), parent=self)
            return
        self.app.pages['modeles_generes'].filtre.set('Tous')
        self.app.montrer('modeles_generes')
        messagebox.showinfo('Proposition conservée',
            f"Modèle n° {identifiant} disponible dans Modèles générés. "
            "Une nouvelle proposition est en attente de validation locale. "
            "Si elle existait déjà, son statut est conservé.", parent=self)

    def montrer_notation(self, identifiant):
        self.modele_id = identifiant
        self.notation.definir(None)
        self.notation.pack(fill="x", pady=(0, 8), after=self.message)

    def noter(self, note, commentaire=""):
        if self.modele_id is None or self.app.session_verrouillee:
            return
        from asydec.declarations import modeles_generes
        try:
            modeles_generes.noter(self.modele_id, note, self.app.utilisateur, commentaire)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Note non enregistrée", str(exc), parent=self)
            return
        self.notation.definir(note, commentaire)
        from asydec.ui.modeles_generes import EFFET_NOTE
        self.message.afficher("ok", f"Modèle n° {self.modele_id} noté {note}/5 ({modeles_generes.NOTES[note]})",
                              [EFFET_NOTE[note]])

    def comparer_xml(self):
        if self.app.session_verrouillee:
            return
        if not self.fichier or not Path(self.fichier).is_file():
            self.comparer_bouton.configure(state="disabled")
            return
        options, importateur = {}, None
        try:
            importateur = (self.resultat or {}).get("info", {}).get("importateur")
            if importateur:
                options["initialdir"] = generer.dossier_rangement(
                    importateur, "reelles", getattr(self.app, "table_imp", None))
        except Exception:  # noqa: BLE001 - emplacement habituel à défaut
            erreur_ignoree('dossier initial de comparaison')
        chemin = filedialog.askopenfilename(parent=self, title="Comparer le XML généré avec un fichier fourni",
                                            filetypes=[("XML", "*.xml")], **options)
        if not chemin:
            return
        # Le fichier comparé est une déclaration réelle : rangée avec celles de l'importateur.
        chemin = generer.ranger_fichier(chemin, importateur, "reelles", getattr(self.app, "table_imp", None))
        try:
            from asydec.declarations.comparaison_prediction import comparer_xmls
            from asydec.ui.comparaison import afficher
            rapport = comparer_xmls(self.fichier, chemin)
            afficher(self, rapport)
        except Exception as exc:
            messagebox.showerror("Comparaison impossible", str(exc), parent=self)
            return
        try:
            # Trace sur le modèle dont l'export archivé est exactement ce fichier.
            from asydec.declarations import modeles_generes
            identifiant = modeles_generes.modele_par_export(Path(self.fichier).read_bytes())
            if identifiant is not None:
                modeles_generes.noter_comparaison(identifiant, chemin, rapport, self.app.utilisateur)
        except Exception as exc:
            messagebox.showwarning("Comparaison non tracée", f"La comparaison est affichée, mais sa trace n'a pas été enregistrée : {exc}", parent=self)

    def enregistrer(self):
        if not self.resultat or self.app.session_verrouillee:
            return
        question = f"Créer le fichier\n\n{self.resultat['nom']}\n\ndans le dossier de l'importateur ?"
        if self.resultat["alertes"]:
            question += "\n\nPoints à vérifier :\n" + "\n".join("• " + a for a in self.resultat["alertes"])
        if not messagebox.askyesno("Générer le XML", question):
            return
        try:
            res = self.app.calculer(enregistrer=True)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Génération impossible", str(exc))
            return
        self.fichier = res["chemin"]
        self.comparer_bouton.configure(state="normal" if Path(self.fichier).is_file() else "disabled")
        self.message.afficher("ok", "✓  Déclaration enregistrée", [espace_travail.relatif(res["chemin"])])
        self.generer.configure(state="disabled", text="Généré  ✓")
        self.finder.pack(side="right", padx=8)
        try:
            from asydec.declarations import modeles_generes
            identifiant = modeles_generes.enregistrer(res, self.app.base, self.app.utilisateur, export=res['chemin'],
                                         reference=self.app.reference, module=getattr(self.app, 'module_travail', 'friperie'))
            self.montrer_notation(identifiant)
        except Exception as exc:
            messagebox.showwarning("XML créé, suivi non enregistré",
                "Le XML a bien été créé. Son ajout à la liste des modèles a échoué : " + str(exc), parent=self)


    def afficher_fichier(self):
        if self.fichier and os.path.exists(self.fichier):
            subprocess.run(["open", "-R", self.fichier], check=False)
