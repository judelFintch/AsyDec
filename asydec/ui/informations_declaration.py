"""Étape de saisie des informations de déclaration."""
import re
import sqlite3
import tkinter as tk
from tkinter import ttk
from asydec.declarations import informations_declaration as regles, licences_ouvertes, taux_declaration
from asydec.ui import theme


class InformationsDeclaration(tk.Toplevel):
    def __init__(self, parent, app, licence, apres_validation):
        super().__init__(parent)
        self.app, self.licence = app, licence
        self.apres_validation = apres_validation
        self.title('Informations déclaration')
        self.geometry(f'860x{min(860, self.winfo_screenheight() - 90)}')
        self.minsize(740, 680)
        self.transient(parent.winfo_toplevel())
        cadre = ttk.Frame(self, padding=20)
        cadre.pack(fill='both', expand=True)
        theme.entete_page(cadre, '3 · Informations déclaration', licence['numero_validation'])
        reperes = ttk.Frame(cadre, padding=12, relief='solid', borderwidth=1)
        reperes.pack(fill='x', pady=(0, 12))
        for cle, titre in (('date_validation', 'Validation licence'), ('date_bl', 'Date du BL')):
            valeur = licence.get(cle)
            try:
                texte = regles.lire_date(valeur).strftime('%d/%m/%Y')
            except ValueError:
                texte = 'Non renseignée'
            colonne = ttk.Frame(reperes)
            colonne.pack(side='left', fill='x', expand=True)
            ttk.Label(colonne, text=titre, style='Doux.TLabel').pack(anchor='w')
            ttk.Label(colonne, text=texte, style='Section.TLabel').pack(anchor='w', pady=(4, 0))
        ttk.Label(cadre, text='Complétez les informations connues avant la dernière étape : génération XML.',
                  style='SousTitre.TLabel', wraplength=740).pack(anchor='w', pady=(0, 14))
        informations = licence.get('informations_declaration', {})
        self.calcul_possible = True
        try:
            proposition = regles.proposer_date_enregistrement(licence.get('date_bl'))
            date_auto = proposition['date'].strftime('%d/%m/%Y')
            anciennes = dict(informations)
            if anciennes.get('date_liquidation') and not anciennes.get('date_cvi'):
                anciennes['date_cvi'] = regles.proposer_date_cvi(anciennes['date_liquidation']).strftime('%d/%m/%Y')
            if anciennes.get('date_enregistrement') == date_auto and all(anciennes.get(c) for c in regles.DATES_AUTO):
                try:
                    regles.verifier(anciennes)
                    dates_auto = {c: anciennes[c] for c in regles.DATES_AUTO}
                except ValueError:
                    dates_auto = regles.proposer_dates_declaration(licence.get('date_bl'))
            else:
                dates_auto = regles.proposer_dates_declaration(licence.get('date_bl'))
            explication = f"BL du {regles.lire_date(licence['date_bl']):%d/%m/%Y} → date proposée : {date_auto}"
            explication += ' · Dernier jour ouvrable entre un et deux mois après le BL.'
            explication += ' · CVI : 2 à 4 jours après la liquidation.'
        except ValueError as exc:
            self.calcul_possible = False
            dates_auto = {c:'' for c in regles.DATES_AUTO}
            date_auto = ''
            explication = str(exc)
        ttk.Label(cadre, text=explication, style='Doux.TLabel' if self.calcul_possible else 'Erreur.TLabel',
                  wraplength=740).pack(anchor='w', pady=(0, 12))
        self.carnet = ttk.Notebook(cadre)
        self.carnet.pack(fill='x', pady=(0, 12))
        chronologie = ttk.Frame(self.carnet, padding=14)
        complements = ttk.Frame(self.carnet, padding=14)
        self.carnet.add(chronologie, text='Numéros et dates')
        self.carnet.add(complements, text='Déclaration et transport')
        self.champs = {}
        for page, champs in ((chronologie, regles.CHAMPS[:8]), (complements, regles.CHAMPS[8:])):
            for colonne in (0, 1):
                page.columnconfigure(colonne, weight=1, uniform='champ')
            for i, (cle, titre, _) in enumerate(champs):
                case = ttk.Frame(page, padding=(0, 0, 16 if i % 2 == 0 else 0, 12))
                case.grid(row=i//2, column=i%2, sticky='ew')
                ttk.Label(case, text=titre + (' *' if cle in ('numero_e','numero_liquidation','numero_quittance') else ''), style='Doux.TLabel').pack(anchor='w', pady=(0, 4))
                variable = tk.StringVar(value=dates_auto[cle] if cle in regles.DATES_AUTO else informations.get(cle, ''))
                self.champs[cle] = variable
                ttk.Entry(case, textvariable=variable, state='readonly' if cle in regles.DATES_AUTO else 'normal').pack(fill='x')
        ttk.Label(chronologie, text='Saisie pour la première part · E, liquidation et manifeste suivants : +1 à +6.\n'
                  'Q partagé par groupes aléatoires de 2 à 6 parts consécutives à la même date, +1 à +6 d’un groupe à l’autre.\n'
                  'Week-ends et fériés RDC exclus · E ≤ liquidation ≤ quittance ≤ aujourd’hui.',
                  style='Doux.TLabel', wraplength=700).grid(row=4, column=0, columnspan=2, sticky='w', pady=6)
        boutons = ttk.Frame(chronologie)
        boutons.grid(row=5, column=0, columnspan=2, sticky='w', pady=6)
        theme.bouton(boutons, 'Reproposer liquidation, quittance et CVI', self.reproposer,
                     state='normal' if self.calcul_possible else 'disabled').grid(row=0, column=0, sticky='w')
        theme.bouton(boutons, 'Proposer E, L, Q et manifeste', lambda: self.proposer_numeros(tout=True),
                     state='normal' if self.calcul_possible else 'disabled').grid(row=0, column=1, sticky='w', padx=(10, 0))
        theme.bouton(boutons, 'Ajouter des E connus…', self.ajouter_numeros_connus).grid(row=1, column=0, sticky='w', pady=(6, 0))
        theme.bouton(boutons, '📈 Suivi des numéros', self.voir_suivi).grid(row=1, column=1, sticky='w', padx=(10, 0), pady=(6, 0))
        self.explication_numeros = tk.StringVar()
        ttk.Label(chronologie, textvariable=self.explication_numeros, style='Doux.TLabel', wraplength=720,
                  justify='left').grid(row=6, column=0, columnspan=2, sticky='w')
        self.alertes_numeros = tk.StringVar()
        ttk.Label(chronologie, textvariable=self.alertes_numeros, style='Alerte.TLabel', wraplength=720,
                  justify='left').grid(row=7, column=0, columnspan=2, sticky='w')
        self._points_suivi = None
        if self.calcul_possible:
            self.proposer_numeros(tout=False)
        for cle in ('numero_e', 'numero_liquidation', 'numero_quittance', 'manifeste', *regles.DATES_AUTO):
            self.champs[cle].trace_add('write', lambda *_: self.after_idle(self.controler_numeros))
        self.controler_numeros()
        self._champ_taux(complements, len(regles.CHAMPS[8:]))
        ttk.Label(cadre, text='Observations', style='Doux.TLabel').pack(anchor='w')
        self.observations = tk.Text(cadre, height=2, wrap='word', font=(theme.POLICE, 12))
        self.observations.pack(fill='both', expand=True, pady=(4, 12))
        self.observations.insert('1.0', informations.get('observations', ''))
        self.erreur = tk.StringVar()
        # Validation toujours visible : barre fixée en bas, avant le reste du contenu.
        actions = ttk.Frame(cadre)
        actions.pack(side='bottom', fill='x', pady=(12, 0), before=cadre.winfo_children()[0])
        theme.bouton(actions, 'Annuler', self.destroy).pack(side='left')
        theme.bouton(actions, 'Enregistrer les informations', self.enregistrer, principal=True,
                     state='normal' if self.calcul_possible else 'disabled').pack(side='right')
        ttk.Label(cadre, textvariable=self.erreur, style='Erreur.TLabel', wraplength=740).pack(
            side='bottom', anchor='w', before=actions)

    def enregistrer(self):
        if self.app.session_verrouillee or not self.calcul_possible:
            return
        valeurs = {cle: v.get() for cle, v in self.champs.items()}
        valeurs['observations'] = self.observations.get('1.0', 'end-1c')
        valeurs['taux_change'] = self.taux.get()
        try:
            licences_ouvertes.enregistrer_informations_declaration(self.licence['numero_validation'], valeurs)
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.erreur.set(str(exc))
            return
        self.apres_validation()
        self.destroy()

    def _champ_taux(self, page, rang):
        """Taux de change de la déclaration : proposé depuis un taux existant, modifiable, sans effet
        sur les autres étapes (seule la case 23 de la déclaration Word l'affiche)."""
        try:
            taux, source = licences_ouvertes.proposer_taux_change(
                self.licence['numero_validation'], preference=(getattr(self.app, 'prefs', None) or {}).get('taux_change'))
        except (ValueError, OSError, sqlite3.Error):
            taux, source = None, ''
        self.taux = tk.StringVar(value=taux_declaration.texte(taux) if taux else '')
        case = ttk.Frame(page, padding=(0, 0, 16, 12))
        case.grid(row=(rang + 1) // 2, column=0, columnspan=2, sticky='ew')
        ttk.Label(case, text='Taux de change (CDF pour 1 USD) · affiché sur la déclaration', style='Doux.TLabel').pack(anchor='w', pady=(0, 4))
        ligne = ttk.Frame(case)
        ligne.pack(fill='x')
        ttk.Entry(ligne, textvariable=self.taux, width=16, justify='right').pack(side='left')
        note = (f'Proposé : {source}.' if taux else 'Aucun taux connu : saisissez-le, ou laissez vide pour garder celui du XML SYDONIA.')
        ttk.Label(ligne, text=note + ' Le changer ne touche à aucune autre étape ; régénérez seulement les déclarations.',
                  style='Doux.TLabel', wraplength=520).pack(side='left', padx=(10, 0))

    def proposer_numeros(self, tout):
        """Numéros E, L, Q et manifeste logiques et croissants, d'après les dossiers déjà traités
        (même année, même bureau si connu). À l'ouverture, seules les cases vides sont remplies."""
        dates = {cle: self.champs[cle].get() for cle in regles.DATES_AUTO}
        try:
            propositions = licences_ouvertes.proposer_numeros(self.licence['numero_validation'], dates,
                                                              self.champs['bureau_code'].get())
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.explication_numeros.set(f'Proposition des numéros impossible : {exc}')
            return
        remplis = []
        for cle, (valeur, explication) in propositions.items():
            if tout or not self.champs[cle].get().strip():
                self.champs[cle].set(valeur)
                remplis.append(explication)
        if remplis:
            compact = [re.sub(r' \(règle : .*?\)', '', re.sub(r', (dossier|liste|déclaration réelle) [^)]*\)', ')', e))
                       for e in remplis]
            self.explication_numeros.set('Numéros proposés (modifiables) : ' + ' · '.join(compact))
        elif not tout:
            self.explication_numeros.set('Numéros déjà saisis conservés · « Proposer E, L, Q et manifeste » '
                                         'pour une proposition d’après les autres dossiers.')

    def ajouter_numeros_connus(self):
        """Coller un tableau de numéros E réels (plaques, E, paiement, déclaration) pour affiner les propositions."""
        from asydec.declarations import numeros_logiques
        fenetre = tk.Toplevel(self)
        fenetre.title('Numéros E connus')
        fenetre.transient(self)
        fenetre.geometry('760x560')
        cadre = ttk.Frame(fenetre, padding=16)
        cadre.pack(fill='both', expand=True)
        ttk.Label(cadre, text='Collez le tableau tel quel depuis Excel ou Word, avec sa ligne d’en-tête '
                  '(# · PLAQUES · PAIEMENT · E · PAIEMENT ORANGE · DECLARATION). Chaque E est retenu avec sa date de '
                  'DÉCLARATION ; les lignes sans E ou sans date de déclaration sont ignorées.',
                  style='SousTitre.TLabel', wraplength=720, justify='left').pack(anchor='w', pady=(0, 8))
        zone = tk.Text(cadre, height=18, wrap='none', font=(theme.POLICE, 11))
        zone.pack(fill='both', expand=True)
        resultat = tk.StringVar(value=f'{len(licences_ouvertes.lister_numeros_connus())} numéro(s) E connus en base.')
        ttk.Label(cadre, textvariable=resultat, style='Doux.TLabel', wraplength=720).pack(anchor='w', pady=(8, 0))

        def enregistrer():
            points, ignorees = numeros_logiques.lire_liste(zone.get('1.0', 'end'))
            if not points:
                resultat.set('Aucun numéro E avec date de déclaration trouvé : vérifiez la ligne d’en-tête.')
                return
            try:
                nouveaux = licences_ouvertes.ajouter_numeros_connus(points)
            except (ValueError, OSError, sqlite3.Error) as exc:
                resultat.set(str(exc))
                return
            ecartes = len(points) - len(numeros_logiques.coherents(points))
            resultat.set(f'{len(points)} numéro(s) lus · {nouveaux} nouveau(x) enregistré(s) · {ignorees} ligne(s) ignorée(s)'
                         + (f' · {ecartes} hors chronologie (écartés des calculs)' if ecartes else '') + '.')
            zone.delete('1.0', 'end')
            self._points_suivi = None
            self.controler_numeros()
            if self.calcul_possible:
                self.proposer_numeros(tout=False)
        actions = ttk.Frame(cadre)
        actions.pack(fill='x', pady=(10, 0))
        theme.bouton(actions, 'Fermer', fenetre.destroy).pack(side='left')
        theme.bouton(actions, 'Enregistrer les numéros', enregistrer, principal=True).pack(side='right')

    def _points(self):
        if self._points_suivi is None:
            try:
                self._points_suivi = licences_ouvertes.points_suivi(exclure=self.licence['numero_validation'])
            except (ValueError, OSError, sqlite3.Error):
                self._points_suivi = []
        return self._points_suivi

    def controler_numeros(self):
        """Signale tout de suite un numéro saisi qui contredit la progression connue (même année)."""
        from asydec.declarations import numeros_logiques
        if not self.winfo_exists():
            return
        messages = []
        for type_, (cle, cle_date, _, _) in numeros_logiques.TYPES.items():
            message = numeros_logiques.controler(self._points(), type_, self.champs[cle].get(),
                                                 numeros_logiques.lire_date(self.champs[cle_date].get()))
            if message:
                messages.append('⚠ ' + message)
        messages += ['⚠ ' + m for m in numeros_logiques.controler_sous_e(
            self.champs['numero_e'].get(), {c: v.get() for c, v in self.champs.items()})]
        self.alertes_numeros.set('\n'.join(messages))

    def voir_suivi(self):
        from asydec.ui.suivi_numeros import SuiviNumeros
        from asydec.declarations import numeros_logiques
        jour = numeros_logiques.lire_date(self.champs['date_enregistrement'].get())
        points = list(self._points())
        # La saisie en cours apparaît aussi (non enregistrée).
        for type_, (cle, cle_date, _, _) in numeros_logiques.TYPES.items():
            numeros_logiques._ajouter(points, type_, self.champs[cle].get(), self.champs[cle_date].get(), '',
                                      'saisie en cours ' + self.licence['numero_validation'])
        SuiviNumeros(self, points, jour.year if jour else None)

    def reproposer(self):
        if self.app.session_verrouillee or not self.calcul_possible:
            return
        actuelles = {cle: self.champs[cle].get() for cle in regles.DATES_AUTO}
        try:
            nombre = len(regles.combinaisons_dates_declaration(self.licence.get('date_bl')))
            dates = regles.proposer_dates_declaration(self.licence.get('date_bl'), exclure=actuelles)
        except ValueError as exc:
            self.erreur.set(str(exc))
            return
        for cle, valeur in dates.items():
            self.champs[cle].set(valeur)
        if nombre <= 1:
            self.erreur.set('Aucune autre proposition possible : avec cette date E, les jours E+2 et E+3 '
                            'ne sont pas ouvrables (week-end ou férié RDC) ou dépassent aujourd’hui, '
                            'et la date CVI en découle.')
        else:
            self.erreur.set('')
