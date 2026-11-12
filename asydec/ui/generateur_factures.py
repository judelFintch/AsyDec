"""Module autonome de génération native facture, packing list et manifeste."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

from asydec.declarations import generateur_factures as service, modeles_generes
from asydec.formats import nombre
from asydec.systeme import conversion_pdf
from asydec.ui import theme


class PageGenerateurFactures(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.modeles = []
        self.modele = None
        self.vars = {k: tk.StringVar() for k in service.profil_dossier({})}
        self.style = tk.StringVar(value='marine')
        self.pdf = tk.BooleanVar(value=conversion_pdf.disponible())
        self.statut = tk.StringVar(value='Sélectionnez un dossier Friperie enregistré.')
        self.resume = tk.StringVar()
        self.designations = []
        theme.entete_page(self, 'Générateur de documents',
                          'Facture, packing list et manifeste créés par AsyDec · cinq présentations · documents en anglais.')
        source = ttk.Frame(self)
        source.pack(fill='x', pady=(8,0))
        theme.bouton(source,'Importer un XML…',self.importer_xml,principal=True).pack(side='left')
        ttk.Label(source,text='ou choisir un dossier enregistré ci-dessous').pack(side='left',padx=10)
        ligne = ttk.Frame(self)
        ligne.pack(fill='x', pady=8)
        ttk.Button(ligne,text='Actualiser',command=self.afficher).pack(side='right',padx=(8,0))
        ttk.Label(ligne, text='Dossier enregistré').pack(side='left', padx=(0,8))
        self.choix = ttk.Combobox(ligne,state='readonly',width=40)
        self.choix.pack(side='left',fill='x',expand=True)
        self.choix.bind('<<ComboboxSelected>>',lambda e:self.charger())
        ttk.Label(self,textvariable=self.resume,wraplength=850).pack(fill='x',pady=(0,10))
        # Barre d'action toujours visible, quelle que soit la hauteur de la fenêtre ou l'onglet ouvert.
        actions = ttk.Frame(self)
        actions.pack(side='bottom',fill='x',pady=(6,0))
        theme.bouton(actions,'✔ Valider et générer les 3 documents…',self.generer,principal=True).pack(side='left')
        ttk.Label(actions,textvariable=self.statut,wraplength=700).pack(side='left',fill='x',expand=True,padx=12)
        onglets = ttk.Notebook(self)
        onglets.pack(fill='both',expand=True)
        identites, articles, presentation = [ttk.Frame(onglets,padding=16) for _ in range(3)]
        for cadre,nom in ((identites,'1 · Identités et transport'),(articles,'2 · Articles en anglais'),(presentation,'3 · Présentation et export')):
            onglets.add(cadre,text=nom)
        champs = [('fournisseur','Fournisseur'),('adresse_fournisseur','Adresse fournisseur'),('adresse_client','Adresse importateur'),
                  ('transporteur','Transporteur'),('depart','Lieu de départ'),('destination','Destination'),
                  ('conteneur','Conteneur'),('scelle','Scellé')]
        ttk.Label(identites,text='L’importateur et la plaque proviennent du dossier ou du XML sélectionné.',wraplength=800).grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,12))
        for i,(cle,libelle) in enumerate(champs,1):
            ttk.Label(identites,text=libelle).grid(row=i,column=0,sticky='w',pady=5,padx=(0,16))
            ttk.Entry(identites,textvariable=self.vars[cle],width=70).grid(row=i,column=1,sticky='ew',pady=5)
        identites.columnconfigure(1,weight=1)
        ttk.Label(articles,text='Vérifiez les libellés anglais. Sélectionnez une ligne pour la modifier. Les quantités et montants restent ceux du dossier.',wraplength=800).pack(anchor='w',pady=(0,8))
        self.table = ttk.Treeview(articles,columns=('code','source','anglais','colis','poids','fob'),show='headings',height=10)
        for cle,nom,largeur in [('code','Code SH',85),('source','Libellé du dossier',200),('anglais','Libellé anglais imprimé',260),
                                ('colis','Colis',65),('poids','Poids kg',85),('fob','FOB USD',90)]:
            self.table.heading(cle,text=nom);self.table.column(cle,width=largeur,stretch=cle in ('source','anglais'))
        self.table.pack(fill='both',expand=True)
        self.table.bind('<Double-1>',lambda e:self.modifier_article())
        ttk.Button(articles,text='Modifier le libellé anglais…',command=self.modifier_article).pack(anchor='w',pady=8)
        descriptions = {'classique':'En-tête centré, police Times, encadrés et tableau quadrillé.',
                        'marine':'Bandeau bleu marine, références à droite, tableau aéré sans traits verticaux.',
                        'epure':'Fond blanc, filet sous l’en-tête, typographie légère.',
                        'registre':'Bandeau vert centré, tableau quadrillé à lignes alternées.',
                        'compact':'Gris anthracite, police plus petite et tableau quadrillé.'}
        ttk.Label(presentation,text='Présentations AsyDec : facture, packing list et manifeste séparés, sur une page chacun.',
                  style='SousTitre.TLabel').pack(anchor='w',pady=(0,4))
        for cle,s in service.STYLES.items():
            bloc = ttk.Frame(presentation)
            bloc.pack(fill='x',pady=4)
            ttk.Radiobutton(bloc,text=s['nom'],variable=self.style,value=cle,width=14).pack(side='left')
            tk.Label(bloc,text='   ',bg='#'+s['couleur']).pack(side='left',padx=8)
            ttk.Label(bloc,text=descriptions[cle],wraplength=650).pack(side='left')
        ttk.Separator(presentation).pack(fill='x',pady=10)
        bib = ttk.Frame(presentation)
        bib.pack(fill='x')
        ttk.Radiobutton(bib,text='Modèle Word de la bibliothèque',variable=self.style,value='bibliotheque').pack(side='left')
        ttk.Button(bib,text='Ajouter un modèle Word…',command=self.ajouter_modele).pack(side='right')
        self.choix_gabarit = ttk.Combobox(presentation,state='readonly',width=40)
        self.choix_gabarit.pack(fill='x',pady=(6,2))
        self.choix_gabarit.bind('<<ComboboxSelected>>',lambda e:self.style.set('bibliotheque'))
        ttk.Label(presentation,text='Bibliothèque commune à tous les modules (« Modèles de facture »). Les modèles du même importateur '
                  'sont proposés en premier ; le Word garde sa mise en page, son fournisseur et son client.',wraplength=800).pack(anchor='w')
        self.gabarits = []
        ttk.Separator(presentation).pack(fill='x',pady=10)
        ttk.Checkbutton(presentation,text='Créer aussi les PDF avec Microsoft Word',variable=self.pdf).pack(anchor='w')
        ttk.Label(presentation,text='Les numéros et dates restent identiques quelle que soit la présentation ou le modèle choisi.',wraplength=800).pack(anchor='w',pady=8)
        theme.bouton(presentation,'Générer la facture, la packing list et le manifeste…',self.generer,principal=True).pack(anchor='w',pady=8)

    def afficher(self):
        ancien = self.modele['id'] if self.modele else None
        cible = getattr(self.app,'generateur_modele_id',None)
        if cible is not None:
            self.app.generateur_modele_id = None
        self.modeles = modeles_generes.lister(module='friperie')
        self.choix['values'] = [f"N° {m['id']} · {m['importateur']} · {m.get('plaque') or 'sans plaque'} · {nombre(m['resultat']['resume']['fob'],2)} USD" for m in self.modeles]
        if cible is None and self.modele is not None and self.modele.get('source')=='xml':
            return  # Garder le XML importé et les libellés déjà corrigés.
        self.choix.set('')
        indice = next((i for i,m in enumerate(self.modeles) if m['id']==(cible if cible is not None else ancien)),None)
        if indice is not None:
            self.choix.current(indice)
            self.charger()
        else:
            self.modele = None
            self.designations=[]
            self.table.delete(*self.table.get_children())
            for v in self.vars.values():v.set('')
            self.resume.set('Aucun dossier sélectionné : choisissez le client et le camion concernés.')

    def charger(self):
        i=self.choix.current()
        if not 0 <= i < len(self.modeles):return
        self._remplir(modeles_generes.detail(self.modeles[i]['id']))
        self.statut.set('Identités reprises du XML de ce dossier. Complétez le transport et vérifiez les libellés anglais avant de générer.')

    def importer_xml(self):
        if self.app.session_verrouillee:return
        chemin=filedialog.askopenfilename(parent=self,title='Déclaration XML ASYCUDA',filetypes=[('XML','*.xml'),('Tous les fichiers','*')])
        if not chemin:return
        try:
            modele=service.modele_depuis_xml(chemin)
        except Exception as exc:
            messagebox.showerror('XML non exploitable',str(exc),parent=self);return
        if not modele['plaque']:
            plaque=simpledialog.askstring('Plaque','Ce XML ne contient pas de plaque. Saisissez-la :',parent=self)
            modele['plaque']=' '.join((plaque or '').split())
        if not modele['importateur']:
            client=simpledialog.askstring('Importateur','Ce XML ne contient pas d’importateur. Saisissez-le :',parent=self)
            modele['importateur']=' '.join((client or '').split())
        self.choix.set('')
        self._remplir(modele)
        self.statut.set(f"XML {modele['fichier']} chargé : complétez le transport et vérifiez les libellés anglais avant de générer."
                        + (''.join('\n⚠ '+a for a in modele['alertes'])))

    def _remplir(self,modele):
        self.modele=modele
        for cle,valeur in service.profil_dossier(self.modele).items():self.vars[cle].set(valeur)
        propositions=service.propositions_articles(self.modele)
        self.designations=[p['anglais'] for p in propositions]
        self.table.delete(*self.table.get_children())
        r=self.modele['resultat'];resume=r['resume'];colis=r.get('colis',resume.get('colis',[]))
        for i,(p,a,q) in enumerate(zip(propositions,resume['articles'],colis)):
            self.table.insert('', 'end',iid=str(i),values=(p['code'],p['source'],p['anglais'] or 'À renseigner',nombre(q),nombre(a['poids'],2),nombre(a['fob'],2)))
        self.resume.set(f"Importateur : {self.modele['importateur']}   ·   Plaque : {self.modele.get('plaque') or 'à enregistrer dans le dossier'}\n"
                        f"{len(propositions)} articles · {nombre(sum(colis))} colis · {nombre(resume['poids'],2)} kg · {nombre(resume['fob'],2)} USD FOB"
                        + (f"   ·   Source : XML {self.modele['fichier']}" if self.modele.get('source')=='xml' else ''))
        self.charger_gabarits()

    def charger_gabarits(self, selection=None):
        try:
            self.gabarits=service.modeles_bibliotheque(self.modele)
        except Exception as exc:
            self.gabarits=[];self.statut.set(f'Bibliothèque de modèles illisible : {exc}')
        def libelle(g):
            client=g.get('destinataire') or 'client non repéré'
            etat='✔ ' if g.get('importateur_correspond') and g.get('pret') else '✖ '
            return f"{etat}{g['nom']} · {client} · {g.get('raison','')}"
        self.choix_gabarit['values']=[libelle(g) for g in self.gabarits]
        indice=next((i for i,g in enumerate(self.gabarits) if g['id']==selection),
                    0 if self.gabarits and self.gabarits[0].get('importateur_correspond') else None)
        if indice is None:self.choix_gabarit.set('')
        else:self.choix_gabarit.current(indice)

    def ajouter_modele(self):
        if self.app.session_verrouillee:return
        chemin=filedialog.askopenfilename(parent=self,title='Modèle de facture Word',filetypes=[('Word','*.docx')])
        if not chemin:return
        try:
            from asydec.declarations import factures
            identifiant=factures.importer(chemin)
        except Exception as exc:
            messagebox.showerror('Modèle non ajouté',str(exc),parent=self);return
        self.charger_gabarits(selection=identifiant)
        self.style.set('bibliotheque')
        g=next((g for g in self.gabarits if g['id']==identifiant),None)
        if g and not g.get('pret'):
            messagebox.showwarning('Modèle à configurer','Le Word est ajouté à la bibliothèque, mais ses zones (numéro, poids, colis, FOB…) '
                                   'doivent être configurées dans « Modèles de facture » avant usage.',parent=self)

    def _style_choisi(self, modele, profil):
        """Style à générer ; pour un Word, demande confirmation de la correspondance des articles."""
        if self.style.get()!='bibliotheque':
            return self.style.get()
        i=self.choix_gabarit.current()
        if not 0<=i<len(self.gabarits):
            raise ValueError('Choisissez un modèle Word dans la liste, ou une présentation AsyDec.')
        g=self.gabarits[i]
        c=service.correspondance_gabarit(g['id'],modele,profil)
        lignes='\n'.join(f"{n}. {w or '—'}  ←  {a}  ({nombre(q)} colis · {nombre(kg,2)} kg · {nombre(fob,2)} USD)"
                         for n,(w,a,q,kg,fob) in enumerate(c['lignes'],1))
        avis=''
        if c['fournisseur'] and profil.get('fournisseur') and c['fournisseur'].split()[0].upper()!=profil['fournisseur'].split()[0].upper():
            avis=f"\n\n⚠ Fournisseur du Word : {c['fournisseur']} ; fournisseur du dossier : {profil['fournisseur']}."
        if not messagebox.askyesno('Confirmer le modèle Word',
                                   f"Modèle « {c['nom']} ».\nLe Word garde ses libellés ; chaque ligne reçoit les quantités "
                                   f"et montants de l’article en face :\n\n{lignes}{avis}\n\nCet ordre est-il correct ?",parent=self):
            return None
        return service.GABARIT+str(g['id'])

    def modifier_article(self):
        if self.app.session_verrouillee or not self.table.selection():return
        i=int(self.table.selection()[0])
        valeur=simpledialog.askstring('Désignation anglaise',f'Article {i+1} · libellé anglais imprimé :',initialvalue=self.designations[i],parent=self)
        if valeur is None:return
        valeur=' '.join(valeur.split())
        if not valeur or len(valeur)>100:
            messagebox.showerror('Libellé invalide','Saisissez entre 1 et 100 caractères.',parent=self);return
        self.designations[i]=valeur
        self.table.set(str(i),'anglais',valeur)

    def generer(self):
        if self.app.session_verrouillee:return
        if self.modele is None:
            messagebox.showinfo('Dossier nécessaire','Sélectionnez un dossier Friperie enregistré ou importez un XML.',parent=self);return
        profil={k:v.get() for k,v in self.vars.items()}
        profil['designations']=list(self.designations)
        try:
            # Relire l'instantané pour ne pas exporter une ancienne plaque (un XML reste en mémoire).
            modele=self.modele if self.modele.get('source')=='xml' else modeles_generes.detail(self.modele['id'])
            service.preparer_donnees(modele,profil)
            style=self._style_choisi(modele,profil)
            if style is None:return
            dossier=filedialog.askdirectory(parent=self,title='Dossier de sortie des documents')
            if not dossier or self.app.session_verrouillee:return
            self.configure(cursor='watch');self.update_idletasks()
            resultat=service.generer_modele(modele,style,profil,self.app.utilisateur)
            fichiers=service.exporter(resultat,Path(dossier))
            erreurs=[];pdfs=[]
            if self.pdf.get():
                for chemin in fichiers.values():
                    self.statut.set(f'Conversion PDF : {chemin.name}');self.update_idletasks()
                    try:pdfs.append(conversion_pdf.docx_vers_pdf(chemin))
                    except conversion_pdf.ConversionImpossible as exc:erreurs.append(str(exc))
            self.statut.set(f"Facture {resultat['numero']} · manifeste {resultat['manifeste']} · date facture {resultat['date_facture']} · date manifeste {resultat['date_manifeste']}\n"
                            f"{len(fichiers)} Word et {len(pdfs)} PDF enregistrés dans {dossier}."
                            + ('\nPDF incomplets : '+ '; '.join(dict.fromkeys(erreurs)) if erreurs else ''))
        except Exception as exc:
            messagebox.showerror('Documents non générés',str(exc),parent=self)
        finally:
            self.configure(cursor='')
