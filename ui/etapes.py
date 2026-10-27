"""Les trois étapes d'une déclaration : dossier, articles, vérification et génération."""
import os
import subprocess
import tkinter as tk
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

import generer
import moteur
import variantes
from ui import theme
from ui.theme import nombre

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

        ttk.Label(self, text="Référence des ratios", style="Section.TLabel").pack(anchor="w", pady=(20, 4))
        ttk.Label(self, text="Articles 4, 7 et 8 : ratios fixes de la référence. Autres articles : fourchettes "
                  "des modèles compatibles.", style="Doux.TLabel").pack(anchor="w")
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
        self._remplir()

    def _remplir(self):
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
        for cle, var in self.valeurs.items():
            var.set(textes[cle] or "—")

    def choisir_disponible(self):
        chemins = self.app.choisir_xml_disponibles()
        if chemins:
            self._ouvrir(chemins[0])

    def parcourir(self):
        chemin = filedialog.askopenfilename(
            initialdir=self.app.prefs.get("dernier_dossier", generer.DEC), title="XML de base du dossier",
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
        theme.entete_page(self, "Articles", "Saisissez ou importez les poids du colisage. Le FOB est calculé "
                          "par les ratios, ou saisi article par article. Colis vides = répartition automatique.")

        outils = ttk.Frame(self)
        outils.pack(fill="x")
        theme.bouton(outils, "Importer un Excel…", self.importer_excel).pack(side="left")
        theme.bouton(outils, "Reprendre la base", self.reprendre_base).pack(side="left", padx=6)
        theme.bouton(outils, "Ajuster au poids total…", self.ajuster_poids).pack(side="left")
        theme.bouton(outils, "Vider", self.vider).pack(side="right")

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

        grille = ttk.Frame(self)
        grille.pack(fill="x", pady=(6, 0))
        for c, (texte, largeur) in enumerate([("Art.", 4), ("Marchandise", 30), ("Poids (kg)", 11), ("FOB (USD)", 11),
                                               ("Colis", 8), ("Ratio", 9), ("Contrôle", 24)]):
            ttk.Label(grille, text=texte, style="Entete.TLabel", width=largeur,
                      anchor="e" if 2 <= c <= 5 else "w").grid(row=0, column=c, padx=5, pady=(0, 4), sticky="ew")
        self.noms, self.ratios, self.etats = [], [], []
        for k in range(8):
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
            for k in range(8):
                e = ttk.Entry(grille, width=largeur, justify="right")
                e.grid(row=k + 1, column=colonne, padx=5, pady=2)
                e.bind("<KeyRelease>", self.planifier)
                liste.append(e)
        self.totaux = [ttk.Label(grille, text="", style="Total.TLabel", anchor="e") for _ in range(3)]
        ttk.Label(grille, text="Total", style="Total.TLabel").grid(row=9, column=1, padx=5, pady=(8, 0), sticky="w")
        for c, label in enumerate(self.totaux):
            label.grid(row=9, column=2 + c, padx=5, pady=(8, 0), sticky="e")

        self.message = theme.Message(self)
        self.message.pack(fill="x", pady=(14, 0))

        barre = pied(self)
        theme.bouton(barre, "Vérifier  →", lambda: app.montrer("verifier"), principal=True).pack(side="right")
        theme.bouton(barre, "←  Dossier", lambda: app.montrer("dossier")).pack(side="right", padx=8)
        self.bind_all("<Command-Return>", lambda e: app.montrer("verifier") if app.page_active == "articles" else None)
        self.changer_mode()

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
        for k in range(8):
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
        for k in range(8):
            designation = info["designations"][k] if k < len(info["designations"]) else ""
            self.noms[k].configure(text=(designation or generer.ARTICLES[k])[:34])
        self.var_fob_total.set(f"{info['fob']:g}")
        self.var_colis_total.set(str(info["colis"]))
        self.remplir(None, mode="RATIOS")

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

    def ajuster_poids(self):
        poids = [lire(e) for e in self.e_poids]
        if any(p is None for p in poids):
            messagebox.showinfo("Ajuster", "Saisissez d'abord les 8 poids.")
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
            from interface import lire_tableau_excel
            t = lire_tableau_excel(chemin)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Import Excel", str(exc))
            return
        n = len(t["poids"])
        if n != 8:
            messagebox.showwarning("Import Excel", f"Le tableau contient {n} articles au lieu de 8 : vérifiez les lignes.")
        complet = lambda liste: n == 8 and all(x is not None for x in liste)
        self.remplir(t["poids"] + [None] * (8 - n), t["fob"] if complet(t["fob"]) else None,
                     t["colis"] if complet(t["colis"]) else None, mode="SAISI" if complet(t["fob"]) else "RATIOS")

    # ------------------------------------------------------ contrôle direct
    def planifier(self, _evenement=None):
        if self._attente:
            self.after_cancel(self._attente)
        self._attente = self.after(250, self.actualiser)

    def actualiser(self):
        """Recalcule à chaque frappe : FOB par ratios, ratio obtenu et contrôle des fourchettes."""
        self._attente = None
        profil = self.app.profil
        if not profil:
            return
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
        for k in range(8):
            bas, haut = profil["bornes"][k]
            regle = f"fixe {bas:.4g}" if bas == haut else f"{bas:.4g} – {haut:.4g}"
            p, f = poids[k], fob[k] if fob else None
            if profil.get("variables_libres") and k in moteur.ARTICLES_VARIABLES:
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
        self.totaux[0].configure(text=nombre(somme(poids)))
        self.totaux[1].configure(text=nombre(somme(fob), 2) if fob and None not in fob else "—")
        self.totaux[2].configure(text=str(int(somme(colis))) if colis else "auto")

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
        ttk.Label(self, textvariable=self.var_fichier, style="Doux.TLabel").pack(anchor="w", pady=(12, 6))

        barre = pied(self)
        self.generer = theme.bouton(barre, "Générer le XML", self.enregistrer, principal=True)
        self.generer.pack(side="right")
        self.regenerer_bouton = theme.bouton(barre, "Régénérer un autre modèle", self.regenerer)
        self.regenerer_bouton.pack(side="left")
        theme.bouton(barre, "Comparer avec un XML…", self.comparer_xml).pack(side="left", padx=8)
        self.finder = theme.bouton(barre, "Afficher dans le Finder", self.afficher_fichier)
        theme.bouton(barre, "←  Modifier les articles", lambda: app.montrer("articles")).pack(side="right", padx=8)

        theme.bouton(self, "Enregistrer la proposition", self.conserver_proposition).pack(anchor="w", pady=(0, 8))

        cadre, self.tableau = theme.tableau(self, [
            ("art", "Art.", 50, "center"), ("nom", "Marchandise", 260, "w"), ("poids", "Poids kg", 100, "e"),
            ("fob", "FOB USD", 110, "e"), ("ratio", "Ratio FOB/kg", 110, "e"),
            ("colis", "Colis", 70, "e"), ("cif", "CIF CDF", 140, "e"),
            ("taxes", "Taxes CDF", 130, "e")], 10)
        cadre.pack(fill="both", expand=True)

    def afficher(self):
        self.finder.pack_forget()
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
            return
        self._presenter(res)

    def _presenter(self, res):
        self.resultat = res
        self.tableau.delete(*self.tableau.get_children())
        self._montrer(res)
        self.deja_vues.setdefault(self._contexte_regeneration(res), set()).add(
            variantes.cle_variante(self._repartition(res)))
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
                nombre=1, profil=profil, exclure=vues)
            v = propositions[0]
            if variantes.cle_variante(v) in vues:
                raise ValueError("La recherche n'a pas trouvé de nouvelle répartition.")
            if (sum(v["poids"]) != total_poids or round(sum(v["fob"]), 2) != round(total_fob, 2)
                    or sum(v["colis"]) != total_colis):
                raise ValueError("La proposition ne respecte pas les totaux demandés.")
            variantes.controler(v, profil)
            # Vérification complète avant de toucher aux valeurs du tableau.
            res = generer.produire(self.app.base, v["poids"], profil["ratios"], self.app.table_imp,
                generer.lire_registre(), mode="SAISI", fob_total=total_fob, fob_saisis=v["fob"],
                colis_total=total_colis, colis_saisis=v["colis"], enregistrer=False, profil=profil)
        except Exception as exc:
            messagebox.showinfo("Proposition actuelle conservée", str(exc), parent=self)
            return
        finally:
            self.regenerer_bouton.configure(state="normal")
        self.app.pages["articles"].remplir(v["poids"], v["fob"], v["colis"], mode="SAISI")
        self.fichier = None
        self.finder.pack_forget()
        self._presenter(res)
        if not res["alertes"]:
            self.message.afficher("ok", "Nouvelle proposition calculée — mêmes totaux, rien d'exporté",
                ["Vérifiez les articles et les taxes. Vous pouvez régénérer ou choisir « Générer le XML »."])

    def _montrer(self, res):
        r = res["resume"]
        self.cartes["poids"].definir(nombre(r["poids"]))
        self.cartes["fob"].definir(nombre(r["fob"], 2))
        self.cartes["colis"].definir(str(int(sum(res["colis"]))))
        self.cartes["taxes"].definir(nombre(r["taxes_totales"]))
        dossier = os.path.relpath(os.path.dirname(res["chemin"]), generer.DEC)
        self.var_fichier.set(f"Fichier :  {res['nom']}     dans  {dossier}")
        noms = res["info"]["designations"]
        for k, a in enumerate(r["articles"]):
            nom = (noms[k] if k < len(noms) else "") or generer.ARTICLES[k]
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
            import modeles_generes
            identifiant = modeles_generes.enregistrer(self.resultat, self.app.base, self.app.utilisateur)
        except Exception as exc:
            messagebox.showerror("Proposition non conservée", str(exc), parent=self)
            return
        self.app.pages['modeles_generes'].filtre.set('Tous')
        self.app.montrer('modeles_generes')
        messagebox.showinfo('Proposition conservée',
            f"Modèle n° {identifiant} disponible dans Modèles générés. "
            "Une nouvelle proposition est en attente de validation locale. "
            "Si elle existait déjà, son statut est conservé.", parent=self)

    def comparer_xml(self):
        if not self.resultat or self.app.session_verrouillee:
            return
        chemin = filedialog.askopenfilename(parent=self, title="Comparer avec un XML fourni",
                                            filetypes=[("XML", "*.xml")])
        if not chemin:
            return
        try:
            from comparaison_prediction import comparer
            from ui.comparaison import afficher
            rapport = comparer(self.resultat, self.app.base, chemin)
            afficher(self, rapport)
        except Exception as exc:
            messagebox.showerror("Comparaison impossible", str(exc), parent=self)

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
        self.message.afficher("ok", "✓  Déclaration enregistrée", [os.path.relpath(res["chemin"], generer.DEC)])
        self.generer.configure(state="disabled", text="Généré  ✓")
        self.finder.pack(side="right", padx=8)
        try:
            import modeles_generes
            modeles_generes.enregistrer(res, self.app.base, self.app.utilisateur, export=res['chemin'])
        except Exception as exc:
            messagebox.showwarning("XML créé, suivi non enregistré",
                "Le XML a bien été créé. Son ajout à la liste des modèles a échoué : " + str(exc), parent=self)


    def afficher_fichier(self):
        if self.fichier and os.path.exists(self.fichier):
            subprocess.run(["open", "-R", self.fichier], check=False)
