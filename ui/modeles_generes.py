"""Liste persistante des propositions, avec validation locale explicite."""
from datetime import datetime
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
import export_pdf
import modeles_generes as service
from ui import theme
from ui.theme import nombre


def rangement(app,importateur,cle):
    """Sous-dossier de rangement de l'importateur (créé au besoin), ou None."""
    if not importateur:
        return None
    try:
        import generer
        return generer.dossier_rangement(importateur,cle,getattr(app,'table_imp',None))
    except Exception:  # noqa: BLE001 - la fenêtre s'ouvrira à l'emplacement habituel
        return None


def ecart_court(m):
    """Dernier écart de taxes (comparé − estimé), avec le nombre de comparaisons."""
    if not m.get('comparaisons'):
        return 'Non comparé'
    ecart=m.get('dernier_ecart')
    if ecart is None:
        return f"Comparé ({m['comparaisons']})"
    fleche='=' if ecart==0 else ('▲' if ecart>0 else '▼')
    return f"{fleche} {nombre(abs(ecart))} ({m['comparaisons']})"


STATUTS_COURTS={'en_attente':'En attente','valide':'Validé','rejete':'Rejeté'}


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
        self.filtre = ttk.Combobox(barre,state='readonly',values=['Tous']+list(service.STATUTS.values())+['Bons modèles ★','Supprimés'],width=24)
        self.filtre.set('Tous')
        self.filtre.pack(side='left',padx=4)
        self.filtre.bind('<<ComboboxSelected>>',lambda e:self.afficher())
        for texte, action in [('Actualiser',self.afficher),('Détails…',self.consulter),('Ouvrir le dossier',self.ouvrir_dossier)]:
            theme.bouton(barre,texte,action).pack(side='left',padx=4)
        self.comparer_bouton=theme.bouton(barre,'Comparer avec un XML…',self.comparer,state='disabled')
        self.comparer_bouton.pack(side='left',padx=4)
        self.pdf_bouton=theme.bouton(barre,'Imprimer en PDF…',self.imprimer,state='disabled')
        self.pdf_bouton.pack(side='left',padx=4)
        actions=ttk.Frame(self)
        actions.pack(fill='x',pady=(0,8))
        self.xml_bouton=theme.bouton(actions,'Télécharger le XML…',self.telecharger_xml,state='disabled')
        self.xml_bouton.pack(side='right',padx=4)
        self.plaque_bouton=theme.bouton(actions,'Plaque…',self.saisir_plaque,state='disabled')
        self.plaque_bouton.pack(side='right',padx=4)
        self.bon_bouton=theme.bouton(actions,'☆ Cocher bon modèle',self.basculer_bon,state='disabled')
        self.bon_bouton.pack(side='right',padx=4)
        self.supprimer_bouton=theme.bouton(actions,'Supprimer…',self.supprimer,state='disabled')
        self.supprimer_bouton.pack(side='right',padx=4)
        theme.bouton(actions,'Reprendre pour modifier',self.reprendre).pack(side='right',padx=4)
        for statut in service.STATUTS:
            theme.bouton(actions,service.STATUTS[statut],lambda s=statut:self.changer(s)).pack(side='left',padx=4)
        self.message=theme.Message(self)
        self.message.pack(fill='x',pady=6)
        # Colonnes lisibles d'un coup d'œil ; le reste est dans le panneau « Modèle sélectionné ».
        cadre,self.table=theme.tableau(self,[
            ('bon','★',30,'center'),('id','N°',45,'e'),('plaque','Plaque',140,'w'),('importateur','Importateur',190,'w'),
            ('statut','Statut',95,'center'),('compare','Écart taxes comparé',150,'e'),('fob','FOB USD',95,'e'),
            ('poids','Poids kg',85,'e'),('taxes','Taxes CDF',110,'e'),('fichier','Fichier XML généré',230,'w')],12)
        cadre.pack(fill='both',expand=True)
        self.table.tag_configure('valide',foreground=theme.OK)
        self.table.tag_configure('rejete',foreground=theme.TEXTE_DOUX)
        self.resume=ttk.LabelFrame(self,text='Modèle sélectionné',padding=10)
        self.resume.pack(fill='x',pady=(8,0))
        self.var_resume=tk.StringVar(value='Sélectionnez un modèle pour voir ses informations.')
        ttk.Label(self.resume,textvariable=self.var_resume,justify='left',wraplength=1100).pack(anchor='w')
        self.table.bind('<Double-1>',lambda e:self.consulter())
        self.table.bind('<<TreeviewSelect>>',lambda e:(self.actualiser_comparaison(),self.afficher_resume()))

    def afficher(self):
        try:
            filtre=next((k for k,v in service.STATUTS.items() if v==self.filtre.get()),None)
            supprimes=self.filtre.get()=='Supprimés'
            lignes=service.lister(filtre,supprimes=supprimes)
            if self.filtre.get()=='Bons modèles ★':
                lignes=[m for m in lignes if m['bon']]
        except Exception as exc:
            self.message.afficher('erreur','Liste indisponible',[str(exc)])
            return
        self.modeles={str(m['id']):m for m in lignes}
        self.comparer_bouton.configure(state='disabled')
        self.pdf_bouton.configure(state='disabled')
        self.xml_bouton.configure(state='disabled')
        self.plaque_bouton.configure(state='disabled')
        self.bon_bouton.configure(state='disabled',text='☆ Cocher bon modèle')
        self.supprimer_bouton.configure(state='disabled',text='Restaurer' if supprimes else 'Supprimer…')
        self.table.delete(*self.table.get_children())
        for identifiant,m in self.modeles.items():
            r=m['resultat']
            self.table.insert('','end',iid=identifiant,tags=(m['statut'],),values=('★' if m['bon'] else '',identifiant,m['plaque'] or '—',
                m['importateur'],STATUTS_COURTS[m['statut']],ecart_court(m),
                nombre(r['resume']['fob'],2),nombre(r['resume']['poids']),nombre(r['resume'].get('taxes_totales')),
                Path(m['chemin_xml']).name if m['chemin_xml'] else '—'))
        self.var_resume.set('Sélectionnez un modèle pour voir ses informations.')
        self.message.afficher('ok',f'{len(lignes)} modèle(s) dans cette liste',
            ['Depuis Vérifier et générer, utilisez « Enregistrer la proposition » ; un export XML est aussi ajouté automatiquement.'])

    def actualiser_comparaison(self):
        identifiant=self.selection()
        modele=self.modeles.get(str(identifiant),{})
        libre=not self.app.session_verrouillee
        self.comparer_bouton.configure(state='normal' if modele.get('exporte') and libre else 'disabled')
        self.pdf_bouton.configure(state='normal' if modele.get('statut')=='valide' and libre else 'disabled')
        self.xml_bouton.configure(state='normal' if modele.get('statut')=='valide' and libre else 'disabled')
        self.plaque_bouton.configure(state='normal' if modele.get('statut')=='valide' and libre else 'disabled')
        self.supprimer_bouton.configure(state='normal' if modele and libre else 'disabled')
        if hasattr(self,'bon_bouton'):
            self.bon_bouton.configure(state='normal' if modele and libre and not modele.get('supprime') else 'disabled',
                text='★ Retirer la coche' if modele.get('bon') else '☆ Cocher bon modèle')

    def afficher_resume(self):
        m=self.modeles.get(str(self.selection()))
        if not m:
            self.var_resume.set('Sélectionnez un modèle pour voir ses informations.')
            return
        r=m['resultat']['resume']
        compare=(f"Comparé {m['comparaisons']} fois, dernière le {date_locale(m['compare_utc'])}"
                 + (f" · écart du total des taxes {nombre(m['dernier_ecart'])} CDF" if m.get('dernier_ecart') is not None else '')
                 if m['comparaisons'] else 'Jamais comparé avec un XML')
        self.var_resume.set('\n'.join((
            f"{'★ Bon modèle · ' if m['bon'] else ''}N° {m['id']} · {m['importateur']} · plaque {m['plaque'] or '—'} · {service.STATUTS[m['statut']]}",
            f"FOB {nombre(r['fob'],2)} USD · poids {nombre(r['poids'])} kg · colis {nombre(sum(m['resultat']['colis']))} · "
            f"total taxes estimé {nombre(r.get('taxes_totales'))} CDF",
            f"Créé le {date_locale(m['cree_utc'])} par {m['auteur']} · dernier événement le {date_locale(m['modifie_utc'])} · {compare}",
            f"Fichier XML généré : {m['chemin_xml'] or 'aucun (proposition non exportée)'}")))

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
            f"{d['importateur']} · plaque {d['plaque'] or '—'} · créé le {date_locale(d['cree_utc'])} par {d['auteur']}. "
            f"{self.texte_comparaisons(d)} Validation locale uniquement.")
        chemin_xml,etat_xml=service.fichier_xml_genere(d)
        ttk.Label(cadre,text=f"Fichier XML généré : {Path(chemin_xml).name if chemin_xml else '—'}",
            style='Section.TLabel').pack(anchor='w',pady=(6,0))
        alerte={'foreground':'#B91C1C'} if 'MODIFIÉ' in etat_xml or 'introuvable' in etat_xml else {}
        ttk.Label(cadre,text=f"{chemin_xml} · {etat_xml}" if chemin_xml else etat_xml,
            wraplength=960,**alerte).pack(anchor='w')
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
            f"{service.resume_evenement(e)}" for e in d['evenements']))
        texte.configure(state='disabled')
        boutons=ttk.Frame(cadre)
        boutons.pack(fill='x',pady=8)
        theme.bouton(boutons,'Fermer',fen.destroy).pack(side='right')
        theme.bouton(boutons,'Détails des taxes…',lambda:self.details_taxes(d,fen)).pack(side='right',padx=8)
        theme.bouton(boutons,'Comparaisons enregistrées…',lambda:self.voir_comparaisons(d,fen),
            state='normal' if any(e['action']=='comparaison' for e in d['evenements']) else 'disabled').pack(side='right',padx=8)
        theme.bouton(boutons,'Reprendre pour modifier',lambda:self.reprendre(identifiant,fen)).pack(side='right',padx=8)
        if d['statut']=='valide':
            theme.bouton(boutons,'Télécharger le XML…',lambda:self.telecharger_xml(identifiant,fen)).pack(side='right',padx=8)
            theme.bouton(boutons,'Plaque…',lambda:self.saisir_plaque(identifiant,fen)).pack(side='right',padx=8)
            theme.bouton(boutons,'Imprimer en PDF…',lambda:self.imprimer(identifiant,fen)).pack(side='right',padx=8)

    def ouvrir_dossier(self):
        """Ouvre dans le Finder le dossier de l'importateur du modèle sélectionné."""
        modele=self.modeles.get(str(self.selection()))
        if not modele:
            return
        dossier=rangement(self.app,modele['importateur'],'historique')
        if dossier:
            import subprocess
            subprocess.run(['open',str(Path(dossier).parent)],check=False)

    def voir_comparaisons(self,d,parent=None):
        """Liste des comparaisons conservées ; double-clic : la fenêtre de comparaison telle qu'enregistrée."""
        if self.app.session_verrouillee:
            return
        liste=service.comparaisons(d)
        fen=tk.Toplevel(parent or self)
        fen.title(f"Comparaisons enregistrées · modèle n° {d['id']}")
        fen.geometry('1100x420')
        cadre=ttk.Frame(fen,padding=16)
        cadre.pack(fill='both',expand=True)
        theme.entete_page(cadre,f"Comparaisons du modèle n° {d['id']}",
            'Double-cliquez une ligne pour revoir la comparaison complète : répartition et total des taxes.')
        zone,table=theme.tableau(cadre,[('date','Date',150,'w'),('fichier','Fichier comparé',360,'w'),
            ('estime','Total taxes estimé',150,'e'),('compare','Total taxes comparé',150,'e'),
            ('ecart','Écart CDF',130,'e'),('auteur','Par',90,'w')],10)
        zone.pack(fill='both',expand=True)
        for k,c in enumerate(liste):
            table.insert('','end',iid=str(k),values=(date_locale(c['date_utc']),Path(c['fichier']).name,
                nombre(c['total_estime']),nombre(c['total_compare']),nombre(c['ecart_total']),c['auteur']))
        def revoir(_e=None):
            choix=table.selection()
            if not choix:
                return
            c=liste[int(choix[0])]
            if not c['rapport']:
                messagebox.showinfo('Comparaison ancienne',
                    'Cette comparaison date d’avant l’enregistrement complet : seuls ses totaux sont conservés.',parent=fen)
                return
            from ui.comparaison import afficher
            rapport=dict(c['rapport'])
            rapport['source']=f"{rapport.get('source','XML généré')} · comparaison du {date_locale(c['date_utc'])}"
            afficher(fen,rapport)
        table.bind('<Double-1>',revoir)
        boutons=ttk.Frame(cadre)
        boutons.pack(fill='x',pady=8)
        theme.bouton(boutons,'Fermer',fen.destroy).pack(side='right')
        theme.bouton(boutons,'Revoir la comparaison',revoir,principal=True).pack(side='right',padx=8)
        if liste:
            table.selection_set('0')
        return fen

    def details_taxes(self,d,parent=None):
        if self.app.session_verrouillee:
            return
        try:
            lignes,explication=service.detail_taxes_modele(d)
        except Exception as exc:
            messagebox.showerror('Détails des taxes indisponibles',str(exc),parent=parent or self)
            return
        if not lignes:
            messagebox.showinfo('Détails des taxes','Aucune ligne de taxe dans ce XML.',parent=parent or self)
            return
        from ui.comparaison import afficher_taxes
        afficher_taxes(parent or self,{'taxes_detail':lignes},explication)

    @staticmethod
    def texte_comparaisons(d):
        dates=[date_locale(e['date_utc']) for e in d['evenements'] if e['action']=='comparaison']
        return f"Comparé {len(dates)} fois, dernière le {dates[-1]}." if dates else 'Jamais comparé avec un XML.'

    def basculer_bon(self):
        """Coche ou décoche « bon modèle » : oriente les répartitions proposées, sans valider quoi que ce soit."""
        if self.app.session_verrouillee:
            return
        identifiant=self.selection()
        if identifiant is None:
            return
        modele=self.modeles.get(str(identifiant),{})
        try:
            service.marquer_bon(identifiant,self.app.utilisateur,not modele.get('bon'))
        except Exception as exc:
            messagebox.showerror('Action impossible',str(exc),parent=self)
            return
        self.afficher()
        if self.table.exists(str(identifiant)):
            self.table.selection_set(str(identifiant))

    def supprimer(self):
        if self.app.session_verrouillee:
            return
        identifiant=self.selection()
        if identifiant is None:
            return
        modele=self.modeles.get(str(identifiant),{})
        try:
            if modele.get('supprime'):
                service.restaurer(identifiant,self.app.utilisateur)
            else:
                if not messagebox.askyesno('Supprimer le modèle',
                    f"Supprimer le modèle n° {identifiant} de la liste ?\n\n"
                    "Il n'apparaîtra plus dans Modèles générés. Rien n'est effacé : le XML exporté, "
                    "les fichiers et l'historique sont conservés, et le modèle peut être restauré "
                    "depuis le filtre « Supprimés ».",icon='warning',parent=self):
                    return
                motif=simpledialog.askstring('Motif de suppression','Motif (facultatif) :',parent=self)
                if motif is None or self.app.session_verrouillee:
                    return
                service.supprimer(identifiant,self.app.utilisateur,motif)
        except Exception as exc:
            messagebox.showerror('Action impossible',str(exc),parent=self)
            return
        self.afficher()

    def saisir_plaque(self,identifiant=None,parent=None):
        if self.app.session_verrouillee:
            return
        identifiant=identifiant if identifiant is not None else self.selection()
        if identifiant is None:
            return
        parent=parent or self
        try:
            d=service.detail(identifiant)
            if d['statut']!='valide':
                raise ValueError('La plaque se saisit sur un modèle Validé localement.')
        except Exception as exc:
            messagebox.showerror('Plaque indisponible',str(exc),parent=parent)
            return
        plaque=simpledialog.askstring('Plaque du camion',
            f"Modèle n° {identifiant} : plaque du camion (ex. T546ECQ/T618ECT) :",initialvalue=d['plaque'],parent=parent)
        if plaque is None or self.app.session_verrouillee:
            return
        try:
            service.definir_plaque(identifiant,plaque,self.app.utilisateur)
        except Exception as exc:
            messagebox.showerror('Plaque non enregistrée',str(exc),parent=parent)
            return
        self.afficher()
        if self.table.exists(str(identifiant)):
            self.table.selection_set(str(identifiant))

    def reprendre(self,identifiant=None,parent=None):
        if self.app.session_verrouillee:
            return
        identifiant=identifiant if identifiant is not None else self.selection()
        if identifiant is None:
            return
        try:
            d=service.detail(identifiant)
            r=d['resultat']
            repartition={'poids':[a['poids'] for a in r['resume']['articles']],
                         'fob':[a['fob'] for a in r['resume']['articles']], 'colis':r['colis']}
            from ui.reprise_modele import reprendre
            if reprendre(self.app,d['base_xml'],d['nom'],parent=parent or self,repartition=repartition):
                # La plaque du modèle repris est proposée ; l'utilisateur peut l'effacer.
                dossier=getattr(self.app,'pages',{}).get('dossier')
                if dossier is not None and d.get('plaque'):
                    dossier.var_plaque.set(d['plaque'])
                if parent is not None:
                    parent.destroy()
        except Exception as exc:
            messagebox.showerror('Reprise impossible',str(exc),parent=parent or self)

    def telecharger_xml(self,identifiant=None,parent=None):
        if self.app.session_verrouillee:
            return
        identifiant=identifiant if identifiant is not None else self.selection()
        if identifiant is None:
            return
        parent=parent or self
        try:
            d=service.detail(identifiant)
            if d['statut']!='valide':
                raise ValueError('Seul un modèle Validé localement peut être téléchargé en XML.')
            nom=service.nom_export(d)
        except Exception as exc:
            messagebox.showerror('XML indisponible',str(exc),parent=parent)
            return
        options={'initialdir':dossier} if (dossier:=rangement(self.app,d.get('importateur'),'valides')) else {}
        chemin=filedialog.asksaveasfilename(parent=parent,title='Enregistrer le XML validé',
            initialfile=nom,defaultextension='.xml',filetypes=[('XML','*.xml')],confirmoverwrite=True,**options)
        if not chemin or self.app.session_verrouillee:
            return
        try:
            destination=service.exporter_xml(identifiant,chemin,self.app.utilisateur,ecraser=Path(chemin).exists())
        except service.ErreurSuiviExport as exc:
            messagebox.showwarning('XML enregistré, suivi incomplet',str(exc),parent=parent)
            return
        except Exception as exc:
            messagebox.showerror('XML non enregistré',str(exc),parent=parent)
            return
        self.afficher()
        messagebox.showinfo('XML enregistré',destination,parent=parent)

    def imprimer(self,identifiant=None,parent=None):
        if self.app.session_verrouillee:
            return
        identifiant=identifiant if identifiant is not None else self.selection()
        if identifiant is None:
            return
        try:
            # Garde indépendante du bouton : le statut est relu dans la base.
            d=service.detail(identifiant)
            if d['statut']!='valide':
                raise ValueError('Seul un modèle « Validé localement » peut être imprimé en PDF.')
        except Exception as exc:
            messagebox.showerror('PDF indisponible',str(exc),parent=parent or self)
            return
        from ui.comparaison import enregistrer_pdf
        nom=Path(service.nom_export(d)).stem
        enregistrer_pdf(parent or self,f"{nom} - modele {identifiant}.pdf",
            lambda chemin:export_pdf.pdf_modele(d,chemin,self.app.utilisateur),rangement(self.app,d.get('importateur'),'pdf'))

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
        try:
            # Garde indépendante du bouton : aucune simulation pré-export n'est comparable.
            contenu=service.lire_export(identifiant)
        except Exception as exc:
            messagebox.showerror('Comparaison indisponible',str(exc),parent=self)
            return
        importateur=self.modeles.get(str(identifiant),{}).get('importateur','')
        options={'initialdir':dossier} if (dossier:=rangement(self.app,importateur,'sources')) else {}
        chemin=filedialog.askopenfilename(parent=self,title='Comparer le XML généré avec un fichier fourni',
            filetypes=[('XML','*.xml')],**options)
        if not chemin:
            return
        try:
            from comparaison_prediction import comparer_xmls
            from ui.comparaison import afficher
            with tempfile.TemporaryDirectory(prefix='asydec-comparaison-') as temp:
                source=Path(temp)/'export.xml'
                source.write_bytes(contenu)
                rapport=comparer_xmls(source,chemin)
            nom=Path(self.modeles.get(str(identifiant),{}).get('chemin_xml') or '').name
            rapport['source']=f"Modèle n° {identifiant} : {nom or 'XML exporté'} (copie archivée)"
            rapport['plaque']=self.modeles.get(str(identifiant),{}).get('plaque') or rapport.get('plaque')
            afficher(self,rapport)
        except Exception as exc:
            messagebox.showerror('Comparaison impossible',str(exc),parent=self)
            return
        try:
            service.noter_comparaison(identifiant,chemin,rapport,self.app.utilisateur)
        except Exception as exc:
            messagebox.showwarning('Comparaison non tracée',f"La comparaison est affichée, mais sa trace n'a pas été enregistrée : {exc}",parent=self)
            return
        self.afficher()
        if self.table.exists(str(identifiant)):
            self.table.selection_set(str(identifiant))
