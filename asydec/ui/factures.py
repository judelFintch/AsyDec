"""Chargement des modèles Word, émission et téléchargement des factures archivées."""
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

from asydec.declarations import factures

AIDE = ('Les factures avec tableau commercial et liste de colisage reconnues sont préparées automatiquement.\n\nPour les autres modèles Word, remplacez les valeurs variables par ces champs :\n\n'
        '{{NUMERO_FACTURE}} : numéro unique automatique\n'
        '{{POIDS}} : poids total en kg\n{{COLIS}} : nombre total de colis\n{{FOB}} : FOB total en USD\n\n'
        'Plaque obligatoire : {{PLAQUE}} (reprise du modèle généré).\n\nFacultatifs : {{NUMERO_MANIFESTE}}, {{DATE_FACTURE}}, {{IMPORTATEUR}}, {{MODELE_ID}}.\n\n'
        'Placez les unités kg et USD à côté des champs. Les champs peuvent se trouver dans les tableaux, '
        'en-têtes et pieds de page. Le modèle original reste intact.')


def nom_fichier(modele_id, defaut):
    """Nom proposé pour le Word : la plaque du camion (« T867DNM-T569DNE.docx »), sinon defaut."""
    try:
        from asydec.declarations import modeles_generes
        plaque = modeles_generes.detail(modele_id).get('plaque')
    except (OSError, ValueError):
        plaque = None
    # Aucune plaque ne peut introduire un chemin : « / » et caractères interdits deviennent « - ».
    texte = re.sub(r'\s*[<>:"/\\|?*\x00-\x1f\x7f]+\s*', '-', str(plaque or ''))
    texte = ' '.join(texte.split()).strip(' .-')[:120]
    return f'{texte or defaut}.docx'


def destinataire(gabarit):
    """Destinataire (Consignee) repéré dans le Word : l'élément qui distingue les modèles entre eux."""
    return gabarit.get('destinataire') or 'Destinataire non repéré'


def retirer(parent, gabarits):
    """Demande confirmation puis retire ces modèles de facture de la bibliothèque. Renvoie True si fait."""
    if not gabarits:
        messagebox.showinfo('Aucun modèle', 'Sélectionnez le ou les modèles de facture à retirer.', parent=parent)
        return False
    try:
        emises = factures.factures_emises([g['id'] for g in gabarits])
    except Exception as exc:
        messagebox.showerror('Retrait impossible', str(exc), parent=parent)
        return False
    lignes = [f"• {g['nom']} (n° {g['id']})" + (f" — {emises[g['id']]} facture(s) déjà émise(s)" if emises[g['id']] else '')
              for g in gabarits]
    if not messagebox.askyesno('Retirer de la bibliothèque', f'Retirer {len(gabarits)} modèle(s) de facture ?\n\n'
            + '\n'.join(lignes) + '\n\nIls ne seront plus proposés. Les factures déjà émises restent archivées et '
            'téléchargeables. Pour réutiliser un modèle, rechargez simplement son fichier Word.', parent=parent):
        return False
    try:
        factures.retirer_modeles([g['id'] for g in gabarits])
    except Exception as exc:
        messagebox.showerror('Retrait impossible', str(exc), parent=parent)
        return False
    return True


def ouvrir(parent, app, modele_id):
    if app.session_verrouillee:
        return
    fenetre = tk.Toplevel(parent)
    fenetre.title(f'Factures du modèle n° {modele_id}')
    fenetre.geometry('720x540')
    cadre = ttk.Frame(fenetre, padding=16)
    cadre.pack(fill='both', expand=True)
    ttk.Label(cadre, text='Modèle de facture Word', font=('', 14, 'bold')).pack(anchor='w')
    ttk.Label(cadre, text='Le poids, les colis et le FOB seront repris du modèle généré sélectionné.',
              wraplength=660).pack(anchor='w', pady=8)
    choix = ttk.Combobox(cadre, state='readonly', width=65)
    choix.pack(fill='x', pady=8)
    modeles = []
    archives = []
    statut = tk.StringVar()
    from asydec.systeme import conversion_pdf
    # Le PDF est fait par Word lui-même (mise en page identique) ; décochée d'office si Word est absent.
    avec_pdf = tk.BooleanVar(value=conversion_pdf.disponible())
    contexte = tk.StringVar()
    ttk.Label(cadre, textvariable=contexte, wraplength=660).pack(fill='x', pady=4)
    recommandation = tk.StringVar()
    ttk.Label(cadre, textvariable=recommandation, wraplength=660).pack(fill='x', pady=4)

    def actualiser():
        nonlocal modeles, archives
        selection_id = modeles[choix.current()]['id'] if 0 <= choix.current() < len(modeles) else None
        from asydec.declarations import modeles_generes
        d = modeles_generes.detail(modele_id)
        contexte.set(f"Plaque du modèle : {d['plaque']}" if d.get('plaque') else
                     'Plaque obligatoire : renseignez-la et enregistrez-la dans Modèles générés avant de créer la facture.')
        modeles = factures.classer_gabarits(factures.lister_modeles(), d)
        choix['values'] = [f"{'Conseillé : ' if m['propose'] else ''}{destinataire(m)} — {m['nom']} (n° {m['id']})"
                           for m in modeles]
        if selection_id is not None:
            choix.set('')
            for i, g in enumerate(modeles):
                if g['id'] == selection_id:
                    choix.current(i)
                    break
        if modeles and choix.current() < 0:
            choix.current(0)
        expliquer()
        archives = factures.lister_factures(modele_id)
        liste.delete(0, 'end')
        for f in archives:
            liste.insert('end', f"{f['numero']} — manifeste {f['manifeste'] or 'ancien'} — {f['date'][:10]}")

    def expliquer():
        if 0 <= choix.current() < len(modeles):
            recommandation.set(modeles[choix.current()]['raison'])
        else:
            recommandation.set('Chargez un modèle Word ou ajoutez-le dans la bibliothèque Modèles de facture.')

    choix.bind('<<ComboboxSelected>>', lambda _e: expliquer())

    def importer():
        if app.session_verrouillee:
            return
        fichier = filedialog.askopenfilename(parent=fenetre, title='Charger votre modèle de facture',
                                             filetypes=[('Document Word', '*.docx')])
        if not fichier:
            return
        try:
            identifiant = factures.importer(fichier)
            actualiser()
            for i, g in enumerate(modeles):
                if g['id'] == identifiant:
                    choix.current(i)
                    break
            expliquer()
            statut.set('Modèle chargé et conservé dans AsyDec.')
        except Exception as exc:
            messagebox.showerror('Modèle non chargé', str(exc), parent=fenetre)

    def dossier_factures():
        """Options du dialogue : 6 - FACTURES de l'importateur du modèle, dans le dossier de travail."""
        try:
            from asydec.declarations import generer, modeles_generes
            importateur = modeles_generes.detail(modele_id).get('importateur')
            return {'initialdir': generer.dossier_rangement(importateur, 'factures', getattr(app, 'table_imp', None))} \
                if importateur else {}
        except (OSError, ValueError):
            return {}

    def enregistrer(facture, chemin=None):
        chemin = chemin or filedialog.asksaveasfilename(parent=fenetre, title='Enregistrer la facture Word',
            initialfile=nom_fichier(modele_id, facture['numero']), defaultextension='.docx',
            filetypes=[('Document Word', '*.docx')], confirmoverwrite=True, **dossier_factures())
        if chemin:
            try:
                Path(chemin).write_bytes(facture['contenu'])
                statut.set(f"Facture enregistrée : {chemin}")
            except OSError as exc:
                messagebox.showerror('Enregistrement impossible',
                    f'{exc}\nLa facture reste disponible dans les archives ci-dessous.', parent=fenetre)
                return
            if avec_pdf.get():
                # Deuxième temps : la même facture en PDF, convertie par Word, à côté du Word.
                statut.set('Création du PDF par Microsoft Word…')
                fenetre.config(cursor='watch')
                fenetre.update_idletasks()
                try:
                    pdf = conversion_pdf.docx_vers_pdf(chemin)
                    statut.set(f"Facture enregistrée : {chemin}\nPDF : {pdf}")
                except conversion_pdf.ConversionImpossible as exc:
                    statut.set(f"Facture enregistrée : {chemin} (sans PDF)")
                    messagebox.showwarning('PDF non créé', f'{exc}\n\nLa facture Word est bien enregistrée.', parent=fenetre)
                finally:
                    fenetre.config(cursor='')

    def generer():
        if app.session_verrouillee:
            return
        if choix.current() < 0:
            messagebox.showinfo('Modèle nécessaire', 'Chargez d’abord votre modèle Word.', parent=fenetre)
            return
        try:
            from asydec.declarations import modeles_generes
            d = modeles_generes.detail(modele_id)
            if not (d.get('plaque') or '').strip():
                raise ValueError('Plaque obligatoire : renseignez et enregistrez la plaque dans Modèles générés, puis revenez créer la facture.')
            gabarit = modeles[choix.current()]
            if not gabarit['pret']:
                configurer(fenetre, gabarit['id'], actualiser)
                return
            if not gabarit['plaque_prevue']:
                raise ValueError('Ajoutez {{PLAQUE}} à son emplacement dans ce modèle Word, puis rechargez-le.')
            confirme = False
            if gabarit['articles']:
                from asydec.declarations import modeles_generes
                d = modeles_generes.detail(modele_id)
                designations = d['resultat'].get('info', {}).get('designations', [])
                lignes = [f"{i}. Facture : {nom}\n    Proposition : {designations[i-1] if i <= len(designations) else 'non renseignée'}"
                          for i, nom in enumerate(gabarit['articles'], 1)]
                confirme = messagebox.askyesno('Vérifier les articles',
                    'Les articles doivent correspondre dans le même ordre.\n\n' + '\n'.join(lignes) +
                    '\n\nConfirmez-vous cette correspondance ? Les libellés et adresses du Word seront conservés.', parent=fenetre)
                if not confirme:
                    return
            chemin = filedialog.asksaveasfilename(parent=fenetre, title='Enregistrer la facture Word',
                initialfile=nom_fichier(modele_id, f'Facture-modele-{modele_id}'), defaultextension='.docx',
                filetypes=[('Document Word', '*.docx')], confirmoverwrite=True, **dossier_factures())
            if not chemin or app.session_verrouillee:
                return
            facture = factures.generer(modele_id, gabarit['id'], app.utilisateur,
                                       correspondance_confirmee=confirme)
            statut.set(f"Facture {facture['numero']} — manifeste {facture['manifeste'] or 'ancien'}")
            actualiser()
            enregistrer(facture, chemin)
        except Exception as exc:
            messagebox.showerror('Facture non générée', str(exc), parent=fenetre)

    def telecharger():
        if app.session_verrouillee or not liste.curselection():
            return
        try:
            enregistrer(factures.lire(archives[liste.curselection()[0]]['id']))
        except Exception as exc:
            messagebox.showerror('Facture indisponible', str(exc), parent=fenetre)

    boutons = ttk.Frame(cadre)
    boutons.pack(fill='x', pady=8)
    ttk.Button(boutons, text='Charger un modèle Word…', command=importer).pack(side='left')
    ttk.Button(boutons, text='Bibliothèque…', command=lambda: (fenetre.destroy(), app.montrer('factures'))).pack(side='left', padx=4)

    def retirer_choisi():
        if app.session_verrouillee or not 0 <= choix.current() < len(modeles):
            return
        if retirer(fenetre, [modeles[choix.current()]]):
            choix.set('')
            statut.set('Modèle de facture retiré de la bibliothèque.')
            actualiser()

    ttk.Button(boutons, text='Retirer ce modèle…', command=retirer_choisi).pack(side='left', padx=4)
    ttk.Button(boutons, text='Préparer mon modèle…', command=lambda: messagebox.showinfo(
        'Champs de la facture', AIDE, parent=fenetre)).pack(side='left', padx=8)
    ttk.Button(cadre, text='Créer ou télécharger la facture du modèle…', command=generer).pack(anchor='w', pady=8)
    ttk.Checkbutton(cadre, variable=avec_pdf,
                    text='Créer aussi le PDF (même mise en page, converti par Microsoft Word)'
                    if conversion_pdf.disponible() else 'Créer aussi le PDF (Microsoft Word absent sur ce poste)',
                    state='normal' if conversion_pdf.disponible() else 'disabled').pack(anchor='w')
    ttk.Label(cadre, text='Factures archivées pour ce modèle').pack(anchor='w', pady=(12, 4))
    liste = tk.Listbox(cadre, height=8, exportselection=False)
    liste.pack(fill='both', expand=True)
    ttk.Button(cadre, text='Télécharger la facture sélectionnée…', command=telecharger).pack(anchor='w', pady=8)
    ttk.Label(cadre, textvariable=statut, wraplength=660).pack(anchor='w')
    try:
        actualiser()
    except Exception as exc:
        messagebox.showerror('Factures indisponibles', str(exc), parent=fenetre)
        fenetre.destroy()


class PageBibliothequeFactures(ttk.Frame):
    """Bibliothèque commune : importer et examiner sans créer de facture."""
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        from asydec.ui import theme
        theme.entete_page(self, 'Modèles de facture Word',
            'Chargez vos modèles ici, avant de générer un dossier. La facture sera créée sur demande depuis Modèles générés.')
        barre = ttk.Frame(self)
        barre.pack(fill='x', pady=10)
        ttk.Button(barre, text='Ajouter un modèle Word…', command=self.importer).pack(side='left')
        ttk.Button(barre, text='Actualiser', command=self.afficher).pack(side='left', padx=8)
        ttk.Button(barre, text='Configurer les champs…', command=self.configurer).pack(side='left')
        ttk.Button(barre, text='Retirer de la bibliothèque…', command=self.retirer).pack(side='left', padx=8)
        ttk.Label(barre, text='⌘-clic ou ⇧-clic : plusieurs modèles').pack(side='left', padx=8)
        self.liste = tk.Listbox(self, height=12, exportselection=False, selectmode='extended')
        self.liste.pack(fill='both', expand=True)
        self.liste.bind('<<ListboxSelect>>', lambda _e: self.analyser())
        self.resume = tk.StringVar(value='Sélectionnez un modèle pour voir son analyse.')
        ttk.Label(self, textvariable=self.resume, justify='left', wraplength=850).pack(fill='x', pady=12)
        self.modeles = []

    def afficher(self):
        if self.app.session_verrouillee:
            return
        try:
            self.modeles = factures.lister_modeles()
            self.liste.delete(0, 'end')
            for g in self.modeles:
                self.liste.insert('end', f"{destinataire(g)}   ·   {g['nom']} — "
                                  f"{'prêt' if g['pret'] else 'champs à configurer'} — {len(g['articles'])} article(s)")
            self.resume.set('Sélectionnez un modèle pour voir son analyse.')
        except Exception as exc:
            messagebox.showerror('Bibliothèque indisponible', str(exc), parent=self)

    def configurer(self):
        if not self.app.session_verrouillee and self.liste.curselection():
            configurer(self, self.modeles[self.liste.curselection()[0]]['id'], self.afficher)

    def retirer(self):
        if self.app.session_verrouillee:
            return
        choisis = [self.modeles[i] for i in self.liste.curselection()]
        if retirer(self, choisis):
            self.afficher()
            self.resume.set(f'{len(choisis)} modèle(s) retiré(s) de la bibliothèque. Les factures déjà émises restent archivées.')

    def analyser(self):
        if not self.liste.curselection():
            return
        if len(self.liste.curselection()) > 1:
            self.resume.set(f'{len(self.liste.curselection())} modèles sélectionnés.')
            return
        g = self.modeles[self.liste.curselection()[0]]
        self.resume.set(f"Destinataire : {g['destinataire'] or 'non repéré'}\n"
            f"Fournisseur : {g['fournisseur'] or 'non repéré'}\n"
            "Prix unitaires : ratio de chaque article (FOB ÷ poids en kg)\n"
            f"Plaque : {'zone prête au remplissage automatique' if g['plaque_prevue'] else 'zone non reconnue ; ajoutez {{PLAQUE}} dans le Word'}\n"
            'Articles : ' + (' ; '.join(g['articles']) or 'non repérés, à vérifier manuellement') +
            '\nChamps : ' + ', '.join(g['champs']))

    def importer(self):
        if self.app.session_verrouillee:
            return
        chemin = filedialog.askopenfilename(parent=self, title='Ajouter un modèle de facture Word',
                                            filetypes=[('Document Word', '*.docx')])
        if not chemin:
            return
        try:
            identifiant = factures.importer(chemin)
            self.afficher()
            for i, g in enumerate(self.modeles):
                if g['id'] == identifiant:
                    self.liste.selection_set(i)
                    self.liste.see(i)
                    self.analyser()
                    break
        except Exception as exc:
            messagebox.showerror('Modèle non chargé', str(exc), parent=self)


def configurer(parent, gabarit_id, apres=None):
    try:
        disponibles = factures.zones_disponibles(gabarit_id)
        gabarit = next(g for g in factures.lister_modeles() if g['id'] == gabarit_id)
    except Exception as exc:
        messagebox.showerror('Configuration impossible', str(exc), parent=parent)
        return
    fen = tk.Toplevel(parent)
    fen.title('Associer les champs du Word')
    fen.geometry('920x650')
    cadre = ttk.Frame(fen, padding=16)
    cadre.pack(fill='both', expand=True)
    ttk.Label(cadre, text='Sélectionnez une zone, indiquez sa valeur actuelle puis le champ qui la remplacera.', wraplength=850).pack(anchor='w')
    ttk.Label(cadre, text='Obligatoires : NUMERO_FACTURE, PLAQUE, POIDS, COLIS, FOB. Associez aussi chaque valeur des articles et ses répétitions.', wraplength=850).pack(anchor='w', pady=8)
    liste = tk.Listbox(cadre, height=12, exportselection=False)
    liste.pack(fill='both', expand=True)
    for zone in disponibles:
        liste.insert('end', f"{zone['partie']} · {zone['paragraphe']} : {zone['texte']}")
    valeur = tk.StringVar()
    ttk.Label(cadre, text='Valeur exacte à remplacer dans cette zone (gardez les unités et les libellés)').pack(anchor='w', pady=(8,0))
    ttk.Entry(cadre, textvariable=valeur).pack(fill='x')
    champs = list(factures.CHAMPS)
    for i in range(1,len(gabarit['articles'])+1):
        champs += [f'{c}_{i}' for c in ('COLIS','POIDS','FOB','PRIX_UNITAIRE')]
    choix = ttk.Combobox(cadre, state='readonly', values=champs)
    choix.set('NUMERO_FACTURE')
    choix.pack(fill='x', pady=8)
    zones = []
    selections = tk.Listbox(cadre, height=5)
    selections.pack(fill='x')

    def selectionner(_e):
        if liste.curselection():
            valeur.set(disponibles[liste.curselection()[0]]['texte'])

    def ajouter():
        if not liste.curselection():
            return
        zone = disponibles[liste.curselection()[0]]
        if not valeur.get() or zone['texte'].count(valeur.get()) != 1:
            messagebox.showinfo('Valeur à préciser', 'Cette valeur doit apparaître exactement une fois dans la zone sélectionnée.', parent=fen)
            return
        zones.append(dict(zone, champ=choix.get(), valeur=valeur.get()))
        selections.insert('end', f"{choix.get()} ← {valeur.get()}")

    def retirer():
        if selections.curselection():
            i = selections.curselection()[0]
            zones.pop(i)
            selections.delete(i)

    def sauver():
        try:
            factures.configurer_zones(gabarit_id,zones)
            if apres:
                apres()
            fen.destroy()
        except Exception as exc:
            messagebox.showerror('Configuration non enregistrée', str(exc), parent=fen)

    liste.bind('<<ListboxSelect>>',selectionner)
    barre = ttk.Frame(cadre)
    barre.pack(fill='x', pady=10)
    ttk.Button(barre,text='Associer cette valeur',command=ajouter).pack(side='left')
    ttk.Button(barre,text='Retirer l’association',command=retirer).pack(side='left',padx=8)
    ttk.Button(barre,text='Enregistrer les associations',command=sauver).pack(side='right')
