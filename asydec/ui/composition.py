"""Choisir le nombre d'articles et vérifier une composition manuelle ou automatique."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk

from asydec.calcul import composition, moteur
from asydec.ui import theme


class FenetreComposition(tk.Toplevel):
    def __init__(self, panneau):
        super().__init__(panneau)
        self.panneau, self.app = panneau, panneau.app
        self.title('Friperie · Composer un modèle')
        self.geometry('1080x650')
        cadre=ttk.Frame(self,padding=18)
        cadre.pack(fill='both',expand=True)
        theme.entete_page(cadre,'Composer un modèle Friperie',
            'Choisissez le nombre d’articles puis les variantes XML. Chaque variante conserve ses taxes et son ratio fixe. '
            'La sélection automatique est une proposition à vérifier avant de l’appliquer.')
        barre=ttk.Frame(cadre)
        barre.pack(fill='x',pady=8)
        ttk.Label(barre,text='Nombre d’articles').pack(side='left')
        self.nombre=tk.StringVar(value=str(len(self.app.info['fob_articles'])))
        ttk.Spinbox(barre,from_=1,to=999,textvariable=self.nombre,width=6).pack(side='left',padx=8)
        theme.bouton(barre,'Sélection automatique',self.automatique).pack(side='left',padx=6)
        theme.bouton(barre,'Vider la sélection',self.vider).pack(side='left',padx=6)
        theme.bouton(barre,'Reprendre la base classique du dossier',self.revenir).pack(side='right')
        ttk.Label(cadre,text='Sélection manuelle : cliquez sur une ligne pour la cocher ou la décocher.',style='Doux.TLabel').pack(anchor='w')
        bas=ttk.Frame(cadre)
        bas.pack(side='bottom',fill='x')
        self.message=theme.Message(bas)
        self.message.pack(fill='x',pady=8)
        theme.bouton(bas,'Appliquer la composition',self.appliquer,principal=True).pack(side='right')
        theme.bouton(bas,'Annuler',self.destroy).pack(side='right',padx=8)
        zone,self.table=theme.tableau(cadre,[('choix','Choix',50,'center'),('code','Position tarifaire',130,'w'),
            ('nom','Marchandise',220,'w'),('ratio','Ratio fixe',100,'e'),('taxes','Taux de taxes',210,'w'),('source','XML de référence',250,'w')],12)
        zone.pack(fill='both',expand=True,pady=10)
        self.table.bind('<ButtonRelease-1>',self.basculer)
        self.selection=[]
        self.entrees={}
        try:
            chemins=list(self.app.chemins_xml_disponibles(generation=True))
            base=getattr(self.app,'base_dossier',None) or self.app.base
            if str(base) not in map(str,chemins):
                chemins.append(base)
            devise=moteur._txt(moteur.charger(base).getroot(),'Valuation/Gs_Invoice/Currency_code')
            self.entrees={k:e for k,e in composition.catalogue(chemins).items() if e['devise']==devise}
            for k,e in self.entrees.items():
                taxes=' · '.join(f'{t} {v:g}' for t,v in e['taxes'].items())
                self.table.insert('','end',iid=k,values=('',e['code'],e['designation'],f"{e['ratio']:.8g}",taxes,
                    f"{Path(e['source']).name} · art. {e['rang']}"))
            self.message.afficher('ok',f'{len({e["article"] for e in self.entrees.values()})} articles disponibles',
                ['Les quantités initiales viennent des variantes choisies. Les totaux pourront ensuite être saisis dans Articles.'])
        except Exception as exc:
            self.message.afficher('erreur','Catalogue indisponible',[str(exc)])

    def rafraichir(self):
        for k in self.entrees:
            self.table.set(k,'choix','✓' if k in self.selection else '')

    def basculer(self, evenement):
        if self.app.session_verrouillee:
            return
        k=self.table.identify_row(evenement.y)
        if not k:
            return
        if k in self.selection:
            self.selection.remove(k)
        else:
            self.selection=[s for s in self.selection if self.entrees[s]['article']!=self.entrees[k]['article']]+[k]
        self.rafraichir()
        self.message.afficher('ok',f'{len(self.selection)} article(s) sélectionné(s)')

    def vider(self):
        self.selection=[]
        self.rafraichir()

    def automatique(self):
        if self.app.session_verrouillee:
            return
        try:
            self.selection=[e['id'] for e in composition.choisir_automatiquement(self.entrees,int(self.nombre.get()))]
            self.rafraichir()
            self.message.afficher('ok',f'{len(self.selection)} articles proposés', ['Vérifiez les taxes, ratios et XML sources avant d’appliquer.'])
        except Exception as exc:
            self.message.afficher('erreur','Sélection impossible',[str(exc)])

    def appliquer(self):
        if self.app.session_verrouillee:
            return
        try:
            choix=[self.entrees[k] for k in self.selection]
            composition.verifier(choix,int(self.nombre.get()))
            self.app.appliquer_composition(choix,int(self.nombre.get()))
            self.destroy()
        except Exception as exc:
            self.message.afficher('erreur','Composition non appliquée',[str(exc)])

    def revenir(self):
        if self.app.session_verrouillee:
            return
        try:
            self.app.appliquer_composition(None,None)
            self.destroy()
        except Exception as exc:
            self.message.afficher('erreur','Retour impossible',[str(exc)])
