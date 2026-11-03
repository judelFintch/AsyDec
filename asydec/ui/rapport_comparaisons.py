"""Rapport des comparaisons : toutes les comparaisons « XML généré / XML comparé » et leur analyse."""
import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from asydec.declarations import detection_reelles
from asydec.declarations import rapport_comparaisons as service
from asydec.formats import date_locale, nombre
from asydec.systeme.journal import erreur_ignoree
from asydec.ui import theme
from asydec.systeme import espace_travail

TOUS = 'Tous les diagnostics'
COULEURS = {service.CALCUL: theme.ERREUR, service.TAUX: theme.ALERTE, service.IDENTIQUE: theme.OK,
            service.REPARTITION: theme.ACCENT, service.AUTRE: theme.TEXTE_DOUX, service.NON_VERIFIABLE: theme.TEXTE_DOUX}


def _pct(valeur, decimales=2):
    return '—' if valeur is None else ('+' if valeur > 0 else '') + nombre(valeur, decimales) + ' %'


def _cdf(valeur):
    return '—' if valeur is None else ('+' if valeur > 0 else '') + nombre(valeur)


class PageRapportComparaisons(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.entrees, self.analyse, self.par_iid = [], None, {}
        theme.entete_page(self, 'Rapport des comparaisons',
            'Toutes les comparaisons entre un XML généré et un XML comparé, analysées ensemble. '
            'Écart = XML comparé − XML généré. « Hors taux » : écart restant une fois l’effet du taux de change retiré.')
        barre = ttk.Frame(self)
        barre.pack(fill='x', pady=(0, 8))
        self.filtre = ttk.Combobox(barre, state='readonly', width=26, values=[TOUS] + list(service.DIAGNOSTICS))
        self.filtre.set(TOUS)
        self.filtre.pack(side='left', padx=(0, 4))
        self.filtre.bind('<<ComboboxSelected>>', lambda e: self.remplir_comparaisons())
        self.filtre_importateur = ttk.Combobox(barre, state='readonly', width=30, values=['Tous les importateurs'])
        self.filtre_importateur.set('Tous les importateurs')
        self.filtre_importateur.pack(side='left', padx=4)
        self.filtre_importateur.bind('<<ComboboxSelected>>', lambda e: self.recalculer())
        theme.bouton(barre, 'Actualiser', self.afficher).pack(side='left', padx=4)
        self.ouvrir_bouton = theme.bouton(barre, 'Ouvrir la comparaison…', self.ouvrir, state='disabled')
        self.ouvrir_bouton.pack(side='left', padx=4)
        theme.bouton(barre, 'Exporter Excel…', self.exporter).pack(side='right')
        self.detection_bouton = theme.bouton(barre, 'Déclarations réelles détectées…', self.examiner_detection,
                                             state='disabled')
        self.detection_bouton.pack(side='right', padx=8)
        self.candidats = []
        self.bandeau = theme.Message(self)
        self.bandeau.pack(fill='x', pady=(0, 8))

        cartes = ttk.Frame(self)
        cartes.pack(fill='x')
        self.cartes = {}
        for k, (cle, libelle) in enumerate((('n', 'Comparaisons'), ('calcul', 'Écarts de calcul'),
                                            ('hors_taux', 'Écart moyen hors taux'), ('moyen', 'Écart moyen brut'))):
            cartes.columnconfigure(k, weight=1, uniform='cartes')
            carte = theme.Carte(cartes, libelle, detail=True)
            carte.grid(row=0, column=k, sticky='nsew', padx=(0 if k == 0 else 8, 0))
            self.cartes[cle] = carte

        ttk.Label(self, text='Ce qu’il faut retenir', style='Section.TLabel').pack(anchor='w', pady=(10, 2))
        self.constats = tk.Text(self, height=8, wrap='word', font=(theme.POLICE, 12), relief='flat',
                                bg=theme.FOND_LATERAL, padx=10, pady=8)
        self.constats.pack(fill='x')
        self.constats.tag_configure('alerte', foreground=theme.ERREUR)
        self.constats.tag_configure('ok', foreground=theme.OK)
        self.constats.configure(state='disabled')

        self.onglets = ttk.Notebook(self)
        self.onglets.pack(fill='both', expand=True, pady=(10, 0))
        self.tables = {}
        for cle, titre, colonnes in (
            ('comparaisons', 'Comparaisons', [
                ('date', 'Date', 135, 'w'), ('id', 'N°', 40, 'e'), ('plaque', 'Plaque', 130, 'w'),
                ('importateur', 'Importateur', 160, 'w'), ('fichier', 'XML comparé', 200, 'w'),
                ('estime', 'Taxes générées', 110, 'e'), ('compare', 'Taxes comparées', 110, 'e'),
                ('ecart', 'Écart CDF', 95, 'e'), ('pct', 'Écart %', 75, 'e'), ('hors_taux', 'Hors taux %', 85, 'e'),
                ('diagnostic', 'Diagnostic', 150, 'w'), ('raisons', 'Pourquoi', 220, 'w')]),
            ('taxes', 'Par taxe', [
                ('taxe', 'Taxe', 120, 'w'), ('portee', 'Portée', 80, 'w'), ('n', 'Comparaisons', 95, 'e'),
                ('estime', 'Total généré', 120, 'e'), ('compare', 'Total comparé', 120, 'e'),
                ('ecart', 'Écart CDF', 100, 'e'), ('hors_taux', 'Hors taux CDF', 110, 'e'),
                ('hors_taux_pct', 'Hors taux %', 90, 'e'), ('sens', 'Sens', 80, 'w'),
                ('taux', 'Taux différent', 95, 'e'), ('absente', 'Absente', 70, 'e')]),
            ('articles', 'Par article', [
                ('code', 'Code', 100, 'w'), ('designation', 'Désignation', 260, 'w'), ('n', 'Comparaisons', 95, 'e'),
                ('ratio', 'Ratio FOB/kg', 100, 'e'), ('poids', 'Poids', 85, 'e'), ('fob', 'FOB', 85, 'e'),
                ('colis', 'Colis', 85, 'e'), ('taxes', 'Taxes', 85, 'e')]),
            ('importateurs', 'Par importateur', [
                ('importateur', 'Importateur', 260, 'w'), ('n', 'Comparaisons', 95, 'e'), ('moyen', 'Écart % moyen', 110, 'e'),
                ('hors_taux', 'Hors taux % moyen', 130, 'e'), ('diagnostics', 'Diagnostics', 380, 'w')])):
            onglet = ttk.Frame(self.onglets, padding=(0, 6, 0, 0))
            self.onglets.add(onglet, text=titre)
            zone, table = theme.tableau(onglet, colonnes, 9)
            zone.pack(fill='both', expand=True)
            self.tables[cle] = table
        for diagnostic, couleur in COULEURS.items():
            self.tables['comparaisons'].tag_configure(diagnostic, foreground=couleur)
        self.legendes = {
            'articles': 'Ratio FOB/kg : toutes les comparaisons, même d’autres dossiers. Poids, FOB, colis : '
                        'répartitions différentes seulement. Taxes : hors autres dossiers.',
            'taxes': 'Comparaisons à répartition identique seulement. « Taxes globales » : montant global, '
                     'les XML ne le détaillent pas.'}
        self.var_legende = tk.StringVar()
        ttk.Label(self, textvariable=self.var_legende, style='Doux.TLabel', wraplength=1100).pack(anchor='w', pady=(4, 0))
        self.onglets.bind('<<NotebookTabChanged>>', lambda e: self.var_legende.set(
            self.legendes.get(list(self.tables)[self.onglets.index('current')], '')))
        table = self.tables['comparaisons']
        table.bind('<Double-1>', lambda e: self.ouvrir())
        table.bind('<<TreeviewSelect>>', lambda e: self.ouvrir_bouton.configure(
            state='normal' if self.entree_choisie(rapport=True) else 'disabled'))

    # ----------------------------------------------------------------- données
    def afficher(self):
        try:
            self.toutes = service.collecter(module=getattr(self.app, 'module_travail', 'friperie'))
        except Exception as exc:  # noqa: BLE001 - base illisible : le dire, ne rien inventer
            self.toutes = []
            self.ecrire_constats([f'Rapport indisponible : {exc}'])
            return
        self.detecter()
        importateurs = sorted({e['importateur'] for e in self.toutes if e['importateur']})
        self.filtre_importateur.configure(values=['Tous les importateurs'] + importateurs)
        if self.filtre_importateur.get() not in importateurs:
            self.filtre_importateur.set('Tous les importateurs')
        self.recalculer()

    def recalculer(self):
        choix = self.filtre_importateur.get()
        self.entrees = [e for e in self.toutes if choix == 'Tous les importateurs' or e['importateur'] == choix]
        self.analyse = service.analyser(self.entrees)
        ind = self.analyse['indicateurs']
        compte = ind['diagnostics']
        self.cartes['n'].definir(str(ind['n']), f"{ind['modeles']} modèle(s)"
                                 + (f" · {ind['repetees']} répétée(s) écartée(s)" if ind['repetees'] else ''))
        self.cartes['calcul'].definir(str(compte[service.CALCUL]),
            f"{compte[service.TAUX]} dû(s) au taux · {compte[service.IDENTIQUE]} identique(s)")
        self.cartes['hors_taux'].definir(_pct(ind['hors_taux_moyen'], 3),
            f"{ind['meme_repartition']} comparaison(s) à répartition identique")
        self.cartes['moyen'].definir(_pct(ind['moyen']),
            f"{compte[service.AUTRE]} autre(s) dossier(s) · {compte[service.REPARTITION]} répartition(s) différente(s)")
        self.ecrire_constats(self.analyse['constats'])
        self.remplir_comparaisons()
        self.remplir_analyses()

    def ecrire_constats(self, phrases):
        self.constats.configure(state='normal')
        self.constats.delete('1.0', 'end')
        for p in phrases:
            tag = 'alerte' if p.lstrip().startswith(('⚠', '→')) else 'ok' if p.startswith('✓') else ()
            self.constats.insert('end', ('' if p.startswith(' ') else '•  ') + p + '\n', tag)
        self.constats.configure(state='disabled')

    def remplir_comparaisons(self):
        table = self.tables['comparaisons']
        table.delete(*table.get_children())
        self.par_iid = {}
        for e in self.entrees:
            if self.filtre.get() not in (TOUS, e['diagnostic']):
                continue
            iid = str(e['evenement'])
            self.par_iid[iid] = e
            repetee = f" (×{e['repetitions']})" if e['repetitions'] > 1 else ''
            table.insert('', 'end', iid=iid, tags=(e['diagnostic'],), values=(
                date_locale(e['date_utc']), e['modele'], e['plaque'] or '—', e['importateur'] or '—',
                Path(e['fichier']).name + repetee, nombre(e['estime']), nombre(e['compare']), _cdf(e['ecart']),
                _pct(e['pourcentage']), _pct(e['pourcentage_hors_taux'], 3) if e['diagnostic'] in service.MEME_REPARTITION else '—',
                e['diagnostic'], ' ; '.join(e['raisons'])))
        self.ouvrir_bouton.configure(state='disabled')

    def remplir_analyses(self):
        for cle in ('taxes', 'articles', 'importateurs'):
            self.tables[cle].delete(*self.tables[cle].get_children())
        for t in self.analyse['taxes']:
            self.tables['taxes'].insert('', 'end', tags=('alerte',) if t['sens'] in ('plus', 'moins') else (), values=(
                t['taxe'], t['portee'], t['n'], nombre(t['estime']), nombre(t['compare']), _cdf(t['ecart']),
                _cdf(t['ecart_hors_taux']), _pct(t['pourcentage_hors_taux'], 3), t['sens'], t['taux_differents'], t['absentes']))
        for a in self.analyse['articles']:
            fort = a['ratio_moyen'] is not None and abs(a['ratio_moyen']) >= service.SEUIL_ARTICLE
            self.tables['articles'].insert('', 'end', tags=('alerte',) if fort else (), values=(
                a['code'], a['designation'], a['n'], *(_pct(a[m + '_moyen'], 1) for m in ('ratio', 'poids', 'fob', 'colis', 'taxes'))))
        for g in self.analyse['importateurs']:
            self.tables['importateurs'].insert('', 'end', values=(
                g['importateur'], g['n'], _pct(g['moyen']), _pct(g['hors_taux_moyen'], 3),
                ', '.join(f'{d} : {n}' for d, n in g['diagnostics'].items())))

    def detecter(self):
        """Cherche dans les dossiers des importateurs les déclarations SYDONIA réelles pas encore connues."""
        try:
            self.candidats = detection_reelles.detecter(module=getattr(self.app, 'module_travail', 'friperie'))
        except Exception:  # noqa: BLE001 - la détection est une aide : le rapport reste disponible
            erreur_ignoree('détection des déclarations réelles')
            self.candidats = []
        self.detection_bouton.configure(state='normal' if self.candidats else 'disabled')
        if not self.candidats:
            self.bandeau.vider()
            return
        rattachees = sum(1 for c in self.candidats if c['modele'] is not None)
        self.bandeau.afficher('alerte', f"{len(self.candidats)} déclaration(s) réelle(s) SYDONIA détectée(s) dans vos dossiers",
            [f"{rattachees} rattachable(s) à un modèle par la plaque, {len(self.candidats) - rattachees} sans modèle. "
             "Ce sont vos repères les plus sûrs : « Déclarations réelles détectées… » pour les vérifier et les ajouter."])

    def examiner_detection(self):
        fenetre = FenetreDetection(self, self.candidats)
        self.wait_window(fenetre)
        if fenetre.enregistre:
            self.afficher()

    # ----------------------------------------------------------------- actions
    def entree_choisie(self, rapport=False):
        selection = self.tables['comparaisons'].selection()
        entree = self.par_iid.get(selection[0]) if selection else None
        return entree if entree and (entree['rapport'] or not rapport) else None

    def ouvrir(self):
        entree = self.entree_choisie()
        if entree is None:
            return
        if not entree['rapport']:
            messagebox.showinfo('Détail indisponible', 'Cette ancienne comparaison n’a que ses totaux : le fichier comparé '
                                'a été déplacé ou modifié. Comparez à nouveau depuis « Modèles générés ».', parent=self)
            return
        from asydec.ui.comparaison import afficher
        rapport = dict(entree['rapport'])
        rapport.setdefault('importateur', entree['importateur'])
        afficher(self, rapport)

    def exporter(self):
        if not self.entrees:
            messagebox.showinfo('Exporter', 'Aucune comparaison à exporter.', parent=self)
            return
        chemin = filedialog.asksaveasfilename(parent=self, title='Exporter le rapport des comparaisons',
            defaultextension='.xlsx', filetypes=[('Excel', '*.xlsx')],
            initialfile=f'Rapport des comparaisons {datetime.datetime.now():%Y-%m-%d %H%M}.xlsx',
            **espace_travail.options_rapport())
        if not chemin:
            return
        try:
            service.exporter(self.entrees, self.analyse, chemin)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror('Export impossible', str(exc), parent=self)
            return
        messagebox.showinfo('Rapport exporté', chemin, parent=self)


AUCUN = 'Aucun : retenir comme déclaration réelle seule'


class FenetreDetection(tk.Toplevel):
    """Déclarations réelles détectées : l'utilisateur vérifie chaque rattachement avant d'enregistrer."""

    def __init__(self, parent, candidats):
        super().__init__(parent)
        self.page, self.enregistre = parent, False
        self.candidats = {str(k): dict(c) for k, c in enumerate(candidats)}
        self.title('Déclarations réelles détectées')
        self.geometry('1280x620')
        self.transient(parent.winfo_toplevel())
        cadre = ttk.Frame(self, padding=16)
        cadre.pack(fill='both', expand=True)
        theme.entete_page(cadre, 'Déclarations réelles détectées',
            'XML SYDONIA trouvés dans les dossiers des importateurs : numéro d’enregistrement propre au fichier, '
            'ni export AsyDec ni gabarit. Rattachés par la plaque du tracteur. Les lignes à vérifier ne sont pas '
            'sélectionnées d’office. Une comparaison enregistrée ne peut plus être effacée.')
        zone, self.table = theme.tableau(cadre, [
            ('fichier', 'Fichier', 200, 'w'), ('plaque', 'Plaque', 140, 'w'), ('importateur', 'Importateur', 170, 'w'),
            ('enregistrement', 'Enregistrement', 105, 'w'), ('date', 'Date', 85, 'w'), ('liquidee', 'Liquidée', 65, 'center'),
            ('action', 'Action proposée', 210, 'w'), ('verifier', 'À vérifier', 300, 'w')], 12)
        zone.pack(fill='both', expand=True)
        self.table.configure(selectmode='extended')
        choix = ttk.Frame(cadre)
        choix.pack(fill='x', pady=8)
        ttk.Label(choix, text='Modèle de la ligne sélectionnée :').pack(side='left')
        self.modele = ttk.Combobox(choix, state='disabled', width=48)
        self.modele.pack(side='left', padx=6)
        self.modele.bind('<<ComboboxSelected>>', lambda e: self.changer_modele())
        boutons = ttk.Frame(cadre)
        boutons.pack(fill='x')
        theme.bouton(boutons, 'Fermer', self.destroy).pack(side='right')
        theme.bouton(boutons, 'Enregistrer la sélection', self.enregistrer, principal=True).pack(side='right', padx=8)
        self.var_selection = tk.StringVar()
        ttk.Label(boutons, textvariable=self.var_selection, style='Doux.TLabel').pack(side='left')
        for iid, c in self.candidats.items():
            self.table.insert('', 'end', iid=iid, values=self.valeurs(c))
        self.table.selection_set([iid for iid, c in self.candidats.items() if not self.a_verifier(c)])
        self.table.bind('<<TreeviewSelect>>', lambda e: self.actualiser())
        self.actualiser()

    @staticmethod
    def a_verifier(c):
        return any(a.startswith(('Articles différents', 'Enregistrée le')) for a in c['avertissements'])

    @staticmethod
    def action(c):
        return f"Comparer au modèle n° {c['modele']}" if c['modele'] is not None else 'Retenir comme déclaration réelle'

    def valeurs(self, c):
        return (c['nom'], c['camion'] or '—', c['importateur'] or '—', c['enregistrement'],
                c['date'].strftime('%d/%m/%Y') if c['date'] else '—', '✓' if c['liquidee'] else '',
                self.action(c), ' '.join(c['avertissements']) or '—')

    def actualiser(self):
        selection = self.table.selection()
        self.var_selection.set(f'{len(selection)} ligne(s) sélectionnée(s) sur {len(self.candidats)}.')
        if len(selection) != 1:
            self.modele.configure(state='disabled', values=[])
            self.modele.set('')
            return
        c = self.candidats[selection[0]]
        self.modele.configure(state='readonly', values=[f"n° {m}" for m in c['modeles']] + [AUCUN])
        self.modele.set(f"n° {c['modele']}" if c['modele'] is not None else AUCUN)

    def changer_modele(self):
        selection = self.table.selection()
        if len(selection) != 1:
            return
        c = self.candidats[selection[0]]
        texte = self.modele.get()
        c['modele'] = None if texte == AUCUN else int(texte.removeprefix('n° '))
        self.table.item(selection[0], values=self.valeurs(c))

    def enregistrer(self):
        choisis = [self.candidats[i] for i in self.table.selection()]
        if not choisis:
            messagebox.showinfo('Aucune sélection', 'Sélectionnez les déclarations à enregistrer.', parent=self)
            return
        comparer = sum(1 for c in choisis if c['modele'] is not None)
        if not messagebox.askyesno('Confirmer', f"{comparer} comparaison(s) seront enregistrées et "
                                   f"{len(choisis) - comparer} déclaration(s) retenues sans modèle.\n\n"
                                   'Cet historique ne peut plus être effacé. Continuer ?', parent=self):
            return
        app = self.page.app
        comparees, retenues, erreurs = detection_reelles.enregistrer(
            choisis, getattr(app, 'utilisateur', ''), module=getattr(app, 'module_travail', 'friperie'),
            table_imp=getattr(app, 'table_imp', None))
        self.enregistre = bool(comparees or retenues)
        lignes = [f'{comparees} comparaison(s) enregistrée(s), {retenues} déclaration(s) retenue(s).'] + erreurs
        (messagebox.showwarning if erreurs else messagebox.showinfo)('Déclarations réelles', '\n'.join(lignes), parent=self)
        if not erreurs:
            self.destroy()
