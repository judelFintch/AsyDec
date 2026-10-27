"""Bibliothèque des références : documents conservés en base SQLite, statuts, marchandises."""
import datetime
import queue
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from zoneinfo import ZoneInfo

import generer
import import_fond
import import_references
import ratios
import service_references as service
from ui import theme
from ui.theme import nombre

# Correction d'événement et onglet Marchandises (avec export) : conservés mais ni
# construits ni déclenchables tant qu'une tâche dédiée ne les active pas.
ACTIONS_ACTIVES = False
# REF-102 : l'import a sa propre autorisation, indépendante des autres actions.
IMPORT_ACTIF = True
# REF-103 : changement de statut des documents, avec sa propre autorisation.
STATUTS_ACTIFS = True
FUSEAU = ZoneInfo("Africa/Lubumbashi")
TOUS = "Tous"
ORIGINES = {"Importé": "importe", "Généré": "genere"}
POLITIQUES = {
    "Acceptées uniquement": ("accepte",),
    "Non vérifiées uniquement": ("non_verifie",),
    "Acceptées et non vérifiées": ("accepte", "non_verifie"),
}
ACTIONS = [("accepte", "Accepté dans SYDONIA…"), ("rejete", "Rejeter…"), ("exclu", "Exclure…"),
           ("non_verifie", "Remettre « non vérifié »…")]


def montant(texte, decimales=0):
    """Texte décimal exact de la base → affichage français ; vide si absent."""
    return "—" if texte in (None, "") else nombre(float(texte), decimales)


def date_locale(horodatage):
    """Horodatage technique UTC de la base → date et heure de Lubumbashi, quel que soit le poste.
    Un horodatage sans fuseau est lu comme UTC (règle de stockage de la base)."""
    if not horodatage:
        return ""
    try:
        moment = datetime.datetime.fromisoformat(horodatage)
    except ValueError:
        return horodatage
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=datetime.timezone.utc)
    return moment.astimezone(FUSEAU).strftime("%d/%m/%Y %H:%M")


class DialogueStatut(tk.Toplevel):
    """Saisie d'un changement de statut ou d'une correction d'événement."""

    def __init__(self, parent, titre, valider, preuve="", auteur="", preuve_requise=False, correction=False):
        super().__init__(parent)
        self.title(titre)
        self.transient(parent.winfo_toplevel())
        self.resizable(False, False)
        self.valider, self.resultat = valider, None
        cadre = ttk.Frame(self, padding=18)
        cadre.pack(fill="both", expand=True)
        ttk.Label(cadre, text=titre, style="Section.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        libelle_preuve = "Preuve ou référence" + (" (obligatoire)" if preuve_requise else "")
        self.var_preuve = tk.StringVar(value=preuve or "")
        self.var_date = tk.StringVar()
        lignes = [(libelle_preuve, ttk.Entry(cadre, textvariable=self.var_preuve, width=60)),
                  ("Date effective (AAAA-MM-JJ)", ttk.Entry(cadre, textvariable=self.var_date, width=14))]
        if not correction:
            # Auteur = utilisateur connecté, affiché mais non modifiable.
            lignes.append(("Auteur", ttk.Label(cadre, text=auteur or "—")))
        for k, (texte, champ) in enumerate(lignes, 1):
            ttk.Label(cadre, text=texte).grid(row=k, column=0, sticky="w", pady=4, padx=(0, 10))
            champ.grid(row=k, column=1, sticky="w", pady=4)
        n = len(lignes) + 1
        ttk.Label(cadre, text="Commentaire" + (" (obligatoire)" if correction or not preuve_requise else "")).grid(
            row=n, column=0, sticky="nw", pady=4)
        self.commentaire = tk.Text(cadre, width=60, height=4, font=(theme.POLICE, 12))
        self.commentaire.grid(row=n, column=1, pady=4)
        if preuve:
            ttk.Label(cadre, text="Preuve proposée d'après le XML : vérifiez-la avant d'enregistrer.",
                      style="Doux.TLabel").grid(row=n + 1, column=1, sticky="w")
        self.erreur = ttk.Label(cadre, text="", style="Erreur.TLabel", wraplength=480)
        self.erreur.grid(row=n + 2, column=0, columnspan=2, sticky="w", pady=(8, 0))
        boutons = ttk.Frame(cadre)
        boutons.grid(row=n + 3, column=0, columnspan=2, sticky="e", pady=(12, 0))
        theme.bouton(boutons, "Annuler", self.destroy).pack(side="right")
        theme.bouton(boutons, "Enregistrer", self.enregistrer, principal=True).pack(side="right", padx=8)
        self.bind("<Escape>", lambda e: self.destroy())
        self.grab_set()

    def valeurs(self):
        return {"preuve": self.var_preuve.get(), "date_effective": self.var_date.get(),
                "commentaire": self.commentaire.get("1.0", "end").strip()}

    def enregistrer(self):
        try:
            self.resultat = self.valider(**self.valeurs())
        except ValueError as exc:
            self.erreur.configure(text=str(exc))
            return
        self.destroy()


class PageReferences(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.documents, self.detail, self.groupes = [], None, []
        self.tache, self._suivi, self._final = None, None, None
        theme.entete_page(self, "Bibliothèque des références", "Les XML importés sont conservés dans la base, avec "
                          "leurs taxes et leur provenance. Un document reste « non vérifié » tant que vous ne "
                          "l'acceptez pas avec une preuve.")
        barre = ttk.Frame(self)
        barre.pack(fill="x")
        self.boutons_import, self.bouton_annuler = [], None
        if IMPORT_ACTIF:
            self.boutons_import = [
                theme.bouton(barre, "Importer des XML…", self.importer_fichiers, principal=True),
                theme.bouton(barre, "Importer un dossier…", self.importer_dossier)]
            for k, b in enumerate(self.boutons_import):
                b.pack(side="left", padx=(0 if k == 0 else 6, 0))
            self.bouton_annuler = theme.bouton(barre, "Annuler l'import", self.annuler)
        self.var_compteurs = tk.StringVar()
        ttk.Label(barre, textvariable=self.var_compteurs, style="Doux.TLabel").pack(side="right")
        self.message = theme.Message(self)
        self.message.pack(fill="x", pady=(10, 6))

        self.onglets = ttk.Notebook(self)
        self.onglets.pack(fill="both", expand=True)
        self.onglet_documents = ttk.Frame(self.onglets, padding=(0, 10, 0, 0))
        self.onglet_marchandises = ttk.Frame(self.onglets, padding=(0, 10, 0, 0))
        self.onglets.add(self.onglet_documents, text="Documents")
        self._construire_documents(self.onglet_documents)
        if ACTIONS_ACTIVES:
            self.onglets.add(self.onglet_marchandises, text="Marchandises")
            self._construire_marchandises(self.onglet_marchandises)
        # Seulement si la page est affichée : la base ne s'ouvre qu'au premier besoin.
        self.onglets.bind("<<NotebookTabChanged>>",
                          lambda e: self.afficher() if getattr(app, "page_active", None) == "references" else None)

    # ================================================================ outils
    def conn(self):
        return self.app.base_refs()

    def _filtre(self, parent, texte, valeurs, largeur=22):
        ttk.Label(parent, text=texte).pack(side="left", padx=(12, 4))
        var = tk.StringVar(value=TOUS)
        choix = ttk.Combobox(parent, textvariable=var, values=valeurs, state="readonly", width=largeur)
        choix.pack(side="left")
        return var, choix

    # ============================================================ documents
    def _construire_documents(self, parent):
        filtres = ttk.Frame(parent)
        filtres.pack(fill="x")
        ttk.Label(filtres, text="Recherche").pack(side="left", padx=(0, 4))
        self.var_recherche = tk.StringVar()
        recherche = ttk.Entry(filtres, textvariable=self.var_recherche, width=22)
        recherche.pack(side="left")
        recherche.bind("<KeyRelease>", lambda e: self.lister())
        self.var_statut, choix_statut = self._filtre(filtres, "Statut", [TOUS] + list(service.STATUTS.values()), 18)
        self.var_importateur, self.choix_importateur = self._filtre(filtres, "Importateur", [TOUS])
        self.var_origine, choix_origine = self._filtre(filtres, "Origine", [TOUS] + list(ORIGINES), 9)
        for choix in (choix_statut, self.choix_importateur, choix_origine):
            choix.bind("<<ComboboxSelected>>", lambda e: self.lister())

        panneaux = ttk.PanedWindow(parent, orient="vertical")
        panneaux.pack(fill="both", expand=True, pady=(8, 0))
        haut = ttk.Frame(panneaux)
        cadre, self.liste = theme.tableau(haut, [
            ("fichier", "Fichier", 300, "w"), ("importateur", "Importateur", 170, "w"), ("ref", "Réf.", 90, "w"),
            ("fob", "FOB", 90, "e"), ("poids", "Poids kg", 90, "e"), ("taxes", "Taxes CDF", 110, "e"),
            ("statut", "Statut", 110, "w"), ("date", "Importé le", 120, "w")], 7)
        cadre.pack(fill="both", expand=True)
        self.liste.tag_configure("accepte", foreground=theme.OK)
        self.liste.tag_configure("rejete", foreground=theme.ERREUR)
        self.liste.tag_configure("exclu", foreground=theme.TEXTE_DOUX)
        self.liste.bind("<<TreeviewSelect>>", lambda e: self.ouvrir_document())
        panneaux.add(haut, weight=2)
        bas = ttk.Frame(panneaux, padding=(0, 8, 0, 0))
        panneaux.add(bas, weight=3)
        self._construire_fiche(bas)

    def _construire_fiche(self, parent):
        entete = ttk.Frame(parent)
        entete.pack(fill="x")
        self.var_titre = tk.StringVar(value="Sélectionnez un document.")
        ttk.Label(entete, textvariable=self.var_titre, style="Section.TLabel").pack(side="left")
        self.var_statut_doc = tk.StringVar()
        self.label_statut = ttk.Label(entete, textvariable=self.var_statut_doc)
        self.label_statut.pack(side="left", padx=12)
        self.boutons_statut = {}
        for statut, texte in reversed(ACTIONS if STATUTS_ACTIFS else []):
            b = theme.bouton(entete, texte, lambda s=statut: self.changer_statut(s), principal=(statut == "accepte"))
            b.pack(side="right", padx=(6, 0))
            self.boutons_statut[statut] = b
        theme.bouton(entete, "XML archivé", self.afficher_archive).pack(side="right", padx=(0, 12))

        cartes = ttk.Frame(parent)
        cartes.pack(fill="x", pady=8)
        self.cartes = {}
        for k, (cle, libelle) in enumerate((("fob", "FOB"), ("poids", "Poids · kg"), ("colis", "Colis"),
                                            ("cif", "CIF · CDF"), ("taux", "Taux"), ("taxes", "Taxes totales · CDF"))):
            cartes.columnconfigure(k, weight=1, uniform="cartes")
            carte = theme.Carte(cartes, libelle)
            carte.grid(row=0, column=k, sticky="nsew", padx=(0 if k == 0 else 6, 0))
            self.cartes[cle] = carte

        fiche = ttk.Notebook(parent)
        fiche.pack(fill="both", expand=True)
        onglet = ttk.Frame(fiche, padding=6)
        fiche.add(onglet, text="Articles et taxes")
        cadre, self.articles = theme.tableau(onglet, [
            ("pos", "Art.", 45, "center"), ("code", "Code", 90, "w"), ("nom", "Désignation", 230, "w"),
            ("poids", "Poids", 80, "e"), ("fob", "FOB", 85, "e"), ("colis", "Colis", 60, "e"),
            ("cif", "CIF CDF", 110, "e"), ("ratio", "Ratio", 75, "e"), ("taxes", "Taxes CDF", 100, "e")], 6)
        cadre.pack(side="left", fill="both", expand=True)
        self.articles.bind("<<TreeviewSelect>>", lambda e: self.montrer_taxes())
        cadre, self.taxes = theme.tableau(onglet, [
            ("code", "Taxe", 55, "w"), ("base", "Base", 95, "e"), ("taux", "Taux", 60, "e"),
            ("montant", "Montant", 95, "e")], 6)
        cadre.pack(side="left", fill="y", padx=(8, 0))

        onglet = ttk.Frame(fiche, padding=6)
        fiche.add(onglet, text="Diagnostics")
        cadre, self.diagnostics = theme.tableau(onglet, [
            ("gravite", "Gravité", 70, "w"), ("art", "Art.", 45, "center"), ("explication", "Explication", 520, "w"),
            ("calcule", "Calculé", 110, "e"), ("declare", "Déclaré", 110, "e")], 6)
        cadre.pack(fill="both", expand=True)

        onglet = ttk.Frame(fiche, padding=6)
        fiche.add(onglet, text="Statuts")
        cadre, self.historique = theme.tableau(onglet, [
            ("saisi", "Saisi le", 120, "w"), ("type", "Type", 85, "w"), ("statut", "Statut", 160, "w"),
            ("date", "Date effective", 100, "w"), ("preuve", "Preuve", 220, "w"),
            ("commentaire", "Commentaire", 220, "w"), ("auteur", "Auteur", 90, "w")], 5)
        cadre.pack(fill="both", expand=True)
        if ACTIONS_ACTIVES:
            theme.bouton(onglet, "Corriger l'événement sélectionné…", self.corriger).pack(anchor="e", pady=(6, 0))

        onglet = ttk.Frame(fiche, padding=6)
        fiche.add(onglet, text="Provenance")
        cadre, self.sources = theme.tableau(onglet, [
            ("nom", "Nom", 260, "w"), ("chemin", "Chemin rencontré", 520, "w"), ("vu", "Vu le", 120, "w")], 5)
        cadre.pack(fill="both", expand=True)
        self._etat_boutons()

    # ---------------------------------------------------------- affichage
    def afficher(self):
        try:
            conn = self.conn()
            c = service.compteurs(conn)
            options = service.options_filtres(conn)
        except Exception as exc:  # noqa: BLE001 - base illisible : le dire, ne rien inventer
            self.message.afficher("erreur", "Base des références illisible", [str(exc)])
            return
        self.var_compteurs.set(
            f"{c['documents']} document(s) · {c['acceptes']} accepté(s) · {c['observations']} ratio(s) · "
            f"{c['anomalies']} anomalie(s)")
        self.choix_importateur.configure(values=[TOUS] + options["importateurs"])
        if ACTIONS_ACTIVES:
            self.choix_importateur_m.configure(values=[TOUS] + options["importateurs"])
        if not c["documents"] and not self.import_en_cours:
            self.message.afficher("alerte", "La base est vide",
                                  ["Importez des XML pour commencer." if IMPORT_ACTIF else
                                   "L'import depuis cette page n'est pas encore activé."])
        if self.onglets.index("current") == 0:
            self.lister()
        elif ACTIONS_ACTIVES:
            self.calculer_marchandises()

    def lister(self):
        statut = next((k for k, v in service.STATUTS.items() if v == self.var_statut.get()), None)
        importateur = None if self.var_importateur.get() == TOUS else self.var_importateur.get()
        origine = ORIGINES.get(self.var_origine.get())
        selection = self.liste.selection()
        self.documents = service.lister_documents(self.conn(), statut, importateur,
                                                  self.var_recherche.get().strip() or None, origine)
        self.liste.delete(*self.liste.get_children())
        for d in self.documents:
            self.liste.insert("", "end", iid=str(d["id"]), tags=(d["statut"],), values=(
                d["nom_initial"], d["importateur"] or "—", d["declarant_reference"] or "—",
                montant(d["fob_total"], 2), montant(d["poids_total"]), montant(d["taxes_totales"]),
                service.STATUTS[d["statut"]], date_locale(d["importe_le"])))
        if selection and self.liste.exists(selection[0]):
            self.liste.selection_set(selection[0])
        elif self.detail and not self.liste.exists(str(self.detail["document"]["id"])):
            self.vider_fiche()

    def document_choisi(self):
        choix = self.liste.selection()
        return int(choix[0]) if choix else None

    def vider_fiche(self):
        self.detail = None
        self.var_titre.set("Sélectionnez un document.")
        self.var_statut_doc.set("")
        for carte in self.cartes.values():
            carte.definir("—")
        for arbre in (self.articles, self.taxes, self.diagnostics, self.historique, self.sources):
            arbre.delete(*arbre.get_children())
        self._etat_boutons()

    def ouvrir_document(self):
        document_id = self.document_choisi()
        if document_id is None:
            return
        try:
            d = self.detail = service.detail_document(self.conn(), document_id)
        except ValueError as exc:
            self.message.afficher("erreur", "Document introuvable", [str(exc)])
            return
        doc, v = d["document"], d["valorisation"]
        self.var_titre.set(f"{doc['nom_initial']}  ·  {doc['importateur'] or '—'}")
        self.var_statut_doc.set(service.STATUTS[d["statut"]] + ("  (" + doc["origine"] + ")" if doc["origine"] == "genere" else ""))
        self.label_statut.configure(style={"accepte": "Ok.TLabel", "rejete": "Erreur.TLabel"}.get(d["statut"], "Alerte.TLabel"))
        devise = v.get("devise_facture") or doc["devise"] or ""
        self.cartes["fob"].definir(f"{montant(v.get('fob_total'), 2)} {devise}".strip())
        self.cartes["poids"].definir(montant(v.get("poids_total")))
        self.cartes["colis"].definir(montant(v.get("colis_total")))
        self.cartes["cif"].definir(montant(v.get("cif_total")))
        self.cartes["taux"].definir(v.get("taux_change") or "—")
        self.cartes["taxes"].definir(montant(v.get("taxes_totales")))
        self.articles.delete(*self.articles.get_children())
        for a in d["articles"]:
            self.articles.insert("", "end", iid=str(a["id"]), values=(
                a["position"], a["code"] or "—", a["designation"] or "—", montant(a["poids_brut"]),
                montant(a["fob"], 2), montant(a["colis"]), montant(a["cif"]),
                f"{float(a['ratio']):.4f}" if a["ratio"] else "—", montant(a["taxes_article"])))
        if d["articles"]:
            self.articles.selection_set(str(d["articles"][0]["id"]))
        self.montrer_taxes()
        self.diagnostics.delete(*self.diagnostics.get_children())
        for g in d["diagnostics"]:
            self.diagnostics.insert("", "end", values=(g["gravite"], g["article_position"] or "", g["explication"],
                                                       g["valeur_calculee"] or "", g["valeur_declaree"] or ""))
        self.historique.delete(*self.historique.get_children())
        for e in d["historique"]:
            libelle = f"{service.STATUTS.get(e['ancien'], '—')} → {service.STATUTS[e['nouveau']]}"
            if e["type"] == "correction":
                libelle = f"corrige n° {e['corrige_id']}"
            self.historique.insert("", "end", iid=str(e["id"]), values=(
                date_locale(e["saisi_le"]), e["type"], libelle, e["date_effective"] or "", e["preuve"] or "",
                e["commentaire"] or "", e["auteur"] or ""))
        self.sources.delete(*self.sources.get_children())
        for s in d["sources"]:
            self.sources.insert("", "end", values=(s["nom"], s["chemin"], date_locale(s["vu_le"])))
        self._etat_boutons()

    def montrer_taxes(self):
        self.taxes.delete(*self.taxes.get_children())
        if not self.detail or not self.articles.selection():
            return
        article = next(a for a in self.detail["articles"] if str(a["id"]) == self.articles.selection()[0])
        for t in article["taxes"]:
            self.taxes.insert("", "end", values=(t["code"], montant(t["base"]), t["taux"] or "—", montant(t["montant"])))
        if not article["taxes"]:
            self.taxes.insert("", "end", values=("—", "", "", "aucune ligne"))

    def _etat_boutons(self):
        actuel = self.detail["statut"] if self.detail else None
        for statut, bouton in self.boutons_statut.items():
            bouton.configure(state="normal" if actuel and statut != actuel and not self.import_en_cours else "disabled")

    # ------------------------------------------------------------- statuts
    def changer_statut(self, nouveau):
        if not STATUTS_ACTIFS or not self.detail:
            return
        if self.import_en_cours:
            self.message.afficher("alerte", "Import en cours", ["Les statuts se changent une fois l'import terminé."])
            return
        document_id = self.detail["document"]["id"]
        acceptation = nouveau == "accepte"
        # Les règles (preuve, motif, dates, historique en ajout seul) restent celles du service.
        dialogue = DialogueStatut(
            self, f"{dict(ACTIONS)[nouveau].rstrip('…')} — {self.detail['document']['nom_initial']}",
            lambda **v: service.enregistrer_statut(self.conn(), document_id, nouveau,
                                                   auteur=self.app.utilisateur, **v),
            preuve=self.detail["preuve_suggeree"] if acceptation else "", auteur=self.app.utilisateur,
            preuve_requise=acceptation)
        self.wait_window(dialogue)
        if dialogue.resultat:
            self.message.afficher("ok", f"Statut enregistré : {service.STATUTS[nouveau]}",
                                  ["L'historique conserve le statut précédent."])
            self.lister()
            self.ouvrir_document()
            self.afficher_compteurs()

    def corriger(self):
        if not ACTIONS_ACTIVES:  # hors REF-101 : désactivé
            return
        if not self.detail or not self.historique.selection():
            self.message.afficher("alerte", "Aucun événement sélectionné", ["Choisissez une ligne dans l'onglet Statuts."])
            return
        evenement_id = int(self.historique.selection()[0])
        dialogue = DialogueStatut(
            self, f"Corriger l'événement n° {evenement_id}",
            lambda **v: service.corriger_evenement(self.conn(), evenement_id, v["commentaire"],
                                                   v["date_effective"], v["preuve"], self.app.utilisateur),
            correction=True)
        self.wait_window(dialogue)
        if dialogue.resultat:
            self.message.afficher("ok", "Correction enregistrée", ["L'événement d'origine reste visible."])
            self.ouvrir_document()

    def afficher_archive(self):
        if self.detail and Path(self.detail["document"]["archive"]).exists():
            subprocess.run(["open", "-R", self.detail["document"]["archive"]], check=False)
        elif self.detail:
            self.message.afficher("erreur", "Archive introuvable", [self.detail["document"]["archive"]])

    def afficher_compteurs(self):
        c = service.compteurs(self.conn())
        self.var_compteurs.set(
            f"{c['documents']} document(s) · {c['acceptes']} accepté(s) · {c['observations']} ratio(s) · "
            f"{c['anomalies']} anomalie(s)")

    # -------------------------------------------------------------- import
    @property
    def import_en_cours(self):
        return self.tache is not None and self.tache.en_cours()

    def importer_fichiers(self):
        if not IMPORT_ACTIF:
            return
        self._importer(filedialog.askopenfilenames(title="XML à importer dans la base", initialdir=generer.DEC,
                                                   filetypes=[("XML", "*.xml")]))

    def importer_dossier(self):
        if not IMPORT_ACTIF:
            return
        dossier = filedialog.askdirectory(title="Dossier de XML (sous-dossiers inclus)", initialdir=generer.DEC)
        if dossier:
            self._importer(import_references.lister_xml(dossier), nom=dossier)

    def annuler(self):
        if not IMPORT_ACTIF or not self.import_en_cours:
            return
        self.tache.annuler()
        self.bouton_annuler.configure(state="disabled")
        self.message.afficher("alerte", "Annulation demandée…", ["Le document en cours se termine, puis l'import s'arrête."])

    def _importer(self, chemins, nom=None):
        """Lance l'import dans une tâche de fond ; l'interface reste libre pendant ce temps."""
        if not IMPORT_ACTIF:
            return
        chemins = list(chemins)
        if not chemins or self.tache is not None:
            return
        fichier_base = self.conn().execute("PRAGMA database_list").fetchone()["file"]
        self.tache, self._final = import_fond.TacheImport(chemins, fichier_base, nom), None
        for b in self.boutons_import:
            b.configure(state="disabled")
        self.bouton_annuler.pack(side="left", padx=6)
        self.bouton_annuler.configure(state="normal")
        self.message.afficher("alerte", f"Import de {len(chemins)} fichier(s) lancé…")
        self.tache.demarrer()
        self._etat_boutons()  # statuts indisponibles pendant l'import
        self._suivi = self.after(100, self._suivre)

    def _suivre(self):
        """Lit les événements de la tâche (fil Tkinter uniquement). La tâche n'est oubliée qu'une
        fois son fil réellement arrêté : un reset ou une fermeture peut toujours l'attendre."""
        self._suivi = None
        tache = self.tache
        if tache is None:
            return
        while True:
            try:
                evenement = tache.evenements.get_nowait()
            except queue.Empty:
                break
            if evenement[0] == "progression":
                _, bilan, chemin = evenement
                self.message.afficher("alerte", f"Import {bilan.traites}/{bilan.trouves}…",
                                      [f"{bilan.importes} nouveau(x), {bilan.doublons} doublon(s), "
                                       f"{bilan.refuses} refusé(s)", Path(chemin).name])
            else:
                self._final = evenement
        if tache.en_cours():
            self._suivi = self.after(100, self._suivre)
        elif self._final is not None and self._final[0] == "fin":
            self._terminer(bilan=self._final[1])
        else:
            self._terminer(erreur=self._final[1] if self._final else "La tâche d'import s'est arrêtée sans bilan.")

    def _terminer(self, bilan=None, erreur=None):
        self.tache = None
        if self.bouton_annuler is not None:
            self.bouton_annuler.pack_forget()
        for b in self.boutons_import:
            b.configure(state="normal")
        if erreur:
            self.message.afficher("erreur", "Import interrompu", [erreur])
        else:
            titre = {"termine": "Import terminé", "annule": "Import annulé"}.get(bilan.etat, "Import interrompu")
            lignes = [f"{bilan.importes} document(s) ajouté(s), {bilan.doublons} doublon(s), "
                      f"{bilan.refuses} refusé(s) sur {bilan.trouves} fichier(s). Aucun n'est accepté automatiquement."]
            if bilan.etat == "annule":
                lignes.append(f"{bilan.trouves - bilan.traites} fichier(s) non traité(s) ; ceux déjà importés sont conservés.")
            lignes += [f"✘ {f} : {r}" for f, r in bilan.refus[:5]]
            self.message.afficher("ok" if bilan.etat == "termine" and not bilan.refuses else "alerte", titre, lignes)
        self._etat_boutons()
        if self.winfo_exists():
            self.afficher_compteurs()
            self.lister()

    def arreter_import(self, delai=5.0):
        """Avant reset, fermeture ou déconnexion : arrête la tâche (attente bornée).
        Renvoie False si elle tourne encore ; sinon annule le suivi périodique et renvoie True."""
        if self.tache is not None and not self.tache.arreter(delai):
            return False
        if self._suivi is not None:
            self.after_cancel(self._suivi)
            self._suivi = None
        self.tache = None
        return True

    def preparer_reset(self):
        """Callback de reset : arrête l'import (5 s au plus) ou refuse le reset."""
        if not self.arreter_import(5.0):
            raise ValueError("Un import de références est encore en cours : reset refusé, réessayez après son arrêt.")

    # =========================================================== marchandises
    def _construire_marchandises(self, parent):
        filtres = ttk.Frame(parent)
        filtres.pack(fill="x")
        ttk.Label(filtres, text="Documents pris en compte").pack(side="left", padx=(0, 4))
        self.var_politique = tk.StringVar(value="Acceptées et non vérifiées")
        politique = ttk.Combobox(filtres, textvariable=self.var_politique, values=list(POLITIQUES),
                                 state="readonly", width=26)
        politique.pack(side="left")
        self.var_importateur_m, self.choix_importateur_m = self._filtre(filtres, "Importateur", [TOUS])
        for choix in (politique, self.choix_importateur_m):
            choix.bind("<<ComboboxSelected>>", lambda e: self.calculer_marchandises())
        theme.bouton(filtres, "Exporter Excel…", self.exporter_marchandises).pack(side="right")
        self.var_politique_info = tk.StringVar()
        ttk.Label(parent, textvariable=self.var_politique_info, style="Doux.TLabel", wraplength=900).pack(anchor="w", pady=6)
        colonnes = [("obs", "Obs.", 50, "e"), ("acc", "Acceptées", 80, "e"), ("nv", "Non vérif.", 80, "e"),
                    ("min", "Min", 75, "e"), ("max", "Max", 75, "e"), ("med", "Médiane", 80, "e"),
                    ("pond", "Pondéré", 80, "e"), ("ecart", "Écart", 65, "e")]
        cadre = ttk.Frame(parent)
        cadre.pack(fill="both", expand=True)
        self.marchandises = ttk.Treeview(cadre, columns=[c[0] for c in colonnes], show="tree headings")
        self.marchandises.heading("#0", text="Marchandise  /  document", anchor="w")
        self.marchandises.column("#0", width=380, anchor="w", stretch=True)
        for cle, titre, largeur, align in colonnes:
            self.marchandises.heading(cle, text=titre, anchor=align)
            self.marchandises.column(cle, width=largeur, anchor=align, stretch=False)
        defil = ttk.Scrollbar(cadre, orient="vertical", command=self.marchandises.yview)
        self.marchandises.configure(yscrollcommand=defil.set)
        self.marchandises.pack(side="left", fill="both", expand=True)
        defil.pack(side="right", fill="y")
        self.marchandises.tag_configure("groupe", font=(theme.POLICE, 12, "bold"))
        self.marchandises.tag_configure("non_verifie", foreground=theme.ALERTE)
        self.marchandises.tag_configure("accepte", foreground=theme.OK)

    def calculer_marchandises(self):
        if not ACTIONS_ACTIVES:  # hors REF-101 : désactivé
            return
        statuts = POLITIQUES[self.var_politique.get()]
        importateur = None if self.var_importateur_m.get() == TOUS else self.var_importateur_m.get()
        observations = service.observations(self.conn(), statuts, importateur)
        self.groupes = ratios.regrouper(observations)
        acceptees = sum(o["statut"] == "accepte" for o in observations)
        if not observations:
            info = "Aucune observation pour ces critères."
        elif len(statuts) == 2:
            info = (f"{len(observations)} ratio(s) : {acceptees} de documents acceptés, "
                    f"{len(observations) - acceptees} de documents non vérifiés (en orange). "
                    "Les documents rejetés ou exclus ne sont jamais comptés.")
        else:
            info = f"{len(observations)} ratio(s) de documents {'acceptés' if statuts == ('accepte',) else 'non vérifiés'}."
        self.var_politique_info.set(info)
        r4 = lambda x: f"{x:.4f}".replace(".", ",")
        self.marchandises.delete(*self.marchandises.get_children())
        for k, g in enumerate(self.groupes):
            obs = g["observations"]
            acc = sum(o["statut"] == "accepte" for o in obs)
            parent = self.marchandises.insert("", "end", iid=f"g{k}", tags=("groupe",),
                                              text=f"{g['position']}.  {g['designation'] or '—'}  ·  {g['code']}  ·  {g['devise']}",
                                              values=(len(obs), acc, len(obs) - acc, r4(g["min"]), r4(g["max"]),
                                                      r4(g["mediane"]), r4(g["pondere"]),
                                                      f"{g['ecart']:.0%}" if g["ecart"] is not None else "—"))
            for o in obs:
                self.marchandises.insert(parent, "end", tags=(o["statut"],),
                                         text=f"{o['fichier']}   (art. {o['position']}, {service.STATUTS[o['statut']].lower()})",
                                         values=("", "", "", "", "", "", r4(o["ratio"]), ""))

    def exporter_marchandises(self):
        if not ACTIONS_ACTIVES:  # hors REF-101 : désactivé
            return
        if not self.groupes:
            self.message.afficher("erreur", "Rien à exporter", ["Aucune observation pour ces critères."])
            return
        chemin = filedialog.asksaveasfilename(
            title="Exporter les fourchettes", defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")],
            initialfile=f"Références {datetime.datetime.now():%Y-%m-%d %H%M}.xlsx")
        if not chemin:
            return
        try:
            ratios.exporter(self.groupes, chemin)
        except Exception as exc:  # noqa: BLE001
            self.message.afficher("erreur", "Export impossible", [str(exc)])
            return
        subprocess.run(["open", chemin], check=False)
