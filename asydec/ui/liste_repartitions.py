"""Consultation des parts enregistrées : aucune modification des propositions."""
from decimal import Decimal
import tkinter as tk
from tkinter import ttk
from asydec.formats import nombre
from asydec.ui import theme


class ListeRepartitions(tk.Toplevel):
    def __init__(self, parent, parts, numero=None):
        super().__init__(parent)
        self.title('Répartitions réalisées')
        self.geometry('1000x560')
        self.minsize(750, 450)
        self.transient(parent.winfo_toplevel())
        self.parts = parts
        cadre = ttk.Frame(self, padding=20)
        cadre.pack(fill='both', expand=True)
        theme.entete_page(cadre, 'Répartitions réalisées', numero or 'Toutes les licences · Répartitions enregistrées')
        barre = ttk.Frame(cadre)
        barre.pack(fill='x', pady=(0, 12))
        ttk.Label(barre, text='Rechercher une licence, un DEC, un soussigné, une plaque ou un conteneur').pack(side='left')
        self.recherche = tk.StringVar()
        ttk.Entry(barre, textvariable=self.recherche, width=30).pack(side='right')
        zone = ttk.Frame(cadre)
        zone.pack(fill='both', expand=True)
        zone.rowconfigure(0, weight=1)
        zone.columnconfigure(0, weight=1)
        self.table = ttk.Treeview(zone, columns=('licence','dec','soussigne','part','fob','poids','plaque','conteneur','scelle','e','date_e','l','date_l','q','date_q','manifeste'), show='headings')
        for cle, titre, largeur in [('licence','Numéro licence',220), ('dec','Numéro DEC',120),
                                   ('soussigne','Soussigné',220), ('part','Part',60),
                                   ('fob','FOB (USD)',130), ('poids','Poids (kg)',110), ('plaque','Plaques proposées',240), ('conteneur','Conteneur',140), ('scelle','Scellé',110),
                                   ('e','Numéro E',120), ('date_e','Date E',110),
                                   ('l','Numéro liquidation',140), ('date_l','Date liquidation',120),
                                   ('q','Numéro Q',120), ('date_q','Date quittance',120), ('manifeste','Manifeste',160)]:
            self.table.heading(cle,text=titre,anchor='w')
            self.table.column(cle,width=largeur,minwidth=largeur,anchor='e' if cle in ('part','fob','poids') else 'w')
        self.table.grid(row=0,column=0,sticky='nsew')
        vertical=ttk.Scrollbar(zone,orient='vertical',command=self.table.yview)
        horizontal=ttk.Scrollbar(zone,orient='horizontal',command=self.table.xview)
        vertical.grid(row=0,column=1,sticky='ns')
        horizontal.grid(row=1,column=0,sticky='ew')
        self.table.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
        self.table.tag_configure('pair',background='#F7F9FC')
        self.resume=tk.StringVar()
        ttk.Label(cadre,textvariable=self.resume,style='Section.TLabel',wraplength=900).pack(anchor='w',pady=12)
        ttk.Label(cadre,text='Une ligne par part validée. Les totaux correspondent aux lignes affichées.',
                  style='Doux.TLabel').pack(anchor='w')
        theme.bouton(cadre,'Fermer',self.destroy).pack(anchor='e',pady=(12,0))
        self.recherche.trace_add('write',self.filtrer)
        self.filtrer()

    def filtrer(self,*_):
        self.table.delete(*self.table.get_children())
        terme=self.recherche.get().strip().casefold()
        visibles=[p for p in self.parts if not terme or terme in ' '.join(str(p.get(c,'')) for c in ('numero_licence','numero_dec','soussigne','plaque','conteneur','scelle')).casefold()]
        for i,part in enumerate(visibles):
            infos=part.get('informations_declaration', {})
            self.table.insert('','end',values=(part['numero_licence'],part['numero_dec'],part['soussigne'],part['part'],
                              nombre(Decimal(part['fob']),2),nombre(part['poids_kg']),part.get('plaque',''),
                              part.get('conteneur',''),part.get('scelle',''),
                              infos.get('numero_e',''),infos.get('date_enregistrement',''),
                              infos.get('numero_liquidation',''),infos.get('date_liquidation',''),
                              infos.get('numero_quittance',''),infos.get('date_quittance',''),infos.get('manifeste','')),tags=('pair',) if i%2==0 else ())
        if not visibles:
            self.resume.set('Aucune répartition enregistrée.' if not self.parts else 'Aucun résultat pour cette recherche.')
            return
        total=sum((Decimal(p['fob']) for p in visibles),Decimal(0))
        poids=sum(p['poids_kg'] for p in visibles)
        licences=len({p['numero_licence'] for p in visibles})
        self.resume.set(f'{licences} licence(s) · {len(visibles)} part(s) · FOB : {nombre(total,2)} USD · Poids : {nombre(poids)} kg')
