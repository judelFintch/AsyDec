"""Parcours de préparation des documents finaux."""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import re
import xml.etree.ElementTree as ET

from asydec.declarations import licences_ouvertes, xml_licence, mise_a_jour_repartitions, recuperation_simulation, facture_licence, facture_kinshop, cvi
from asydec.declarations import declaration_licence, finalisation

from asydec.declarations.documents_finaux import preparer_licence, proposer_date_facture, ECART_FACTURE_MIN, ECART_FACTURE_MAX
from asydec.ui import theme, synthese_licence
from asydec.systeme import espace_travail
from asydec.ui.details_licence import DetailsLicence
from asydec.ui.liste_licences import ListeLicences
from asydec.ui.repartition_licence import FenetreRepartition
from asydec.ui.liste_repartitions import ListeRepartitions
from asydec.ui.informations_declaration import InformationsDeclaration
from asydec.ui.recuperation_simulation import FenetreComparaison
from asydec.ui.generation_xml import FenetreGenerationXML
from asydec.declarations.import_licence import lire_licence
from asydec.declarations import import_excel_licence
from asydec.formats import nombre as format_nombre
from asydec.ui.import_excel_licence import ChoixLicenceExcel


class PageDocumentsFinaux(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.licence = None
        self.import_en_cours = False
        self.a_verifier = False
        self.fichier_licence = None
        self.modifie = False
        self.vue_active = 'liste'
        self.liste = ListeLicences(self, self.nouvelle, self.rouvrir, self.traiter_licence, self.voir_repartitions,
                                   supprimer=self.supprimer_licence, recommencer=self.recommencer_licence,
                                   marquer_physique=self.marquer_physique)
        # « Tout supprimer » (self.supprimer_toutes) volontairement absent de la liste : trop risqué à cet endroit.
        self.formulaire = ttk.Frame(self)
        self.traitement = ttk.Frame(self)
        haut = ttk.Frame(self.formulaire)
        haut.pack(fill='x', pady=(0, 12))
        theme.bouton(haut, '← Licences ouvertes', self.voir_licences).pack(side='left')
        self.etat_dossier = tk.StringVar(value='Étape 1 · Ouverture du dossier')
        ttk.Label(haut, textvariable=self.etat_dossier, style='Doux.TLabel').pack(side='right')
        entete = ttk.Frame(self.formulaire)
        entete.pack(fill='x', pady=(0, 14))
        titres = ttk.Frame(entete)
        titres.pack(side='left', fill='x', expand=True)
        self.titre_formulaire = tk.StringVar(value='Nouvelle licence')
        ttk.Label(titres, textvariable=self.titre_formulaire, style='Titre.TLabel').pack(anchor='w')
        ttk.Label(titres, text='Complétez les quatre rubriques, puis validez l’ouverture du dossier.',
                  style='SousTitre.TLabel', wraplength=550).pack(anchor='w', pady=(4, 0))
        self.bouton_import = theme.bouton(entete, 'Importer PDF / photo', self.importer)
        self.bouton_import.pack(side='right', padx=(12, 0))
        # Troisième mode d'ouverture : une ligne d'un fichier Excel (liste des DEC de la banque).
        self.bouton_excel = theme.bouton(entete, 'Importer Excel', self.importer_excel)
        self.bouton_excel.pack(side='right', padx=(12, 0))
        self.source = tk.StringVar(value='Saisie manuelle ou import d’une licence.')
        ttk.Label(self.formulaire, textvariable=self.source, wraplength=780,
                  style='Doux.TLabel').pack(anchor='w', pady=(0, 12))
        # Pied fixe : la validation reste accessible quelle que soit la rubrique.
        self.pied = ttk.Frame(self.formulaire, padding=(0, 12))
        self.pied.pack(side='bottom', fill='x')
        self.confirme = tk.BooleanVar(value=False)
        self.verification = ttk.Checkbutton(self.pied,
                  text='J’ai vérifié les informations importées avec la licence.',
                  variable=self.confirme, command=self._modifier)
        self.actions_validation = ttk.Frame(self.pied)
        self.actions_validation.pack(fill='x')
        theme.bouton(self.actions_validation, 'Retour à la liste', self.voir_licences).pack(side='left')
        self.bouton_valider = theme.bouton(self.actions_validation, 'Valider et enregistrer →', self.valider, principal=True)
        self.bouton_valider.pack(side='right')
        self.message = theme.Message(self.formulaire)
        self.carnet = ttk.Notebook(self.formulaire)
        self.carnet.pack(fill='both', expand=True)
        page_licence = ttk.Frame(self.carnet, padding=20)
        self.carnet.add(page_licence, text='Licence')
        ttk.Label(page_licence, text='Identification de la licence', style='Section.TLabel').pack(anchor='w')
        ttk.Label(page_licence, text='Le numéro licence complet identifie le dossier ; le numéro DEC est conservé séparément.',
                  style='Doux.TLabel', wraplength=760).pack(anchor='w', pady=(4, 16))
        cadre = ttk.Frame(page_licence)
        cadre.pack(fill='x')
        cadre.columnconfigure(0, weight=1, uniform='champ')
        cadre.columnconfigure(1, weight=1, uniform='champ')
        self.champs = {}
        for indice, (cle, libelle) in enumerate((
                ('numero_validation', 'Numéro licence'), ('numero_dec', 'Numéro DEC'),
                ('montant_fob', 'Montant FOB'), ('date_validation', 'Date de validation · JJ/MM/AAAA'),
                ('numero_facture', 'Numéro facture'), ('date_facture', 'Date facture · JJ/MM/AAAA'))):
            cellule = ttk.Frame(cadre, padding=(0, 0, 18 if indice % 2 == 0 else 0, 16))
            cellule.grid(row=indice // 2, column=indice % 2, sticky='ew')
            ttk.Label(cellule, text=libelle, style='Doux.TLabel').pack(anchor='w', pady=(0, 6))
            variable = tk.StringVar()
            self.champs[cle] = variable
            ttk.Entry(cellule, textvariable=variable).pack(fill='x')
            variable.trace_add('write', self._modifier)
        proposition = ttk.Frame(page_licence)
        proposition.pack(fill='x', pady=(0, 12))
        ttk.Button(proposition, text='Proposer n° et date de facture',
                   command=self.proposer_facture).pack(side='left')
        ttk.Label(proposition, text=f'Si la licence n’en porte pas : facture datée de {ECART_FACTURE_MIN} à {ECART_FACTURE_MAX} '
                  'jours avant la licence, jour ouvrable ; numéro INV suivant.', style='Doux.TLabel', wraplength=520).pack(side='left', padx=12)
        calcul = ttk.Frame(page_licence, padding=16, relief='solid', borderwidth=1)
        calcul.pack(fill='x', pady=(6, 0))
        ttk.Label(calcul, text='Date du BL · Calcul automatique', style='Section.TLabel').pack(anchor='w')
        self.resultat = tk.StringVar()
        ttk.Label(calcul, textvariable=self.resultat, style='SousTitre.TLabel', wraplength=740).pack(anchor='w', pady=8)
        ttk.Label(calcul, text='Premier jour du lundi au vendredi entre J+3 et J+5 calendaires. Hors week-ends et jours fériés RDC.',
                  style='Doux.TLabel', wraplength=740).pack(anchor='w')
        self.details = DetailsLicence(self.carnet, self._modifier, self.app, fob=lambda: self.champs['montant_fob'].get())
        self._modifier()
        self.modifie = False
        self.liste.pack(fill='both', expand=True)
        self.afficher()

    def _montrer_formulaire(self):
        self.liste.pack_forget()
        self.traitement.pack_forget()
        self.formulaire.pack(fill='both', expand=True)
        self.vue_active = 'formulaire'

    def afficher(self):
        """L’entrée dans le module présente toujours les licences enregistrées."""
        if self.vue_active == 'formulaire' and not self._peut_remplacer():
            return
        self.modifie = False
        self._afficher_liste()

    def _afficher_liste(self, notification='', selection=None):
        try:
            licences = licences_ouvertes.lister()
        except (ValueError, OSError, sqlite3.Error) as exc:
            messagebox.showerror('Licences ouvertes', str(exc), parent=self)
            return
        self.liste.charger(licences, notification=notification, selection=selection)
        self.formulaire.pack_forget()
        self.traitement.pack_forget()
        self.liste.pack(fill='both', expand=True)
        self.vue_active = 'liste'

    def _preparer_licence(self):
        valeurs = {cle: var.get() for cle, var in self.champs.items()}
        licence = preparer_licence(**valeurs)
        if hasattr(self, 'details'):
            details = self.details.valeurs()
            attendu = details.get('nombre_produits_attendu')
            if attendu is not None and len(details['produits']) != attendu:
                raise ValueError(f"Liste des produits incomplète : {len(details['produits'])}/{attendu} articles. Vérifiez l’onglet Produits.")
            licence.update(details)
        return licence

    def proposer_facture(self):
        """Remplit le numéro (INV suivant) et la date de facture (au moins un mois avant la licence)."""
        validation = self.champs['date_validation'].get().strip()
        try:
            date_facture = proposer_date_facture(validation)
            numero_facture = licences_ouvertes.proposer_numero_facture()
        except (ValueError, OSError, sqlite3.Error):
            messagebox.showerror('Facture', 'Saisissez d’abord une date de validation valide (JJ/MM/AAAA).', parent=self)
            return
        actuels = [self.champs[c].get().strip() for c in ('numero_facture', 'date_facture')]
        if any(actuels) and not messagebox.askyesno(
                'Facture', f"Remplacer {' du '.join(v for v in actuels if v)} par {numero_facture} du {date_facture} ?",
                parent=self):
            return
        self.champs['numero_facture'].set(numero_facture)
        self.champs['date_facture'].set(date_facture)

    def _modifier(self, *_):
        self.modifie = True
        self.licence = None
        self.message.pack_forget()
        self.etat_dossier.set('Étape 1 · À compléter')
        if hasattr(self, 'details'):
            self.details._afficher_total()  # le FOB a pu changer : total des articles à recomparer
        try:
            licence = self._preparer_licence()
        except ValueError as exc:
            self.resultat.set(str(exc))
            self.bouton_valider.configure(state='disabled')
            return
        self.resultat.set(f"Date du BL : {licence['date_bl']:%d/%m/%Y} · J+{licence['delai']}")
        self.bouton_valider.configure(state='disabled' if self.import_en_cours or
                                      (self.a_verifier and not self.confirme.get()) else 'normal')

    def importer(self):
        if self.app.session_verrouillee or self.import_en_cours:
            return
        chemin = filedialog.askopenfilename(parent=self, title='Importer la licence d’importation',
                    filetypes=[('Licence PDF ou photo', '*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp')])
        if not chemin:
            return
        if (any(v.get().strip() for v in self.champs.values()) or self.details.produits
                or any(v for partie in ('soussigne', 'fournisseur') for v in self.details.valeurs()[partie].values())) and not messagebox.askyesno(
                'Nouvelle licence', 'Remplacer les informations du formulaire par celles de cette licence ?', parent=self):
            return
        self.import_en_cours = True
        self.bouton_import.configure(state='disabled')
        self.bouton_excel.configure(state='disabled')
        self.bouton_valider.configure(state='disabled')
        self.source.set('Lecture de la licence en cours…')
        executant = ThreadPoolExecutor(max_workers=1)
        future = executant.submit(lire_licence, chemin)
        executant.shutdown(wait=False)

        def terminer():
            if not future.done() or self.app.session_verrouillee:
                self.after(150, terminer)
                return
            self.import_en_cours = False
            self.bouton_import.configure(state='normal')
            self.bouton_excel.configure(state='normal')
            try:
                valeurs, texte = future.result()
            except Exception as exc:
                self.source.set('Import impossible. Vous pouvez continuer en saisie manuelle.')
                self._modifier()
                self.message.pack(fill='x', before=self.carnet, pady=(0, 12))
                self.message.afficher('erreur', 'Lecture impossible', [str(exc)])
                return
            self.a_verifier = True
            self.fichier_licence = chemin
            self.confirme.set(False)
            for cle, variable in self.champs.items():
                variable.set(valeurs.get(cle, ''))
            self.details.charger(valeurs)
            self.source.set(f'{Path(chemin).name} · {sum(bool(valeurs.get(cle)) for cle in self.champs)}/{len(self.champs)} champs licence · {len(self.details.produits)} articles. Vérifiez les quatre onglets.')
            self.verification.pack(anchor='w', before=self.actions_validation, pady=(0, 10))
            self._modifier()
            fenetre = tk.Toplevel(self)
            fenetre.title('Texte extrait de la licence — à vérifier')
            fenetre.geometry('750x500')
            zone = tk.Text(fenetre, wrap='word')
            zone.pack(fill='both', expand=True)
            zone.insert('1.0', texte)
            zone.configure(state='disabled')
            theme.bouton(fenetre, 'Revenir au formulaire', fenetre.destroy).pack(pady=8)

        self.after(150, terminer)

    def _formulaire_rempli(self):
        return (any(v.get().strip() for v in self.champs.values()) or self.details.produits
                or any(v for partie in ('soussigne', 'fournisseur') for v in self.details.valeurs()[partie].values()))

    def importer_excel(self):
        if self.app.session_verrouillee or self.import_en_cours:
            return
        chemin = filedialog.askopenfilename(parent=self, title='Importer une licence depuis Excel',
                                            filetypes=[('Fichier Excel', '*.xlsx *.xlsm')])
        if not chemin:
            return
        try:
            lignes = import_excel_licence.lire_excel(chemin)
            deja = [l['numero'] for l in licences_ouvertes.lister()]
        except (ValueError, OSError, sqlite3.Error) as exc:
            messagebox.showerror('Importer Excel', str(exc), parent=self)
            return
        try:
            importateurs, fournisseurs = import_excel_licence.sources_existantes()
        except (ValueError, OSError, sqlite3.Error):
            importateurs, fournisseurs = [], []
        # Fenêtre affichée même pour une seule licence : elle propose aussi la reprise
        # de l'importateur et du fournisseur d'une licence existante.
        choix = ChoixLicenceExcel(self, lignes, deja, Path(chemin).name, importateurs, fournisseurs)
        self.wait_window(choix)
        choisies = choix.resultat
        if not choisies:
            return
        if len(choisies) > 1:
            self._ouvrir_plusieurs(choisies, choix.importateur, choix.fournisseur)
            return
        ligne = choisies[0]
        if ligne['numero_validation'].upper() in {str(n).upper() for n in deja} and not messagebox.askyesno(
                'Licence déjà ouverte', f"La licence {ligne['numero_validation']} est déjà enregistrée. "
                'La reprendre quand même dans le formulaire ?', parent=self):
            return
        if self._formulaire_rempli() and not messagebox.askyesno(
                'Nouvelle licence', 'Remplacer les informations du formulaire par celles de cette licence ?', parent=self):
            return
        valeurs = import_excel_licence.valeurs_formulaire(ligne, choix.importateur, choix.fournisseur)
        self.a_verifier = True
        self.fichier_licence = None  # le fichier Excel liste plusieurs licences : il n'est pas rangé dans le dossier DEC
        self.confirme.set(False)
        for cle, variable in self.champs.items():
            variable.set(valeurs.get(cle, ''))
        self.details.charger(valeurs)
        repris = self.details.completer_automatiquement()
        remarques = []
        if ligne['devise'] and ligne['devise'] != 'USD':
            remarques.append(f"devise {ligne['devise']} (montant à vérifier)")
        if import_excel_licence.expiree(ligne):
            remarques.append(f"licence expirée le {ligne['date_extreme']}")
        self.source.set(f"{Path(chemin).name} · {ligne['numero_validation']} · {ligne['soussigne'] or 'client non renseigné'}"
                        + (f" · extrême validité {ligne['date_extreme']}" if ligne['date_extreme'] else '')
                        + ('. Attention : ' + ', '.join(remarques) if remarques else '')
                        + (f" · importateur repris : {choix.importateur['nom']}" if choix.importateur else '')
                        + (f" · fournisseur repris : {choix.fournisseur['nom']}" if choix.fournisseur else '')
                        + (f' · repris automatiquement : {repris}' if repris else '')
                        + ('. Complétez les produits et la facture dans les onglets.' if choix.fournisseur
                           else '. Complétez le fournisseur, les produits et la facture dans les onglets.'))
        self.verification.pack(anchor='w', before=self.actions_validation, pady=(0, 10))
        self._modifier()

    def _ouvrir_plusieurs(self, lignes, importateur=None, fournisseur=None):
        """Enregistre directement plusieurs licences ; celles déjà ouvertes ne sont pas modifiées."""
        expirees = sum(import_excel_licence.expiree(l) for l in lignes)
        if not messagebox.askyesno('Ouvrir plusieurs licences',
                f'Ouvrir {len(lignes)} licences d’un coup ?\n\n'
                'Numéro, DEC, montant, date de validation et client sont repris du fichier Excel. '
                'Les licences déjà ouvertes ne sont pas modifiées.'
                + (f'\n\nAttention : {expirees} licence(s) sélectionnée(s) sont expirées.' if expirees else '')
                + (f"\n\nImportateur repris : {importateur['nom']}" if importateur else '')
                + (f"\nFournisseur repris : {fournisseur['nom']}" if fournisseur else '')
                + ('\n\nLes produits' + ('' if fournisseur else ' et le fournisseur')
                   + ' seront à compléter en rouvrant chaque licence.'), parent=self):
            return
        if not self._peut_remplacer():
            return
        try:
            ouvertes, ignorees, erreurs = import_excel_licence.ouvrir_plusieurs(lignes, importateur=importateur,
                                                                                fournisseur=fournisseur)
        except (ValueError, OSError, sqlite3.Error) as exc:
            messagebox.showerror('Importer Excel', str(exc), parent=self)
            return
        dossiers_non_crees = 0
        for numero in ouvertes:
            try:
                espace_travail.dossier_dec(import_excel_licence.numero_dec(numero))
            except (OSError, ValueError):
                dossiers_non_crees += 1
        self.modifie = False
        resume = f'{len(ouvertes)} licence(s) ouverte(s)'
        if ignorees:
            resume += f' · {len(ignorees)} déjà ouverte(s), non modifiée(s)'
        if erreurs:
            resume += f' · {len(erreurs)} refusée(s)'
        if dossiers_non_crees:
            resume += f' · {dossiers_non_crees} dossier(s) DEC non créé(s)'
        if erreurs:
            messagebox.showwarning('Licences refusées', '\n'.join(f'{n} : {m}' for n, m in erreurs[:15])
                                   + (f'\n… et {len(erreurs) - 15} autre(s).' if len(erreurs) > 15 else ''), parent=self)
        self._afficher_liste(notification=resume + ('. Complétez les produits de chacune.' if fournisseur
                                                     else '. Complétez le fournisseur et les produits de chacune.'),
                             selection=ouvertes[0] if ouvertes else None)

    def valider(self):
        if self.app.session_verrouillee or self.import_en_cours or (self.a_verifier and not self.confirme.get()):
            return
        try:
            licence = self._preparer_licence()
            licences_ouvertes.enregistrer(licence)
            self.licence = licence
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.message.pack(fill='x', before=self.carnet, pady=(0, 12))
            self.message.afficher('erreur', str(exc))
            return
        self.modifie = False
        numero = self.licence['numero_validation']
        notification = f'Licence {numero} enregistrée · Étape 1 validée.'
        try:
            dossier = espace_travail.dossier_dec(self.licence['numero_dec']) if self.licence.get('numero_dec') else None
            fichier = getattr(self, 'fichier_licence', None)
            if fichier and dossier is not None:
                espace_travail.ranger_dans_dec(fichier, self.licence['numero_dec'], 'licence')
            self.fichier_licence = None
            if dossier is not None:
                notification += f' Dossier : {espace_travail.relatif(dossier)}'
        except (OSError, ValueError) as exc:
            notification += f' Dossier DEC non créé : {exc}'
        self._afficher_liste(notification=notification, selection=numero)

    def _peut_remplacer(self):
        if self.app.session_verrouillee or self.import_en_cours:
            return False
        return not self.modifie or messagebox.askyesno(
            'Modifications non enregistrées',
            'Quitter ce formulaire sans enregistrer les modifications ? Pour les conserver, annulez puis validez l’étape 1.',
            parent=self)

    def nouvelle(self):
        if not self._peut_remplacer():
            return
        self.a_verifier = False
        self.fichier_licence = None
        self.confirme.set(False)
        self.verification.pack_forget()
        for variable in self.champs.values():
            variable.set('')
        self.details.charger({})
        self.source.set('Nouvelle licence : importez un document ou remplissez le formulaire.')
        self.carnet.select(0)
        self._modifier()
        self.modifie = False
        self.titre_formulaire.set('Nouvelle licence')
        self._montrer_formulaire()
        return True

    def rouvrir(self, numero):
        if not self._peut_remplacer():
            return False
        try:
            valeurs = licences_ouvertes.charger(numero)
        except (ValueError, OSError, sqlite3.Error) as exc:
            messagebox.showerror('Licence', str(exc), parent=self)
            return False
        self.a_verifier = False
        self.confirme.set(False)
        self.verification.pack_forget()
        for cle, variable in self.champs.items():
            variable.set(valeurs.get(cle, ''))
        self.details.charger(valeurs)
        # Une donnée devenue incohérente (ex. facture datée après la licence) ne doit pas empêcher
        # d'ouvrir le dossier : il s'ouvre, l'erreur est signalée et le bouton de validation reste bloqué.
        try:
            self.licence = self._preparer_licence()
            erreur = None
        except ValueError as exc:
            self.licence = None
            erreur = str(exc)
        try:
            espace_travail.dossier_dec(valeurs.get('numero_dec'))  # dossier DEC créé à l'ouverture
        except (OSError, ValueError):
            pass
        self.source.set('Licence enregistrée : ' + numero)
        self.etat_dossier.set('Étape 1 · Enregistrée')
        self.titre_formulaire.set(numero)
        self.modifie = False
        # Client connu sur une autre licence : fiche complète et fournisseur repris automatiquement.
        repris = self.details.completer_automatiquement(exclure=numero)
        if repris:
            self.modifie = True
            self.etat_dossier.set('Étape 1 · À compléter')
            self.source.set(f'Licence enregistrée : {numero} · repris automatiquement : {repris}. '
                            'Vérifiez puis cliquez sur « Valider et enregistrer ».')
        if erreur:
            self.etat_dossier.set('Étape 1 · À corriger')
            self.resultat.set(erreur)
            self.bouton_valider.configure(state='disabled')
            self.source.set(f'Licence enregistrée : {numero} · à corriger : {erreur}')
        self.carnet.select(0)
        self._montrer_formulaire()
        if erreur:
            messagebox.showwarning('Dossier à corriger',
                                   f'{erreur}\n\nCorrigez la valeur dans l’onglet Licence (par exemple avec '
                                   '« Proposer n° et date de facture »), puis cliquez sur « Valider et enregistrer ».\n\n'
                                   'Le traitement du dossier reste accessible avec « Traitement licence ».', parent=self)
        return True

    def marquer_physique(self, numero, physique):
        """Coche « en physique » depuis la liste ; renvoie la date enregistrée, '' si décoché, None si échec."""
        if self.app.session_verrouillee:
            return None
        try:
            return licences_ouvertes.marquer_physique(numero, physique)
        except (ValueError, OSError, sqlite3.Error) as exc:
            messagebox.showerror('Dossier en physique', str(exc), parent=self)
            return None

    def supprimer_licence(self, numero, recommencer=False):
        """Retire la licence de la liste. Soussigné, fournisseur et articles restent proposés
        pour les autres licences ; le dossier DEC est déplacé dans les sauvegardes."""
        if self.app.session_verrouillee or self.import_en_cours:
            return False
        if not messagebox.askyesno(
                'Supprimer et recommencer' if recommencer else 'Supprimer la licence',
                f'Supprimer la licence {numero} de la liste ?\n\n'
                + ('Le formulaire sera rouvert avec ses informations de départ (numéros, FOB, dates, client, '
                   'fournisseur, articles) ; répartition, factures, XML et CVI repartent de zéro.\n\n' if recommencer else '')
                + 'Le client, le fournisseur et les articles restent toujours proposés pour les autres licences. '
                  'Le dossier DEC est déplacé (pas effacé) dans « 6 - SAUVEGARDES/LICENCES SUPPRIMEES » : '
                  'la même DEC repartira d’un dossier propre.', icon='warning', parent=self):
            return False
        try:
            licence = licences_ouvertes.supprimer(numero)
        except (ValueError, OSError, sqlite3.Error) as exc:
            messagebox.showerror('Supprimer la licence', str(exc), parent=self)
            return False
        dossier = self._archiver_dossier(licence, garder=('licence',) if recommencer else ())
        if not recommencer:
            self._afficher_liste(notification=f'Licence {numero} supprimée · client, fournisseur et articles conservés'
                                 + dossier + '.')
            return True
        valeurs = licences_ouvertes.base_recommencer(licence)
        self.a_verifier = False
        self.fichier_licence = None
        self.confirme.set(False)
        self.verification.pack_forget()
        for cle, variable in self.champs.items():
            variable.set(str(valeurs.get(cle, '') or ''))
        self.details.charger(valeurs)
        self.carnet.select(0)
        self._modifier()
        self.titre_formulaire.set(f'{numero} · à recommencer')
        self.source.set(f'Licence {numero} supprimée puis rouverte avec ses informations de départ{dossier}. '
                        'Vérifiez puis cliquez sur « Valider et enregistrer ».')
        self._montrer_formulaire()
        return True

    @staticmethod
    def _archiver_dossier(licence, garder=()):
        """Déplace le dossier DEC d'une licence supprimée dans les sauvegardes ; renvoie un texte de compte rendu."""
        try:
            # Dossier partagé avec une autre licence encore ouverte (même DEC) : laissé en place.
            partage = any(str(l['numero_dec']).strip() == str(licence.get('numero_dec', '')).strip()
                          for l in licences_ouvertes.lister())
            archive = None if partage else espace_travail.archiver_dossier_dec(licence.get('numero_dec'), garder=garder)
        except (OSError, ValueError, sqlite3.Error) as exc:
            return f' · dossier DEC non déplacé ({exc})'
        return f' · dossier DEC déplacé dans {espace_travail.relatif(archive)}' if archive is not None else ''

    def supprimer_toutes(self):
        """Vide la liste des licences ouvertes, avec les mêmes protections qu'une suppression simple."""
        if self.app.session_verrouillee or self.import_en_cours:
            return False
        try:
            nombre = len(licences_ouvertes.lister())
        except (ValueError, OSError, sqlite3.Error) as exc:
            messagebox.showerror('Tout supprimer', str(exc), parent=self)
            return False
        if not nombre:
            messagebox.showinfo('Tout supprimer', 'Aucune licence ouverte.', parent=self)
            return False
        if not messagebox.askyesno(
                'Tout supprimer', f'Supprimer les {nombre} licence(s) ouverte(s) de la liste ?\n\n'
                'Les clients, fournisseurs et articles restent toujours proposés. Les dossiers DEC sont déplacés '
                '(pas effacés) dans « 6 - SAUVEGARDES/LICENCES SUPPRIMEES ».', icon='warning', parent=self):
            return False
        if not messagebox.askyesno('Tout supprimer', f'Confirmer : les {nombre} licences vont disparaître de la liste.',
                                   icon='warning', default='no', parent=self):
            return False
        try:
            licences = licences_ouvertes.supprimer_toutes()
        except (ValueError, OSError, sqlite3.Error) as exc:
            messagebox.showerror('Tout supprimer', str(exc), parent=self)
            self._afficher_liste()
            return False
        echecs = [r for r in (self._archiver_dossier(l) for l in licences) if 'non déplacé' in r]
        self._afficher_liste(notification=f'{len(licences)} licence(s) supprimée(s) · clients, fournisseurs et articles '
                             'conservés · dossiers DEC déplacés dans 6 - SAUVEGARDES/LICENCES SUPPRIMEES'
                             + (f' ({len(echecs)} non déplacé(s), fichiers peut-être ouverts)' if echecs else '') + '.')
        return True

    def recommencer_licence(self, numero):
        return self.supprimer_licence(numero, recommencer=True)

    def voir_licences(self):
        if not self._peut_remplacer():
            return
        if self.details.editeur is not None and self.details.editeur.winfo_exists():
            self.details.editeur.destroy()
        self.modifie = False
        self._afficher_liste()

    def generer_xml(self, numero):
        if self.app.session_verrouillee or self.import_en_cours:
            return
        try:
            licence = licences_ouvertes.charger(numero)
        except (ValueError, OSError, sqlite3.Error) as exc:
            messagebox.showerror('Génération XML', str(exc), parent=self)
            return
        if not licence.get('repartition') or not licence.get('informations_declaration'):
            messagebox.showinfo('Étapes à compléter', 'Validez la répartition et les poids, puis les informations de déclaration avant de générer le XML.', parent=self)
            return
        if not mise_a_jour_repartitions.est_a_jour(licence):
            messagebox.showinfo('Mise à jour requise', 'Validez la mise à jour des répartitions avant la génération XML.', parent=self)
            return
        if not facture_licence.est_a_jour(licence):
            messagebox.showinfo('Factures requises', 'Produisez d’abord la facture et la packing list de chaque part (étape 5).', parent=self)
            return
        try:
            # Modèle de structure choisi automatiquement : l'utilisateur n'a rien à charger.
            modele = xml_licence.proposer_modele(licence)
        except (ValueError, OSError) as exc:
            messagebox.showerror('Génération XML', str(exc), parent=self)
            return
        FenetreGenerationXML(self, licence, modele, lambda choisi: self._generer_parts(numero, choisi))

    def _generer_parts(self, numero, modele):
        """Écrit un XML par montant de part différent dans le dossier DEC (parts identiques : un seul XML).
        Renvoie un message d'erreur ou None."""
        try:
            licence = licences_ouvertes.charger(numero)
            vues = xml_licence.vues_a_generer(licence)
            # Tous les XML sont préparés avant toute écriture : rien n'est écrit si l'un échoue.
            for vue in vues:
                xml_licence.preparer(vue, modele)
            base = re.sub(r'[^A-Za-z0-9._-]', '-', numero)
            dossier = espace_travail.dossier_dec(licence['numero_dec'], 'xml_generes')
            if dossier is None:
                choisi = filedialog.askdirectory(parent=self, title='Dossier où enregistrer les XML préremplis')
                if not choisi:
                    return 'Enregistrement annulé.'
                dossier = Path(choisi)
            ecrits = []
            for vue in vues:
                part = vue['part_generee']
                nom = f"{base} - {xml_licence.libelle_parts(part['identiques'])} - a completer.xml"
                # Tout ce qui est produit pour la licence va dans son dossier DEC, sans écraser.
                destination = espace_travail.destination_libre(dossier, nom)[0]
                xml_licence.exporter(licence, modele, destination, vue)
                ecrits.append(dict(parts=part['identiques'], fob=part['fob'], fichier=str(destination)))
            premier = Path(ecrits[0]['fichier'])
            licences_ouvertes.enregistrer_xml_genere(numero, premier.read_text(encoding='utf-8'), premier, fichiers=ecrits)
            licences_ouvertes.retenir_modele_structure(numero, modele)
        except FileExistsError:
            return 'Ce fichier existe déjà : réessayez pour obtenir un nouveau nom.'
        except (ValueError, OSError, sqlite3.Error, ET.ParseError) as exc:
            return str(exc)
        self.traiter_licence(numero)
        liste = '\n'.join(f"• {xml_licence.libelle_parts(e['parts']).capitalize()} : FOB {format_nombre(float(e['fob']), 2)} USD"
                          for e in ecrits)
        messagebox.showinfo('XML enregistrés', f"{len(ecrits)} XML (un par montant de part différent) :\n{liste}\n\n"
                            f'{espace_travail.relatif(dossier)}\n\n'
                            + ('XML complet établi sur la déclaration réelle ' + Path(modele).name
                               + ' : bureau, déclarant, banque, transport, documents, valeur, fret, assurance et taxes.'
                               if xml_licence.est_base_licence(modele) else xml_licence.AVERTISSEMENT)
                            + '\n\nLe XML de la part 1 est conservé pour la récupération simulation.', parent=self)
        return None

    def _references_facture(self, numero, licence):
        """N° et date de facture de la licence ; lus sur la licence PDF du dossier DEC, sinon demandés."""
        if licence.get('numero_facture') and licence.get('date_facture'):
            return licence
        trouves = {}
        try:
            dossier = espace_travail.dossier_dec(licence['numero_dec'], 'licence')
            for fichier in sorted(dossier.iterdir()) if dossier is not None else ():
                if fichier.suffix.lower() in ('.pdf', '.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp'):
                    valeurs, _ = lire_licence(fichier)
                    if valeurs.get('numero_facture') and valeurs.get('date_facture'):
                        trouves = valeurs
                        break
        except Exception:
            trouves = {}  # lecture facultative : la saisie reste possible
        if not (trouves.get('numero_facture') or licence.get('numero_facture')):
            try:  # rien sur la licence : proposition, modifiable dans la fenêtre de saisie
                trouves = dict(numero_facture=licences_ouvertes.proposer_numero_facture(),
                               date_facture=licence.get('date_facture') or proposer_date_facture(licence.get('date_validation')))
            except (ValueError, OSError, sqlite3.Error):
                pass
        from tkinter import simpledialog
        numero_facture = simpledialog.askstring(
            'Numéro de facture', 'Numéro de facture de la licence (rubrique « N° Facture ») :',
            initialvalue=trouves.get('numero_facture', licence.get('numero_facture', '')), parent=self)
        if not numero_facture:
            return None
        date_facture = simpledialog.askstring(
            'Date de facture', 'Date de facture de la licence (JJ/MM/AAAA) :',
            initialvalue=trouves.get('date_facture', licence.get('date_facture', '')), parent=self)
        if not date_facture:
            return None
        try:
            licences_ouvertes.enregistrer_references_facture(numero, numero_facture, date_facture)
            return licences_ouvertes.charger(numero)
        except (ValueError, OSError, sqlite3.Error) as exc:
            messagebox.showerror('Facture', str(exc), parent=self)
            return None

    def choisir_facture_bibliotheque(self, numero):
        """Réutilise les Word enregistrés dans Modèles de facture pour toute la licence."""
        if self.app.session_verrouillee or self.import_en_cours:
            return
        from asydec.declarations import factures
        try:
            modeles = factures.lister_modeles()
        except (ValueError, OSError, sqlite3.Error) as exc:
            messagebox.showerror('Modèles de facture', str(exc), parent=self)
            return
        if not modeles:
            messagebox.showinfo('Modèles de facture',
                                'Ajoutez d’abord vos modèles Word dans « Modèles de facture », '
                                'ou utilisez « Choisir le modèle de facture… ».', parent=self)
            return
        fenetre = tk.Toplevel(self)
        fenetre.title('Produire les factures depuis un modèle existant')
        fenetre.transient(self.winfo_toplevel())
        cadre = ttk.Frame(fenetre, padding=18)
        cadre.pack(fill='both', expand=True)
        ttk.Label(cadre, text='Choisissez une facture avec packing list. AsyDec reprend sa présentation et remplit\n'
                  'les articles, quantités, prix, poids, numéro et date de la licence.').pack(anchor='w', pady=(0, 10))
        choix = ttk.Combobox(cadre, state='readonly', width=85,
                             values=[f"{m['nom']} — {m.get('destinataire') or 'Destinataire non repéré'}"
                                     for m in modeles])
        choix.pack(fill='x', pady=8)
        choix.current(0)

        def produire():
            try:
                modele = factures.lire_modele(modeles[choix.current()]['id'])
            except (ValueError, OSError, sqlite3.Error) as exc:
                messagebox.showerror('Modèles de facture', str(exc), parent=fenetre)
                return
            fenetre.destroy()
            self.generer_facture(numero, modele_bibliotheque=modele)

        theme.bouton(cadre, 'Produire les factures et packing lists', produire, principal=True).pack(anchor='e', pady=10)
        fenetre.grab_set()

    def generer_facture(self, numero, simple=False, modele_bibliotheque=None):
        """Étape 5 : une facture + packing list Word par part, depuis le modèle fourni
        ou, avec simple=True, créées par AsyDec sans modèle."""
        if self.app.session_verrouillee or self.import_en_cours:
            return
        try:
            licence = licences_ouvertes.charger(numero)
        except (ValueError, OSError, sqlite3.Error) as exc:
            messagebox.showerror('Factures', str(exc), parent=self)
            return
        if not mise_a_jour_repartitions.est_a_jour(licence):
            messagebox.showinfo('Mise à jour requise', 'Validez la mise à jour des répartitions avant les factures.', parent=self)
            return
        licence = self._references_facture(numero, licence)
        if licence is None:
            return
        precedentes = licence.get('factures_parts') or {}
        options = {}
        if precedentes.get('methode', 'modele') == 'modele' and precedentes.get('modele') \
                and Path(precedentes['modele']).parent.is_dir():
            options = {'initialdir': str(Path(precedentes['modele']).parent), 'initialfile': Path(precedentes['modele']).name}
        modele = None
        if modele_bibliotheque is not None:
            modele = modele_bibliotheque['nom']
        elif not simple:
            modele = filedialog.askopenfilename(parent=self, title='Choisir le modèle de facture (Word avec packing list)',
                                                filetypes=[('Document Word', '*.docx')], **options)
            if not modele:
                return
        try:
            # Toutes les parts sont préparées en mémoire : rien n'est écrit si l'une échoue.
            contenu_modele = (modele_bibliotheque['contenu'] if modele_bibliotheque is not None
                              else Path(modele).read_bytes() if modele else None)
            resultats = facture_licence.generer(licence, contenu_modele)
            globale = facture_licence.generer_globale(licence, contenu_modele)
        except (ValueError, OSError) as exc:
            messagebox.showerror('Factures', str(exc), parent=self)
            return
        try:
            dossier = espace_travail.dossier_dec(licence['numero_dec'], 'factures')
            if dossier is None:
                choisi = filedialog.askdirectory(parent=self, title='Dossier où enregistrer les factures')
                if not choisi:
                    return
                dossier = Path(choisi)
            # Une nouvelle génération remplace les fichiers produits précédemment par AsyDec.
            anciens = {str(Path(f)) for p in (precedentes.get('parts') or []) + [precedentes.get('globale') or {}]
                       for f in (p.get('fichiers') or {}).values()}

            def ecrire(resultat):
                # Deux fichiers séparés : la facture et la packing list.
                ecrits = {}
                for document, contenu in resultat['documents'].items():
                    destination = Path(dossier) / facture_licence.nom_fichier(numero, resultat, document)
                    if destination.exists() and str(destination) not in anciens:
                        destination = espace_travail.destination_libre(dossier, destination.name)[0]
                    destination.write_bytes(contenu)
                    ecrits[document] = destination
                return ecrits
            fichiers = [ecrire(resultat) for resultat in resultats]
            fichiers_globale = ecrire(globale)
            licences_ouvertes.enregistrer_factures(numero, facture_licence.fiche(
                licence, resultats, fichiers, modele, globale, fichiers_globale))
        except (ValueError, OSError, sqlite3.Error) as exc:
            messagebox.showerror('Factures', str(exc), parent=self)
            return
        self.traiter_licence(numero)
        alertes = facture_licence.avertissements_quantites(licence)
        avertissement = ('\n\nQuantités fractionnaires de pièces à vérifier sur la licence :\n'
                         + '\n'.join(alertes[:5])
                         + (f'\n… et {len(alertes) - 5} autre(s).' if len(alertes) > 5 else '')) if alertes else ''
        notification = messagebox.showwarning if alertes else messagebox.showinfo
        notification('Factures et packing lists enregistrées',
                            f"{len(resultats)} facture(s) et {len(resultats)} packing list(s) séparées du {resultats[0]['date']} : "
                            f"{resultats[0]['numero']} à {resultats[-1]['numero']}.\n"
                            f"Facture globale {globale['numero']} : FOB {format_nombre(float(globale['fob']), 2)} USD, "
                            f"{globale['articles']} article(s), {format_nombre(globale['poids_kg'], 2)} kg.\n\n"
                            f"{espace_travail.relatif(dossier)}{avertissement}",
                            parent=self)

    def generer_cvi(self, numero):
        if self.app.session_verrouillee or self.import_en_cours:
            return
        from asydec.ui.cvi import ComplementsCVI
        modele = cvi.modele_defaut()
        if not modele.is_file():
            choisi = filedialog.askopenfilename(parent=self, title='Modèle CVI Word préparé avec balises',
                                                filetypes=[('Modèle Word CVI', '*.docx')])
            if not choisi:
                return
            modele = Path(choisi)
        try:
            licence = licences_ouvertes.charger(numero)
            fenetre = ComplementsCVI(self, licence)
            self.wait_window(fenetre)
            if fenetre.resultat is None:
                return
            complements = fenetre.resultat
            resultats = cvi.generer(licence, modele.read_bytes(), complements)
            dossier = espace_travail.dossier_dec(licence['numero_dec'], 'cvi')
            if dossier is None:
                choisi = filedialog.askdirectory(parent=self, title='Enregistrer le CVI et le BL de la première répartition')
                if not choisi:
                    return
                dossier = Path(choisi)
            fichiers = []
            for part, contenu in resultats:
                destination = espace_travail.destination_libre(dossier, f'CVI-BL-part-{part}.docx')[0]
                destination.write_bytes(contenu)
                fichiers.append(str(destination))
            licences_ouvertes.enregistrer_cvi(numero, dict(modele=str(modele), fichiers=fichiers,
                                                        complements=complements,
                                                        empreinte=cvi.empreinte(licence, complements)))
        except (ValueError, OSError, sqlite3.Error) as exc:
            messagebox.showerror('Remplissage CVI', str(exc), parent=self)
            return
        self.traiter_licence(numero)
        nombre_bl = cvi.nombre_bl(licence)
        messagebox.showinfo('CVI et BL enregistrés', f'CVI et {nombre_bl} BL enregistrés dans un Word de {1 + nombre_bl} pages.\n\n{dossier}', parent=self)

    # Fichiers déjà produits par étape : utilisés pour retrouver le dossier sans dossier de travail.
    TITRES_RANGEMENT = {None: 'Dossier DEC', 'licence': 'Licence', 'factures': 'Factures', 'cvi': 'CVI et BL',
                        'xml_generes': 'XML générés', 'xml_sydonia': 'XML SYDONIA', 'declarations': 'Déclarations'}

    @staticmethod
    def _fichiers_produits(licence, cle):
        if cle == 'factures':
            factures = licence.get('factures_parts') or {}
            return [f for p in (factures.get('parts') or []) + [factures.get('globale') or {}]
                    for f in (p.get('fichiers') or {}).values()]
        if cle == 'cvi':
            return (licence.get('cvi_parts') or {}).get('fichiers') or []
        if cle == 'declarations':
            return [f['fichier'] for f in (licence.get('declarations') or {}).get('fichiers') or []]
        if cle == 'xml_generes':
            xml = licence.get('xml_genere') or {}
            return [f['fichier'] for f in xml.get('fichiers') or []] or [xml.get('fichier')]
        if cle == 'xml_sydonia':
            return [(licence.get('recuperation_simulation') or {}).get('fichier')]
        return []

    def ouvrir_rangement(self, numero, cle=None):
        """Ouvre le dossier où l'étape range ses fichiers (sous-dossier du dossier DEC)."""
        titre = self.TITRES_RANGEMENT.get(cle, 'Dossier')
        try:
            licence = licences_ouvertes.charger(numero)
            dossier = espace_travail.dossier_dec(licence['numero_dec'], cle)
        except (ValueError, OSError, sqlite3.Error) as exc:
            messagebox.showerror(titre, str(exc), parent=self)
            return
        if dossier is None:
            fichiers = [f for f in self._fichiers_produits(licence, cle) if f]
            dossier = Path(fichiers[0]).parent if fichiers else None
        if dossier is None:
            messagebox.showinfo(titre, 'Aucun dossier de travail ni fichier enregistré pour cette étape.', parent=self)
            return
        self.ouvrir_dossier(Path(dossier))

    def ouvrir_cvi(self, numero):
        self.ouvrir_rangement(numero, 'cvi')

    def ouvrir_factures(self, numero):
        self.ouvrir_rangement(numero, 'factures')

    HAUTEUR_LISTE = 230

    def _bloc_liste(self, parent, titre, licence, cle, chemins):
        """Cadre de liste à hauteur limitée (défilement au-delà) avec, en tête, le chemin cliquable du dossier.

        Renvoie le cadre intérieur, où les lignes sont placées avec grid à partir de la ligne 1."""
        cadre = ttk.Frame(parent, padding=12, relief='solid', borderwidth=1)
        cadre.pack(fill='x', pady=(0, 16))
        entete = ttk.Frame(cadre)
        entete.pack(fill='x', pady=(0, 8))
        ttk.Label(entete, text=titre, style='Section.TLabel').pack(side='left')
        try:
            dossier = espace_travail.dossier_dec(licence['numero_dec'], cle)
        except (OSError, ValueError, KeyError):
            dossier = None
        existants = [Path(c) for c in chemins if c and Path(c).is_file()]
        if existants and (dossier is None or existants[0].parent != Path(dossier)):
            dossier = existants[0].parent
        if dossier is not None:
            lien = tk.Label(entete, text='📂 ' + espace_travail.relatif(dossier), fg=theme.ACCENT, bg=theme.FOND,
                            font=(theme.POLICE, 10, 'underline'), cursor='hand2', anchor='e')
            lien.pack(side='right', padx=(14, 0))
            lien.bind('<Button-1>', lambda _e, d=Path(dossier): self.ouvrir_dossier(d))
        zone = ttk.Frame(cadre)
        zone.pack(fill='x')
        toile = tk.Canvas(zone, highlightthickness=0, bg=theme.FOND, height=40)
        barre = ttk.Scrollbar(zone, orient='vertical', command=toile.yview)
        toile.configure(yscrollcommand=barre.set)
        toile.pack(side='left', fill='x', expand=True)
        interieur = tk.Frame(toile, bg=theme.FOND)
        fenetre = toile.create_window((0, 0), window=interieur, anchor='nw')

        def ajuster(_e=None):
            hauteur = interieur.winfo_reqheight()
            toile.configure(scrollregion=(0, 0, interieur.winfo_reqwidth(), hauteur),
                            height=min(hauteur, self.HAUTEUR_LISTE))
            if hauteur > self.HAUTEUR_LISTE:
                if not barre.winfo_ismapped():
                    barre.pack(side='right', fill='y')
            elif barre.winfo_ismapped():
                barre.pack_forget()
        interieur.bind('<Configure>', ajuster)
        toile.bind('<Configure>', lambda e: toile.itemconfigure(fenetre, width=e.width))

        def molette(evenement):
            if toile.winfo_exists() and interieur.winfo_reqheight() > self.HAUTEUR_LISTE:
                toile.yview_scroll(-1 * (evenement.delta if abs(evenement.delta) < 20 else evenement.delta // 120), 'units')
        toile.bind('<Enter>', lambda _: toile.bind_all('<MouseWheel>', molette))
        toile.bind('<Leave>', lambda _: toile.unbind_all('<MouseWheel>'))
        return interieur

    def _liste_xml_generes(self, parent, licence):
        """Liste cliquable des XML générés à l'étape 7 : nom du fichier (ouvre le XML) et 📂 (le montre dans le dossier)."""
        xml = licence.get('xml_genere') or {}
        entrees = xml.get('fichiers') or ([dict(parts=[1], fichier=xml['fichier'])] if xml.get('fichier') else [])
        if not entrees:
            return
        bloc = self._bloc_liste(parent, f'XML générés ({len(entrees)})', licence, 'xml_generes',
                                [e['fichier'] for e in entrees])
        bloc.columnconfigure(1, weight=1)
        for i, entree in enumerate(entrees, 1):
            chemin = Path(entree['fichier'])
            existe = chemin.is_file()
            parts = xml_licence.libelle_parts(entree.get('parts') or [1]).capitalize()
            fob = f" · FOB {format_nombre(float(entree['fob']), 2)} USD" if entree.get('fob') else ''
            ttk.Label(bloc, text=parts + fob, style='Doux.TLabel').grid(row=i, column=0, sticky='w', padx=(0, 14), pady=2)
            lien = tk.Label(bloc, text=chemin.name + ('' if existe else '  (introuvable)'),
                            fg=theme.ACCENT if existe else theme.TEXTE_DOUX, bg=theme.FOND,
                            font=(theme.POLICE, 11, 'underline' if existe else 'normal'),
                            cursor='hand2' if existe else '', anchor='w')
            lien.grid(row=i, column=1, sticky='w', pady=2)
            if existe:
                lien.bind('<Button-1>', lambda _e, c=chemin: self.ouvrir_fichier(c))
                dossier = tk.Label(bloc, text='📂 Afficher dans le dossier', fg=theme.ACCENT, bg=theme.FOND,
                                   font=(theme.POLICE, 10), cursor='hand2')
                dossier.grid(row=i, column=2, sticky='e', padx=(14, 0), pady=2)
                dossier.bind('<Button-1>', lambda _e, c=chemin: self.ouvrir_fichier(c, reveler=True))

    def imprimer_documents(self, numero):
        """Factures, packing lists, CVI + BL, déclarations et fiche : un seul PDF, envoyé à l'imprimante."""
        if self.app.session_verrouillee or self.import_en_cours:
            return
        from asydec.ui.impression_documents import FenetreImpression
        try:
            licence = licences_ouvertes.charger(numero)
        except (ValueError, OSError, sqlite3.Error) as exc:
            messagebox.showerror('Imprimer les documents', str(exc), parent=self)
            return
        FenetreImpression(self, self.app, licence, self.ouvrir_fichier)

    def imprimer_dossier(self, numero):
        """Fiche PDF du dossier (informations et répartitions), enregistrée dans le dossier DEC puis ouverte
        pour impression (Aperçu, Edge, Acrobat…)."""
        from asydec.declarations import fiche_dossier
        try:
            licence = licences_ouvertes.charger(numero)
            contenu = fiche_dossier.pdf(licence)
            dossier = espace_travail.dossier_dec(licence['numero_dec'])
        except (ValueError, OSError, sqlite3.Error) as exc:
            messagebox.showerror('Imprimer détails dossier', str(exc), parent=self)
            return
        if dossier is None:
            choisi = filedialog.askdirectory(parent=self, title='Dossier où enregistrer la fiche du dossier')
            if not choisi:
                return
            dossier = Path(choisi)
        destination = Path(dossier) / f'{numero} - details dossier.pdf'
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(contenu)
        except OSError as exc:
            messagebox.showerror('Imprimer détails dossier',
                                 f'{exc}\n\nFermez la fiche si elle est ouverte, puis recommencez.', parent=self)
            return
        self.ouvrir_fichier(destination)

    def ouvrir_fichier(self, chemin, reveler=False):
        """Ouvre le fichier avec l'application par défaut, ou le sélectionne dans le Finder / l'Explorateur."""
        import subprocess
        import sys
        try:
            if sys.platform == 'darwin':
                subprocess.run(['open', '-R', str(chemin)] if reveler else ['open', str(chemin)], check=False)
            elif sys.platform == 'win32':
                if reveler:
                    subprocess.run(['explorer', '/select,', str(chemin)], check=False)
                else:
                    import os
                    os.startfile(str(chemin))
        except OSError as exc:
            messagebox.showerror('Fichier XML', str(exc), parent=self)

    def ouvrir_dossier(self, dossier):
        import subprocess
        import sys
        try:
            dossier.mkdir(parents=True, exist_ok=True)
            if sys.platform == 'darwin':
                subprocess.run(['open', str(dossier)], check=False)
            elif sys.platform == 'win32':
                import os
                os.startfile(str(dossier))
        except OSError as exc:
            messagebox.showerror('Dossier DEC', str(exc), parent=self)

    def _dossier_dec(self, licence, cle):
        try:
            dossier = espace_travail.dossier_dec(licence['numero_dec'], cle)
        except (OSError, ValueError):
            return {}
        return {'initialdir': str(dossier)} if dossier is not None else {}

    def recuperer_simulation(self, numero):
        """Importe un ou plusieurs XML SYDONIA ; chacun est comparé au XML attendu de la part qui lui correspond."""
        if self.app.session_verrouillee or self.import_en_cours:
            return
        try:
            licence = licences_ouvertes.charger(numero)
        except (ValueError, OSError, sqlite3.Error) as exc:
            messagebox.showerror('Récupération simulation', str(exc), parent=self)
            return
        chemins = filedialog.askopenfilenames(parent=self, title='Choisir le ou les XML récupérés de SYDONIA (Cmd/Ctrl + clic)',
                                              filetypes=[('XML SYDONIA', '*.xml')], **self._dossier_dec(licence, 'xml_sydonia'))
        if not chemins:
            return
        sydonias = []
        for chemin in chemins:
            try:
                chemin = str(espace_travail.ranger_dans_dec(chemin, licence['numero_dec'], 'xml_sydonia') or chemin)
            except (OSError, ValueError):
                pass  # la comparaison reste possible depuis le fichier d'origine
            try:
                contenu = Path(chemin).read_text(encoding='utf-8')
            except UnicodeDecodeError:
                contenu = Path(chemin).read_bytes().decode('latin-1')
            except OSError as exc:
                messagebox.showerror('Récupération simulation', f'{Path(chemin).name} : {exc}', parent=self)
                return
            sydonias.append((chemin, contenu))
        try:
            licences_ouvertes.enregistrer_recuperations(numero, sydonias)
        except (ValueError, OSError, sqlite3.Error) as exc:
            messagebox.showerror('Récupération simulation', str(exc), parent=self)
            return
        self.traiter_licence(numero)
        self.voir_comparaison(numero)

    def generer_verifications(self, numero):
        """Étape 8 sans SYDONIA : XML de vérification pour les parts sans XML SYDONIA importé."""
        if self.app.session_verrouillee or self.import_en_cours:
            return
        from asydec.declarations import taux_declaration
        try:
            licence = licences_ouvertes.charger(numero)
            dossier = espace_travail.dossier_dec(licence['numero_dec'], 'xml_sydonia')
        except (ValueError, OSError, sqlite3.Error) as exc:
            messagebox.showerror('XML de vérification', str(exc), parent=self)
            return
        if dossier is None:
            choisi = filedialog.askdirectory(parent=self, title='Dossier où enregistrer les XML de vérification')
            if not choisi:
                return
            dossier = Path(choisi)
        taux = taux_declaration.du_dossier(licence)
        if not messagebox.askyesno(
                'XML de vérification',
                'AsyDec va produire, pour chaque part sans XML SYDONIA importé, un XML de vérification à partir '
                'du XML attendu (étape 7) : montants en francs congolais, bases et taxes recalculés '
                + (f'au taux {taux} de l’étape 3.' if taux else 'au taux du XML généré (aucun taux saisi à l’étape 3).')
                + '\n\nLes XML SYDONIA déjà importés sont gardés. Ces fichiers sont marqués « vérification AsyDec » : '
                  'ce ne sont pas des déclarations réelles et ils ne servent jamais de référence.\n\nContinuer ?',
                parent=self):
            return
        try:
            fichiers = licences_ouvertes.generer_verifications(numero, dossier)
        except (ValueError, OSError, sqlite3.Error, ET.ParseError) as exc:
            messagebox.showerror('XML de vérification', str(exc), parent=self)
            return
        self.traiter_licence(numero)
        messagebox.showinfo('XML de vérification', f'{len(fichiers)} XML de vérification enregistré(s) et comparé(s) :\n'
                            + espace_travail.relatif(dossier), parent=self)

    @staticmethod
    def _comparaisons(licence):
        """Comparaisons enregistrées (une par XML SYDONIA importé), recalculées pour l'affichage."""
        recuperation = licence['recuperation_simulation']
        xml = licence.get('xml_genere') or {}
        imports = recuperation.get('imports') or [dict(fichier=recuperation['fichier'], contenu=recuperation['contenu'],
                                                       importe_le=recuperation.get('importe_le'), parts=[1],
                                                       libelle='part 1', reference=xml['contenu'])]
        fichiers = xml.get('fichiers') or [dict(parts=[1], fichier=xml.get('fichier'))]
        resultat = []
        for i in imports:
            genere = next((f['fichier'] for f in fichiers if set(i.get('parts') or [1]) <= set(f.get('parts') or [1])),
                          xml.get('fichier', '—'))
            resultat.append(dict(titre=i.get('libelle', 'part 1'), genere=genere, sydonia=i['fichier'],
                                 importe_le=i.get('importe_le'),
                                 comparaison=recuperation_simulation.comparer(i['reference'], i['contenu'])))
        return resultat

    def voir_comparaison(self, numero):
        if self.app.session_verrouillee or self.import_en_cours:
            return
        try:
            licence = licences_ouvertes.charger(numero)
            if not licence.get('recuperation_simulation'):
                messagebox.showinfo('Récupération simulation', 'Importez d’abord le XML récupéré de SYDONIA.', parent=self)
                return
            comparaisons = self._comparaisons(licence)
        except (ValueError, OSError, sqlite3.Error, KeyError) as exc:
            messagebox.showerror('Récupération simulation', str(exc), parent=self)
            return
        FenetreComparaison(self, licence, comparaisons)

    def generer_declarations(self, numero):
        """Étape 9 : une déclaration Word par part, depuis le modèle fourni (forme inchangée).

        La préparation (environ une demi-seconde par part) tourne en arrière-plan avec une barre de
        progression : l'application reste réactive même avec 20 ou 30 déclarations."""
        if self.app.session_verrouillee or self.import_en_cours:
            return
        modele = declaration_licence.modele_defaut()
        if not modele.is_file():
            choisi = filedialog.askopenfilename(parent=self, title='Modèle de déclaration Word préparé avec balises',
                                                filetypes=[('Modèle Word', '*.docx')])
            if not choisi:
                return
            modele = Path(choisi)
        try:
            licence = licences_ouvertes.charger(numero)
            contenu_modele = modele.read_bytes()
            dossier = espace_travail.dossier_dec(licence['numero_dec'], 'declarations')
        except (ValueError, OSError, sqlite3.Error) as exc:
            messagebox.showerror('Génération déclaration', str(exc), parent=self)
            return
        if dossier is None:
            choisi = filedialog.askdirectory(parent=self, title='Dossier où enregistrer les déclarations')
            if not choisi:
                return
            dossier = Path(choisi)

        import queue
        import threading
        file = queue.Queue()
        fenetre = tk.Toplevel(self)
        fenetre.title('Génération des déclarations')
        fenetre.transient(self.winfo_toplevel())
        fenetre.resizable(False, False)
        fenetre.protocol('WM_DELETE_WINDOW', lambda: None)  # pas de fermeture pendant le travail
        cadre = ttk.Frame(fenetre, padding=20)
        cadre.pack(fill='both', expand=True)
        statut = tk.StringVar(value='Préparation des déclarations…')
        ttk.Label(cadre, textvariable=statut, width=48).pack(anchor='w', pady=(0, 10))
        barre = ttk.Progressbar(cadre, mode='determinate', maximum=100, length=380)
        barre.pack(fill='x')
        self.import_en_cours = True

        def travail():
            try:
                # Toutes les parts sont préparées en mémoire : rien n'est écrit si l'une échoue.
                resultats = declaration_licence.generer(
                    licence, contenu_modele, lambda fait, total: file.put(('progression', fait, total)))
                file.put(('fini', resultats))
            except Exception as exc:  # affiché à l'utilisateur ; aucun fichier n'a été écrit
                file.put(('erreur', exc))

        def suivre():
            try:
                while True:
                    evenement = file.get_nowait()
                    if evenement[0] == 'progression':
                        _, fait, total = evenement
                        barre['value'] = 100 * fait / total if total else 100
                        statut.set(f'Déclaration {min(fait + 1, total)} / {total} en préparation…' if fait < total
                                   else f'{total} déclaration(s) prêtes · enregistrement…')
                    else:
                        self.import_en_cours = False
                        fenetre.destroy()
                        if evenement[0] == 'erreur':
                            messagebox.showerror('Génération déclaration', str(evenement[1]), parent=self)
                        else:
                            self._enregistrer_declarations(numero, licence, evenement[1], dossier, modele)
                        return
            except queue.Empty:
                pass
            self.after(120, suivre)

        threading.Thread(target=travail, daemon=True).start()
        self.after(120, suivre)

    def _enregistrer_declarations(self, numero, licence, resultats, dossier, modele):
        try:
            anciens = {str(Path(f['fichier'])) for f in (licence.get('declarations') or {}).get('fichiers') or []}
            fichiers = []
            for resultat in resultats:
                destination = Path(dossier) / declaration_licence.nom_fichier(numero, resultat['part'])
                if destination.exists() and str(destination) not in anciens:
                    destination = espace_travail.destination_libre(dossier, destination.name)[0]
                destination.write_bytes(resultat['contenu'])
                fichiers.append(destination)
            licences_ouvertes.enregistrer_declarations(numero, declaration_licence.fiche(resultats, fichiers, modele))
            sans = declaration_licence.parts_sans_sydonia(licences_ouvertes.charger(numero))
        except (ValueError, OSError, sqlite3.Error, ET.ParseError) as exc:
            messagebox.showerror('Génération déclaration', str(exc), parent=self)
            return
        self.traiter_licence(numero)
        plusieurs = [r['part'] for r in resultats if r['articles'] > 1]
        a_revoir = [r for r in resultats if r['controle']['manquantes']]
        # Coupures (police du modèle jamais changée) : regroupées, les mêmes cases reviennent sur chaque part.
        coupees = {}
        for r in resultats:
            for c in r.get('coupures') or []:
                coupees.setdefault(c, []).append(r['part'])
        texte_coupures = '\n'.join(f"• {c}" + (f" (parts {', '.join(map(str, p))})" if len(p) < len(resultats) else ' (toutes les parts)')
                                   for c, p in list(coupees.items())[:8])
        # Message court même avec 30 parts : le détail de chaque part reste dans la liste de l'étape 9.
        details = '\n'.join(f"• Part {r['part']} : {declaration_licence.texte_controle(r['controle'])}"
                             for r in a_revoir[:8])
        if len(a_revoir) > 8:
            details += f"\n• … et {len(a_revoir) - 8} autre(s)"
        incomplet = bool(a_revoir or sans or coupees)
        (messagebox.showwarning if incomplet else messagebox.showinfo)(
            'Déclarations enregistrées',
            f"{len(resultats)} déclaration(s) Word enregistrée(s), remplie(s) depuis le XML SYDONIA de chaque part."
            + (f"\n\nÀ revoir ({len(a_revoir)}) :\n{details}" if a_revoir
               else '\n\n✓ Toutes les parts sont prêtes pour la déclaration.')
            + (f"\n\nTexte coupé pour garder la police et la taille du modèle :\n{texte_coupures}" if coupees else '')
            + (f"\n\nSans XML SYDONIA importé à l’étape 8, pas de déclaration pour : part(s) {', '.join(map(str, sans))}."
               if sans else '')
            + (f"\n\nParts à plusieurs articles ({', '.join(map(str, plusieurs))}) : le formulaire ne porte que "
               'le premier article.' if plusieurs else '')
            + f"\n\n{espace_travail.relatif(dossier)}", parent=self)

    def _liste_declarations(self, parent, licence):
        """Liste cliquable des déclarations Word de l'étape 9."""
        entrees = (licence.get('declarations') or {}).get('fichiers') or []
        if not entrees:
            return
        bloc = self._bloc_liste(parent, f'Déclarations générées ({len(entrees)})', licence, 'declarations',
                                [e['fichier'] for e in entrees])
        bloc.columnconfigure(2, weight=1)
        for ligne, entree in enumerate(entrees, 1):
            ttk.Label(bloc, text=f"Part {entree['part']}" + (f" · E {entree['numero_e']}" if entree.get('numero_e') else ''),
                      style='Doux.TLabel').grid(row=ligne, column=0, sticky='w', padx=(0, 14), pady=2)
            ttk.Label(bloc, text=entree.get('origine', ''), style='Doux.TLabel', wraplength=260,
                      justify='left').grid(row=ligne, column=1, sticky='w', padx=(0, 14))
            chemin = Path(entree['fichier'])
            existe = chemin.is_file()
            lien = tk.Label(bloc, text=chemin.name + ('' if existe else '  (introuvable)'),
                            fg=theme.ACCENT if existe else theme.TEXTE_DOUX, bg=theme.FOND,
                            font=(theme.POLICE, 11, 'underline' if existe else 'normal'), cursor='hand2' if existe else '',
                            wraplength=360, justify='left', anchor='w')
            lien.grid(row=ligne, column=2, sticky='w', pady=2)
            if existe:
                lien.bind('<Button-1>', lambda _e, c=chemin: self.ouvrir_fichier(c))
                dossier = tk.Label(bloc, text='📂 Afficher dans le dossier', fg=theme.ACCENT, bg=theme.FOND,
                                   font=(theme.POLICE, 10), cursor='hand2')
                dossier.grid(row=ligne, column=3, sticky='e', padx=(14, 0), pady=2)
                dossier.bind('<Button-1>', lambda _e, c=chemin: self.ouvrir_fichier(c, reveler=True))
        coupees = sorted({c for e in entrees for c in e.get('coupures') or []})
        if coupees:
            tk.Label(bloc, text='✂ Texte coupé pour garder la police du modèle :\n' + '\n'.join('• ' + c for c in coupees),
                     fg=theme.ALERTE, bg=theme.FOND, font=(theme.POLICE, 10), wraplength=900, justify='left',
                     anchor='w').grid(row=len(entrees) + 1, column=0, columnspan=4, sticky='w', pady=(8, 0))

    def _liste_xml_sydonia(self, parent, licence):
        """Liste des XML SYDONIA importés à l'étape 8 : part associée, résultat, lien vers le fichier."""
        recuperation = licence.get('recuperation_simulation') or {}
        imports = recuperation.get('imports') or ([dict(fichier=recuperation['fichier'], parts=[1], libelle='part 1',
                                                        resume=recuperation['resume'])] if recuperation.get('fichier') else [])
        if not imports:
            return
        bloc = self._bloc_liste(parent, f'XML SYDONIA importés ({len(imports)})', licence, 'xml_sydonia',
                                [e['fichier'] for e in imports])
        bloc.columnconfigure(2, weight=1)
        for ligne, entree in enumerate(imports, 1):
            resume = entree.get('resume') or {}
            if resume.get('controles_differents'):
                etat, couleur = f"✗ {resume['controles_differents']} contrôle(s) différent(s)", theme.ERREUR
            elif resume.get('modifie') or resume.get('retire'):
                etat, couleur = '⚠ autres champs modifiés', theme.ALERTE
            else:
                etat, couleur = '✓ identique', theme.OK
            if entree.get('simule'):
                etat, couleur = '◆ vérification AsyDec (sans SYDONIA)', theme.ACCENT
            ttk.Label(bloc, text=str(entree.get('libelle', 'part 1')).capitalize(), style='Doux.TLabel').grid(
                row=2 * ligne - 1, column=0, sticky='w', padx=(0, 14), pady=2)
            tk.Label(bloc, text=etat, fg=couleur, bg=theme.FOND, font=(theme.POLICE, 10, 'bold')).grid(
                row=2 * ligne - 1, column=1, sticky='w', padx=(0, 14), pady=2)
            chemin = Path(entree['fichier'])
            existe = chemin.is_file()
            lien = tk.Label(bloc, text=chemin.name + ('' if existe else '  (introuvable)'),
                            fg=theme.ACCENT if existe else theme.TEXTE_DOUX, bg=theme.FOND,
                            font=(theme.POLICE, 11, 'underline' if existe else 'normal'), cursor='hand2' if existe else '',
                            wraplength=360, justify='left', anchor='w')
            lien.grid(row=2 * ligne - 1, column=2, sticky='w', pady=2)
            if existe:
                lien.bind('<Button-1>', lambda _e, c=chemin: self.ouvrir_fichier(c))
                dossier = tk.Label(bloc, text='📂 Afficher dans le dossier', fg=theme.ACCENT, bg=theme.FOND,
                                   font=(theme.POLICE, 10), cursor='hand2')
                dossier.grid(row=2 * ligne - 1, column=3, sticky='e', padx=(14, 0), pady=2)
                dossier.bind('<Button-1>', lambda _e, c=chemin: self.ouvrir_fichier(c, reveler=True))
            controle = entree.get('controle_declaration')
            if controle:
                tk.Label(bloc, text='→ déclaration (étape 9) : ' + declaration_licence.texte_controle(controle),
                         fg=theme.ERREUR if controle['manquantes'] else theme.OK, bg=theme.FOND,
                         font=(theme.POLICE, 10), wraplength=900, justify='left', anchor='w').grid(
                    row=2 * ligne, column=0, columnspan=4, sticky='w', pady=(0, 6))

    def traiter_licence(self, numero):
        if not self._peut_remplacer():
            return
        try:
            licence = licences_ouvertes.charger(numero)
        except (ValueError, OSError, sqlite3.Error) as exc:
            messagebox.showerror('Traitement licence', str(exc), parent=self)
            return
        for widget in self.traitement.winfo_children():
            widget.destroy()
        haut = ttk.Frame(self.traitement)
        haut.pack(fill='x', pady=(0, 16))
        theme.bouton(haut, '← Licences ouvertes', self.voir_licences).pack(side='left')
        try:
            dossier_dec = espace_travail.dossier_dec(licence['numero_dec'])
        except (OSError, ValueError):
            dossier_dec = None
        if dossier_dec is not None:
            theme.bouton(haut, f'Ouvrir le dossier {dossier_dec.name}', lambda d=dossier_dec: self.ouvrir_dossier(d)).pack(side='right')
        theme.bouton(haut, '🖨  Imprimer les documents…', lambda: self.imprimer_documents(numero),
                     principal=True).pack(side='right', padx=(0, 10))
        theme.bouton(haut, 'Détails dossier (PDF)', lambda: self.imprimer_dossier(numero)).pack(side='right', padx=(0, 10))
        theme.entete_page(self.traitement, 'Traitement licence', numero)
        repartition_resume = licence.get('repartition') or {}
        morceaux = [licence.get('soussigne', {}).get('nom') or 'Soussigné non renseigné',
                    f"DEC {licence.get('numero_dec', '')}",
                    f"FOB {synthese_licence.nombre(synthese_licence.decimal(licence.get('montant_fob')), 2)} USD"]
        if repartition_resume.get('parts'):
            morceaux += [f"{len(repartition_resume['parts'])} part(s)",
                         f"{synthese_licence.nombre(repartition_resume.get('poids_total_kg'))} kg"]
        ttk.Label(self.traitement, text='  ·  '.join(morceaux), style='Section.TLabel',
                  wraplength=900).pack(anchor='w', pady=(0, 14))
        from asydec.declarations.numeros_logiques import parts_hors_regle
        hors_regle = parts_hors_regle(licence)
        if hors_regle:
            bandeau = tk.Frame(self.traitement, bg=theme.FOND_ERREUR, padx=12, pady=8)
            bandeau.pack(fill='x', pady=(0, 12))
            details = '\n'.join(f"• Part {n} : " + ' · '.join(m.split(' :')[0] for m in messages)
                                for n, messages in hors_regle[:5])
            if len(hors_regle) > 5:
                details += f"\n• … et {len(hors_regle) - 5} autre(s) part(s)"
            tk.Label(bandeau, text='⚠ Règle non respectée : liquidation, Q et manifeste doivent toujours être '
                                   f'inférieurs au E ({len(hors_regle)} part(s)).\n' + details,
                     fg=theme.ERREUR, bg=theme.FOND_ERREUR, font=(theme.POLICE, 11), justify='left',
                     anchor='w').pack(side='left', fill='x', expand=True)
            theme.bouton(bandeau, 'Corriger à l’étape 3', lambda: self.informations_declaration(numero),
                         principal=True).pack(side='right')

        repartition = licence.get('repartition')
        informations = licence.get('informations_declaration')
        a_jour = mise_a_jour_repartitions.est_a_jour(licence)
        if repartition:
            nb = len(repartition['parts'])
            poids_parts = sorted({p['poids_kg'] for p in repartition['parts']})
            texte_poids = (f"{poids_parts[0]:,} kg par part" if len(poids_parts) == 1
                           else f"{poids_parts[0]:,} à {poids_parts[-1]:,} kg par part")
            texte_repartition = (f"{nb} part(s) · {texte_poids} · "
                                 f"{repartition['poids_total_kg']:,} kg au total".replace(',', ' '))
            if repartition.get('nombre_parts_choisi') or not repartition.get('plafond_actif', True):
                texte_repartition += (' · ' + ('nombre de parts choisi' if repartition.get('nombre_parts_choisi') else 'nombre automatique')
                                      + ('' if repartition.get('plafond_actif', True) else ' · sans plafond de 120 000 USD'))
        else:
            texte_repartition = ('Divisez le FOB et les quantités en parts de 120 000 USD maximum, '
                                 'puis confirmez un poids égal de 22 000 à 24 000 kg par part.')
        if informations:
            texte_infos = ' · '.join(f'{titre} : {informations[cle]}' for cle, titre in
                                     (('numero_e', 'E'), ('numero_liquidation', 'L'), ('numero_quittance', 'Q'),
                                      ('manifeste', 'Manifeste')) if informations.get(cle)) or 'Informations enregistrées.'
            if (licence.get('taux_change') or {}).get('valeur'):
                texte_infos += f" · Taux déclaration : {licence['taux_change']['valeur']}"
        else:
            texte_infos = 'Numéros E, liquidation, Q, manifeste, références, bureau douanier et transport.'
        factures = licence.get('factures_parts')
        facture_ok = facture_licence.est_a_jour(licence)
        reference = licence.get('numero_facture')
        if facture_ok:
            liste = factures['parts']
            origine = (('présentation KINSHOP' if facture_kinshop.disponible(licence) else 'facture simple AsyDec') if factures.get('methode') == 'simple'
                       else 'modèle ' + Path(factures['modele']).name)
            texte_facture = (f"{len(liste)} facture(s) et {len(liste)} packing list(s) séparées du {factures['date_facture']} : "
                             f"{liste[0]['numero']} à {liste[-1]['numero']}, plus la facture globale "
                             f"{factures['globale']['numero']} (FOB {format_nombre(float(factures['globale']['fob']), 2)} USD) "
                             f"· {origine} · dossier 4 - FACTURES.")
        elif factures:
            texte_facture = ('Les répartitions ou le numéro de facture ont changé depuis la génération, '
                             'ou la facture globale manque : produisez à nouveau les factures (les fichiers seront remplacés).')
        else:
            texte_facture = (f"Une facture et une packing list par part, numérotées "
                             f"{(reference or 'N° facture de la licence')}-1, -2…, chacune dans son propre fichier Word, "
                             f"plus une facture et une packing list globales ({reference or 'N° facture de la licence'}) "
                             'qui totalisent le FOB, les quantités et les poids de toutes les parts par article.\n\n'
                             '• Modèle fourni : choisissez un Word ; sa structure, ses polices et ses logos sont conservés, '
                             'seuls les articles, quantités, prix, poids, totaux, numéro, date, plaque et manifeste sont mis à jour.\n'
                             '• Facture simple AsyDec : sans modèle, AsyDec crée un Word sobre avec les données importantes '
                             '(vendeur, acheteur, licence, DEC, plaque, conteneur, scellé, manifeste, articles, poids et totaux).\n\n'
                             'Dans les deux cas, le poids de la part est réparti entre les articles selon les quantités.')
        if declaration_licence.est_a_jour(licence):
            texte_declaration = (f"{len(licence['declarations']['fichiers'])} déclaration(s) Word, une par part, "
                                 'remplie(s) sur le modèle fourni sans en changer la forme · dossier 6 - DECLARATIONS.')
        elif licence.get('declarations'):
            texte_declaration = ('Les XML ou le taux de change de l’étape 3 ont changé depuis la génération des '
                                 'déclarations : générez-les à nouveau (les fichiers seront remplacés).')
        else:
            texte_declaration = ('Une déclaration (DCU) Word par part, remplie sur votre modèle sans changer sa forme : '
                                 'cases, polices et image de fond conservées. E, L, Q, leurs dates, manifeste et plaques '
                                 'viennent toujours de l’étape 3 ; le reste du XML SYDONIA importé pour la part à '
                                 'l’étape 8 (une case vide y est complétée depuis AsyDec et signalée).')
        recuperation = licence.get('recuperation_simulation')
        if recuperation:
            texte_recuperation = recuperation_simulation.conclusion(recuperation['resume'])
        elif licence.get('xml_genere'):
            texte_recuperation = ('Importez le ou les XML récupérés de SYDONIA (plusieurs à la fois possible) : '
                                  'chacun est comparé au XML attendu de sa part.\n'
                                  'Sans accès à SYDONIA : « Générer les XML de vérification » produit, pour les parts '
                                  'sans XML importé, un XML recalculé au taux de l’étape 3 (marqué vérification AsyDec).')
        else:
            texte_recuperation = 'Disponible après la génération XML (étape 7).'
        statut_final = finalisation.statut(licence)
        fiche_finale = licence.get('finalisation') or {}
        if statut_final == finalisation.EN_ATTENTE_ARCHIVAGE:
            texte_finalisation = (f"Dossier finalisé le {self._date_locale(fiche_finale.get('finalise_le'))} : "
                                  'en attente d’archivage. Il apparaît avec ce statut dans la liste des licences. '
                                  'Pour corriger un document, annulez la finalisation, régénérez-le puis finalisez à nouveau.'
                                  + (f"\nObservation : {fiche_finale['observation']}" if fiche_finale.get('observation') else ''))
        elif statut_final == finalisation.A_REFAIRE:
            texte_finalisation = ('Des documents ont été régénérés depuis la finalisation : vérifiez-les, '
                                  'puis finalisez à nouveau le dossier.')
        else:
            texte_finalisation = ('Dernière étape : vérifie que tous les documents sont produits et à jour, '
                                  'puis met le dossier « en attente d’archivage ». Rien n’est déplacé ni effacé.')
        etapes = (
            ('Licence', 'Informations de la licence', True, True,
             'Coordonnées, prix et articles récupérés sur la licence.',
             (('Consulter la licence', lambda: self.rouvrir(numero)),
              ('📂 Dossier licence', lambda: self.ouvrir_rangement(numero, 'licence')))),
            ('Répartition', 'Répartition et poids', bool(repartition), True, texte_repartition,
             (('Répartition', lambda: self.repartir_licence(numero)),
              ('Voir les répartitions', lambda: self.voir_repartitions(numero)),
              ('📂 Dossier DEC', lambda: self.ouvrir_rangement(numero)))),
            ('Informations', 'Informations déclaration', bool(informations), bool(repartition), texte_infos,
             (('Informations déclaration', lambda: self.informations_declaration(numero)),
              ('📂 Dossier DEC', lambda: self.ouvrir_rangement(numero)))),
            ('Mise à jour', 'Mise à jour des répartitions', a_jour, bool(repartition and informations),
             'Applique les informations saisies à toutes les parts et vérifie E, liquidation et Q.',
             (('Mettre à jour les répartitions', lambda: self.mettre_a_jour_repartitions(numero)),
              ('📂 Dossier DEC', lambda: self.ouvrir_rangement(numero)))),
            ('Factures', 'Factures et packing lists', facture_ok, a_jour, texte_facture,
             (('Choisir le modèle de facture…', lambda: self.generer_facture(numero)),
              ('Depuis mes modèles enregistrés…', lambda: self.choisir_facture_bibliotheque(numero)),
              ('Facture KINSHOP' if facture_kinshop.disponible(licence) else 'Facture simple AsyDec', lambda: self.generer_facture(numero, simple=True)),
              ('📂 Dossier factures', lambda: self.ouvrir_rangement(numero, 'factures')))),
            ('CVI + BL', 'Remplissage CVI et BL', cvi.est_a_jour(licence), a_jour and facture_ok,
             'Un seul fichier Word : le CVI puis 1 à 3 BL. Un BL réunit 10 conteneurs au plus : 1 BL jusqu’à 10 répartitions, 2 BL jusqu’à 20, 3 BL jusqu’à 30 ; chacun a son numéro, ses conteneurs, scellés, poids et colis. Les polices et positions du modèle sont conservées. '
             'Les numéros E, L et Q proviennent de la première répartition validée. Sur le CVI : DIB = numéro complet de licence ; '
             'FOB, CIF, quantité, poids et n° de facture = totaux de tout le dossier (facture globale), comme le BL.',
             (('Remplir CVI et BL…', lambda: self.generer_cvi(numero)),
              ('📂 Dossier CVI et BL', lambda: self.ouvrir_rangement(numero, 'cvi')))),
            ('XML', 'Génération XML', bool(licence.get('xml_genere')), a_jour and facture_ok,
             'Génère un XML par montant de part différent : les parts au même FOB et aux mêmes quantités '
             'n’ont qu’un XML (ex. « parts 1-2 »). Chaque XML reprend le FOB et les quantités de sa part, avec E, L, Q, '
             'plaques et manifeste de la première part du groupe. Avec une déclaration réelle de licence '
             '(dossier XML_LICENCES), le XML est complet : bureau, déclarant, banque, transport, documents joints, '
             'poids, colis, valeur, fret, assurance et taxes.',
             (('Générer XML…', lambda: self.generer_xml(numero)),
              ('📂 Dossier XML générés', lambda: self.ouvrir_rangement(numero, 'xml_generes')))),
            ('SYDONIA', 'Récupération simulation', bool(recuperation), bool(licence.get('xml_genere')), texte_recuperation,
             (('Importer les XML SYDONIA…', lambda: self.recuperer_simulation(numero)),
              ('Générer les XML de vérification (sans SYDONIA)', lambda: self.generer_verifications(numero)),
              ('Voir la comparaison', lambda: self.voir_comparaison(numero)),
              ('📂 Dossier XML SYDONIA', lambda: self.ouvrir_rangement(numero, 'xml_sydonia')))),
            ('Déclaration', 'Génération déclaration', declaration_licence.est_a_jour(licence), bool(recuperation),
             texte_declaration,
             (('Générer les déclarations', lambda: self.generer_declarations(numero)),
              ('📂 Dossier déclarations', lambda: self.ouvrir_rangement(numero, 'declarations')))),
            ('Finaliser', 'Finalisation du dossier', statut_final == finalisation.EN_ATTENTE_ARCHIVAGE,
             statut_final != finalisation.EN_COURS or finalisation.pret(licence), texte_finalisation,
             ((('Annuler la finalisation', lambda: self.annuler_finalisation(numero))
               if statut_final == finalisation.EN_ATTENTE_ARCHIVAGE
               else ('Finaliser le dossier', lambda: self.finaliser(numero))),
              ('Détails dossier (PDF)', lambda: self.imprimer_dossier(numero)),
              ('📂 Dossier DEC', lambda: self.ouvrir_rangement(numero)))),
        )
        etats = []
        for court, titre, fait, accessible, description, boutons in etapes:
            if fait and titre == 'Récupération simulation' and recuperation['resume'].get('controles_differents'):
                etats.append(('⚠', 'Écarts à vérifier', theme.ERREUR, theme.FOND_ERREUR, 'Erreur.TLabel'))
            elif titre == 'Finalisation du dossier' and statut_final == finalisation.A_REFAIRE:
                etats.append(('⚠', 'À refaire', theme.ERREUR, theme.FOND_ERREUR, 'Erreur.TLabel'))
            elif fait and titre == 'Finalisation du dossier':
                etats.append(('✓', 'En attente d’archivage', theme.OK, theme.FOND_OK, 'Ok.TLabel'))
            elif fait:
                etats.append(('✓', 'Terminée', theme.OK, theme.FOND_OK, 'Ok.TLabel'))
            elif accessible:
                etats.append(('●', 'À faire', theme.ALERTE, theme.FOND_ALERTE, 'Alerte.TLabel'))
            else:
                etats.append(('○', 'Bloquée', theme.TEXTE_DOUX, theme.FOND_LATERAL, 'Doux.TLabel'))

        # Frise : les 10 étapes dans l'ordre, cliquables ; l'étape affichée est encadrée.
        frise = tk.Frame(self.traitement, bg=theme.FOND)
        frise.pack(fill='x', pady=(0, 14))
        pastilles = []
        for i, ((court, *_), (icone, _, couleur, fond, _)) in enumerate(zip(etapes, etats)):
            if i:
                tk.Frame(frise, bg='#D1D5DB', height=2).pack(side='left', fill='x', expand=True, padx=4)
            pastille = tk.Label(frise, text=f'{icone}  {i + 1} · {court}', bg=fond, fg=couleur, cursor='hand2',
                                font=(theme.POLICE, 10, 'bold'), padx=6, pady=7,
                                highlightthickness=2, highlightbackground=fond)
            pastille.pack(side='left')
            pastilles.append(pastille)

        carnet = ttk.Notebook(self.traitement)
        carnet.pack(fill='both', expand=True)
        panneau = ttk.Frame(carnet, padding=20)
        page_synthese = ttk.Frame(carnet)
        carnet.add(panneau, text='Étape en cours')
        carnet.add(page_synthese, text='Synthèse de la licence')
        self._synthese_defilante(page_synthese, licence)

        def afficher(index):
            for j, pastille in enumerate(pastilles):
                fond = etats[j][3]
                pastille.configure(highlightbackground=theme.ACCENT if j == index else fond)
            for widget in panneau.winfo_children():
                widget.destroy()
            court, titre, fait, accessible, description, boutons = etapes[index]
            icone, statut, _, _, style = etats[index]
            entete = ttk.Frame(panneau)
            entete.pack(fill='x')
            ttk.Label(entete, text=f'{index + 1} · {titre}', style='Titre.TLabel').pack(side='left')
            ttk.Label(entete, text=f'{icone} {statut}', style=style).pack(side='left', padx=(14, 0))
            ttk.Label(panneau, text=description, style='SousTitre.TLabel', wraplength=820,
                      justify='left').pack(anchor='w', pady=(10, 18))
            if not accessible:
                ttk.Label(panneau, text='Terminez d’abord les étapes précédentes.', style='Doux.TLabel').pack(anchor='w', pady=(0, 12))
            if titre == 'Génération XML':
                self._liste_xml_generes(panneau, licence)
            elif titre == 'Récupération simulation':
                self._liste_xml_sydonia(panneau, licence)
            elif titre == 'Génération déclaration':
                self._liste_declarations(panneau, licence)
            elif titre == 'Finalisation du dossier':
                self._liste_controles(panneau, licence)
            actions = ttk.Frame(panneau)
            actions.pack(anchor='w')
            for j, (texte, commande) in enumerate(boutons):
                theme.bouton(actions, texte, commande, principal=accessible and j == 0,
                             # Ouvrir un dossier reste possible même quand l'étape est bloquée.
                             state='normal' if accessible or texte.startswith('📂') else 'disabled').pack(side='left', padx=(0, 10))
            navigation = ttk.Frame(panneau)
            navigation.pack(side='bottom', fill='x', pady=(20, 0))
            if index > 0:
                theme.bouton(navigation, f'← {index} · {etapes[index - 1][0]}', lambda: afficher(index - 1)).pack(side='left')
            if index < len(etapes) - 1:
                theme.bouton(navigation, f'{index + 2} · {etapes[index + 1][0]} →', lambda: afficher(index + 1)).pack(side='right')
            carnet.select(panneau)

        for i, pastille in enumerate(pastilles):
            pastille.bind('<Button-1>', lambda _e, i=i: afficher(i))
        # Étape affichée par défaut : la première à faire, sinon la dernière.
        a_faire = next((i for i, (_, _, fait, accessible, _, _) in enumerate(etapes) if accessible and not fait), None)
        afficher(a_faire if a_faire is not None else len(etapes) - 1)
        self.formulaire.pack_forget()
        self.liste.pack_forget()
        self.traitement.pack(fill='both', expand=True)
        self.modifie = False
        self.vue_active = 'traitement'

    def _synthese_defilante(self, parent, licence):
        defilement = ttk.Scrollbar(parent, orient='vertical')
        defilement.pack(side='right', fill='y')
        toile = tk.Canvas(parent, highlightthickness=0, bg=theme.FOND, yscrollcommand=defilement.set)
        toile.pack(side='left', fill='both', expand=True)
        defilement.configure(command=toile.yview)
        contenu = ttk.Frame(toile, padding=16)
        identifiant = toile.create_window((0, 0), window=contenu, anchor='nw')
        contenu.bind('<Configure>', lambda _: toile.configure(scrollregion=toile.bbox('all')))
        toile.bind('<Configure>', lambda e: toile.itemconfigure(identifiant, width=e.width))

        def molette(evenement):
            if toile.winfo_exists():
                toile.yview_scroll(-1 * (evenement.delta if abs(evenement.delta) < 20 else evenement.delta // 120), 'units')
        toile.bind('<Enter>', lambda _: toile.bind_all('<MouseWheel>', molette))
        toile.bind('<Leave>', lambda _: toile.unbind_all('<MouseWheel>'))
        synthese_licence.construire(contenu, licence).pack(fill='x')

    @staticmethod
    def _date_locale(iso):
        from datetime import datetime
        try:
            return datetime.fromisoformat(iso).astimezone().strftime('%d/%m/%Y à %H:%M')
        except (TypeError, ValueError):
            return '?'

    def _liste_controles(self, parent, licence):
        cadre = ttk.LabelFrame(parent, text='Contrôles avant archivage', padding=12)
        cadre.pack(fill='x', pady=(0, 16))
        for libelle, reussi, bloquant in finalisation.controles(licence):
            icone, style = ('✓', 'Ok.TLabel') if reussi else ('✗', 'Erreur.TLabel') if bloquant else ('⚠', 'Alerte.TLabel')
            ttk.Label(cadre, text=f'{icone}  {libelle}' + ('' if reussi or bloquant else ' (non bloquant)'),
                      style=style).pack(anchor='w', pady=1)

    def finaliser(self, numero):
        if self.app.session_verrouillee or self.import_en_cours:
            return
        try:
            licence = licences_ouvertes.charger(numero)
        except (ValueError, OSError, sqlite3.Error) as exc:
            messagebox.showerror('Finaliser le dossier', str(exc), parent=self)
            return
        manquants = finalisation.bloquants(licence)
        if manquants:
            messagebox.showwarning('Finaliser le dossier', 'Le dossier n’est pas complet :\n\n• '
                                   + '\n• '.join(manquants), parent=self)
            return
        avertissements = [l for l, reussi, bloquant in finalisation.controles(licence) if not reussi and not bloquant]
        if not messagebox.askyesno(
                'Finaliser le dossier', f'Finaliser le dossier {numero} et le mettre en attente d’archivage ?\n\n'
                + (''.join(f'⚠ {a}\n' for a in avertissements) + '\n' if avertissements else '')
                + 'Les documents restent en place ; vous pourrez annuler la finalisation si une correction est nécessaire.',
                parent=self):
            return
        try:
            licences_ouvertes.finaliser(numero)
        except (ValueError, OSError, sqlite3.Error) as exc:
            messagebox.showerror('Finaliser le dossier', str(exc), parent=self)
            return
        self.traiter_licence(numero)

    def annuler_finalisation(self, numero):
        if self.app.session_verrouillee or self.import_en_cours:
            return
        if not messagebox.askyesno('Annuler la finalisation',
                                   f'Remettre le dossier {numero} « en cours » ? Il ne sera plus en attente d’archivage.',
                                   icon='warning', parent=self):
            return
        try:
            licences_ouvertes.annuler_finalisation(numero)
        except (ValueError, OSError, sqlite3.Error) as exc:
            messagebox.showerror('Annuler la finalisation', str(exc), parent=self)
            return
        self.traiter_licence(numero)

    def repartir_licence(self, numero):
        if self.app.session_verrouillee or self.import_en_cours:
            return
        try:
            licence = licences_ouvertes.charger(numero)
        except (ValueError, OSError, sqlite3.Error) as exc:
            messagebox.showerror('Répartition', str(exc), parent=self)
            return
        FenetreRepartition(self, self.app, licence, lambda: self.traiter_licence(numero))

    def voir_repartitions(self, numero=None):
        if self.app.session_verrouillee or self.import_en_cours:
            return
        try:
            parts = licences_ouvertes.lister_repartitions(numero)
        except (ValueError, OSError, sqlite3.Error) as exc:
            messagebox.showerror('Répartitions réalisées', str(exc), parent=self)
            return
        ListeRepartitions(self, parts, numero)

    def informations_declaration(self, numero):
        if self.app.session_verrouillee or self.import_en_cours:
            return
        try:
            licence = licences_ouvertes.charger(numero)
        except (ValueError, OSError, sqlite3.Error) as exc:
            messagebox.showerror('Informations déclaration', str(exc), parent=self)
            return
        if not licence.get('repartition'):
            messagebox.showinfo('Répartition à valider', 'Validez d’abord la répartition et les poids.', parent=self)
            return
        InformationsDeclaration(self, self.app, licence, lambda: self.traiter_licence(numero))

    def mettre_a_jour_repartitions(self, numero):
        if self.app.session_verrouillee or self.import_en_cours:
            return
        try:
            licences_ouvertes.mettre_a_jour_repartitions(numero)
        except (ValueError, OSError, sqlite3.Error) as exc:
            messagebox.showerror('Mise à jour impossible', str(exc), parent=self)
            return
        self.traiter_licence(numero)
        self.voir_repartitions(numero)
