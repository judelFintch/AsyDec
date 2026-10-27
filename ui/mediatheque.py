"""Point d'entrée commun des archives XML réutilisables dans les autres modules."""
from pathlib import Path
from tkinter import ttk, filedialog, messagebox
from ui import theme


class PageMediatheque(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.documents = []
        theme.entete_page(self, 'Médiathèque XML',
            'Ajoutez vos fichiers une seule fois. Retrouvez-les ensuite dans Dossier, Répartitions, Ratios et Étude. '
            'Un import ne constitue pas une acceptation douanière. Les XML partiels servent uniquement aux études.')
        barre = ttk.Frame(self)
        barre.pack(fill='x', pady=8)
        for libelle, action in [('Ajouter des XML…', self.ajouter), ('Ajouter un dossier…', self.dossier),
                                ('Actualiser', self.afficher), ('Retirer la sélection…', self.retirer)]:
            theme.bouton(barre, libelle, action).pack(side='left', padx=4)
        cadre, self.table = theme.tableau(self, [
            ('nom', 'XML', 360, 'w'), ('statut', 'Statut', 120, 'w'),
            ('positions', 'Positions présentes', 150, 'w'), ('usage', 'Utilisation', 170, 'w')], 14)
        cadre.pack(fill='both', expand=True)
        self.table.configure(selectmode='extended')
        self.message = theme.Message(self)
        self.message.pack(fill='x', pady=8)

    def afficher(self):
        import service_references
        try:
            self.documents = self.app.xml_disponibles()
        except Exception as exc:
            self.message.afficher('erreur', 'Médiathèque indisponible', [str(exc)])
            return
        self.table.delete(*self.table.get_children())
        for k, d in enumerate(self.documents):
            self.table.insert('', 'end', iid=str(k), values=(d['nom'],
                service_references.STATUTS.get(d['statut'], d['statut']),
                ', '.join(map(str, d['positions'])), d['usage']))
        self.message.afficher('ok', f'{len(self.documents)} XML disponible(s)',
            ['Dans chaque module, cliquez sur « XML déjà disponibles » ou « Médiathèque XML » pour utiliser ces archives.'])

    def _ajouter(self, chemins):
        if chemins:
            erreurs = self.app.partager_xml(chemins)
            self.afficher()
            if erreurs:
                self.message.afficher('alerte', 'Import partiel', erreurs[:8])

    def ajouter(self):
        self._ajouter(filedialog.askopenfilenames(parent=self, title='Ajouter à la médiathèque',
                                                 filetypes=[('XML', '*.xml')]))

    def dossier(self):
        dossier = filedialog.askdirectory(parent=self, title='Dossier XML (sous-dossiers inclus)')
        if dossier:
            self._ajouter(sorted(p for p in Path(dossier).rglob('*') if p.is_file() and p.suffix.lower() == '.xml'))

    def retirer(self):
        documents = [self.documents[int(k)] for k in self.table.selection()]
        if documents and messagebox.askyesno('Retirer de la médiathèque',
                'Retirer ces XML de la liste partagée et fermer le dossier actif s’il les utilise ? '
                'Les originaux, exports et historiques sont conservés.', parent=self):
            self.app.retirer_xml(documents)
            self.afficher()
