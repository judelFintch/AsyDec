"""Liste persistante des propositions, avec validation locale explicite."""
from datetime import datetime
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
import modeles_generes as service
from ui import theme
from ui.theme import nombre


def date_locale(valeur):
    return datetime.fromisoformat(valeur).astimezone().strftime('%d/%m/%Y %H:%M:%S')


class PageModelesGeneres(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.modeles = {}
        theme.entete_page(self, 'Modèles générés',
            'Propositions conservées et XML exportés depuis cette fonctionnalité. '
            'La validation est locale ; elle ne signifie pas une acceptation douanière. '
            'Les anciens exports restent consultables dans Historique.')
        barre = ttk.Frame(self)
        barre.pack(fill='x', pady=8)
        self.filtre = ttk.Combobox(barre,state='readonly',values=['Tous']+list(service.STATUTS.values()),width=24)
        self.filtre.set('En attente')
        self.filtre.pack(side='left',padx=4)
        self.filtre.bind('<<ComboboxSelected>>',lambda e:self.afficher())
        for texte, action in [('Actualiser',self.afficher),('Consulter',self.consulter),
                              ('Comparer avec un XML…',self.comparer)]:
            theme.bouton(barre,texte,action).pack(side='left',padx=4)
        actions=ttk.Frame(self)
        actions.pack(fill='x',pady=(0,8))
        for statut in service.STATUTS:
            theme.bouton(actions,service.STATUTS[statut],lambda s=statut:self.changer(s)).pack(side='left',padx=4)
        self.message=theme.Message(self)
        self.message.pack(fill='x',pady=6)
        cadre,self.table=theme.tableau(self,[
            ('id','N°',50,'e'),('date','Créé le',155,'w'),('modifie','Dernier événement',155,'w'),
            ('importateur','Importateur',180,'w'),('statut','Validation locale',160,'w'),
            ('fob','FOB USD',110,'e'),('poids','Poids kg',100,'e'),('colis','Colis',75,'e')],16)
        cadre.pack(fill='both',expand=True)
        self.table.bind('<Double-1>',lambda e:self.consulter())

    def afficher(self):
        try:
            filtre=next((k for k,v in service.STATUTS.items() if v==self.filtre.get()),None)
            lignes=service.lister(filtre)
        except Exception as exc:
            self.message.afficher('erreur','Liste indisponible',[str(exc)])
            return
        self.modeles={str(m['id']):m for m in lignes}
        self.table.delete(*self.table.get_children())
        for identifiant,m in self.modeles.items():
            r=m['resultat']
            self.table.insert('','end',iid=identifiant,values=(identifiant,date_locale(m['cree_utc']),date_locale(m['modifie_utc']),
                m['importateur'],service.STATUTS[m['statut']],nombre(r['resume']['fob'],2),
                nombre(r['resume']['poids']),sum(r['colis'])))
        self.message.afficher('ok',f'{len(lignes)} modèle(s) dans cette liste',
            ['Depuis Vérifier et générer, utilisez « Enregistrer la proposition » ; un export XML est aussi ajouté automatiquement.'])

    def selection(self):
        choix=self.table.selection()
        return int(choix[0]) if choix else None

    def consulter(self):
        if self.app.session_verrouillee:
            return
        identifiant=self.selection()
        if identifiant is None:
            return
        try:
            d=service.detail(identifiant)
        except Exception as exc:
            messagebox.showerror('Modèle indisponible',str(exc),parent=self)
            return
        fen=tk.Toplevel(self)
        fen.title(f'Modèle conservé n° {identifiant}')
        fen.geometry('1020x650')
        cadre=ttk.Frame(fen,padding=16)
        cadre.pack(fill='both',expand=True)
        theme.entete_page(cadre,f"Modèle n° {identifiant} · {service.STATUTS[d['statut']]}",
            f"{d['importateur']} · créé le {date_locale(d['cree_utc'])} par {d['auteur']}. Validation locale uniquement.")
        zone,table=theme.tableau(cadre,[('art','Art.',50,'e'),('poids','Poids kg',100,'e'),
            ('fob','FOB USD',120,'e'),('colis','Colis',80,'e'),('ratio','Ratio FOB/kg',130,'e'),
            ('cif','CIF CDF',140,'e'),('taxes','Taxes CDF',140,'e')],9)
        zone.pack(fill='x',pady=8)
        r=d['resultat']
        from import_references import extraire
        sources=[a for a in extraire(d['base_xml'])['articles'] if a['fob'] is not None and float(a['fob'])!=0]
        for source,a,colis in zip(sources,r['resume']['articles'],r['colis']):
            table.insert('','end',values=(source['position'],nombre(a['poids']),nombre(a['fob'],2),colis,
                nombre(a['fob']/a['poids'],4) if a['poids']>0 else '—',nombre(a['cif']),nombre(a['taxes'])))
        texte=tk.Text(cadre,height=9,wrap='word',font=(theme.POLICE,11))
        texte.pack(fill='both',expand=True)
        texte.insert('1.0','\n'.join(f"{date_locale(e['date_utc'])} · {e['auteur']} · "
            f"{service.STATUTS.get(e['statut'], e['action'])} · {e['detail']}" for e in d['evenements']))
        texte.configure(state='disabled')
        theme.bouton(cadre,'Fermer',fen.destroy).pack(anchor='e',pady=8)

    def changer(self,statut):
        if self.app.session_verrouillee:
            return
        identifiant=self.selection()
        if identifiant is None:
            return
        if not messagebox.askyesno('Validation locale',
            f"Modèle n° {identifiant} : {service.STATUTS[statut]} ?\n"
            "Ce statut est interne à l'outil et ne prouve aucune acceptation douanière.",parent=self):
            return
        commentaire=simpledialog.askstring('Commentaire de validation locale',
            'Motif obligatoire pour un rejet, commentaire facultatif sinon :',parent=self)
        if commentaire is None or self.app.session_verrouillee:
            return
        try:
            service.changer_statut(identifiant,statut,self.app.utilisateur,commentaire)
        except Exception as exc:
            messagebox.showerror('Statut non modifié',str(exc),parent=self)
            return
        self.afficher()

    def comparer(self):
        if self.app.session_verrouillee:
            return
        identifiant=self.selection()
        if identifiant is None:
            return
        chemin=filedialog.askopenfilename(parent=self,title='Comparer le modèle conservé avec un XML',filetypes=[('XML','*.xml')])
        if not chemin:
            return
        try:
            from comparaison_prediction import comparer
            from ui.comparaison import afficher
            d=service.detail(identifiant)
            with tempfile.TemporaryDirectory(prefix='asydec-comparaison-') as temp:
                source=Path(temp)/'base.xml'
                source.write_bytes(d['base_xml'])
                rapport=comparer(d['resultat'],source,chemin)
            afficher(self,rapport)
        except Exception as exc:
            messagebox.showerror('Comparaison impossible',str(exc),parent=self)
