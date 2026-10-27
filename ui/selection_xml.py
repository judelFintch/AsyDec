"""Sélecteur commun des XML déjà disponibles : aucune boîte d'ouverture de fichier."""
import tkinter as tk
from tkinter import ttk
import service_references
from ui import theme


def choisir(parent, documents, multiple=False, titre='XML déjà disponibles'):
    fen=tk.Toplevel(parent)
    fen.title(titre)
    fen.geometry('970x480')
    fen.transient(parent.winfo_toplevel())
    fen.resultat=[]
    cadre=ttk.Frame(fen,padding=16)
    cadre.pack(fill='both',expand=True)
    ttk.Label(cadre,text=titre,style='Titre.TLabel').pack(anchor='w')
    ttk.Label(cadre,text='Choisissez les fichiers déjà conservés. Leur réutilisation ne change pas leur statut.',wraplength=900).pack(anchor='w',pady=8)
    recherche=tk.StringVar()
    ttk.Label(cadre,text='Rechercher par fichier ou importateur').pack(anchor='w')
    ttk.Entry(cadre,textvariable=recherche).pack(fill='x',pady=4)
    zone,tableau=theme.tableau(cadre,[('nom','Fichier',420,'w'),('importateur','Importateur',200,'w'),
                                    ('statut','Statut',140,'w'),('source','Origine',130,'w')],9)
    tableau.configure(selectmode='extended' if multiple else 'browse')
    zone.pack(fill='both',expand=True)
    message=tk.StringVar()
    ttk.Label(cadre,textvariable=message,style='Doux.TLabel').pack(anchor='w',pady=5)
    def filtrer(*args):
        tableau.delete(*tableau.get_children())
        mot=recherche.get().casefold().strip()
        for k,d in enumerate(documents):
            if mot and mot not in (d['nom']+' '+d['importateur']).casefold():
                continue
            tableau.insert('','end',iid=str(k),values=((f"[{d['id']}] " if d['id'] is not None else '')+d['nom'],d['importateur'],
                service_references.STATUTS.get(d['statut'],d['statut']),d['source']))
        message.set(f'{len(tableau.get_children())} XML disponible(s).'+(' Sélection multiple possible.' if multiple else ''))
    recherche.trace_add('write',filtrer)
    def valider(event=None):
        choix=tableau.selection()
        if not choix:
            return
        fen.resultat=[documents[int(k)]['chemin'] for k in choix]
        fen.destroy()
    barre=ttk.Frame(cadre)
    barre.pack(fill='x',pady=4)
    if multiple:
        theme.bouton(barre,'Tout sélectionner',lambda:tableau.selection_set(tableau.get_children())).pack(side='left')
    theme.bouton(barre,'Utiliser la sélection',valider,principal=True).pack(side='right')
    theme.bouton(barre,'Annuler',fen.destroy).pack(side='right',padx=8)
    tableau.bind('<Double-1>',valider)
    fen.bind('<Return>',valider)
    filtrer()
    fen.grab_set()
    parent.wait_window(fen)
    return fen.resultat
