"""Fenêtre « Imprimer les documents » : tout le dossier imprimé en une seule fois."""
from pathlib import Path
import queue
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from asydec.declarations import impression_dossier, licences_ouvertes
from asydec.systeme import espace_travail, impression
from asydec.ui import theme


class FenetreImpression(tk.Toplevel):
    def __init__(self, parent, app, licence, ouvrir_fichier):
        super().__init__(parent)
        self.app, self.licence, self.ouvrir_fichier = app, licence, ouvrir_fichier
        self.numero = licence['numero_validation']
        self.title('Imprimer les documents')
        self.transient(parent.winfo_toplevel())
        self.resizable(False, False)
        self.file = queue.Queue()
        self.occupe = False
        cadre = ttk.Frame(self, padding=20)
        cadre.pack(fill='both', expand=True)
        theme.entete_page(cadre, 'Imprimer les documents', self.numero)
        ttk.Label(cadre, text='Cochez les documents : ils sont réunis dans un seul PDF puis envoyés à l’imprimante, '
                              'sans ouvrir chaque fichier.', style='SousTitre.TLabel', wraplength=520,
                  justify='left').pack(anchor='w', pady=(0, 12))

        self.docs = impression_dossier.documents(licence)
        bloc = ttk.LabelFrame(cadre, text='Documents', padding=12)
        bloc.pack(fill='x')
        self.choix = {}
        for cle, titre in impression_dossier.GROUPES:
            nombre = 1 if cle == 'fiche' else len(self.docs[cle])
            variable = tk.BooleanVar(value=nombre > 0 and cle in impression_dossier.PAR_DEFAUT)
            self.choix[cle] = variable
            texte = titre if cle == 'fiche' else f'{titre} ({nombre})' if nombre else f'{titre} — non générés'
            ttk.Checkbutton(bloc, text=texte, variable=variable,
                            state='normal' if nombre else 'disabled').pack(anchor='w', pady=2)

        ordre = ttk.LabelFrame(cadre, text='Ordre des pages', padding=12)
        ordre.pack(fill='x', pady=(12, 0))
        self.par_part = tk.BooleanVar(value=True)
        ttk.Radiobutton(ordre, text='Par part : facture, packing list et déclaration de chaque part à la suite',
                        variable=self.par_part, value=True).pack(anchor='w')
        ttk.Radiobutton(ordre, text='Par type : toutes les factures, puis les packing lists, puis les déclarations',
                        variable=self.par_part, value=False).pack(anchor='w')

        reglages = ttk.LabelFrame(cadre, text='Imprimante', padding=12)
        reglages.pack(fill='x', pady=(12, 0))
        noms, defaut = impression.imprimantes()
        self.imprimante = tk.StringVar(value=defaut or '')
        ligne = ttk.Frame(reglages)
        ligne.pack(fill='x')
        ttk.Combobox(ligne, textvariable=self.imprimante, values=noms, state='readonly' if noms else 'disabled',
                     width=36).pack(side='left')
        ttk.Label(ligne, text='Exemplaires', style='Doux.TLabel').pack(side='left', padx=(14, 6))
        self.copies = tk.IntVar(value=1)
        ttk.Spinbox(ligne, from_=1, to=20, textvariable=self.copies, width=4).pack(side='left')
        self.recto_verso = tk.BooleanVar(value=False)
        ttk.Checkbutton(reglages, text='Recto verso', variable=self.recto_verso).pack(anchor='w', pady=(8, 0))
        # Une fois imprimé, le dossier passe dans « En physique » de la liste des licences.
        self.physique = tk.BooleanVar(value=True)
        texte = 'Cocher le dossier « en physique » après l’impression'
        if licence.get('physique'):
            texte += ' (déjà en physique)'
        ttk.Checkbutton(reglages, text=texte, variable=self.physique).pack(anchor='w', pady=(4, 0))
        if not noms:
            ttk.Label(reglages, text='Aucune imprimante détectée : utilisez « Ouvrir le PDF ».',
                      style='Alerte.TLabel').pack(anchor='w', pady=(6, 0))

        self.statut = tk.StringVar()
        ttk.Label(cadre, textvariable=self.statut, style='Doux.TLabel', wraplength=520).pack(anchor='w', pady=(12, 4))
        self.barre = ttk.Progressbar(cadre, mode='determinate', maximum=100)
        self.barre.pack(fill='x')
        actions = ttk.Frame(cadre)
        actions.pack(fill='x', pady=(14, 0))
        theme.bouton(actions, 'Fermer', self.fermer).pack(side='left')
        self.bouton_imprimer = theme.bouton(actions, '🖨  Imprimer', lambda: self.lancer(True), principal=True,
                                            state='normal' if noms else 'disabled')
        self.bouton_imprimer.pack(side='right')
        self.bouton_pdf = theme.bouton(actions, 'Ouvrir le PDF', lambda: self.lancer(False))
        self.bouton_pdf.pack(side='right', padx=(0, 8))
        self.protocol('WM_DELETE_WINDOW', self.fermer)

    def fermer(self):
        if self.occupe:
            return
        self.destroy()

    def _destination(self):
        try:
            dossier = espace_travail.dossier_dec(self.licence.get('numero_dec'))
        except (OSError, ValueError):
            dossier = None
        base = Path(dossier) if dossier else Path(tempfile.gettempdir())
        return base / f'{self.numero} - impression.pdf'

    def lancer(self, imprimer):
        if self.occupe or self.app.session_verrouillee:
            return
        choisis = {c for c, v in self.choix.items() if v.get()}
        elements = impression_dossier.ordonner(self.docs, choisis, self.par_part.get())
        if not elements:
            messagebox.showinfo('Imprimer les documents', 'Cochez au moins un document disponible.', parent=self)
            return
        reglages = dict(imprimante=self.imprimante.get() or None, copies=max(1, int(self.copies.get() or 1)),
                        recto_verso=self.recto_verso.get())
        physique = self.physique.get()
        self.occupe = True
        for bouton in (self.bouton_imprimer, self.bouton_pdf):
            bouton.configure(state='disabled')
        self.statut.set(f'Préparation de {len(elements)} document(s)…')
        self.barre['value'] = 0

        def progression(fait, total):
            self.file.put(('progression', fait, total))

        def travail():
            try:
                chemin, pages = impression_dossier.assembler(self.licence, elements, self._destination(), progression)
                message = ''
                if imprimer:
                    message = impression.imprimer(chemin, titre=f'{self.numero} - documents', **reglages)
                    if physique and not self.licence.get('physique'):
                        try:
                            self.licence['physique'] = licences_ouvertes.marquer_physique(
                                self.numero, True, source='impression')
                            message += '\nDossier coché « en physique ».'
                        except Exception as exc:  # l'impression est faite : seule la coche a échoué
                            message += f'\nImpression faite, mais la coche « en physique » a échoué : {exc}'
                self.file.put(('fini', chemin, pages, message))
            except Exception as exc:  # message affiché ; le Word d'origine n'est jamais modifié
                self.file.put(('erreur', str(exc)))

        threading.Thread(target=travail, daemon=True).start()
        self.after(150, lambda: self._suivre(imprimer))

    def _suivre(self, imprimer):
        try:
            while True:
                evenement = self.file.get_nowait()
                if evenement[0] == 'progression':
                    _, fait, total = evenement
                    self.barre['value'] = 100 * fait / total if total else 100
                    self.statut.set(f'Conversion par Word : {fait} / {total} document(s)…' if total
                                    else 'Assemblage du PDF…')
                elif evenement[0] == 'fini':
                    _, chemin, pages, message = evenement
                    self._terminer()
                    self.barre['value'] = 100
                    self.statut.set(f'{pages} page(s) · {chemin.name}' + (f'\n{message}' if message else ''))
                    if not imprimer:
                        self.ouvrir_fichier(chemin)
                    return
                elif evenement[0] == 'erreur':
                    self._terminer()
                    self.statut.set('')
                    messagebox.showerror('Imprimer les documents', evenement[1], parent=self)
                    return
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(150, lambda: self._suivre(imprimer))

    def _terminer(self):
        self.occupe = False
        self.bouton_pdf.configure(state='normal')
        self.bouton_imprimer.configure(state='normal' if self.imprimante.get() else 'disabled')
