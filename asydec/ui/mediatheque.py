"""Médiathèque XML du module ouvert : chaque type de dossier a la sienne, sans partage."""
import tkinter as tk
from tkinter import ttk, messagebox

from asydec.ui import theme
from asydec.declarations import modeles_generes
from asydec.references import catalogue_xml
from asydec.ui.outils import texte_usage


class PageMediatheque(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.documents = []
        theme.entete_page(self, 'Médiathèque XML',
            'Les XML de ce type de dossier uniquement : ils servent dans Dossier, Répartitions, Ratios et Étude de ce module. '
            'Les ajouts utilisent l’import de fond de la Bibliothèque, avec progression et annulation. '
            'Le repérage initial des fichiers dans un dossier peut prendre du temps. '
            'Un import ne constitue pas une acceptation douanière. Les XML partiels servent uniquement aux études.')
        barre = ttk.Frame(self)
        barre.pack(fill='x', pady=8)
        for libelle, action in [('Ajouter des XML…', self.ajouter), ('Ajouter un dossier…', self.dossier),
                                ('Actualiser', self.afficher),
                                ('Marquer déjà utilisé', lambda: self.signaler(True)),
                                ('Retirer le signalement', lambda: self.signaler(False)), ('Retirer la sélection…', self.retirer)]:
            theme.bouton(barre, libelle, action).pack(side='left', padx=4)
        cadre, self.table = theme.tableau(self, [
            ('nom', 'XML', 360, 'w'), ('statut', 'Statut', 120, 'w'),
            ('positions', 'Positions présentes', 150, 'w'), ('usage', 'Utilisation', 170, 'w'),
            ('deja', 'Déjà utilisé', 260, 'w')], 14)
        cadre.pack(fill='both', expand=True)
        self.table.configure(selectmode='extended')
        self.message = theme.Message(self)
        self.message.pack(fill='x', pady=8)

    def afficher(self):
        from asydec.references import service_references
        try:
            self.documents = self.app.xml_disponibles()
            usages = modeles_generes.usages_references()
        except Exception as exc:
            self.message.afficher('erreur', 'Médiathèque indisponible', [str(exc)])
            return
        self.table.delete(*self.table.get_children())
        for k, d in enumerate(self.documents):
            usage = usages.get(d['empreinte'])
            self.table.insert('', 'end', iid=str(k), tags=('alerte',) if usage else (), values=(d['nom'],
                service_references.STATUTS.get(d['statut'], d['statut']),
                ', '.join(map(str, d['positions'])), d['usage'], 'Oui · ' + texte_usage(usage) if usage else '—'))
        module = catalogue_xml.MODULES.get(getattr(self.app, 'module_travail', 'friperie'), '')
        self.message.afficher('ok', f'{len(self.documents)} XML dans la médiathèque {module}',
            ['Les autres types de dossier ont leur propre médiathèque : un XML ajouté ici n’y apparaît pas.'])

    def signaler(self, utilise):
        if self.app.session_verrouillee:
            return
        documents = [self.documents[int(k)] for k in self.table.selection()]
        if not documents:
            self.message.afficher('alerte', 'Sélectionnez un ou plusieurs modèles XML.')
            return
        erreurs = []
        for document in documents:
            try:
                modeles_generes.signaler_reference(document['chemin'], self.app.utilisateur, utilise=utilise)
            except Exception as exc:
                erreurs.append(f"{document['nom']} : {exc}")
        self.afficher()
        self.message.afficher('alerte' if erreurs else 'ok',
            f"{len(documents) - len(erreurs)} modèle(s) " +
            ('marqué(s) comme déjà utilisé(s)' if utilise else 'sans signalement manuel'),
            erreurs or ['Cette information sera affichée dans les propositions de répartition.'])

    def _importer_bibliotheque(self, dossier=False):
        if self.app.session_verrouillee:
            return
        self.app.montrer('references')
        page = self.app.pages['references']
        if page.tache is not None:
            page.message.afficher('alerte', 'Un import est déjà en cours',
                ['Suivez sa progression ici ou demandez son annulation avant un nouvel ajout.'])
            return
        page.message.afficher('alerte', 'Ajout à la médiathèque du module',
            ['L’import s’exécute en tâche de fond ; sa progression et son annulation sont disponibles ici.'])
        page.module_import_suivant = getattr(self.app, 'module_travail', 'friperie')
        try:
            if dossier:
                page.importer_dossier()
            else:
                page.importer_fichiers()
        finally:
            page.module_import_suivant = None

    def ajouter(self):
        self._importer_bibliotheque()

    def dossier(self):
        self._importer_bibliotheque(dossier=True)

    def retirer(self):
        documents = [self.documents[int(k)] for k in self.table.selection()]
        if documents and messagebox.askyesno('Retirer de la médiathèque',
                'Retirer ces XML de la médiathèque de ce module et fermer le dossier actif s’il les utilise ? '
                'Les originaux, exports et historiques sont conservés.', parent=self):
            self.app.retirer_xml(documents)
            self.afficher()
