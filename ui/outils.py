"""Outils : recherche de répartitions, étude des XML, historique des déclarations."""
import datetime
import os
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import etude_xml
import catalogue_xml
import generer
import moteur
import variantes
from ui import theme
from ui.theme import nombre


# ==========================================================================
# Répartitions
# ==========================================================================
class PageRepartitions(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.propositions, self.ecartes, self.deja_vues = [], [], {}
        theme.entete_page(self, "Répartitions", "Proposez des répartitions poids / FOB / colis à partir de trois "
                          "totaux, d'après vos modèles enregistrés. Chaque proposition respecte les fourchettes de contrôle.")

        saisie = ttk.Frame(self)
        saisie.pack(fill="x")
        self.champs = {}
        for cle, texte in (("fob", "FOB total (USD)"), ("poids", "Poids total (kg)"), ("colis", "Colis total")):
            ttk.Label(saisie, text=texte).pack(side="left", padx=(0, 4))
            var = tk.StringVar()
            ttk.Entry(saisie, textvariable=var, width=11, justify="right").pack(side="left", padx=(0, 16))
            self.champs[cle] = var
        theme.bouton(saisie, "Rechercher", self.rechercher, principal=True).pack(side="left")
        self.autres = theme.bouton(saisie, "Autres propositions", lambda: self.rechercher(autres=True))
        self.autres.pack(side="left", padx=6)
        theme.bouton(saisie, "Nouveaux modèles…", self.ajouter_modeles).pack(side="right")
        theme.bouton(saisie, "XML disponibles…", self.choisir_modeles).pack(side="right", padx=6)
        self.selection_modeles = None
        self.var_modeles = tk.StringVar()
        ttk.Label(self, textvariable=self.var_modeles, style="Doux.TLabel").pack(anchor="e", pady=(4, 0))

        self.message = theme.Message(self)
        self.message.pack(fill="x", pady=(8, 8))

        barre = ttk.Frame(self)
        barre.pack(side="bottom", fill="x", pady=(12, 0))
        theme.bouton(barre, "Utiliser cette proposition  →", self.utiliser, principal=True).pack(side="right")

        cadre, self.liste = theme.tableau(self, [
            ("n", "N°", 50, "center"), ("modele", "Modèle de référence", 430, "w"),
            ("score", "Proximité / 100", 130, "e"), ("taxes", "Taxes estimées CDF", 170, "e")], 6)
        cadre.pack(fill="x")
        self.liste.bind("<<TreeviewSelect>>", self.detailler)
        ttk.Label(self, text="Détail de la proposition", style="Section.TLabel").pack(anchor="w", pady=(14, 6))
        cadre, self.detail = theme.tableau(self, [
            ("art", "Art.", 50, "center"), ("poids", "Poids kg", 110, "e"), ("fob", "FOB USD", 110, "e"),
            ("colis", "Colis", 80, "e"), ("ratio", "Ratio FOB/kg", 110, "e"), ("regle", "Contrôle", 220, "w")], 9)
        cadre.pack(fill="both", expand=True)

    def afficher(self):
        n = len(self.app.xml_disponibles(generation=True))
        self.var_modeles.set(f"{n} modèle(s) enregistré(s)")
        if self.app.info and not self.champs["fob"].get():
            i = self.app.info
            self.champs["fob"].set(f"{i['fob']:g}")
            self.champs["poids"].set(f"{i['poids']:g}")
            self.champs["colis"].set(str(i["colis"]))
        self.autres.configure(state="normal" if self.propositions else "disabled")

    def rechercher(self, autres=False):
        try:
            fob, poids, colis = (generer.nombre(self.champs[c].get()) for c in ("fob", "poids", "colis"))
            if None in (fob, poids, colis):
                raise ValueError("Renseignez le FOB, le poids et les colis.")
            self.message.afficher("alerte", "Recherche en cours…")
            self.update_idletasks()
            cle = (poids, fob, colis)
            vues = self.deja_vues.setdefault(cle, set())
            chemins = self.selection_modeles or self.app.chemins_xml_disponibles(generation=True)
            propositions, ecartes = variantes.rechercher_modeles(poids, fob, colis, chemins=chemins,
                                                                 nombre=3 if autres else 12, exclure=vues)
            for v in propositions:
                v["resultat"] = generer.produire(
                    v["controle"], v["poids"], v["profil"]["ratios"], self.app.table_imp, {}, mode="SAISI",
                    fob_total=fob, fob_saisis=v["fob"], colis_total=colis, colis_saisis=v["colis"],
                    enregistrer=False, profil=v["profil"])
                vues.add(variantes.cle_variante(v))
        except Exception as exc:  # noqa: BLE001
            self.message.afficher("erreur", "Aucune proposition", str(exc).splitlines()[:6])
            return
        self.propositions, self.ecartes = propositions, ecartes
        self.liste.delete(*self.liste.get_children())
        for k, v in enumerate(propositions):
            self.liste.insert("", "end", iid=str(k), values=(
                k + 1, v["modele"], nombre(v["proximite"], 2), nombre(v["resultat"]["resume"]["taxes_totales"])))
        self.message.afficher("ok", f"{len(propositions)} proposition(s), de la plus proche à la moins proche de vos modèles",
                              [f"{len(ecartes)} modèle(s) non utilisable(s) pour ces totaux."] if ecartes else [])
        self.autres.configure(state="normal")
        self.liste.selection_set("0")

    def selection(self):
        choix = self.liste.selection()
        return self.propositions[int(choix[0])] if choix else None

    def detailler(self, _evenement=None):
        v = self.selection()
        self.detail.delete(*self.detail.get_children())
        if not v:
            return
        for k in range(8):
            bas, haut = v["profil"]["bornes"][k]
            if k in moteur.ARTICLES_VARIABLES:
                libre = v["profil"].get("variables_libres")
                regle = f"ajustable, réf. {bas:.4g}" if libre else f"ratio fixe {bas:.4g}"
            else:
                regle = f"entre {bas:.4g} et {haut:.4g}"
            self.detail.insert("", "end", values=(k + 1, nombre(v["poids"][k], 3), nombre(v["fob"][k], 2),
                                                  v["colis"][k], f"{v['fob'][k] / v['poids'][k]:.4f}", regle))
        self.detail.insert("", "end", tags=("total",), values=(
            "", nombre(sum(v["poids"]), 3), nombre(sum(v["fob"]), 2), sum(v["colis"]), "", ""))

    def _ouvrir_dossier_proposition(self, proposition):
        """Adopte une archive seulement après confirmation des données du dossier."""
        try:
            documents = self.app.xml_disponibles(generation=True)
            disponibles = {str(Path(d['chemin']).resolve()): d for d in documents}
            chemin = proposition['controle']
            while True:
                document = disponibles.get(str(Path(chemin).resolve()))
                if document is None:
                    raise ValueError("Ce XML n'est plus disponible comme base de génération dans la médiathèque.")
                if variantes.signature(chemin) != proposition['profil']['signature']:
                    raise ValueError("Ce XML n'a pas les mêmes articles que la proposition. Choisissez une base compatible.")
                racine = moteur.charger(chemin).getroot()
                info = moteur.infos_dossier(racine)
                fret = moteur._txt(racine, 'Valuation/Gs_external_freight/Amount_foreign_currency') or '0'
                assurance = moteur._txt(racine, 'Valuation/Gs_insurance/Amount_foreign_currency') or '0'
                texte = (f"Base proposée : {document['nom']}\n"
                         f"Importateur : {info['importateur'] or '—'}\n"
                         f"Référence : {info['reference'] or '—'}\n"
                         f"Taux de change : {info['taux']:g}\n"
                         f"Fret : {fret} · Assurance : {assurance}\n\n"
                         "La déclaration reprendra ces informations et les autres frais de ce XML. "
                         "Les poids, FOB et colis seront ceux de votre proposition.\n\n"
                         "Oui : utiliser cette base. Non : choisir un autre XML de la médiathèque. "
                         "Annuler : conserver la simulation sans ouvrir de dossier.")
                choix = messagebox.askyesnocancel('Confirmer le dossier de la proposition', texte, parent=self)
                if choix is None:
                    return False
                if choix:
                    return self.app.ouvrir_base(chemin)
                chemins = self.app.choisir_xml_disponibles(generation=True)
                if not chemins:
                    return False
                chemin = chemins[0]
        except Exception as exc:
            self.message.afficher('erreur', 'Dossier non ouvert', [str(exc)])
            return False

    def utiliser(self):
        if self.app.session_verrouillee:
            return
        v = self.selection()
        if not v:
            return
        if not self.app.base and not self._ouvrir_dossier_proposition(v):
            return
        if not self.app.choisir_reference(v["controle"], v["profil"]):
            return
        articles = self.app.pages["articles"]
        articles.var_fob_total.set(f"{round(sum(v['fob']), 2):g}")
        articles.remplir(v["poids"], v["fob"], v["colis"], mode="SAISI")
        self.app.montrer("verifier")

    def choisir_modeles(self):
        chemins = self.app.choisir_xml_disponibles(multiple=True, generation=True)
        if chemins:
            self.selection_modeles = chemins
            self.var_modeles.set(f'{len(chemins)} modèle(s) sélectionné(s), déjà disponibles')

    def ajouter_modeles(self):
        chemins = filedialog.askopenfilenames(title="XML de référence à conserver", filetypes=[("XML", "*.xml")])
        self.app.partager_xml(chemins)
        self.selection_modeles = None
        erreurs, total = [], 0
        for chemin in chemins:
            try:
                variantes.conserver(chemin)
                total += 1
            except Exception as exc:  # noqa: BLE001
                erreurs.append(f"{os.path.basename(chemin)} : {exc}")
        if chemins:
            genre = "alerte" if erreurs else "ok"
            self.message.afficher(genre, f"{total} modèle(s) conservé(s)", erreurs)
            self.afficher()


# ==========================================================================
# Étude des XML
# ==========================================================================
class PageEtude(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.etudes = []
        theme.entete_page(self, "Étude des XML", "Comparez les ratios FOB/kg de vos déclarations à une référence. "
                          "Sélectionnez la référence dans la liste, puis « Analyser ».")
        barre = ttk.Frame(self)
        barre.pack(fill="x")
        theme.bouton(barre, "Médiathèque XML…", self.choisir_disponibles).pack(side="left", padx=6)
        theme.bouton(barre, "Ajouter des XML…", self.ajouter_fichiers).pack(side="left")
        theme.bouton(barre, "Ajouter un dossier…", self.ajouter_dossier).pack(side="left", padx=6)
        theme.bouton(barre, "Exporter Excel…", self.exporter).pack(side="right")
        theme.bouton(barre, "Analyser", self.analyser, principal=True).pack(side="right", padx=6)
        self.var_seuil = tk.StringVar(value="10")
        ttk.Entry(barre, textvariable=self.var_seuil, width=5, justify="right").pack(side="right")
        ttk.Label(barre, text="Seuil (%)").pack(side="right", padx=4)

        self.message = theme.Message(self)
        self.message.pack(fill="x", pady=(10, 8))
        cadre, self.liste = theme.tableau(self, [
            ("fichier", "Fichier", 380, "w"), ("importateur", "Importateur", 220, "w"),
            ("articles", "Articles", 80, "e"), ("devise", "Devise", 80, "center"), ("alertes", "Alertes", 80, "e")], 7)
        cadre.pack(fill="x")
        ttk.Label(self, text="Écarts de ratio par rapport à la référence", style="Section.TLabel").pack(anchor="w", pady=(14, 6))
        cadre, self.ecarts = theme.tableau(self, [
            ("fichier", "Fichier", 330, "w"), ("art", "Art.", 50, "center"), ("sens", "Sens", 90, "center"),
            ("ecart", "Écart", 90, "e"), ("valeurs", "Référence → étudié", 190, "e"), ("etat", "", 110, "w")], 8)
        cadre.pack(fill="both", expand=True)

    def afficher(self):
        self.etudes, erreurs = etude_xml.charger()
        noms = {d['empreinte']: d['nom'] for d in self.app.xml_disponibles()}
        self.etudes = [dict(e, fichier=noms.get(e['id'], e['fichier'])) for e in self.etudes if e['id'] not in catalogue_xml.retraits()]
        self.liste.delete(*self.liste.get_children())
        for k, e in enumerate(self.etudes):
            self.liste.insert("", "end", iid=str(k), values=(
                e["fichier"], e["importateur"], len(e["articles"]), e["devise"], len(e["alertes"])))
        if erreurs:
            self.message.afficher("alerte", "Études illisibles", erreurs)
        elif not self.etudes:
            self.message.afficher("alerte", "Aucun XML étudié", ["Ajoutez des XML ou un dossier entier pour commencer."])

    def _importer(self, chemins):
        self.app.partager_xml(chemins)
        erreurs = []
        for chemin in chemins:
            try:
                etude_xml.enregistrer(chemin)
            except Exception as exc:  # noqa: BLE001
                erreurs.append(f"{os.path.basename(chemin)} : {exc}")
        self.afficher()
        if chemins:
            self.message.afficher("alerte" if erreurs else "ok",
                                  f"{len(chemins) - len(erreurs)} XML ajouté(s) à l'étude", erreurs[:8])

    def choisir_disponibles(self):
        chemins = self.app.choisir_xml_disponibles(multiple=True)
        if chemins:
            self._importer(chemins)

    def ajouter_fichiers(self):
        self._importer(filedialog.askopenfilenames(title="XML à étudier", filetypes=[("XML", "*.xml")]))

    def ajouter_dossier(self):
        dossier = filedialog.askdirectory(title="Dossier à étudier (sous-dossiers inclus)")
        if dossier:
            self._importer([p for p in Path(dossier).rglob("*") if p.is_file() and p.suffix.lower() == ".xml"])

    def _reference_et_seuil(self):
        if not self.liste.selection():
            raise ValueError("Sélectionnez dans la liste le XML qui sert de référence.")
        seuil = generer.nombre(self.var_seuil.get())
        if seuil is None or seuil < 0:
            raise ValueError("Indiquez un seuil positif, en %.")
        return self.etudes[int(self.liste.selection()[0])]["id"], seuil / 100

    def analyser(self):
        try:
            reference, seuil = self._reference_et_seuil()
            rapport = etude_xml.comparer(self.etudes, reference, seuil)
        except Exception as exc:  # noqa: BLE001
            self.message.afficher("erreur", "Analyse impossible", [str(exc)])
            return
        self.ecarts.delete(*self.ecarts.get_children())
        ratios = sorted((c for c in rapport["changements"] if c["metrique"] == "ratio" and c["relatif"] is not None),
                        key=lambda c: abs(c["relatif"]), reverse=True)
        for c in ratios:
            self.ecarts.insert("", "end", tags=("alerte",) if c["important"] else (), values=(
                c["fichier"], c["article"], c["sens"].capitalize(), f"{c['relatif']:+.1%}".replace(".", ","),
                f"{c['avant']:.4f} → {c['apres']:.4f}", "À examiner" if c["important"] else ""))
        importants = sum(c["important"] for c in ratios)
        self.message.afficher("alerte" if importants else "ok",
                              f"Référence : {rapport['reference']['fichier']}",
                              [f"{len(ratios)} ratio(s) comparé(s), {importants} au-delà de {seuil:.0%}.",
                               f"{len(rapport['problemes'])} point(s) à vérifier dans l'export Excel."])

    def exporter(self):
        try:
            reference, seuil = self._reference_et_seuil()
        except ValueError as exc:
            self.message.afficher("erreur", "Export impossible", [str(exc)])
            return
        chemin = filedialog.asksaveasfilename(
            title="Exporter l'analyse", defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")],
            initialfile=f"Analyse XML {datetime.datetime.now():%Y-%m-%d %H%M}.xlsx")
        if not chemin:
            return
        try:
            etude_xml.exporter(self.etudes, chemin, reference, seuil)
        except Exception as exc:  # noqa: BLE001
            self.message.afficher("erreur", "Export impossible", [str(exc)])
            return
        subprocess.run(["open", chemin], check=False)


# ==========================================================================
# Historique
# ==========================================================================
class PageHistorique(ttk.Frame):
    TOUS = "Tous les importateurs"

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        theme.entete_page(self, "Historique", "Déclarations générées, les plus récentes d'abord. "
                          "Double-cliquez une ligne pour l'afficher dans le Finder.")
        barre = ttk.Frame(self)
        barre.pack(fill="x", pady=(0, 10))
        self.var_filtre = tk.StringVar(value=self.TOUS)
        self.filtre = ttk.Combobox(barre, textvariable=self.var_filtre, state="readonly", width=30)
        self.filtre.pack(side="left")
        self.filtre.bind("<<ComboboxSelected>>", lambda e: self.afficher())
        theme.bouton(barre, "Ouvrir le dossier des déclarations",
                     lambda: subprocess.run(["open", generer.DEC], check=False)).pack(side="right")
        self.var_total = tk.StringVar()
        ttk.Label(barre, textvariable=self.var_total, style="Doux.TLabel").pack(side="left", padx=12)
        cadre, self.liste = theme.tableau(self, [
            ("date", "Date", 150, "w"), ("importateur", "Importateur", 200, "w"), ("fichier", "Fichier", 520, "w")], 20)
        cadre.pack(fill="both", expand=True)
        self.liste.bind("<Double-1>", self.ouvrir)

    def fichiers(self):
        resultats = []
        for dossier in Path(generer.DEC).iterdir():
            historique = dossier / "1 - HISTORIQUE"
            if dossier.is_dir() and historique.is_dir():
                resultats += [(p.stat().st_mtime, dossier.name, p) for p in historique.glob("*.xml")]
        return sorted(resultats, reverse=True)

    def afficher(self):
        tous = self.fichiers()
        self.filtre.configure(values=[self.TOUS] + sorted({imp for _, imp, _ in tous}))
        choix = self.var_filtre.get()
        visibles = [f for f in tous if choix == self.TOUS or f[1] == choix]
        self.liste.delete(*self.liste.get_children())
        for date, importateur, chemin in visibles:
            self.liste.insert("", "end", iid=str(chemin), values=(
                datetime.datetime.fromtimestamp(date).strftime("%d/%m/%Y %H:%M"), importateur, chemin.name))
        self.var_total.set(f"{len(visibles)} déclaration(s)")

    def ouvrir(self, _evenement=None):
        if self.liste.selection():
            subprocess.run(["open", "-R", self.liste.selection()[0]], check=False)


# ==========================================================================
# Récupération des ratios
# ==========================================================================
class PageRatios(ttk.Frame):
    COLONNES = [("n", "Obs.", 60, "e"), ("min", "Min", 85, "e"), ("max", "Max", 85, "e"),
                ("moyenne", "Moyenne", 90, "e"), ("mediane", "Médiane", 90, "e"),
                ("pondere", "Pondéré", 90, "e"), ("ecart", "Écart", 80, "e")]

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.chemins, self.groupes, self.erreurs = [], [], []
        theme.entete_page(self, "Récupération des ratios", "Chargez un groupe de XML : les ratios FOB/kg sont "
                          "extraits et regroupés par article (même code et même désignation). Dépliez un article "
                          "pour voir le ratio de chaque fichier.")
        barre = ttk.Frame(self)
        barre.pack(fill="x")
        theme.bouton(barre, "Nouveaux XML…", self.ajouter_fichiers, principal=True).pack(side="left")
        theme.bouton(barre, "XML déjà disponibles…", self.choisir_disponibles).pack(side="left", padx=6)
        theme.bouton(barre, "Ajouter un dossier…", self.ajouter_dossier).pack(side="left", padx=6)
        theme.bouton(barre, "Vider", self.vider).pack(side="left")
        theme.bouton(barre, "Exporter Excel…", self.exporter).pack(side="right")
        self.var_importateur = tk.BooleanVar(value=False)
        ttk.Checkbutton(barre, text="Séparer par importateur", variable=self.var_importateur,
                        command=self.calculer).pack(side="right", padx=12)

        self.message = theme.Message(self)
        self.message.pack(fill="x", pady=(10, 8))
        cadre = ttk.Frame(self)
        cadre.pack(fill="both", expand=True)
        self.arbre = ttk.Treeview(cadre, columns=[c[0] for c in self.COLONNES], show="tree headings")
        self.arbre.heading("#0", text="Article  /  fichier", anchor="w")
        self.arbre.column("#0", width=430, anchor="w", stretch=True)
        for cle, titre, largeur, align in self.COLONNES:
            self.arbre.heading(cle, text=titre, anchor=align)
            self.arbre.column(cle, width=largeur, anchor=align, stretch=False)
        defil = ttk.Scrollbar(cadre, orient="vertical", command=self.arbre.yview)
        self.arbre.configure(yscrollcommand=defil.set)
        self.arbre.pack(side="left", fill="both", expand=True)
        defil.pack(side="right", fill="y")
        self.arbre.tag_configure("groupe", font=(theme.POLICE, 12, "bold"))
        self.arbre.tag_configure("fichier", foreground=theme.TEXTE_DOUX)
        self.message.afficher("alerte", "Aucun XML chargé", ["Ajoutez des fichiers ou un dossier entier (sous-dossiers inclus)."])

    def _ajouter(self, chemins):
        self.app.partager_xml(chemins)
        connus = set(self.chemins)
        self.chemins += [str(c) for c in chemins if str(c) not in connus]
        self.calculer()

    def choisir_disponibles(self):
        chemins = self.app.choisir_xml_disponibles(multiple=True)
        if chemins:
            self._ajouter(chemins)

    def ajouter_fichiers(self):
        self._ajouter(filedialog.askopenfilenames(title="XML à analyser", initialdir=generer.DEC,
                                                  filetypes=[("XML", "*.xml")]))

    def ajouter_dossier(self):
        dossier = filedialog.askdirectory(title="Dossier de XML (sous-dossiers inclus)", initialdir=generer.DEC)
        if dossier:
            self._ajouter(sorted(p for p in Path(dossier).rglob("*") if p.is_file() and p.suffix.lower() == ".xml"))

    def vider(self):
        self.chemins = []
        self.calculer()

    def calculer(self):
        import ratios
        self.arbre.delete(*self.arbre.get_children())
        if not self.chemins:
            self.groupes, self.erreurs = [], []
            self.message.afficher("alerte", "Aucun XML chargé", ["Ajoutez des fichiers ou un dossier entier."])
            return
        self.message.afficher("alerte", f"Lecture de {len(self.chemins)} fichier(s)…")
        self.update_idletasks()
        observations, self.erreurs = ratios.extraire(self.chemins)
        noms = {str(Path(d['chemin']).resolve()): d['nom'] for d in self.app.xml_disponibles()}
        for observation in observations:
            observation['fichier'] = noms.get(str(Path(observation['chemin']).resolve()), observation['fichier'])
        self.groupes = ratios.regrouper(observations, self.var_importateur.get())
        r4 = lambda x: f"{x:.4f}".replace(".", ",")
        for k, g in enumerate(self.groupes):
            titre = f"{g['position']}.  {g['designation'] or '(sans désignation)'}  ·  {g['code']}"
            if g["importateur"]:
                titre += f"  ·  {g['importateur']}"
            parent = self.arbre.insert("", "end", iid=f"g{k}", text=titre, tags=("groupe",), values=(
                len(g["observations"]), r4(g["min"]), r4(g["max"]), r4(g["moyenne"]), r4(g["mediane"]),
                r4(g["pondere"]), f"{g['ecart']:.0%}" if g["ecart"] is not None else "—"))
            for o in g["observations"]:
                self.arbre.insert(parent, "end", tags=("fichier",), text=f"{o['fichier']}   (art. {o['position']})",
                                  values=("", "", "", "", "", r4(o["ratio"]), ""))
        fichiers = len(self.chemins) - len(self.erreurs)
        lignes = [f"{len(observations)} ratio(s) extrait(s) de {fichiers} fichier(s) lisible(s)."]
        if self.erreurs:
            lignes.append(f"{len(self.erreurs)} fichier(s) écarté(s) : " + " | ".join(self.erreurs[:3])
                          + (" …" if len(self.erreurs) > 3 else ""))
        self.message.afficher("alerte" if self.erreurs else "ok",
                              f"{len(self.groupes)} article(s) regroupé(s)", lignes)

    def exporter(self):
        if not self.groupes:
            self.message.afficher("erreur", "Rien à exporter", ["Ajoutez d'abord des XML."])
            return
        chemin = filedialog.asksaveasfilename(
            title="Exporter les ratios", defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")],
            initialfile=f"Ratios {datetime.datetime.now():%Y-%m-%d %H%M}.xlsx")
        if not chemin:
            return
        import ratios
        try:
            ratios.exporter(self.groupes, chemin, self.erreurs)
        except Exception as exc:  # noqa: BLE001
            self.message.afficher("erreur", "Export impossible", [str(exc)])
            return
        subprocess.run(["open", chemin], check=False)
