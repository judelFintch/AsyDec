"""Présentation des propositions : indicateurs et tableaux, sans sortie console."""
import tkinter as tk
from tkinter import ttk

from asydec.calcul import moteur
from asydec.calcul import variantes
from asydec.formats import nombre


class VueSimulation(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=8)
        style=ttk.Style(self)
        style.configure('Simulation.Treeview',rowheight=28,font=('Arial',11))
        style.configure('Simulation.Treeview.Heading',font=('Arial',11,'bold'))
        self.titre=tk.StringVar(value='Sélectionnez une proposition pour consulter sa répartition')
        ttk.Label(self,textvariable=self.titre,font=('Arial',12,'bold'),wraplength=1050).pack(anchor='w',pady=(0,6))
        indicateurs=ttk.Frame(self)
        indicateurs.pack(fill='x',pady=4)
        self.indicateurs={}
        for k,(cle,libelle) in enumerate((('poids','Poids total · kg'),('fob','FOB total · USD'),('colis','Colis'),('taxes','Taxes estimées · CDF'),('score','Proximité · /100'))):
            indicateurs.columnconfigure(k,weight=1,uniform='indicateurs')
            carte=ttk.LabelFrame(indicateurs,text=libelle,padding=7)
            carte.grid(row=0,column=k,sticky='nsew',padx=3)
            valeur=tk.StringVar(value='—')
            ttk.Label(carte,textvariable=valeur,font=('Arial',16,'bold')).pack(anchor='w')
            self.indicateurs[cle]=valeur
        self.statut=tk.StringVar(value='Les détails apparaîtront après la recherche.')
        ttk.Label(self,textvariable=self.statut,wraplength=1050).pack(anchor='w',pady=5)
        grille=ttk.Frame(self)
        grille.pack(fill='both',expand=True)
        grille.columnconfigure(0,weight=1)
        grille.rowconfigure(0,weight=1)
        colonnes=[('article','Art.',45),('nom','Marchandise',250),('poids','Poids kg',95),('fob','FOB USD',100),
                  ('colis','Colis',65),('ratio','Ratio obtenu',105),('regle','Ratio de référence / bornes',190),('etat','Contrôle',125)]
        self.tableau=ttk.Treeview(grille,columns=[c[0] for c in colonnes],show='headings',height=8,style='Simulation.Treeview')
        for cle,titre,largeur in colonnes:
            self.tableau.heading(cle,text=titre)
            self.tableau.column(cle,width=largeur,minwidth=45,anchor='w' if cle in ('nom','regle','etat') else 'e',stretch=cle=='nom')
        self.tableau.grid(row=0,column=0,sticky='nsew')
        vertical=ttk.Scrollbar(grille,orient='vertical',command=self.tableau.yview)
        vertical.grid(row=0,column=1,sticky='ns')
        horizontal=ttk.Scrollbar(grille,orient='horizontal',command=self.tableau.xview)
        horizontal.grid(row=1,column=0,sticky='ew')
        self.tableau.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
        self.tableau.tag_configure('total',font=('Arial',11,'bold'))
        ttk.Label(self,text='Ratios vérifiés après arrondi au centime. La proximité mesure la ressemblance aux références et les écarts des ratios ajustables, sans garantie d’optimum.',wraplength=1050).pack(anchor='w',pady=(5,0))
        ttk.Label(self,text='Les taxes utilisent les taux et frais du XML de référence ; elles seront recalculées avec le dossier réel.',wraplength=1050).pack(anchor='w',pady=(0,4))
        notes=ttk.LabelFrame(self,text='Informations et points à vérifier',padding=3)
        notes.pack(fill='x')
        self.notes=ttk.Treeview(notes,columns=('message',),show='headings',height=2)
        self.notes.heading('message',text='Détail (sélectionnez une ligne pour lire le message complet)')
        self.notes.column('message',width=900)
        self.notes.pack(side='left',fill='both',expand=True)
        scroll=ttk.Scrollbar(notes,orient='vertical',command=self.notes.yview)
        scroll.pack(side='right',fill='y')
        self.notes.configure(yscrollcommand=scroll.set)
        self.message=tk.StringVar()
        ttk.Label(self,textvariable=self.message,wraplength=1050).pack(anchor='w')
        self.notes.bind('<<TreeviewSelect>>',self._selection_note)

    def _selection_note(self,event=None):
        choix=self.notes.selection()
        self.message.set(self.notes.item(choix[0],'values')[0] if choix else '')

    def afficher(self,v,profil,reference,ecartes=(),numero=None):
        variantes.controler(v,profil)
        self.titre.set((f'Proposition {numero} — ' if numero is not None else 'Proposition — ')+reference)
        r=v['resultat']['resume']
        valeurs={'poids':nombre(sum(v['poids'])),'fob':nombre(sum(v['fob']),2),'colis':nombre(sum(v['colis'])),
                 'taxes':nombre(r['taxes_totales']),'score':nombre(v.get('proximite',variantes.evaluer(v,profil)['proximite']),2)}
        for cle,valeur in valeurs.items():
            self.indicateurs[cle].set(valeur)
        self.statut.set('8 articles contrôlés · Poids entiers · Totaux respectés · Colis à confirmer avec le colisage réel')
        self.tableau.delete(*self.tableau.get_children())
        noms=v['resultat']['info'].get('designations',[])
        for k in range(8):
            bas,haut=profil['bornes'][k]
            fixe=k in moteur.ARTICLES_VARIABLES
            ajustable=fixe and profil.get('variables_libres')
            ecart=(v['fob'][k]/v['poids'][k]/profil['ratios'][k]-1)*100
            self.tableau.insert('','end',values=(k+1,noms[k] if k<len(noms) else f'Article {k+1}',
                nombre(v['poids'][k]),nombre(v['fob'][k],2),nombre(v['colis'][k]),nombre(v['fob'][k]/v['poids'][k],6),
                ('Ajustable · réf. '+nombre(profil['ratios'][k],6)) if ajustable else ('Fixe : '+nombre(bas,6)) if fixe else nombre(bas,6)+' à '+nombre(haut,6),
                (f'Écart {ecart:+.1f} %') if ajustable else 'Fixe respecté' if fixe else 'Dans les bornes'))
        self.tableau.insert('','end',values=('','TOTAL',valeurs['poids'],valeurs['fob'],valeurs['colis'],'','',''),tags=('total',))
        self.notes.delete(*self.notes.get_children())
        self.message.set('')
        messages=list(v['resultat'].get('alertes',[]))+list(ecartes)
        if len(profil['references'])==1:
            messages.insert(0,'Une seule référence compatible : les fourchettes sont réduites à un ratio unique.')
        for message in messages or ['Aucun autre signal dans les contrôles effectués.']:
            self.notes.insert('','end',values=(message,))
