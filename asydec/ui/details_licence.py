"""Formulaires des parties et éditeur des produits d'une licence."""
import tkinter as tk
from tkinter import ttk, messagebox
from copy import deepcopy

from asydec.declarations.details_licence import COLONNES_PRODUITS
from asydec.declarations import reprises_licence
from asydec.ui import theme

LIBELLES = ('Tarif douanier', 'Désignation', 'Pays d’origine', 'Quantité',
            'Unité statistique', 'Prix unitaire', 'Devise')


class DetailsLicence:
    def __init__(self, carnet, modifier, app, fob=None):
        self.modifier = modifier
        # Montant FOB du formulaire (onglet Licence), pour calculer les quantités des articles.
        self.fob = fob or (lambda: '')
        self.app = app
        self.parties = {}
        self.produits = []
        self.attendu = None
        self.editeur = None
        for cle, titre, champs in (
                ('soussigne', 'Soussigné', (('nom', 'Nom / raison sociale'), ('adresse', 'Adresse'),
                    ('telephone', 'Téléphone'), ('email', 'E-mail'),
                    ('identifiants', 'Identifiants (NRC, impôt, import/export)'))),
                ('fournisseur', 'Fournisseur étranger', (('nom', 'Nom du fournisseur étranger'),
                    ('adresse', 'Adresse / détails du fournisseur'), ('telephone', 'Téléphone'),
                    ('email', 'E-mail'), ('fax', 'Fax')))):
            page = ttk.Frame(carnet, padding=16)
            carnet.add(page, text=titre)
            page.columnconfigure(1, weight=1)
            self.parties[cle] = {}
            self._ligne_reprise(page, cle)
            for ligne, (champ, libelle) in enumerate(champs, 1):
                ttk.Label(page, text=libelle).grid(row=ligne, column=0, sticky='nw', padx=(0, 14), pady=8)
                if champ in ('adresse', 'identifiants'):
                    widget = tk.Text(page, height=3, wrap='word', width=50, font=(theme.POLICE, 12))
                    widget.bind('<<Modified>>', self._texte_modifie)
                else:
                    widget = tk.StringVar()
                    entree = ttk.Entry(page, textvariable=widget)
                    entree.grid(row=ligne, column=1, sticky='ew', pady=8)
                    widget.trace_add('write', lambda *_: self.modifier())
                self.parties[cle][champ] = widget
                if isinstance(widget, tk.Text):
                    widget.grid(row=ligne, column=1, sticky='ew', pady=8)
        page = ttk.Frame(carnet, padding=12)
        carnet.add(page, text='Produits')
        self.compte = tk.StringVar(value='Liste des produits : 0 article')
        ttk.Label(page, textvariable=self.compte, style='Section.TLabel').pack(anchor='w', pady=(8, 2))
        self.total = tk.StringVar()
        self.etiquette_total = ttk.Label(page, textvariable=self.total, style='Doux.TLabel')
        self.etiquette_total.pack(anchor='w', pady=(0, 8))
        cadre = ttk.Frame(page)
        cadre.pack(fill='both', expand=True)
        cadre.rowconfigure(0, weight=1)
        cadre.columnconfigure(0, weight=1)
        self.table = ttk.Treeview(cadre, columns=COLONNES_PRODUITS, show='headings', height=8)
        for cle, libelle in zip(COLONNES_PRODUITS, LIBELLES):
            self.table.heading(cle, text=libelle)
            self.table.column(cle, width=280 if cle == 'designation' else 120, stretch=False)
        self.table.grid(row=0, column=0, sticky='nsew')
        vertical = ttk.Scrollbar(cadre, orient='vertical', command=self.table.yview)
        vertical.grid(row=0, column=1, sticky='ns')
        horizontal = ttk.Scrollbar(cadre, orient='horizontal', command=self.table.xview)
        horizontal.grid(row=1, column=0, sticky='ew')
        self.table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.table.bind('<Double-1>', lambda _: self.editer())
        actions = ttk.Frame(page)
        actions.pack(fill='x', pady=8)
        for titre, commande in [('Proposer des articles sur le FOB', self.proposer_articles),
                                ('Proposer avec un article choisi…', self.proposer_choisis),
                                ('Ajouter un article', lambda: self.editer(nouveau=True)),
                                ('Ajouter depuis une autre licence…', self.ajouter_existants),
                                ('Calculer les quantités sur le FOB', self.calculer_quantites),
                                ('Voir / modifier', self.editer), ('Supprimer', self.supprimer)]:
            theme.bouton(actions, titre, commande).pack(side='left', padx=(0, 8))
        ttk.Label(page, text='Double-cliquez sur un article pour lire et modifier sa désignation complète.',
                  wraplength=700).pack(anchor='w')

    def _texte_modifie(self, evenement):
        widget = evenement.widget
        if widget.edit_modified():
            widget.edit_modified(False)
            self.modifier()

    def _ligne_reprise(self, page, partie):
        """Liste des soussignés / fournisseurs déjà saisis sur d'autres licences, à recopier ici."""
        ligne = ttk.Frame(page)
        ligne.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 10))
        ligne.columnconfigure(1, weight=1)
        ttk.Label(ligne, text='Reprendre d’une licence existante', style='Doux.TLabel').grid(row=0, column=0, padx=(0, 10))
        variable = tk.StringVar()
        sources = []

        def rafraichir():
            try:
                importateurs, fournisseurs = reprises_licence.parties_existantes()
            except Exception:  # base illisible : la saisie manuelle reste possible
                importateurs, fournisseurs = [], []
            sources[:] = importateurs if partie == 'soussigne' else fournisseurs
            liste.configure(values=[s['libelle'] for s in sources] or ['Aucun enregistré pour l’instant'])

        def appliquer():
            if self.app.session_verrouillee:
                return
            source = next((s for s in sources if s['libelle'] == variable.get()), None)
            if source is None:
                return
            actuel = self.valeurs()[partie]
            if any(actuel.values()) and actuel != {c: source['coordonnees'].get(c, '') for c in actuel} and not messagebox.askyesno(
                    'Reprendre les informations', f"Remplacer les informations de cet onglet par celles de {source['coordonnees']['nom']} ?",
                    parent=page):
                return
            self._appliquer_partie(partie, source['coordonnees'])

        liste = ttk.Combobox(ligne, textvariable=variable, state='readonly', postcommand=rafraichir)
        liste.grid(row=0, column=1, sticky='ew')
        liste.bind('<<ComboboxSelected>>', lambda _: appliquer())
        rafraichir()

    def _appliquer_partie(self, partie, coordonnees):
        for champ, widget in self.parties[partie].items():
            valeur = coordonnees.get(champ, '')
            if isinstance(widget, tk.Text):
                widget.delete('1.0', 'end')
                widget.insert('1.0', valeur)
            else:
                widget.set(valeur)
        self.modifier()

    def completer_automatiquement(self, exclure=None):
        """Client connu : sa fiche complète et son dernier fournisseur sont repris sans rien choisir.
        Renvoie un texte décrivant ce qui a été repris (vide si rien)."""
        actuel = self.valeurs()
        try:
            complete = reprises_licence.completer_parties(actuel['soussigne'], actuel['fournisseur'], exclure=exclure)
        except Exception:  # base illisible : on garde le formulaire tel quel
            return ''
        repris = []
        if complete['source_soussigne']:
            self._appliquer_partie('soussigne', complete['soussigne'])
            repris.append(f"client {complete['soussigne']['nom']} (licence {complete['source_soussigne']})")
        if complete['source_fournisseur']:
            self._appliquer_partie('fournisseur', complete['fournisseur'])
            repris.append(f"fournisseur {complete['fournisseur']['nom']} (licence {complete['source_fournisseur']})")
        return ' · '.join(repris)

    def _poids(self, articles):
        """Proportions : valeur actuelle (quantité × prix) de chaque article, moyenne pour ceux sans quantité."""
        valeurs = [reprises_licence.poids_origine([a]) for a in articles]
        connues = [v[0] for v in valeurs if v]
        if not connues:
            return None
        moyenne = sum(connues) / len(connues)
        return [v[0] if v else moyenne for v in valeurs]

    def calculer_quantites(self, poids=None, silencieux=False):
        """Quantités de tous les articles pour que leur total soit exactement le FOB de la licence."""
        if self.app.session_verrouillee or not self.produits:
            return
        try:
            produits, ecart = reprises_licence.repartir_quantites(self.produits, self.fob(), poids or self._poids(self.produits))
        except ValueError as exc:
            messagebox.showerror('Calcul des quantités', str(exc), parent=self.table)
            return
        self.produits = produits
        self.actualiser()
        if ecart:
            messagebox.showwarning('Calcul des quantités',
                f'Quantités calculées au plus près : il reste un écart de {ecart} USD avec le FOB.\n\n'
                'Avec ces prix, le montant exact n’est pas atteignable. Ajoutez un article à petit prix '
                '(il servira d’appoint) ou ajustez un prix unitaire.', parent=self.table)
        elif not silencieux:
            messagebox.showinfo('Calcul des quantités', 'Quantités calculées : le total des articles est égal au FOB '
                                'de la licence, au centime près.', parent=self.table)

    def proposer_articles(self):
        """Licence sans articles : articles et quantités tirés d'une licence modèle, total = FOB.
        Chaque clic donne une nouvelle proposition."""
        if self.app.session_verrouillee:
            return
        if self.produits and not messagebox.askyesno(
                'Proposer des articles', 'Remplacer les articles actuels par une nouvelle proposition ?', parent=self.table):
            return
        try:
            proposition = reprises_licence.proposer_articles(self.fob(), self.valeurs()['soussigne'].get('nom', ''))
        except ValueError as exc:
            messagebox.showerror('Proposer des articles', str(exc), parent=self.table)
            return
        except Exception as exc:  # base illisible
            messagebox.showerror('Proposer des articles', f'Licences modèles illisibles : {exc}', parent=self.table)
            return
        self.produits = proposition['produits']
        self.actualiser()
        n, total = len(self.produits), proposition['nombre_modele']
        modele = (f"l’article unique de la licence {proposition['source']}" if total == 1
                  else f"{n} article(s) sur les {total} de la licence {proposition['source']}")
        if proposition['ecart']:
            messagebox.showwarning('Proposer des articles', f'Proposition tirée de {modele}.\n\nIl reste un écart de '
                                   f"{proposition['ecart']} USD avec le FOB : ajustez une quantité ou un prix.", parent=self.table)
        else:
            messagebox.showinfo('Proposer des articles', f'Proposition tirée de {modele}. Total des articles = FOB, au centime '
                                'près.\n\nCliquez à nouveau pour une autre proposition ; double-cliquez sur un article pour le modifier.',
                                parent=self.table)

    def proposer_choisis(self):
        """Proposition limitée aux articles choisis (ex. Motocycles 8711100000 seul) :
        ils remplacent les articles actuels, quantités et prix calculés pour que le total soit exactement le FOB."""
        if self.app.session_verrouillee:
            return
        if not str(self.fob()).strip():
            messagebox.showerror('Proposer avec un article choisi', 'Renseignez d’abord le montant FOB de la licence '
                                 '(onglet Licence).', parent=self.table)
            return
        try:
            articles = reprises_licence.articles_existants()
            # Vraies déclarations SYDONIA (dossier XML_LICENCES) : leurs articles sont aussi proposés.
            articles += reprises_licence.articles_declarations(connus=articles)
        except Exception as exc:
            messagebox.showerror('Articles existants', str(exc), parent=self.table)
            return
        if not articles:
            messagebox.showinfo('Articles existants', 'Aucun article enregistré sur une autre licence ni dans les '
                                'déclarations du dossier XML_LICENCES.', parent=self.table)
            return
        choix = ChoixArticles(self.table, articles, self.fob(), proposition=True)
        self.table.wait_window(choix)
        if not choix.resultat:
            return
        if self.produits and not messagebox.askyesno(
                'Proposer avec un article choisi', 'Remplacer les articles actuels par cette proposition ?', parent=self.table):
            return
        nouveaux = [reprises_licence.copier_article(a) for a in choix.resultat]
        try:
            produits, ecart = reprises_licence.repartir_quantites(
                nouveaux, self.fob(), reprises_licence.poids_origine(choix.resultat))
        except ValueError as exc:
            messagebox.showerror('Proposer avec un article choisi', str(exc), parent=self.table)
            return
        self.produits = produits
        self.actualiser()
        ajustes = [f"{' '.join(str(n.get('designation', '')).split())[:50]} : {a.get('prix_unitaire')} → {n['prix_unitaire']}"
                   for a, n in zip(choix.resultat, produits) if str(a.get('prix_unitaire')) != str(n.get('prix_unitaire'))
                   and reprises_licence._decimal(a.get('prix_unitaire')) != reprises_licence._decimal(n.get('prix_unitaire'))]
        if ecart:
            messagebox.showwarning('Proposer avec un article choisi', f'Il reste un écart de {ecart} USD avec le FOB : '
                                   'ajustez une quantité ou un prix.', parent=self.table)
        else:
            messagebox.showinfo('Proposer avec un article choisi',
                                f'{len(produits)} article(s) proposé(s) : quantité × prix = FOB de la licence, au centime près.'
                                + ('\n\nPrix unitaire ajusté pour tomber juste :\n' + '\n'.join(ajustes) if ajustes else ''),
                                parent=self.table)

    def ajouter_existants(self):
        if self.app.session_verrouillee:
            return
        try:
            articles = reprises_licence.articles_existants()
            # Vraies déclarations SYDONIA (dossier XML_LICENCES) : leurs articles sont aussi proposés.
            articles += reprises_licence.articles_declarations(connus=articles)
        except Exception as exc:
            messagebox.showerror('Articles existants', str(exc), parent=self.table)
            return
        if not articles:
            messagebox.showinfo('Articles existants', 'Aucun article enregistré sur une autre licence ni dans les '
                                'déclarations du dossier XML_LICENCES.', parent=self.table)
            return
        choix = ChoixArticles(self.table, articles, self.fob())
        self.table.wait_window(choix)
        if not choix.resultat:
            return
        if choix.calculer.get():
            # Proportions : articles déjà présents à leur valeur actuelle, nouveaux à leur valeur d'origine.
            poids = self._poids(self.produits + choix.resultat)
            self.produits.extend(reprises_licence.copier_article(a) for a in choix.resultat)
            self.actualiser()
            self.calculer_quantites(poids)
            return
        self.produits.extend(reprises_licence.copier_article(a, choix.garder_quantite.get()) for a in choix.resultat)
        self.actualiser()
        if not choix.garder_quantite.get():
            messagebox.showinfo('Articles ajoutés', f'{len(choix.resultat)} article(s) ajouté(s). Indiquez la quantité de chacun '
                                '(double-clic sur l’article) pour que le total corresponde au FOB de la licence.', parent=self.table)

    def charger(self, valeurs):
        if self.editeur is not None and self.editeur.winfo_exists():
            self.editeur.destroy()
        for partie, champs in self.parties.items():
            for cle, widget in champs.items():
                valeur = valeurs.get(partie, {}).get(cle, '')
                if isinstance(widget, tk.Text):
                    widget.delete('1.0', 'end')
                    widget.insert('1.0', valeur)
                    widget.edit_modified(False)
                else:
                    widget.set(valeur)
        self.produits = deepcopy(valeurs.get('produits', []))
        self.attendu = valeurs.get('nombre_produits_attendu')
        self.actualiser()

    def valeurs(self):
        resultat = {partie: {cle: (widget.get('1.0', 'end-1c') if isinstance(widget, tk.Text)
                                  else widget.get()).strip() for cle, widget in champs.items()}
                    for partie, champs in self.parties.items()}
        resultat['produits'] = deepcopy(self.produits)
        resultat['nombre_produits_attendu'] = self.attendu
        return resultat

    def actualiser(self):
        self.table.delete(*self.table.get_children())
        for indice, article in enumerate(self.produits):
            self.table.insert('', 'end', iid=str(indice), values=[article.get(c, '').replace('\n', ' ') for c in COLONNES_PRODUITS])
        compte = f'Liste des produits : {len(self.produits)} article(s)'
        if self.attendu is not None:
            compte += f' / {self.attendu} annoncé(s) sur la licence'
        self.compte.set(compte)
        self._afficher_total()
        self.modifier()

    def _afficher_total(self):
        from decimal import Decimal
        from asydec.formats import nombre
        total, incomplets = Decimal(0), 0
        for article in self.produits:
            q, p = reprises_licence._decimal(article.get('quantite')), reprises_licence._decimal(article.get('prix_unitaire'))
            if q is None or p is None:
                incomplets += 1
                continue
            total += (q * p).quantize(Decimal('.01'))
        fob = reprises_licence._decimal(self.fob())
        if not self.produits:
            texte = ''
        elif fob is None:
            texte = f'Total des articles : {nombre(total, 2)} USD'
        else:
            from asydec.declarations.repartition_licence import ecart_arrondi
            ecart = fob - total
            try:
                arrondi = None if incomplets or fob <= 0 else ecart_arrondi(self.produits, fob)
            except ValueError:
                arrondi = None
            if ecart == 0 and not incomplets:
                verdict = '✓ égal au FOB'
            elif arrondi is not None:
                # Quantité arrondie sur la licence : corrigée à l'enregistrement pour que quantité × prix = FOB.
                from asydec.declarations.repartition_licence import ajuster_articles
                corriges = [f"{' '.join(str(n.get('designation', '')).split())[:30]} : {n['quantite']} × {n['prix_unitaire']}"
                            for a, n in zip(self.produits, ajuster_articles(self.produits, fob)) if a != n]
                verdict = (f'écart d’arrondi {nombre(ecart, 2)} USD, corrigé à l’enregistrement'
                           + (' → ' + ' · '.join(corriges) if corriges else ''))
            else:
                verdict = f'écart {nombre(ecart, 2)} USD'
            texte = f'Total des articles : {nombre(total, 2)} USD · FOB licence : {nombre(fob, 2)} USD · ' + verdict
        if incomplets:
            texte += f' · {incomplets} article(s) sans quantité ou prix'
        self.total.set(texte)

    def supprimer(self):
        if self.app.session_verrouillee:
            return
        selection = self.table.selection()
        if selection and messagebox.askyesno('Supprimer l’article', 'Retirer cet article du formulaire ?', parent=self.table):
            del self.produits[int(selection[0])]
            self.actualiser()

    def editer(self, nouveau=False):
        if self.app.session_verrouillee:
            return
        selection = self.table.selection()
        if not nouveau and not selection:
            return
        if self.editeur is not None and self.editeur.winfo_exists():
            self.editeur.lift()
            return
        indice = None if nouveau else int(selection[0])
        article = {} if nouveau else self.produits[indice]
        fenetre = self.editeur = tk.Toplevel(self.table)
        fenetre.title('Ajouter un article' if nouveau else 'Détails de l’article')
        fenetre.transient(self.table.winfo_toplevel())
        fenetre.columnconfigure(1, weight=1)
        champs = {}
        for ligne, (cle, libelle) in enumerate(zip(COLONNES_PRODUITS, LIBELLES)):
            ttk.Label(fenetre, text=libelle).grid(row=ligne, column=0, sticky='nw', padx=12, pady=8)
            widget = tk.Text(fenetre, height=5 if cle == 'designation' else 1, width=60, wrap='word')
            widget.grid(row=ligne, column=1, sticky='ew', padx=12, pady=8)
            widget.insert('1.0', article.get(cle, ''))
            champs[cle] = widget

        def enregistrer():
            if self.app.session_verrouillee:
                return
            valeurs = {cle: w.get('1.0', 'end-1c').strip() for cle, w in champs.items()}
            if not valeurs['designation']:
                messagebox.showerror('Article', 'Renseignez la désignation de l’article.', parent=fenetre)
                return
            if indice is None:
                self.produits.append(valeurs)
            else:
                self.produits[indice] = valeurs
            self.actualiser()
            fenetre.destroy()
        theme.bouton(fenetre, 'Enregistrer l’article', enregistrer, principal=True).grid(row=7, column=1, sticky='e', padx=12, pady=12)


class ChoixArticles(tk.Toplevel):
    """Articles déjà saisis sur d'autres licences ; resultat = articles choisis (copiés), ou None."""

    def __init__(self, parent, articles, fob='', proposition=False):
        super().__init__(parent)
        self.title('Proposer avec les articles choisis' if proposition else 'Ajouter des articles d’une autre licence')
        self.geometry('1100x600')
        self.minsize(820, 420)
        self.transient(parent.winfo_toplevel())
        self.articles, self.resultat = articles, None
        cadre = ttk.Frame(self, padding=20)
        cadre.pack(fill='both', expand=True)
        bas = ttk.Frame(cadre)
        bas.pack(side='bottom', fill='x', pady=(12, 0))
        theme.bouton(bas, 'Annuler', self.destroy).pack(side='left')
        self.bouton = theme.bouton(bas, 'Proposer' if proposition else 'Ajouter', self.choisir, principal=True, state='disabled')
        self.bouton.pack(side='right')
        theme.bouton(bas, 'Tout sélectionner', lambda: self.table.selection_set(self.table.get_children())).pack(side='right', padx=(0, 10))
        self.garder_quantite = tk.BooleanVar(value=False)
        self.calculer = tk.BooleanVar(value=bool(str(fob).strip()))
        options = ttk.Frame(cadre)
        if not proposition:  # proposition : quantités toujours calculées sur le FOB
            options.pack(side='bottom', fill='x', pady=(10, 0))
        ttk.Checkbutton(options, text=f'Calculer les quantités pour atteindre le FOB de la licence ({fob or "non renseigné"} USD), '
                        'en gardant les proportions d’origine', variable=self.calculer,
                        state='normal' if str(fob).strip() else 'disabled').pack(anchor='w')
        ttk.Checkbutton(options, text='Sinon : garder les quantités d’origine', variable=self.garder_quantite).pack(anchor='w')
        theme.entete_page(cadre, 'Articles déjà utilisés', f'{len(articles)} article(s) sur les licences ouvertes')
        ttk.Label(cadre, text='Sélectionnez un ou plusieurs articles (Cmd/Ctrl ou Maj + clic). Désignation, code SH, origine, '
                  'unité, prix et devise sont copiés ; les quantités sont calculées sur le FOB de cette licence.',
                  style='SousTitre.TLabel', wraplength=1000).pack(anchor='w', pady=(0, 10))
        filtre = ttk.Frame(cadre)
        filtre.pack(fill='x', pady=(0, 8))
        ttk.Label(filtre, text='Rechercher (désignation, code SH, licence…)').pack(side='left', padx=(0, 8))
        self.recherche = tk.StringVar()
        ttk.Entry(filtre, textvariable=self.recherche, width=36).pack(side='left')
        self.recherche.trace_add('write', self.afficher)
        zone, self.table = theme.tableau(cadre, [
            ('designation', 'Désignation', 360, 'w'), ('tarif', 'Code SH', 110, 'center'), ('origine', 'Origine', 90, 'center'),
            ('unite', 'Unité', 110, 'center'), ('prix', 'Prix unitaire', 100, 'e'), ('quantite', 'Qté d’origine', 100, 'e'),
            ('licences', 'Licence(s)', 220, 'w')], hauteur=14)
        zone.pack(fill='both', expand=True)
        self.table.configure(selectmode='extended')
        self.table.bind('<<TreeviewSelect>>', lambda _: self._selection())
        self.table.bind('<Double-1>', lambda _: self.choisir())
        self.afficher()
        self.grab_set()

    def afficher(self, *_):
        self.table.delete(*self.table.get_children())
        terme = self.recherche.get().strip().casefold()
        for i, source in enumerate(self.articles):
            a = source['article']
            valeurs = (' '.join(str(a.get('designation', '')).split()), a.get('tarif_douanier', ''), a.get('pays_origine', ''),
                       a.get('unite', ''), f"{a.get('prix_unitaire', '')} {a.get('devise', '')}".strip(), a.get('quantite', ''),
                       ', '.join(source['licences']))
            if terme and terme not in ' '.join(map(str, valeurs)).casefold():
                continue
            self.table.insert('', 'end', iid=str(i), values=valeurs)
        self._selection()

    def _selection(self):
        n = len(self.table.selection())
        self.bouton.configure(state='normal' if n else 'disabled', text=f'Ajouter {n} article(s)' if n else 'Ajouter')

    def choisir(self):
        selection = self.table.selection()
        if not selection:
            return
        self.resultat = [self.articles[int(i)]['article'] for i in sorted(selection, key=int)]
        self.destroy()
