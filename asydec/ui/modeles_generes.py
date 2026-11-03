"""Liste persistante des propositions, avec validation locale explicite."""
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog

from asydec.calcul import anomalies
from asydec.declarations import export_pdf
from asydec.declarations import modeles_generes as service
from asydec.formats import date_locale, nombre
from asydec.ui import theme
from asydec.ui.notation import BarreNotation, etoiles
from asydec.systeme.journal import erreur_ignoree


def rangement(app,importateur,cle):
    """Sous-dossier de rangement de l'importateur (créé au besoin), ou None."""
    if not importateur:
        return None
    try:
        from asydec.declarations import generer
        return generer.dossier_rangement(importateur,cle,getattr(app,'table_imp',None))
    except Exception:  # noqa: BLE001 - la fenêtre s'ouvrira à l'emplacement habituel
        erreur_ignoree('dossier initial')
        return None


EFFET_NOTE={n:('Il servira d’exemple pour les prochaines répartitions aux mêmes articles.' if n>=4 else
               'Les prochaines répartitions trop proches de lui seront signalées et placées après les autres.' if n<=2 else
               'Note enregistrée : sans effet sur les prochaines répartitions.') for n in range(1,6)}

TEXTES_RISQUE={'eleve':'● Élevé','moyen':'● À vérifier',None:'—'}


def _contexte_anomalies(app):
    """(groupes de références, modèles enregistrés) du module de travail ; lève une exception si illisible."""
    from asydec.references import service_references
    from asydec.references import catalogue_xml
    conn = app.base_refs()
    module = getattr(app, 'module_travail', 'friperie')
    documents = [d for d in catalogue_xml.lister(conn, module=module) if d['id'] is not None]
    autorises = {d['id'] for d in documents}
    observations=[o for o in service_references.observations(conn,('accepte','non_verifie'))
                  if o['document_id'] in autorises]
    # Déclarations réelles comparées : elles comptent dans les fourchettes, même hors médiathèque.
    observations += service.observations_reelles(module=module, connues={d['empreinte'] for d in documents})
    return anomalies.references_par_groupe(observations), service.donnees_analyse(module=module)


def analyser_modeles(app):
    """{id: alertes} pour tous les modèles ; vide si les références ou les modèles sont illisibles."""
    try:
        groupes, modeles = _contexte_anomalies(app)
    except Exception:  # noqa: BLE001 - l'analyse est une aide : la liste reste utilisable sans elle
        erreur_ignoree('analyse des anomalies des modèles')
        return {}
    return {m['id']:anomalies.analyser(m,groupes,modeles) for m in modeles}


def classer_propositions(app, propositions, base=None, profil=None, cle=None):
    """[(proposition, alertes)] du moins au plus risqué, ordre d'origine à risque égal.
    base et profil : communs à toutes les propositions, sinon v['controle'] et v['profil'].
    cle : note d'intention (plus petite = meilleure), qui départage à niveau de risque égal.
    Sans références lisibles, les alertes restent vides et seule la note d'intention classe."""
    from asydec.calcul import variantes
    try:
        groupes, modeles = _contexte_anomalies(app)
    except Exception:  # noqa: BLE001 - l'analyse est une aide : la génération reste possible sans elle
        erreur_ignoree('analyse des anomalies des propositions')
        sortie = [(v, []) for v in propositions]
        return sorted(sortie, key=lambda t: cle(t[0])) if cle else sortie
    contenus, sortie = {}, []
    for v in propositions:
        try:
            chemin = base or v['controle']
            if chemin not in contenus:
                contenus[chemin] = Path(chemin).read_bytes()
            modele = service.donnees_proposition(contenus[chemin], v,
                                                 variantes.articles_ajustables(profil or v['profil']))
            alertes = anomalies.analyser(modele, groupes, modeles)
        except Exception:  # noqa: BLE001 - une proposition illisible n'est pas jugée, mais reste proposée
            erreur_ignoree("analyse d'une proposition")
            alertes = []
        sortie.append((v, alertes))
    if cle:
        return sorted(sortie, key=lambda t: (anomalies.gravite(t[1])[0], cle(t[0])))
    return sorted(sortie, key=lambda t: anomalies.gravite(t[1]))


def texte_risque(alertes):
    """Phrase courte sur le risque d'une proposition, pour les messages de génération."""
    graves=[a for a in alertes if a['niveau']!='info']
    if not graves:
        return 'Anomalies : aucun signal par rapport aux dossiers connus.'
    return (f"Anomalies : {anomalies.LIBELLES[anomalies.niveau(alertes)]} · {len(graves)} point(s) · "
            f"{graves[0]['message']}")


def resume_risque(alertes):
    texte=texte_risque(alertes)
    return texte if anomalies.niveau(alertes) is None else texte+'  (bouton « Anomalies… » pour le détail)'


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
        self.filtre = ttk.Combobox(barre,state='readonly',values=['Tous']+list(service.STATUTS.values())+['À risque ⚠','Bons modèles ★','Bien notés (4-5)','Mal notés (1-2)','Supprimés'],width=24)
        self.filtre.set('Tous')
        self.filtre.pack(side='left',padx=4)
        self.filtre.bind('<<ComboboxSelected>>',lambda e:self.afficher())
        for texte, action in [('Actualiser',self.afficher),('Détails…',self.consulter),('Ouvrir le dossier',self.ouvrir_dossier),('Anomalies…',self.voir_anomalies)]:
            theme.bouton(barre,texte,action).pack(side='left',padx=4)
        self.comparer_bouton=theme.bouton(barre,'Comparer avec un XML…',self.comparer,state='disabled')
        self.comparer_bouton.pack(side='left',padx=4)
        self.pdf_bouton=theme.bouton(barre,'Imprimer en PDF…',self.imprimer,state='disabled')
        self.pdf_bouton.pack(side='left',padx=4)
        actions=ttk.Frame(self)
        actions.pack(fill='x',pady=(0,8))
        self.xml_bouton=theme.bouton(actions,'Télécharger le XML…',self.telecharger_xml,state='disabled')
        self.xml_bouton.pack(side='right',padx=4)
        # Plaque du modèle sélectionné, modifiable directement, quel que soit son statut.
        self.plaque_bouton=theme.bouton(actions,'Enregistrer la plaque',
            lambda:self.saisir_plaque(plaque=self.var_plaque_modele.get()),state='disabled')
        self.plaque_bouton.pack(side='right',padx=(4,12))
        self.var_plaque_modele=tk.StringVar()
        self.champ_plaque=ttk.Entry(actions,textvariable=self.var_plaque_modele,width=20,state='disabled')
        self.champ_plaque.pack(side='right')
        self.champ_plaque.bind('<Return>',lambda e:self.saisir_plaque(plaque=self.var_plaque_modele.get()))
        ttk.Label(actions,text='Plaque',style='Doux.TLabel').pack(side='right',padx=(4,4))
        self.bon_bouton=theme.bouton(actions,'☆ Cocher bon modèle',self.basculer_bon,state='disabled')
        self.bon_bouton.pack(side='right',padx=4)
        self.supprimer_bouton=theme.bouton(actions,'Supprimer…',self.supprimer,state='disabled')
        self.supprimer_bouton.pack(side='right',padx=4)
        for statut in service.STATUTS:
            theme.bouton(actions,service.STATUTS[statut],lambda s=statut:self.changer(s)).pack(side='left',padx=4)
        versions=ttk.Frame(self)
        versions.pack(fill='x',pady=(0,8))
        theme.bouton(versions,'Corriger le dossier…',self.corriger_dossier).pack(side='left',padx=4)
        theme.bouton(versions,'Reprendre pour modifier',self.reprendre).pack(side='left',padx=4)
        theme.bouton(versions,'Factures Word…',self.facturer).pack(side='left',padx=4)
        # Note du modèle sélectionné : 4-5 = exemple à suivre, 1-2 = à éviter pour les prochaines générations.
        self.notation=BarreNotation(self,self.noter)
        self.notation.pack(fill='x',pady=(0,8))
        self.notation.definir(None,actif=False)
        self.message=theme.Message(self)
        self.message.pack(fill='x',pady=6)
        # Colonnes lisibles d'un coup d'œil ; le reste est dans le panneau « Modèle sélectionné ».
        cadre,self.table=theme.tableau(self,[
            ('bon','★',30,'center'),('note','Note',80,'center'),('id','N°',45,'e'),('risque','Risque',110,'w'),('plaque','Plaque',140,'w'),('importateur','Importateur',190,'w'),
            ('statut','Statut',95,'center'),('compare','Écart taxes comparé',150,'e'),('fob','FOB USD',95,'e'),
            ('poids','Poids kg',85,'e'),('taxes','Taxes CDF',110,'e'),('fichier','Fichier XML généré',230,'w')],12)
        cadre.pack(fill='both',expand=True)
        self.table.tag_configure('valide',foreground=theme.OK)
        self.table.tag_configure('rejete',foreground=theme.TEXTE_DOUX)
        self.table.tag_configure('risque_eleve',foreground=theme.ERREUR)
        self.table.tag_configure('risque_moyen',foreground=theme.ALERTE)
        self.analyses={}
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
            lignes=service.lister(filtre,supprimes=supprimes,module=getattr(self.app, 'module_travail', 'friperie'))
            if self.filtre.get()=='Bons modèles ★':
                lignes=[m for m in lignes if m['bon']]
            elif self.filtre.get()=='Bien notés (4-5)':
                lignes=[m for m in lignes if (m.get('note') or 0)>=service.NOTE_BONNE]
            elif self.filtre.get()=='Mal notés (1-2)':
                lignes=[m for m in lignes if m.get('note') and m['note']<=service.NOTE_MAUVAISE]
            self.analyses=analyser_modeles(self.app)
            if self.filtre.get()=='À risque ⚠':
                lignes=[m for m in lignes if anomalies.niveau(self.analyses.get(m['id'],[])) in ('eleve','moyen')]
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
            risque=anomalies.niveau(self.analyses.get(m['id'],[]))
            self.table.insert('','end',iid=identifiant,tags=(f'risque_{risque}' if risque else m['statut'],),
                values=('★' if m['bon'] else '',etoiles(m.get('note')),identifiant,TEXTES_RISQUE[risque],m['plaque'] or '—',
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
        modifiable=bool(modele) and libre and not modele.get('supprime')
        self.plaque_bouton.configure(state='normal' if modifiable else 'disabled')
        if hasattr(self,'notation'):
            self.notation.definir(modele.get('note'),modele.get('note_commentaire'),modifiable)
        if hasattr(self,'champ_plaque'):
            self.var_plaque_modele.set(modele.get('plaque') or '')
            self.champ_plaque.configure(state='normal' if modifiable else 'disabled')
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
        try:
            from asydec.declarations import factures
            suggestion = factures.resume_suggestion(m)
        except Exception:
            erreur_ignoree('suggestion de modèle de facture')
            suggestion = 'Facture : bibliothèque indisponible.'
        self.var_resume.set('\n'.join((
            f"{'★ Bon modèle · ' if m['bon'] else ''}N° {m['id']} · {m['importateur']} · plaque {m['plaque'] or '—'} · {service.STATUTS[m['statut']]}",
            f"FOB {nombre(r['fob'],2)} USD · poids {nombre(r['poids'])} kg · colis {nombre(sum(m['resultat']['colis']))} · "
            f"total taxes estimé {nombre(r.get('taxes_totales'))} CDF",
            f"Créé le {date_locale(m['cree_utc'])} par {m['auteur']} · dernier événement le {date_locale(m['modifie_utc'])} · {compare}",
            f"Fichier XML généré : {m['chemin_xml'] or 'aucun (proposition non exportée)'}",
            resume_risque(self.analyses.get(m['id'],[])), suggestion)))

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
        from asydec.references.import_references import extraire
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
        theme.bouton(boutons,'Corriger le dossier…',lambda:self.corriger_dossier(identifiant,fen)).pack(side='right',padx=8)
        theme.bouton(boutons,'Reprendre pour modifier',lambda:self.reprendre(identifiant,fen)).pack(side='right',padx=8)
        if not d['supprime']:
            theme.bouton(boutons,'Plaque…',lambda:self.saisir_plaque(identifiant,fen)).pack(side='right',padx=8)
        if d['statut']=='valide':
            theme.bouton(boutons,'Télécharger le XML…',lambda:self.telecharger_xml(identifiant,fen)).pack(side='right',padx=8)
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

    def voir_anomalies(self):
        """Alertes du modèle sélectionné, de la plus grave à la simple information."""
        identifiant=self.selection()
        if identifiant is None or self.app.session_verrouillee:
            return
        alertes=self.analyses.get(identifiant)
        if alertes is None:
            messagebox.showinfo('Anomalies','Analyse indisponible pour ce modèle (références illisibles ou modèle incomplet).',parent=self)
            return
        fen=tk.Toplevel(self)
        fen.title(f'Anomalies · modèle n° {identifiant}')
        fen.geometry('1050x460')
        cadre=ttk.Frame(fen,padding=16)
        cadre.pack(fill='both',expand=True)
        theme.entete_page(cadre,f"Modèle n° {identifiant} · {anomalies.LIBELLES[anomalies.niveau(alertes)]}",
            'Comparaison avec les dossiers connus de la bibliothèque des références et avec vos autres modèles. '
            'Indicatif : aucune référence ne prouve un rejet SYDONIA ; vérifiez chaque point.')
        zone,table=theme.tableau(cadre,[('niveau','Niveau',120,'w'),('article','Article',130,'w'),('message','Explication',760,'w')],12)
        zone.pack(fill='both',expand=True)
        table.tag_configure('eleve',foreground=theme.ERREUR)
        table.tag_configure('moyen',foreground=theme.ALERTE)
        for a in alertes:
            table.insert('','end',tags=(a['niveau'],),values=(anomalies.LIBELLES[a['niveau']],a['article'] or '—',a['message']))
        if not alertes:
            table.insert('','end',values=('—','—','Aucun signal par rapport aux dossiers connus.'))
        theme.bouton(cadre,'Fermer',fen.destroy).pack(anchor='e',pady=8)
        return fen

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
            from asydec.ui.comparaison import afficher
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
        from asydec.ui.comparaison import afficher_taxes
        afficher_taxes(parent or self,{'taxes_detail':lignes},explication)

    @staticmethod
    def texte_comparaisons(d):
        dates=[date_locale(e['date_utc']) for e in d['evenements'] if e['action']=='comparaison']
        return f"Comparé {len(dates)} fois, dernière le {dates[-1]}." if dates else 'Jamais comparé avec un XML.'

    def noter(self,note,commentaire=''):
        """Note le modèle sélectionné ; elle oriente les prochaines générations (4-5 suivi, 1-2 évité)."""
        if self.app.session_verrouillee:
            return
        identifiant=self.selection()
        if identifiant is None:
            return
        try:
            service.noter(identifiant,note,self.app.utilisateur,commentaire)
        except Exception as exc:
            messagebox.showerror('Note non enregistrée',str(exc),parent=self)
            return
        self.afficher()
        if self.table.exists(str(identifiant)):
            self.table.selection_set(str(identifiant))
        self.message.afficher('ok',f'Modèle n° {identifiant} noté {note}/5 ({service.NOTES[note]})',
            [EFFET_NOTE[note]])

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

    def saisir_plaque(self,identifiant=None,parent=None,plaque=None):
        """Plaque d'un modèle généré (en attente, validé ou rejeté) ; plaque=None : elle est demandée."""
        if self.app.session_verrouillee:
            return
        identifiant=identifiant if identifiant is not None else self.selection()
        if identifiant is None:
            return
        parent=parent or self
        try:
            d=service.detail(identifiant)
            if d['supprime']:
                raise ValueError('Restaurez le modèle avant de changer sa plaque.')
        except Exception as exc:
            messagebox.showerror('Plaque indisponible',str(exc),parent=parent)
            return
        if plaque is None:
            plaque=simpledialog.askstring('Plaque du camion',
                f"Modèle n° {identifiant} : plaque du camion (ex. T546ECQ/T618ECT) :",initialvalue=d['plaque'],parent=parent)
        if plaque is None or self.app.session_verrouillee:
            return
        try:
            plaque=service.definir_plaque(identifiant,plaque,self.app.utilisateur)
        except Exception as exc:
            messagebox.showerror('Plaque non enregistrée',str(exc),parent=parent)
            return
        export=next((e for e in reversed(d['evenements']) if e['action']==service.EXPORT),None)
        if export and plaque!=d['plaque'] and messagebox.askyesno('Mettre à jour le XML généré',
                f"Plaque {plaque} enregistrée pour le modèle n° {identifiant}.\n\n"
                "Inscrire aussi cette plaque dans le fichier XML déjà généré, à la même place ? "
                "Seule la plaque change dans le fichier.",parent=parent):
            try:
                chemin=service.mettre_a_jour_export(identifiant,self.app.utilisateur)
                messagebox.showinfo('XML mis à jour',f"Plaque {plaque} inscrite dans :\n{chemin}",parent=parent)
            except Exception as exc:
                messagebox.showerror('XML non mis à jour',str(exc),parent=parent)
        self.afficher()
        if self.table.exists(str(identifiant)):
            self.table.selection_set(str(identifiant))

    def corriger_dossier(self, identifiant=None, parent=None):
        if self.app.session_verrouillee:
            return
        identifiant = identifiant if identifiant is not None else self.selection()
        if identifiant is None:
            return
        from asydec.ui.correction_modele import FenetreCorrection
        return FenetreCorrection(self, identifiant, parent)

    def reprendre(self,identifiant=None,parent=None):
        if self.app.session_verrouillee:
            return
        identifiant=identifiant if identifiant is not None else self.selection()
        if identifiant is None:
            return
        try:
            d=service.detail(identifiant)
            r=d['resultat']
            if r.get('module', 'friperie') != getattr(self.app, 'module_travail', 'friperie'):
                raise ValueError('Ouvrez le module du modèle avant de le reprendre.')
            repartition={'poids':[a['poids'] for a in r['resume']['articles']],
                         'fob':[a['fob'] for a in r['resume']['articles']], 'colis':r['colis']}
            from asydec.ui.reprise_modele import reprendre
            if reprendre(self.app,d['base_xml'],d['nom'],parent=parent or self,repartition=repartition):
                # La plaque du modèle repris est proposée ; l'utilisateur peut l'effacer.
                dossier=getattr(self.app,'pages',{}).get('dossier')
                if dossier is not None and d.get('plaque'):
                    dossier.var_plaque.set(d['plaque'])
                # La base archivée garde son importateur d'origine : le choix du modèle est rétabli.
                fixer=getattr(self.app,'fixer_importateur',None)
                if callable(fixer):
                    fixer(r.get('importateur_choisi'))
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

    def facturer(self):
        if self.app.session_verrouillee:
            return
        identifiant = self.selection()
        if identifiant is None:
            messagebox.showinfo('Facture', 'Sélectionnez un modèle généré.', parent=self)
            return
        from asydec.ui.factures import ouvrir
        ouvrir(self, self.app, identifiant)

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
        from asydec.ui.comparaison import enregistrer_pdf
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
        options={'initialdir':dossier} if (dossier:=rangement(self.app,importateur,'reelles')) else {}
        chemin=filedialog.askopenfilename(parent=self,title='Comparer le XML généré avec un fichier fourni',
            filetypes=[('XML','*.xml')],**options)
        if not chemin:
            return
        # Le fichier comparé est une déclaration réelle : rangée avec celles de l'importateur.
        from asydec.declarations import generer
        chemin=generer.ranger_fichier(chemin,importateur,'reelles',getattr(self.app,'table_imp',None))
        try:
            from asydec.declarations.comparaison_prediction import comparer_xmls
            from asydec.ui.comparaison import afficher
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
