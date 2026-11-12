"""Écran d'entrée des documents finaux : dossiers de licence enregistrés.

Chaque dossier peut être coché « en physique » (papier imprimé en main) : la liste se sépare alors entre
les dossiers à traiter et ceux déjà en physique.
"""
from datetime import datetime
from decimal import Decimal
import tkinter as tk
from tkinter import ttk

from asydec.declarations import finalisation
from asydec.formats import nombre
from asydec.ui import theme

COCHE, VIDE = '☑', '☐'
VUES = (('tous', 'Tous'), ('a_traiter', 'À traiter'), ('physique', 'En physique'))


def libelle_physique(valeur_iso):
    """« ☑ 10/11 » si le dossier est en physique (date de la coche), sinon « ☐ »."""
    if not valeur_iso:
        return VIDE
    try:
        return f'{COCHE} ' + datetime.fromisoformat(valeur_iso).astimezone().strftime('%d/%m')
    except ValueError:
        return COCHE


class ListeLicences(ttk.Frame):
    def __init__(self, parent, nouvelle, ouvrir, traiter, voir_repartitions, supprimer=None, recommencer=None,
                 tout_supprimer=None, marquer_physique=None):
        super().__init__(parent)
        self.marquer_physique = marquer_physique
        self.ouvrir = ouvrir
        self.supprimer, self.recommencer = supprimer, recommencer
        self.traiter = traiter
        self.licences = []
        entete = ttk.Frame(self)
        entete.pack(fill='x', pady=(0, 20))
        gauche = ttk.Frame(entete)
        gauche.pack(side='left', fill='x', expand=True)
        theme.entete_page(gauche, 'Licences ouvertes', 'Retrouvez vos dossiers ou commencez une nouvelle licence.')
        theme.bouton(entete, '+ Nouvelle licence', nouvelle, principal=True).pack(side='right', padx=(12, 0))
        theme.bouton(entete, 'Répartitions réalisées', voir_repartitions).pack(side='right', padx=(12, 0))
        if tout_supprimer:
            theme.bouton(entete, 'Tout supprimer', tout_supprimer).pack(side='right', padx=(12, 0))
        self.notification = tk.StringVar()
        self.avis = ttk.Label(self, textvariable=self.notification, style='Ok.TLabel', wraplength=780)
        # Licences dont le BL a moins d'un mois : pas encore de date d'enregistrement (numéro E) possible.
        self.alertes = tk.StringVar()
        self.avis_alertes = ttk.Label(self, textvariable=self.alertes, style='Alerte.TLabel', wraplength=780, justify='left')
        barre = ttk.Frame(self, padding=14, relief='solid', borderwidth=1)
        barre.pack(fill='x', pady=(0, 16))
        self.total = tk.StringVar(value='0 licence')
        ttk.Label(barre, textvariable=self.total, style='Section.TLabel').pack(side='left')
        # Séparation des dossiers : à traiter (pas encore en physique) / en physique.
        self.vue = tk.StringVar(value='tous')
        vues = ttk.Frame(barre)
        vues.pack(side='left', padx=(24, 0))
        self.boutons_vue = {}
        for cle, titre in VUES:
            bouton = ttk.Radiobutton(vues, text=titre, value=cle, variable=self.vue, style='Toolbutton',
                                     command=self.filtrer)
            bouton.pack(side='left', padx=(0, 4))
            self.boutons_vue[cle] = (bouton, titre)
        self.recherche = tk.StringVar()
        recherche = ttk.Frame(barre)
        recherche.pack(side='right')
        ttk.Label(recherche, text='Rechercher', style='Doux.TLabel').pack(side='left', padx=(0, 8))
        ttk.Entry(recherche, textvariable=self.recherche, width=30).pack(side='left')
        self.cadre = ttk.Frame(self, relief='solid', borderwidth=1, padding=1)
        self.cadre.pack(fill='both', expand=True)
        self.cadre.rowconfigure(0, weight=1)
        self.cadre.columnconfigure(0, weight=1)
        self.table = ttk.Treeview(self.cadre, columns=('physique', 'licence', 'dec', 'soussigne', 'fob', 'articles', 'statut'),
                                  show='headings', selectmode='browse', height=12)
        for cle, titre, largeur in [('physique', 'Physique', 90), ('licence', 'Numéro licence', 225), ('dec', 'Numéro DEC', 130),
                                    ('soussigne', 'Soussigné', 240), ('fob', 'Montant FOB', 130), ('articles', 'Articles', 80),
                                    ('statut', 'Statut', 170)]:
            self.table.heading(cle, text=titre, anchor='center' if cle == 'physique' else 'w')
            self.table.column(cle, width=largeur, minwidth=largeur,
                              anchor='center' if cle == 'physique' else 'e' if cle in ('fob', 'articles') else 'w')
        self.table.tag_configure('pair', background='#F7F9FC')
        self.table.tag_configure('alerte', background=theme.FOND_ALERTE, foreground=theme.ALERTE)
        self.table.tag_configure('archivage', background=theme.FOND_OK, foreground=theme.OK)
        self.table.tag_configure('a_refaire', background=theme.FOND_ERREUR, foreground=theme.ERREUR)
        self.table.grid(row=0, column=0, sticky='nsew')
        vertical = ttk.Scrollbar(self.cadre, orient='vertical', command=self.table.yview)
        horizontal = ttk.Scrollbar(self.cadre, orient='horizontal', command=self.table.xview)
        vertical.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')
        self.table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.vide = ttk.Label(self.cadre, text='', justify='center', style='SousTitre.TLabel')
        pied = ttk.Frame(self)
        pied.pack(fill='x', pady=(14, 0))
        self.compteur = tk.StringVar()
        ttk.Label(pied, textvariable=self.compteur, style='Doux.TLabel').pack(side='left')
        self.bouton_ouvrir = theme.bouton(pied, 'Ouvrir le dossier →', self.ouvrir_selection, principal=True, state='disabled')
        self.bouton_ouvrir.pack(side='right')
        self.bouton_traitement = theme.bouton(pied, 'Traitement licence', self.traiter_selection, state='disabled')
        self.bouton_traitement.pack(side='right', padx=(0, 8))
        self.bouton_physique = theme.bouton(pied, f'{COCHE} En physique', self.basculer_selection, state='disabled')
        self.bouton_physique.pack(side='right', padx=(0, 8))
        # Suppression : clients, fournisseurs et articles de la licence restent proposés ailleurs.
        self.bouton_recommencer = theme.bouton(pied, 'Supprimer et recommencer', lambda: self._action(self.recommencer),
                                               state='disabled')
        self.bouton_recommencer.pack(side='right', padx=(0, 8))
        self.bouton_supprimer = theme.bouton(pied, 'Supprimer', lambda: self._action(self.supprimer), state='disabled')
        self.bouton_supprimer.pack(side='right', padx=(0, 8))
        self.recherche.trace_add('write', self.filtrer)
        self.table.bind('<<TreeviewSelect>>', self.selectionner)
        self.table.bind('<Button-1>', self.clic_case, add='+')
        self.table.bind('<space>', lambda _e: self.basculer_selection())
        self.table.bind('<Double-1>', self.ouvrir_selection)
        self.table.bind('<Return>', self.ouvrir_selection)

    def charger(self, licences, notification='', selection=None):
        self.licences = licences
        self.notification.set(notification)
        if notification:
            self.avis.pack(anchor='w', before=self.cadre, pady=(0, 12))
        else:
            self.avis.pack_forget()
        alertes = [l for l in licences if l.get('alerte') or l.get('numeros')]
        self.alertes.set('\n'.join(f"⚠ {l['numero']} — {l.get('alerte') or l['numeros']}."
                                   + (f"\n⚠ {l['numero']} — {l['numeros']}." if l.get('alerte') and l.get('numeros') else '')
                                   for l in alertes))
        if alertes:
            self.avis_alertes.pack(anchor='w', before=self.cadre, pady=(0, 12))
        else:
            self.avis_alertes.pack_forget()
        self.recherche.set('')
        en_attente = sum(l.get('statut') == finalisation.EN_ATTENTE_ARCHIVAGE for l in licences)
        self.total.set(f'{len(licences)} licence(s) ouverte(s)'
                       + (f' · {en_attente} en attente d’archivage' if en_attente else ''))
        self._compter_vues()
        self.filtrer()
        if selection:
            for i, licence in enumerate(licences):
                if licence['numero'] == selection:
                    self.table.selection_set(str(i))
                    self.table.see(str(i))
                    break
        self.selectionner()

    def filtrer(self, *_):
        self.table.delete(*self.table.get_children())
        terme = self.recherche.get().strip().casefold()
        vue = self.vue.get()
        for i, licence in enumerate(self.licences):
            if (vue == 'physique' and not licence.get('physique')) or (vue == 'a_traiter' and licence.get('physique')):
                continue
            if terme and terme not in ' '.join([str(licence[c]) for c in ('numero', 'numero_dec', 'soussigne')]
                                         + [finalisation.LIBELLES.get(licence.get('statut'), '')]).casefold():
                continue
            fob = nombre(Decimal(licence['montant_fob']), 2)
            numero = ('⚠ ' if licence.get('alerte') or licence.get('numeros') else '') + licence['numero']
            statut = licence.get('statut') or finalisation.EN_COURS
            etiquettes = (('a_refaire',) if statut == finalisation.A_REFAIRE or licence.get('numeros')
                          else ('archivage',) if statut == finalisation.EN_ATTENTE_ARCHIVAGE
                          else ('alerte',) if licence.get('alerte') else ('pair',) if i % 2 == 0 else ())
            self.table.insert('', 'end', iid=str(i), values=(libelle_physique(licence.get('physique')), numero, licence['numero_dec'],
                              licence['soussigne'], fob, licence['articles'],
                              'Numéros E/L/Q/M à corriger' if licence.get('numeros') else
                              ('📦 ' if statut == finalisation.EN_ATTENTE_ARCHIVAGE else '')
                              + finalisation.LIBELLES[statut]), tags=etiquettes)
        compte = len(self.table.get_children())
        self.compteur.set(f'{compte} résultat(s) · Double-cliquez pour ouvrir · cochez « Physique » '
                          'quand le dossier papier est imprimé.')
        if not compte:
            self.vide.configure(text='Aucun dossier en physique.' if self.licences and vue == 'physique' and not terme else
                                'Tous les dossiers sont en physique.' if self.licences and vue == 'a_traiter' and not terme else
                                'Aucun résultat pour cette recherche.' if self.licences else
                                'Aucune licence ouverte\n\nCliquez sur « Nouvelle licence » pour créer votre premier dossier.')
            self.vide.place(relx=.5, rely=.45, anchor='center')
        else:
            self.vide.place_forget()
        self.selectionner()

    def selectionner(self, *_):
        etat = 'normal' if self.table.selection() else 'disabled'
        self.bouton_ouvrir.configure(state=etat)
        self.bouton_traitement.configure(state=etat)
        selection = self.table.selection()
        physique = bool(selection and self.licences[int(selection[0])].get('physique'))
        self.bouton_physique.configure(state=etat if self.marquer_physique else 'disabled',
                                       text=f'{VIDE} Retirer du physique' if physique else f'{COCHE} En physique')
        self.bouton_supprimer.configure(state=etat if self.supprimer else 'disabled')
        self.bouton_recommencer.configure(state=etat if self.recommencer else 'disabled')

    def _action(self, commande):
        selection = self.table.selection()
        if selection and commande:
            commande(self.licences[int(selection[0])]['numero'])

    def ouvrir_selection(self, *_):
        selection = self.table.selection()
        if selection:
            self.ouvrir(self.licences[int(selection[0])]['numero'])

    def traiter_selection(self):
        selection = self.table.selection()
        if selection:
            self.traiter(self.licences[int(selection[0])]['numero'])

    def _compter_vues(self):
        physiques = sum(bool(l.get('physique')) for l in self.licences)
        comptes = dict(tous=len(self.licences), a_traiter=len(self.licences) - physiques, physique=physiques)
        for cle, (bouton, titre) in self.boutons_vue.items():
            bouton.configure(text=f'{titre} ({comptes[cle]})')

    def clic_case(self, evenement):
        """Un clic dans la colonne « Physique » coche ou décoche le dossier."""
        if self.table.identify_region(evenement.x, evenement.y) != 'cell' or self.table.identify_column(evenement.x) != '#1':
            return None
        ligne = self.table.identify_row(evenement.y)
        if ligne:
            self.basculer(int(ligne))
        return 'break'

    def basculer_selection(self):
        selection = self.table.selection()
        if selection:
            self.basculer(int(selection[0]))

    def basculer(self, indice):
        if not self.marquer_physique:
            return
        licence = self.licences[indice]
        valeur = self.marquer_physique(licence['numero'], not licence.get('physique'))
        if valeur is None:  # échec signalé par l'écran appelant
            return
        licence['physique'] = valeur
        self._compter_vues()
        self.filtrer()
        if str(indice) in self.table.get_children():
            self.table.selection_set(str(indice))
            self.table.see(str(indice))
