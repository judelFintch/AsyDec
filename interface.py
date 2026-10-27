"""Interface graphique du générateur de déclarations ASYCUDA.

Lancer : double-clic sur « INTERFACE.command », ou
    .venv/bin/python interface.py
"""
import datetime
import os
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill

import generer
import moteur
import variantes
import etude_xml
from presentation import VueSimulation, nombre as afficher_nombre

DOSSIER_SIMULATIONS = os.path.join(generer.ICI, "SIMULATIONS")


def lire_tableau_excel(chemin):
    """Lit un tableau d'articles dans un fichier Excel : cherche une ligne d'en-tête
    contenant « Poids » (et si possible « FOB », « Colis »), puis les lignes d'articles
    jusqu'à « Total ». Renvoie {poids, fob, colis, noms} (listes de 8 au plus)."""
    wb = load_workbook(chemin, data_only=True, read_only=True)
    try:
        for ws in wb.worksheets:
            lignes = list(ws.iter_rows(values_only=True))
            for h, ligne in enumerate(lignes):
                entetes = [str(c or "").strip().lower() for c in ligne]
                col = lambda mot: next((i for i, t in enumerate(entetes) if t.startswith(mot)), None)
                c_poids, c_fob, c_colis = col("poids"), col("fob"), col("colis")
                c_nom = col("marchandise")
                if c_poids is None:
                    continue
                res = {"poids": [], "fob": [], "colis": [], "noms": []}
                for suite in lignes[h + 1:]:
                    debut = " ".join(str(c or "") for c in suite[:2]).strip().lower()
                    if debut.startswith("total") or len(res["poids"]) == 8:
                        break
                    p = generer.nombre(suite[c_poids]) if c_poids < len(suite) else None
                    if p is None:
                        continue
                    res["poids"].append(p)
                    res["fob"].append(generer.nombre(suite[c_fob]) if c_fob is not None else None)
                    res["colis"].append(generer.nombre(suite[c_colis]) if c_colis is not None else None)
                    res["noms"].append(str(suite[c_nom]) if c_nom is not None and suite[c_nom] else None)
                if res["poids"]:
                    return res
        raise ValueError("Aucun tableau avec une colonne « Poids » trouvé dans ce fichier.")
    finally:
        wb.close()


class Application(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Déclarations ASYCUDA – DEC FRIPERIE")
        self.geometry("1120x860")
        self.minsize(1000, 760)
        self.ratios, self.table_imp = generer.charger_reglages()
        self.info = None
        self.dossier_a_confirmer = False
        self.dernier_fichier = None

        self.var_base = tk.StringVar()
        self.var_fob = tk.StringVar()
        self.var_colis = tk.StringVar()
        self.var_mode = tk.StringVar(value="RATIOS")
        self.var_dossier = tk.StringVar(value="Aucun fichier de base chargé.")
        self.var_totaux = tk.StringVar()
        self.var_sim_poids = tk.StringVar()
        self.var_sim_fob = tk.StringVar()
        self.var_sim_nb = tk.StringVar(value="Aucune simulation enregistrée.")
        self.simulations = []
        self.dernier_resultat = None
        self.controle_variantes = None
        self.var_controle = tk.StringVar()
        self.var_reference = tk.StringVar()
        self.var_methode = tk.StringVar(value="Choisissez une méthode pour préparer votre modèle.")

        self._construire()

    # ------------------------------------------------------------------ UI
    def _construire(self):
        pad = {"padx": 8, "pady": 4}
        zone = ttk.Frame(self)
        zone.pack(fill="both", expand=True)
        defilement = tk.Canvas(zone, highlightthickness=0)
        barre_verticale = ttk.Scrollbar(zone, orient="vertical", command=defilement.yview)
        defilement.configure(yscrollcommand=barre_verticale.set)
        barre_verticale.pack(side="right", fill="y")
        defilement.pack(side="left", fill="both", expand=True)
        cadre = ttk.Frame(defilement, padding=12)
        contenu = defilement.create_window((0, 0), window=cadre, anchor="nw")
        cadre.bind("<Configure>", lambda event: defilement.configure(scrollregion=defilement.bbox("all")))
        defilement.bind("<Configure>", lambda event: defilement.itemconfigure(contenu, width=event.width))

        barre = ttk.Frame(cadre)
        barre.pack(fill="x", pady=(0, 6))
        ttk.Label(barre, text="Déclarations ASYCUDA", font=("TkDefaultFont", 12, "bold")).pack(side="left")
        ttk.Button(barre, text="Refresh — dernière version", command=self.rafraichir_projet).pack(side="right")

        methodes = ttk.LabelFrame(cadre, text="Comment préparer votre modèle ?", padding=6)
        methodes.pack(fill="x", pady=(0, 6))
        choix_methodes = [
            ("1. Depuis un fichier Excel", "Importer les poids, FOB et colis par article.", self.methode_excel),
            ("2. Saisir les trois totaux", "Indiquer le poids, le FOB et les colis voulus.", lambda: self.methode_totaux(False)),
            ("3. Reprendre les totaux du XML", "Garder les totaux et proposer une autre répartition.", lambda: self.methode_totaux(True)),
        ]
        for colonne, (titre, description, action) in enumerate(choix_methodes):
            methodes.columnconfigure(colonne, weight=1, uniform="methodes")
            carte = ttk.Frame(methodes, padding=4)
            carte.grid(row=0, column=colonne, sticky="nsew")
            ttk.Button(carte, text=titre, command=action).pack(fill="x")
            ttk.Label(carte, text=description, wraplength=300).pack(anchor="w", pady=(3, 0))
        ttk.Label(methodes, textvariable=self.var_methode, foreground="#1F4E79").grid(row=1, column=0, columnspan=3, sticky="w", padx=4)
        ttk.Label(methodes, text="Un XML de base est nécessaire pour produire la déclaration finale.").grid(row=2, column=0, columnspan=3, sticky="w", padx=4)

        # 1. Fichier de base
        f1 = ttk.LabelFrame(cadre, text="1. Fichier de base (déclaration SYDONIA du dossier)", padding=8)
        f1.pack(fill="x")
        ttk.Entry(f1, textvariable=self.var_base).pack(side="left", fill="x", expand=True, **pad)
        ttk.Button(f1, text="Parcourir…", command=self.parcourir).pack(side="left", **pad)
        ttk.Button(f1, text="Charger", command=self.charger_base).pack(side="left", **pad)
        ttk.Label(cadre, textvariable=self.var_dossier, foreground="#1F4E79").pack(fill="x", padx=8, pady=(4, 8))
        ttk.Label(cadre, textvariable=self.var_controle, foreground="#C55A11").pack(fill="x", padx=8)

        bibli = ttk.Frame(cadre)
        bibli.pack(fill="x")
        ttk.Button(bibli, text="Conserver des XML de contrôle…", command=self.importer_modeles).pack(side="left", padx=4)
        ttk.Button(bibli, text="Proposer des variantes…", command=self.proposer_variantes).pack(side="left", padx=4)

        ttk.Button(bibli, text="Étudier des XML…", command=self.etudier_xml).pack(side="left", padx=4)

        references = ttk.Frame(cadre)
        references.pack(fill="x", pady=3)
        ttk.Label(references, text="Référence des ratios (tous les parcours) :").pack(side="left")
        self.choix_reference = ttk.Combobox(references, textvariable=self.var_reference, state="readonly", width=65)
        self.choix_reference.pack(side="left", fill="x", expand=True)
        ttk.Label(cadre, text="Art. 4/7/8 : ratios ajustables pour équilibrer le FOB. Autres : fourchettes des références compatibles. Arrondis au centime.").pack(anchor="w")

        # 2. Paramètres
        f2 = ttk.LabelFrame(cadre, text="2. Paramètres", padding=8)
        f2.pack(fill="x")
        ttk.Label(f2, text="FOB total (USD)").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(f2, textvariable=self.var_fob, width=14).grid(row=0, column=1, **pad)
        ttk.Label(f2, text="Colis total").grid(row=0, column=2, sticky="w", **pad)
        ttk.Entry(f2, textvariable=self.var_colis, width=10).grid(row=0, column=3, **pad)
        ttk.Label(f2, text="Mode FOB").grid(row=0, column=4, sticky="w", **pad)
        ttk.Radiobutton(f2, text="FOB calculés dans les bornes", value="RATIOS",
                        variable=self.var_mode, command=self._etat_fob).grid(row=0, column=5, sticky="w")
        ttk.Radiobutton(f2, text="FOB saisis (contrôlés)", value="SAISI",
                        variable=self.var_mode, command=self._etat_fob).grid(row=0, column=6, sticky="w")

        # 3. Articles
        f3 = ttk.LabelFrame(cadre, text="3. Articles (poids du colisage)", padding=8)
        f3.pack(fill="x", pady=(8, 0))
        for c, t in enumerate(["Art.", "Marchandise", "Poids (kg entiers)", "FOB (USD)", "Colis (vide = auto)", "Ratio"]):
            ttk.Label(f3, text=t, font=("TkDefaultFont", 11, "bold")).grid(row=0, column=c, sticky="w", padx=6)
        self.e_poids, self.e_fob, self.e_colis, self.l_ratio, self.l_nom = [], [], [], [], []
        for i in range(8):
            ttk.Label(f3, text=str(i + 1)).grid(row=i + 1, column=0, padx=6)
            l = ttk.Label(f3, text=generer.ARTICLES[i], width=28)
            l.grid(row=i + 1, column=1, sticky="w", padx=6)
            self.l_nom.append(l)
            for liste, col, w in ((self.e_poids, 2, 12), (self.e_fob, 3, 12), (self.e_colis, 4, 10)):
                e = ttk.Entry(f3, width=w, justify="right")
                e.grid(row=i + 1, column=col, padx=6, pady=2)
                liste.append(e)
            r = ttk.Label(f3, text=f"réf. {self.ratios[i]}", width=16)
            r.grid(row=i + 1, column=5, sticky="w", padx=6)
            self.l_ratio.append(r)
        ttk.Label(f3, textvariable=self.var_totaux, font=("TkDefaultFont", 11, "bold")).grid(
            row=9, column=1, columnspan=5, sticky="w", padx=6, pady=(6, 0))
        self._etat_fob()

        # Simulation
        fs = ttk.LabelFrame(cadre, text="Simulation (rien n'est enregistré tant que vous ne cliquez pas sur « Générer le XML »)", padding=8)
        fs.pack(fill="x", pady=(8, 0))
        ttk.Button(fs, text="Vérifier / simuler le tableau", command=self.simuler).pack(side="left", padx=4)
        ttk.Button(fs, text="Ajouter à la comparaison", command=self.ajouter_simulation).pack(side="left", padx=4)
        ttk.Button(fs, text="Exporter les simulations (Excel)", command=self.exporter_simulations).pack(side="left", padx=4)
        ttk.Button(cadre, text="Utiliser le même poids, FOB et colis que le XML chargé", command=self.utiliser_totaux_base).pack(anchor="w", padx=8, pady=3)
        ttk.Label(cadre, textvariable=self.var_sim_nb, foreground="#7F6000").pack(fill="x", padx=8)

        # 4. Actions
        f4 = ttk.Frame(cadre, padding=(0, 10))
        f4.pack(fill="x")
        ttk.Button(f4, text="Importer un tableau Excel…", command=self.importer_excel).pack(side="left", padx=4)
        ttk.Button(f4, text="Reprendre les valeurs de la base", command=self.reprendre_base).pack(side="left", padx=4)
        ttk.Button(f4, text="Aperçu (sans enregistrer)", command=self.apercu).pack(side="left", padx=4)
        ttk.Button(f4, text="Générer le XML", command=self.generer).pack(side="left", padx=4)
        ttk.Button(f4, text="Afficher le fichier", command=self.afficher).pack(side="left", padx=4)
        ttk.Button(f4, text="Vider", command=self.vider).pack(side="right", padx=4)

        # 5. Résultat
        f5 = ttk.LabelFrame(cadre, text="Résultat", padding=8)
        f5.pack(fill="both", expand=True)
        self.onglets_resultat=ttk.Notebook(f5)
        self.onglets_resultat.pack(fill="both",expand=True)
        self.vue_resultat=VueSimulation(self.onglets_resultat)
        messages=ttk.Frame(self.onglets_resultat)
        self.onglets_resultat.add(self.vue_resultat,text="Simulation détaillée")
        self.onglets_resultat.add(messages,text="Messages et historique du calcul")
        self.txt = tk.Text(messages, height=8, wrap="word", font=("Arial", 11))
        self.txt.pack(fill="both", expand=True)
        self._ecrire("1. Chargez le XML du dossier. 2. Choisissez la référence des ratios. 3. Importez les articles ou proposez des répartitions. 4. Vérifiez le tableau, puis générez le XML.")

    def _etat_fob(self):
        etat = "normal" if self.var_mode.get() == "SAISI" else "disabled"
        for e in self.e_fob:
            e.configure(state=etat)

    def _fin_controle(self):
        """Quitte le contrôle d'une variante et revient aux ratios de SAISIE.xlsx."""
        if not self.controle_variantes:
            return
        self.controle_variantes = None
        self.ratios = generer.charger_reglages()[0]
        for k in range(8):
            self.l_ratio[k].configure(text=f"réf. {self.ratios[k]}")
        self.var_controle.set("")

    def _ecrire(self, texte):
        self.onglets_resultat.select(1)
        self.txt.configure(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", texte)
        self.txt.configure(state="disabled")

    @staticmethod
    def _val(e):
        t = e.get().strip()
        return generer.nombre(t) if t else None

    @staticmethod
    def _remplir(e, valeur):
        etat = str(e.cget("state"))
        e.configure(state="normal")
        e.delete(0, "end")
        if valeur is not None:
            e.insert(0, f"{valeur:.15g}" if isinstance(valeur, float) else str(valeur))
        e.configure(state=etat)

    # ------------------------------------------------------------- actions
    def parcourir(self):
        chemin = filedialog.askopenfilename(initialdir=generer.DEC, title="Fichier de base SYDONIA",
                                            filetypes=[("Déclarations XML", "*.xml"), ("Tous", "*.*")])
        if chemin:
            self.var_base.set(chemin)
            self.charger_base()

    def charger_base(self):
        try:
            chemin = generer.trouver_base(self.var_base.get())
            self.info = moteur.infos_dossier(moteur.charger(chemin).getroot())
        except Exception as e:  # noqa: BLE001
            self.info = None
            messagebox.showerror("Fichier de base", str(e))
            return
        self._fin_controle()
        self.dossier_a_confirmer = False
        self.var_base.set(chemin)
        i = self.info
        self.var_dossier.set(
            f"{i['importateur']} ({i['code']})  •  réf. {i['reference']}  •  manifeste {i['manifeste']}  •  "
            f"camion {i['camion']}  •  taux {i['taux']:g}\n"
            f"Base : FOB {i['fob']:,.2f} USD  •  {i['poids']:,.0f} kg  •  {i['colis']} colis".replace(",", " "))
        for k, d in enumerate(i["designations"][:8]):
            self.l_nom[k].configure(text=(d or generer.ARTICLES[k])[:30])
        self.utiliser_totaux_base()
        self.actualiser_references()

    def actualiser_references(self):
        if not self.info:
            return
        base=self.var_base.get()
        candidats=[base]
        for p in variantes.modeles():
            try:
                variantes.verifier_modele(p)
                if variantes.signature(p)==variantes.signature(base) and str(p)!=base:
                    candidats.append(str(p))
            except Exception:
                continue
        self.choix_reference.configure(values=candidats)
        if self.var_reference.get() not in candidats:
            self.var_reference.set(base)

    def methode_excel(self):
        self.var_methode.set("Méthode 1 — importer le tableau Excel, vérifier les articles, puis générer le XML.")
        self.importer_excel()

    def methode_totaux(self, reprendre_xml=False):
        if not reprendre_xml:
            self.var_methode.set("Méthode 2 — saisissez les trois totaux ; recherche dans les modèles enregistrés.")
            self.simuler_depuis_bibliotheque()
            return
        if not self.var_base.get().strip():
            self.parcourir()
            if not self.var_base.get().strip():
                return
        self.charger_base()
        if not self.info:
            return
        if reprendre_xml:
            self.utiliser_totaux_base()
            self.var_methode.set("Méthode 3 — totaux du XML chargé ; choisissez une nouvelle répartition.")
        else:
            self.var_methode.set("Méthode 2 — modifiez les trois totaux, puis créez et choisissez une proposition.")
        self.proposer_variantes(saisir_totaux=not reprendre_xml)

    def utiliser_totaux_base(self):
        """Reprend uniquement les totaux de la base, sans modifier les articles."""
        if not self.info:
            self.charger_base()
            return
        self.var_sim_poids.set(f"{self.info['poids']:.15g}")
        self.var_sim_fob.set(f"{self.info['fob']:.15g}")
        self.var_fob.set(f"{self.info['fob']:.15g}")
        self.var_colis.set(str(self.info['colis']))

    def reprendre_base(self):
        if not self.info:
            self.charger_base()
            if not self.info:
                return
        for k in range(8):
            self._remplir(self.e_poids[k], self.info["poids_articles"][k] if k < len(self.info["poids_articles"]) else None)
            self._remplir(self.e_fob[k], self.info["fob_articles"][k] if k < len(self.info["fob_articles"]) else None)
            self._remplir(self.e_colis[k], None)
        self.var_fob.set(f"{self.info['fob']:g}")
        self.var_colis.set(str(self.info["colis"]))

    def vider(self):
        for liste in (self.e_poids, self.e_fob, self.e_colis):
            for e in liste:
                self._remplir(e, None)
        self._fin_controle()
        self.var_totaux.set("")
        self._ecrire("Champs vidés.")

    def _calculer(self, enregistrer):
        if not self.info:
            self.charger_base()
            if not self.info:
                return None
        try:
            colis = [self._val(e) for e in self.e_colis]
            controle=self.var_reference.get() or self.var_base.get()
            profil=variantes.construire_profil(controle)
            res = generer.produire(
                self.var_base.get(),
                [self._val(e) for e in self.e_poids],
                self.ratios, self.table_imp, self.registre_charge(),
                mode=self.var_mode.get(),
                fob_total=generer.nombre(self.var_fob.get()) if self.var_fob.get().strip() else None,
                fob_saisis=[self._val(e) for e in self.e_fob],
                colis_total=generer.nombre(self.var_colis.get()) if self.var_colis.get().strip() else None,
                colis_saisis=colis,
                enregistrer=enregistrer, profil=profil,
            )
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Calcul impossible", str(e))
            return None
        if enregistrer:
            generer.ecrire_registre(self._registre)
        self.controle_variantes = profil
        self.var_controle.set("Contrôle commun actif : ratios 4/7/8 ajustables ; autres dans leurs fourchettes.")
        self.ratios=list(profil['ratios'])
        self._afficher_resultat(res, enregistrer)
        self.dernier_resultat = res
        return res

    # ------------------------------------------------------- import Excel
    def importer_excel(self):
        chemin = filedialog.askopenfilename(initialdir=os.path.expanduser("~/Downloads"),
                                            title="Tableau Excel (poids, FOB, colis)",
                                            filetypes=[("Excel", "*.xlsx *.xlsm"), ("Tous", "*.*")])
        if not chemin:
            return
        try:
            t = lire_tableau_excel(chemin)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Import Excel", str(e))
            return
        n = len(t["poids"])
        for k in range(8):
            self._remplir(self.e_poids[k], t["poids"][k] if k < n else None)
            self._remplir(self.e_fob[k], t["fob"][k] if k < n else None)
            self._remplir(self.e_colis[k], t["colis"][k] if k < n and t["colis"][k] is not None else None)
        fob_complets = n == 8 and all(f is not None for f in t["fob"])
        if fob_complets:
            self.var_mode.set("SAISI")
            self.var_fob.set(f"{round(sum(t['fob']), 2):g}")
        self._etat_fob()
        if n == 8 and all(c is not None for c in t["colis"]):
            self.var_colis.set(str(int(sum(t["colis"]))))
        self._ecrire(f"Tableau importé : {os.path.basename(chemin)}\n"
                     f"{n} articles • {sum(t['poids']):,.0f} kg".replace(",", " ")
                     + (f" • FOB {sum(t['fob']):,.2f} USD (mode « FOB saisis »)".replace(",", " ") if fob_complets else "")
                     + ("\n⚠ Le tableau n'a pas 8 articles." if n != 8 else "")
                     + "\n\nVérifiez les valeurs, choisissez le fichier de base, puis « Aperçu » ou « Simuler ».")

    # ---------------------------------------------------------- simulation
    def simuler(self):
        """Vérifie toujours le tableau affiché, sans en changer les poids ni les totaux."""
        if all(not e.get().strip() for e in self.e_poids):
            messagebox.showinfo("Simulation", "Le tableau est vide. Choisissez en haut « Saisir les trois totaux » ou « Reprendre les totaux du XML » pour obtenir des propositions.")
            return
        self._calculer(enregistrer=False)

    def ajouter_simulation(self):
        res = self._calculer(enregistrer=False)
        if not res:
            return
        r = res["resume"]
        self.simulations.append({
            "nom": f"Simulation {len(self.simulations) + 1}",
            "dossier": f"{res['info']['importateur']} – {res['info']['reference']}",
            "poids": [a["poids"] for a in r["articles"]], "fob": res["fob"], "colis": res["colis"],
            "cif": [a["cif"] for a in r["articles"]], "taxes": [a["taxes"] for a in r["articles"]],
            "taxes_globales": r["taxes_globales"], "taxes_totales": r["taxes_totales"],
            "alertes": res["alertes"],
        })
        self.var_sim_nb.set(f"{len(self.simulations)} simulation(s) dans la comparaison.")

    def exporter_simulations(self):
        if not self.simulations:
            messagebox.showinfo("Simulations", "Ajoutez d'abord au moins une simulation à la comparaison.")
            return
        os.makedirs(DOSSIER_SIMULATIONS, exist_ok=True)
        chemin = os.path.join(DOSSIER_SIMULATIONS,
                              f"Simulations {datetime.datetime.now():%Y-%m-%d %H%M}.xlsx")
        wb = Workbook()
        ws = wb.active
        ws.title = "COMPARAISON"
        ws.append(["SIMULATIONS – document de travail, ce n'est pas une déclaration"])
        ws["A1"].font = Font(bold=True, size=13, color="C00000")
        ws.append([f"Créé le {datetime.datetime.now():%d/%m/%Y %H:%M}"])
        ws.append([])
        entete = ["Art.", "Marchandise"]
        for s in self.simulations:
            entete += [f"{s['nom']} – Poids", "FOB", "Ratio", "Colis", "Taxes CDF"]
        ws.append(entete)
        jaune = PatternFill("solid", fgColor="FFF2CC")
        for c in ws[4]:
            c.font = Font(bold=True)
            c.fill = jaune
        for k in range(8):
            ligne = [k + 1, generer.ARTICLES[k]]
            for s in self.simulations:
                p, f = s["poids"][k], s["fob"][k]
                ligne += [p, f, round(f / p, 4) if p else None, s["colis"][k], s["taxes"][k]]
            ws.append(ligne)
        tot = ["", "TOTAL"]
        for s in self.simulations:
            tot += [sum(s["poids"]), round(sum(s["fob"]), 2), None, sum(s["colis"]), sum(s["taxes"])]
        ws.append(tot)
        glob = ["", "Taxes globales"]
        for s in self.simulations:
            glob += ["", "", "", "", s["taxes_globales"]]
        ws.append(glob)
        tt = ["", "TOTAL TAXES"]
        for s in self.simulations:
            tt += ["", "", "", "", s["taxes_totales"]]
        ws.append(tt)
        for c in ws[ws.max_row]:
            c.font = Font(bold=True)
        ws.append([])
        for s in self.simulations:
            ws.append([s["nom"], s["dossier"], "Alertes : " + (" | ".join(s["alertes"]) or "aucune")])
        ws.column_dimensions["B"].width = 26
        wb.save(chemin)
        subprocess.run(["open", chemin], check=False)
        self.var_sim_nb.set(f"{len(self.simulations)} simulation(s) exportée(s) : {os.path.basename(chemin)}")

    def etudier_xml(self):
        fen = tk.Toplevel(self)
        fen.title("Étude des XML — ratios et variations")
        fen.geometry("1050x720")
        statut = tk.StringVar()
        ttk.Label(fen, textvariable=statut).pack(fill="x", padx=10, pady=5)
        tableau = ttk.Treeview(fen, columns=("fichier","importateur","articles","devise","alertes"), show="headings", height=9)
        for cle,titre in [("fichier","Fichier"),("importateur","Importateur"),("articles","Articles"),("devise","Devise"),("alertes","Alertes")]:
            tableau.heading(cle,text=titre)
            tableau.column(cle,width=320 if cle=="fichier" else 150)
        tableau.pack(fill="both",expand=True,padx=10)
        detail=tk.Text(fen,height=17,wrap="word",font=("Menlo",11))
        detail.pack(fill="both",expand=True,padx=10,pady=8)
        etudes=[]

        def afficher(event=None):
            if not tableau.selection():
                return
            indice=tableau.selection()[0]
            if not indice.isdigit() or int(indice)>=len(etudes):
                return
            e=etudes[int(indice)]
            detail.delete("1.0","end")
            detail.insert("end",f"{e['fichier']}\nSource : {e['source']}\nDevise : {e['devise']} — ratio = FOB / poids brut (kg)\n\n")
            for a in e['articles']:
                ratio=f"{a['ratio']:.8g}" if a['ratio'] is not None else "non calculable"
                detail.insert("end",f"Art. {a['article']} — {a['code']} — {a['designation']}\nPoids : {a['poids']} kg | FOB : {a['fob']} | Colis : {a['colis']} | Ratio : {ratio}\n\n")
            detail.insert("end","Alertes : " + (" | ".join(e['alertes']) or "aucune"))

        def actualiser():
            donnees,erreurs=etude_xml.charger()
            etudes[:]=donnees
            tableau.delete(*tableau.get_children())
            for k,e in enumerate(etudes):
                tableau.insert("","end",iid=str(k),values=(e['fichier'],e['importateur'],len(e['articles']),e['devise'],len(e['alertes'])))
            statut.set(f"{len(etudes)} XML conservé(s). Sélectionnez une ligne pour consulter ses ratios. Export : toute la bibliothèque d’études.")
            if etudes:
                tableau.selection_set("0")
                afficher()
            if erreurs:
                messagebox.showwarning("Études illisibles","\n".join(erreurs),parent=fen)

        def importer(chemins):
            erreurs=[]
            for chemin in chemins:
                try:
                    etude_xml.enregistrer(chemin)
                except Exception as exc:
                    erreurs.append(f"{os.path.basename(chemin)} : {exc}")
            actualiser()
            if self.info:
                self.actualiser_references()
            if erreurs:
                messagebox.showwarning("Fichiers non étudiés","\n".join(erreurs),parent=fen)

        def fichiers():
            importer(filedialog.askopenfilenames(parent=fen,title="XML à étudier (sélection multiple)",filetypes=[("XML","*.xml")]))

        def dossier():
            from pathlib import Path
            chemin=filedialog.askdirectory(parent=fen,title="Dossier à étudier, sous-dossiers inclus")
            if chemin:
                importer([p for p in Path(chemin).rglob('*') if p.is_file() and p.suffix.lower()=='.xml'])

        def reference_et_seuil():
            if not tableau.selection():
                raise ValueError("Sélectionnez le XML qui servira de référence.")
            seuil=generer.nombre(var_seuil.get())
            if seuil is None or seuil<0:
                raise ValueError("Indiquez un seuil de variation positif ou nul, en %.")
            return etudes[int(tableau.selection()[0])]['id'],seuil/100

        def analyser_complet():
            try:
                reference,seuil=reference_et_seuil()
                rapport=etude_xml.comparer(etudes,reference,seuil)
                detail.delete("1.0","end")
                detail.insert("end",f"ANALYSE COMPLÈTE — référence : {rapport['reference']['fichier']}\nSeuil : {seuil:.1%}. Écarts par rapport au modèle choisi, sans chronologie.\n")
                for sens in ('HAUSSE','BAISSE','STABLE','NON COMPARABLE'):
                    detail.insert("end",f"{sens} : {sum(c['sens']==sens for c in rapport['changements'])} mesures\n")
                detail.insert("end","\nPrincipaux écarts de ratios (plus forts en premier) :\n")
                ratios=sorted((c for c in rapport['changements'] if c['metrique']=='ratio' and c['relatif'] is not None),key=lambda c:abs(c['relatif']),reverse=True)
                for c in ratios[:30]:
                    detail.insert("end",f"{c['fichier']} — art. {c['article']} : {c['sens']} {c['relatif']:+.2%} ({c['avant']:.6g} → {c['apres']:.6g})" + (" — À EXAMINER" if c['important'] else "") + "\n")
                detail.insert("end","\nPoints à vérifier :\n")
                for p in rapport['problemes']:
                    detail.insert("end",f"{p['fichier']} — {p['niveau']} : {p['detail']}\n")
                if not rapport['problemes']:
                    detail.insert("end","Aucun signal détecté par ces contrôles.\n")
            except Exception as exc:
                messagebox.showerror("Analyse",str(exc),parent=fen)

        def exporter():
            if not etudes:
                messagebox.showinfo("Analyse","Importez d’abord des XML à étudier.",parent=fen)
                return
            chemin=filedialog.asksaveasfilename(parent=fen,title="Exporter les données et variations",defaultextension=".xlsx",
                initialfile=f"Analyse XML {datetime.datetime.now():%Y-%m-%d %H%M%S}.xlsx",filetypes=[("Excel","*.xlsx")])
            if chemin:
                try:
                    reference,seuil=reference_et_seuil()
                    etude_xml.exporter(etudes,chemin,reference,seuil)
                    messagebox.showinfo("Export terminé",f"Analyse enregistrée :\n{chemin}\nLes formules se recalculent à l’ouverture dans Excel.",parent=fen)
                except Exception as exc:
                    messagebox.showerror("Export impossible",str(exc),parent=fen)

        reglages=ttk.Frame(fen)
        reglages.pack(fill="x",padx=10)
        ttk.Label(reglages,text="Référence = XML sélectionné dans la liste. Seuil à examiner (%) :").pack(side="left")
        var_seuil=tk.StringVar(value="10")
        ttk.Entry(reglages,textvariable=var_seuil,width=8).pack(side="left",padx=4)
        ttk.Button(reglages,text="Analyse complète",command=analyser_complet).pack(side="left",padx=8)
        actions=ttk.Frame(fen)
        actions.pack(fill="x",padx=10,pady=8)
        ttk.Button(actions,text="Ajouter des XML…",command=fichiers).pack(side="left",padx=4)
        ttk.Button(actions,text="Ajouter un dossier…",command=dossier).pack(side="left",padx=4)
        ttk.Button(actions,text="Exporter l’analyse Excel…",command=exporter).pack(side="left",padx=4)
        tableau.bind("<<TreeviewSelect>>",afficher)
        actualiser()

    def importer_modeles(self):
        chemins = filedialog.askopenfilenames(title="XML de référence", filetypes=[("XML", "*.xml")])
        erreurs, total = [], 0
        for chemin in chemins:
            try:
                variantes.conserver(chemin)
                total += 1
            except Exception as exc:
                erreurs.append(f"{os.path.basename(chemin)} : {exc}")
        if self.info:
            self.actualiser_references()
        if chemins:
            messagebox.showinfo("Bibliothèque", f"{total} modèle(s) conservé(s).\n" + "\n".join(erreurs))

    def simuler_depuis_bibliotheque(self):
        fen=tk.Toplevel(self)
        fen.title("Option 2 — totaux et recherche automatique des modèles")
        fen.geometry("1200x860")
        fen.minsize(960, 720)
        ttk.Label(fen,text="Saisissez vos totaux. Les contrôles utilisent les modèles déjà enregistrés ; aucun fichier à charger.",wraplength=950).pack(padx=10,pady=8)
        champs=[]
        saisie=ttk.Frame(fen,padding=8)
        saisie.pack(fill="x")
        for titre in ("FOB total (USD)","Poids total (kg entiers)","Nombre total de colis"):
            ligne=ttk.Frame(saisie)
            ligne.pack(side="left",fill="x",expand=True,padx=6)
            ttk.Label(ligne,text=titre).pack(anchor="w")
            entree=ttk.Entry(ligne)
            entree.pack(fill="x",pady=3)
            champs.append(entree)
        champs[0].focus_set()
        actions=ttk.Frame(fen)
        actions.pack(fill="x",padx=10,pady=8)
        lancer=ttk.Button(actions,text="1. Rechercher et simuler",command=lambda:chercher())
        lancer.pack(side="left",padx=4)
        autre=ttk.Button(actions,text="Autres propositions",command=lambda:chercher(True),state="disabled")
        autre.pack(side="left",padx=4)
        valider=ttk.Button(actions,text="3. Choisir cette proposition",command=lambda:reprendre(),state="disabled")
        valider.pack(side="left",padx=4)
        etape=tk.StringVar(value="Étape 1 : saisissez les trois totaux, puis cliquez sur « Rechercher et simuler » (ou Entrée).")
        ttk.Label(fen,textvariable=etape,foreground="#1F4E79",wraplength=950).pack(fill="x",padx=14,pady=4)
        for entree in champs:
            entree.bind("<Return>",lambda event:chercher())
        ttk.Label(fen,text="Ratios 4/7/8 ajustables ; autres dans les fourchettes compatibles. Colis estimés : 10 minimum chacun, tous différents (total ≥ 108).").pack(padx=10,pady=5)
        tableau=ttk.Treeview(fen,columns=("numero","modele","score","taxes"),show="headings",height=4,style="Simulation.Treeview")
        for cle,titre,largeur in (("numero","Proposition",95),("modele","Modèle de référence",570),("score","Proximité /100",140),("taxes","Taxes estimées CDF",180)):
            tableau.heading(cle,text=titre)
            tableau.column(cle,width=largeur)
        tableau.pack(fill="x",padx=10)
        detail=VueSimulation(fen)
        detail.pack(fill="both",expand=True,padx=8,pady=6)
        candidats=[]
        historiques={}
        ecartes=[]

        def afficher(event=None):
            if not tableau.selection():
                return
            indice=tableau.selection()[0]
            if not indice.isdigit() or int(indice)>=len(candidats):
                return
            v=candidats[int(indice)]
            etape.set("Étape 3 : consultez les détails ci-dessous, puis cliquez sur « Choisir cette proposition ».")
            detail.afficher(v,v['profil'],v['modele'],ecartes,numero=int(indice)+1)

        def chercher(regenerer=False):
            lancer.configure(state="disabled")
            autre.configure(state="disabled")
            valider.configure(state="disabled")
            etape.set("Recherche de répartitions compatibles dans les modèles enregistrés…")
            fen.update_idletasks()
            try:
                fob,poids,colis=[generer.nombre(e.get()) for e in champs]
                if any(v is None for v in (fob,poids,colis)):
                    raise ValueError("Renseignez le FOB, le poids et les colis.")
                cle=(poids,fob,colis)
                vus=historiques.get(cle,set())
                propositions,erreurs=variantes.rechercher_modeles(poids,fob,colis,nombre=1 if regenerer else 12,exclure=vus)
                for v in propositions:
                    v['resultat']=generer.produire(v['controle'],v['poids'],v['profil']['ratios'],self.table_imp,{},
                        mode="SAISI",fob_total=fob,fob_saisis=v['fob'],colis_total=colis,colis_saisis=v['colis'],
                        enregistrer=False,profil=v['profil'])
                candidats[:]=propositions
                ecartes[:]=erreurs
                historiques.setdefault(cle,set()).update(variantes.cle_variante(v) for v in propositions)
                tableau.delete(*tableau.get_children())
                for k,v in enumerate(candidats):
                    tableau.insert("","end",iid=str(k),values=(f"N° {k+1}",v['modele'],afficher_nombre(v['proximite'],2),afficher_nombre(v['resultat']['resume']['taxes_totales'])))
                tableau.selection_set("0")
                afficher()
                etape.set(f"{len(candidats)} proposition(s) trouvée(s). Étape 2 : cliquez sur une ligne pour voir le détail ; étape 3 : choisissez votre proposition.")
            except Exception as exc:
                etape.set("La recherche n’a pas abouti. Vérifiez le message et vos totaux." + (" Les propositions précédentes restent disponibles." if candidats else ""))
                messagebox.showerror("Recherche de modèles",str(exc),parent=fen)
            finally:
                lancer.configure(state="normal")
                autre.configure(state="normal" if candidats else "disabled")
                valider.configure(state="normal" if candidats else "disabled")

        def reprendre():
            if not tableau.selection():
                return
            v=candidats[int(tableau.selection()[0])]
            self.var_base.set(v['controle'])
            self.charger_base()
            self.var_reference.set(v['controle'])
            self.var_mode.set("SAISI")
            self._etat_fob()
            for k in range(8):
                for entrees,cle in ((self.e_poids,'poids'),(self.e_fob,'fob'),(self.e_colis,'colis')):
                    self._remplir(entrees[k],v[cle][k])
            self.var_fob.set(f"{sum(v['fob']):.2f}")
            self.var_colis.set(str(sum(v['colis'])))
            self._calculer(False)
            self.dossier_a_confirmer=True
            self.var_dossier.set("SIMULATION SUR MODÈLE ENREGISTRÉ — XML du dossier à associer seulement lors de l’export.")
            fen.destroy()

        tableau.bind("<<TreeviewSelect>>",afficher)

    def proposer_variantes(self, saisir_totaux=False, totaux=None):
        if not self.info and not self.var_base.get().strip():
            self.parcourir()
            if not self.var_base.get().strip():
                return
        if not self.info:
            self.charger_base()
            if not self.info:
                return
        fen = tk.Toplevel(self)
        fen.title("Variantes contrôlées — classement par proximité des références")
        fen.geometry("1200x900")
        self.actualiser_references()
        disponibles = [self.var_base.get()] + [str(p) for p in variantes.modeles() if str(p)!=self.var_base.get()]
        ttk.Label(fen, text="XML de contrôle conservé (même ordre et mêmes marchandises que la base)").pack()
        choix = ttk.Combobox(fen, state="readonly", values=[os.path.basename(p) for p in disponibles], width=85)
        choix.pack(fill="x", padx=10)
        if disponibles:
            selection_reference=self.var_reference.get()
            choix.current(disponibles.index(selection_reference) if selection_reference in disponibles else 0)
        champs = []
        valeurs = [self.info['poids'], self.info['fob'], self.info['colis']]
        if totaux is not None:
            valeurs = [ancien if nouveau is None else nouveau for ancien,nouveau in zip(valeurs,totaux)]
        for titre, valeur in zip(("Poids total (kg entiers)", "FOB total (USD)", "Colis total"), valeurs):
            ligne = ttk.Frame(fen)
            ligne.pack(fill="x", padx=10, pady=3)
            ttk.Label(ligne, text=titre, width=22).pack(side="left")
            entree = ttk.Entry(ligne)
            entree.insert(0, f"{valeur:.15g}")
            entree.pack(side="left")
            champs.append(entree)
        if saisir_totaux:
            champs[0].focus_set()
            champs[0].selection_range(0, "end")
        def reprendre_totaux():
            for entree, cle in zip(champs, ('poids', 'fob', 'colis')):
                self._remplir(entree, self.info[cle])
        ttk.Button(fen, text="Utiliser le même poids, FOB et colis que le XML chargé", command=reprendre_totaux).pack(anchor="w", padx=10, pady=4)
        ttk.Label(fen, text="Ratios 4/7/8 ajustables ; autres dans les fourchettes. Colis auto : minimum 10 chacun, tous différents (total ≥ 108).").pack()
        tableau = ttk.Treeview(fen, columns=("score", "poids", "fob", "colis", "taxes"), show="headings", height=4)
        for cle, titre in zip(("score", "poids", "fob", "colis", "taxes"), ("Proximité / 100", "Poids kg", "FOB USD", "Colis", "Taxes estimées CDF")):
            tableau.heading(cle, text=titre)
            tableau.column(cle, width=140)
        tableau.pack(fill="x", padx=10, pady=8)
        detail = VueSimulation(fen)
        detail.pack(fill="both", expand=True, padx=8, pady=6)
        candidats = []
        contexte = {}
        deja_proposes = {}

        def selection(event=None):
            if not tableau.selection() or tableau.selection()[0] not in tableau.get_children():
                return
            v = candidats[int(tableau.selection()[0])]
            profil=contexte['profil']
            detail.afficher(v,profil,contexte['controle'],profil['exclus'],numero=int(tableau.selection()[0])+1)

        def calculer(regenerer=False):
            try:
                if choix.current() < 0:
                    raise ValueError("Conservez d'abord un XML de contrôle.")
                controle = str(disponibles[choix.current()])
                info = variantes.verifier_modele(controle)
                base = generer.trouver_base(self.var_base.get())
                variantes.verifier_modele(base)
                if variantes.signature(base) != variantes.signature(controle):
                    raise ValueError("La base et le contrôle doivent avoir les mêmes codes et désignations dans le même ordre.")
                profil = variantes.construire_profil(controle)
                ratios = profil['ratios']
                valeurs = [generer.nombre(e.get()) for e in champs]
                cle = (base, controle, tuple(valeurs), tuple(profil['bornes']))
                historique = deja_proposes.get(cle, set())
                propositions = variantes.generer(*valeurs, ratios, profil=profil,
                    nombre=1 if regenerer else 12, exclure=historique)

                registre = generer.lire_registre()
                for v in propositions:
                    ratios_v = [ratios[k] if k in moteur.ARTICLES_VARIABLES else v['fob'][k]/v['poids'][k] for k in range(8)]
                    v['resultat'] = generer.produire(base, v['poids'], ratios_v, self.table_imp, registre,
                        mode="SAISI", fob_total=valeurs[1], fob_saisis=v['fob'],
                        colis_total=valeurs[2], colis_saisis=v['colis'], enregistrer=False, profil=profil)
                deja_proposes.setdefault(cle, set()).update(variantes.cle_variante(v) for v in propositions)
                candidats[:] = propositions
                contexte.update(base=base, ratios=ratios, profil=profil, controle=os.path.basename(controle), reference_chemin=controle)
                tableau.delete(*tableau.get_children())
                for k,v in enumerate(candidats):
                    tableau.insert("", "end", iid=str(k), values=(v["proximite"], f"{sum(v['poids']):.0f}",
                        f"{sum(v['fob']):.2f}", sum(v['colis']), v['resultat']['resume']['taxes_totales']))
                tableau.selection_set("0")
                selection()
            except Exception as exc:
                messagebox.showerror("Variantes", str(exc), parent=fen)

        def appliquer():
            if not tableau.selection() or tableau.selection()[0] not in tableau.get_children():
                return
            v = candidats[int(tableau.selection()[0])]
            self.var_base.set(contexte['base'])
            self.charger_base()
            self.var_reference.set(contexte['reference_chemin'])
            self.controle_variantes = contexte['profil']
            self.ratios = [contexte['ratios'][k] if k in moteur.ARTICLES_VARIABLES else v['fob'][k]/v['poids'][k] for k in range(8)]
            self.var_controle.set(f"CONTRÔLE ACTIF ({contexte['controle']}) : ratios de la variante. "
                                  "Contrôle appliqué aussi avant chaque export.")
            self.var_mode.set("SAISI")
            self._etat_fob()
            for k in range(8):
                for entrees, cle in [(self.e_poids,"poids"), (self.e_fob,"fob"), (self.e_colis,"colis")]:
                    self._remplir(entrees[k], v[cle][k])
            self.var_fob.set(f"{sum(v['fob']):.2f}")
            self.var_colis.set(str(sum(v['colis'])))
            self._calculer(False)
            fen.destroy()

        tableau.bind("<<TreeviewSelect>>", selection)
        actions = ttk.Frame(fen)
        actions.pack(fill="x", pady=8)
        ttk.Button(actions, text="Créer 12 variantes", command=calculer).pack(side="left", padx=10)
        ttk.Button(actions, text="Régénérer un autre modèle", command=lambda: calculer(True)).pack(side="left", padx=10)
        ttk.Button(actions, text="Reprendre la variante choisie", command=appliquer).pack(side="left", padx=10)

    def registre_charge(self):
        self._registre = generer.lire_registre()
        return self._registre

    def _afficher_resultat(self, res, enregistre):
        r = res["resume"]
        for k in range(8):
            if self.var_mode.get() != "SAISI":
                self._remplir(self.e_fob[k], res["fob"][k])
            p = r["articles"][k]["poids"]
            self.l_ratio[k].configure(text=f"{res['fob'][k] / p:.4f}  (réf. {self.ratios[k]})" if p else "")
        self.var_totaux.set(f"Total : {r['poids']:,.0f} kg   •   {r['fob']:,.2f} USD   •   "
                            f"{sum(res['colis'])} colis".replace(",", " "))
        lignes = ["ENREGISTRÉ : " + os.path.relpath(res["chemin"], generer.DEC) if enregistre
                  else "APERÇU (rien n'est enregistré) – fichier qui serait créé : " + res["nom"], ""]
        if self.controle_variantes:
            score = variantes.evaluer({'poids':[a['poids'] for a in r['articles']],
                                      'fob':res['fob'], 'colis':res['colis']}, self.controle_variantes)
            lignes.append(f"CONTRÔLE ACTIF : ratios 4/7/8 ajustables, autres dans les fourchettes (arrondis au centime).")
            lignes.append(f"Proximité : {score['proximite']}/100 — référence : {score['reference_proche']}")
        lignes.append(f"{'Art':<4}{'Poids':>9}{'FOB':>11}{'Colis':>7}{'CIF CDF':>14}{'Taxes CDF':>13}")
        for k, a in enumerate(r["articles"]):
            lignes.append(f"{k+1:<4}{a['poids']:>9,.0f}{a['fob']:>11,.2f}{res['colis'][k]:>7}"
                          f"{a['cif']:>14,}{a['taxes']:>13,}".replace(",", " "))
        lignes += ["",
                   f"Taxes articles : {r['taxes_articles']:,} CDF   +   taxes globales : {r['taxes_globales']:,} CDF".replace(",", " "),
                   f"TOTAL TAXES : {r['taxes_totales']:,} CDF".replace(",", " "), ""]
        lignes += ["Alertes :"] + [f"  ⚠ {a}" for a in res["alertes"]] if res["alertes"] else ["Alertes : aucune ✔"]
        self._ecrire("\n".join(lignes))
        if self.controle_variantes:
            v={'poids':[a['poids'] for a in r['articles']], 'fob':res['fob'], 'colis':res['colis'], 'resultat':res}
            self.vue_resultat.afficher(v,self.controle_variantes,os.path.basename(self.var_reference.get()))
            self.onglets_resultat.select(0)

    def apercu(self):
        self._calculer(enregistrer=False)

    def generer(self):
        if self.dossier_a_confirmer:
            chemin=filedialog.askopenfilename(title="Export : associer le XML du dossier réel",filetypes=[("XML","*.xml")])
            if not chemin:
                return
            try:
                variantes.verifier_modele(chemin)
                if variantes.signature(chemin)!=variantes.signature(self.var_reference.get()):
                    raise ValueError("Le XML du dossier doit avoir les mêmes articles, dans le même ordre et la même devise que la proposition.")
                fob,colis=self.var_fob.get(),self.var_colis.get()
                reference=self.var_reference.get()
                self.var_base.set(chemin)
                self.charger_base()
                if not self.info:
                    return
                self.var_reference.set(reference)
                self.var_fob.set(fob)
                self.var_colis.set(colis)
            except Exception as exc:
                messagebox.showerror("Association du dossier",str(exc))
                return
        res = self._calculer(enregistrer=False)
        if not res:
            return
        message = f"Créer le fichier :\n\n{res['nom']}\n\ndans {os.path.dirname(os.path.relpath(res['chemin'], generer.DEC))} ?"
        if res["alertes"]:
            message += "\n\nAlertes :\n" + "\n".join(f"• {a}" for a in res["alertes"])
        if not messagebox.askyesno("Générer le XML", message):
            return
        res = self._calculer(enregistrer=True)
        if res:
            self.dernier_fichier = res["chemin"]
            messagebox.showinfo("Fichier créé", res["nom"])

    def rafraichir_projet(self):
        """Relance l'interpréteur pour recharger tous les modules depuis le disque."""
        if not messagebox.askyesno(
            "Recharger la dernière version",
            "Recharger la version du projet présente sur cet ordinateur ?\n\n"
            "Les saisies et simulations non enregistrées seront perdues. "
            "Les XML, modèles et études déjà enregistrés seront conservés.",
            parent=self,
        ):
            return
        try:
            os.execv(sys.executable, [sys.executable, os.path.abspath(__file__)])
        except OSError as exc:
            messagebox.showerror("Rechargement impossible", str(exc), parent=self)

    def afficher(self):
        if self.dernier_fichier and os.path.exists(self.dernier_fichier):
            subprocess.run(["open", "-R", self.dernier_fichier], check=False)
        else:
            subprocess.run(["open", generer.DEC], check=False)


if __name__ == "__main__":
    # Le lancement graphique passe par la connexion et la navigation actuelles.
    from ui.app import main
    main()
