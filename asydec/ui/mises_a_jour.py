"""Mises à jour facultatives, sans bloquer le fil Tkinter."""
import queue
import threading
from tkinter import ttk, messagebox, StringVar
import sys

from asydec import chemins
from asydec.systeme import mises_a_jour as service
from asydec.systeme.version import courante
from asydec.ui import theme


class PageMisesAJour(ttk.Frame):
    def __init__(self,parent,app):
        super().__init__(parent)
        self.app=app
        self.meta=None
        self.occupe=False
        self.resultats=queue.Queue()
        windows = sys.platform == 'win32'
        theme.entete_page(self,'Mises à jour Windows' if windows else 'Mises à jour Mac','Les mises à jour sont facultatives. Vos données et vos numéros de factures restent conservés.')
        self.etat=StringVar(value='Vérifiez la disponibilité d’une nouvelle version.')
        ttk.Label(self,textvariable=self.etat,wraplength=820).pack(anchor='w',pady=16)
        ttk.Button(self,text='Vérifier les mises à jour',command=self.verifier).pack(anchor='w',pady=8)
        self.installer_bouton=ttk.Button(self,text='Télécharger et installer…',command=self.installer,state='disabled')
        self.installer_bouton.pack(anchor='w',pady=8)
        ttk.Label(self,text=('Dépôt GitHub privé : jeton en lecture seule, conservé pour cette session uniquement.' if windows
                            else 'Dépôt GitHub privé : jeton en lecture seule, enregistré dans le Trousseau macOS.'),wraplength=800).pack(anchor='w',pady=(20,4))
        self.jeton=StringVar()
        ttk.Entry(self,textvariable=self.jeton,show='•',width=64).pack(anchor='w')
        ttk.Button(self,text='Utiliser le jeton pour cette session' if windows else 'Enregistrer le jeton dans le Trousseau',command=self.retenir_jeton).pack(anchor='w',pady=8)
        v=courante()
        from asydec.systeme import mises_a_jour as maj
        installee = (v.get('architecture') or 'non précisée') if windows else maj.TYPES_MAC.get(v.get('architecture'), {}).get('libelle', v.get('architecture') or 'non précisée')
        ordinateur = f'Windows ({maj.architecture()})' if windows else f'Ce Mac : {maj.type_mac()}'
        ttk.Label(self,text=f"{ordinateur}\nVersion installée : {installee}\n"
                            f"Construction : {v['version']} · {v['revision'][:12]}\nDonnées : {chemins.RACINE}",wraplength=820).pack(anchor='w',pady=20)

    def retenir_jeton(self):
        if self.app.session_verrouillee:
            return
        token=self.jeton.get().strip()
        if not token:
            return
        try:
            self.etat.set(service.retenir_token(token))
        except (ValueError, OSError) as exc:
            self.etat.set(str(exc))
        finally:
            self.jeton.set('')

    def travailler(self,action,fin,discret=False):
        if self.occupe or self.app.session_verrouillee:
            return
        self.occupe=True
        def worker():
            try:
                self.resultats.put((True,action()))
            except Exception as exc:
                self.resultats.put((False,str(exc)))
        threading.Thread(target=worker,daemon=True).start()
        def lire():
            try:
                ok,valeur=self.resultats.get_nowait()
            except queue.Empty:
                self.after(150,lire)
                return
            self.occupe=False
            if ok:
                try:
                    fin(valeur)
                except Exception as exc:
                    self.etat.set('Installation non effectuée : '+str(exc))
                    messagebox.showerror('Mise à jour non effectuée',str(exc),parent=self)
            else:
                self.etat.set('Vérification ou installation indisponible : '+valeur)
                if not discret:
                    messagebox.showerror('Mise à jour non effectuée',valeur,parent=self)
        self.after(150,lire)

    def verifier(self,discret=False):
        if self.occupe or self.app.session_verrouillee:
            return
        self.meta = None
        self.installer_bouton.configure(state='disabled')
        self.etat.set('Recherche d’une version publiée sur GitHub…')
        def fini(meta):
            self.meta=meta
            disponible=meta['disponible']
            self.etat.set(f"Nouvelle version disponible : {meta['version']}" if disponible else 'Cette installation est à jour.')
            self.installer_bouton.configure(state='normal' if disponible and chemins.COMPILE else 'disabled')
            if disponible:
                self.app.var_version.set('Mise à jour GitHub disponible')
        self.travailler(lambda:service.verifier(service.token_github()),fini,discret)

    def installer(self):
        if not self.meta or self.app.session_verrouillee or self.occupe:
            return
        if not messagebox.askyesno('Installer la mise à jour',
            'Télécharger cette version puis fermer AsyDec pour l’installer ?\n'
            'Enregistrez votre travail en cours. Les données déjà enregistrées seront conservées.',parent=self):
            return
        self.etat.set('Téléchargement et vérification de l’application…')
        def fini(nouvelle):
            if self.app.session_verrouillee:
                self.etat.set('Session verrouillée : relancez l’installation après reconnexion.')
                return
            self.app.preparer_reset()
            self.app._ecrire_prefs()
            service.lancer_installation(nouvelle)
            self.app.reconnexion=False
            self.app.rechargement=False
            self.app.quitter()
        self.travailler(lambda:service.preparer(self.meta,service.token_github()),fini)
