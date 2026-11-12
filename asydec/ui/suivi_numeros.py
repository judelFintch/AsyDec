"""Fenêtre « Suivi des numéros » : progression des E, liquidations, Q et manifestes dans l'année."""
from datetime import date
import random
import tkinter as tk
from tkinter import ttk

from asydec.declarations import numeros_logiques as N
from asydec.ui import theme

COULEURS = (('saisie', 'Saisies AsyDec', '#2563EB'), ('liste', 'Listes collées', '#059669'),
            ('déclaration réelle', 'Déclarations réelles', '#7C3AED'), ('dossier', 'Dossiers', '#0EA5E9'))
ECARTE = '#9CA3AF'


def categorie(source):
    for prefixe, libelle, couleur in COULEURS:
        if str(source).startswith(prefixe):
            return libelle, couleur
    return 'Autres', '#6B7280'


class SuiviNumeros(tk.Toplevel):
    def __init__(self, parent, points, annee=None):
        super().__init__(parent)
        self.title('Suivi des numéros E, L, Q et manifeste')
        self.geometry('1000x720')
        self.minsize(820, 600)
        self.points = points
        annees = sorted({p['date'].year for p in points} | {date.today().year}, reverse=True)
        self.annee = tk.IntVar(value=annee or annees[0])
        self.type_ = tk.StringVar(value='E')
        cadre = ttk.Frame(self, padding=16)
        cadre.pack(fill='both', expand=True)
        theme.entete_page(cadre, 'Suivi des numéros', 'Progression dans l’année, d’après tout ce qui est connu')
        barre = ttk.Frame(cadre)
        barre.pack(fill='x', pady=(0, 8))
        for type_, (_, _, libelle, _) in N.TYPES.items():
            ttk.Radiobutton(barre, text=libelle, value=type_, variable=self.type_,
                            command=self.dessiner).pack(side='left', padx=(0, 12))
        ttk.Label(barre, text='Année', style='Doux.TLabel').pack(side='left', padx=(20, 6))
        choix = ttk.Combobox(barre, values=annees, textvariable=self.annee, width=6, state='readonly')
        choix.pack(side='left')
        choix.bind('<<ComboboxSelected>>', lambda _e: self.dessiner())
        self.resume = tk.StringVar()
        ttk.Label(cadre, textvariable=self.resume, style='Section.TLabel', wraplength=940,
                  justify='left').pack(anchor='w', pady=(0, 6))
        self.toile = tk.Canvas(cadre, bg='white', highlightthickness=1, highlightbackground='#E5E7EB', height=380)
        self.toile.pack(fill='both', expand=True)
        legende = ttk.Frame(cadre)
        legende.pack(fill='x', pady=(6, 6))
        for _, libelle, couleur in COULEURS + (('', 'Hors chronologie (écartés)', ECARTE),):
            tk.Label(legende, text='●', fg=couleur, bg=theme.FOND).pack(side='left')
            ttk.Label(legende, text=libelle, style='Doux.TLabel').pack(side='left', padx=(2, 14))
        self.table = ttk.Treeview(cadre, columns=('date', 'numero', 'source', 'etat'), show='headings', height=7)
        for cle, titre, largeur in (('date', 'Date', 110), ('numero', 'Numéro', 100), ('source', 'Source', 520),
                                    ('etat', 'État', 150)):
            self.table.heading(cle, text=titre, anchor='w')
            self.table.column(cle, width=largeur, anchor='w')
        self.table.pack(fill='x')
        self.toile.bind('<Configure>', lambda _e: self.dessiner())

    def dessiner(self):
        type_, annee = self.type_.get(), int(self.annee.get())
        libelle = N.TYPES[type_][2]
        donnees = N.tendance(self.points, type_, annee)
        retenus, ecartes = donnees['retenus'], donnees['ecartes']
        jour = date.today() if date.today().year == annee else date(annee, 12, 31)
        estime = N.proposer_numero(self.points, type_, jour, 1, tirage=random.Random(0))
        dernier = retenus[-1] if retenus else None
        self.resume.set(
            f"{libelle} {annee} : {len(retenus)} numéro(s) connus"
            + (f" · {len(ecartes)} hors chronologie" if ecartes else '')
            + f" · environ {donnees['rythme']:.0f} par jour"
            + (f" · dernier connu {dernier['numero']} le {dernier['date']:%d/%m/%Y}" if dernier else '')
            + (f"\nProchain numéro probable au {jour:%d/%m/%Y} : {estime[0]}" if estime else ''))
        self._graphique(retenus, ecartes, annee, jour, estime)
        self.table.delete(*self.table.get_children())
        for p in sorted(retenus + ecartes, key=lambda p: (p['date'], p['numero']), reverse=True)[:200]:
            self.table.insert('', 'end', values=(f"{p['date']:%d/%m/%Y}", p['numero'], p['source'],
                                                 'écarté' if p in ecartes else categorie(p['source'])[0]))

    def _graphique(self, retenus, ecartes, annee, jour, estime):
        t = self.toile
        t.delete('all')
        largeur, hauteur = max(t.winfo_width(), 400), max(t.winfo_height(), 200)
        g, d, h, b = 70, 20, 16, 34
        tous = retenus + ecartes
        maximum = max([p['numero'] for p in tous] + ([estime[0]] if estime else []) + [10])
        maximum = int(maximum * 1.08) + 1
        debut, fin = date(annee, 1, 1), date(annee, 12, 31)
        x = lambda j: g + (largeur - g - d) * (j - debut).days / (fin - debut).days
        y = lambda n: hauteur - b - (hauteur - b - h) * n / maximum
        for mois in range(1, 13):
            xm = x(date(annee, mois, 1))
            t.create_line(xm, h, xm, hauteur - b, fill='#F3F4F6')
            t.create_text(xm + 4, hauteur - b + 12, text=('janv', 'févr', 'mars', 'avr', 'mai', 'juin', 'juil',
                                                          'août', 'sept', 'oct', 'nov', 'déc')[mois - 1],
                          anchor='w', fill='#6B7280', font=(theme.POLICE, 9))
        for k in range(5):
            n = maximum * k / 4
            t.create_line(g, y(n), largeur - d, y(n), fill='#F3F4F6')
            t.create_text(g - 6, y(n), text=f'{n:,.0f}'.replace(',', ' '), anchor='e', fill='#6B7280',
                          font=(theme.POLICE, 9))
        t.create_line(g, hauteur - b, largeur - d, hauteur - b, fill='#9CA3AF')
        if len(retenus) > 1:
            t.create_line(*[c for p in retenus for c in (x(p['date']), y(p['numero']))], fill='#93C5FD', width=2)
        for p in ecartes:
            t.create_text(x(p['date']), y(p['numero']), text='×', fill=ECARTE, font=(theme.POLICE, 11, 'bold'))
        for p in retenus:
            couleur = categorie(p['source'])[1]
            t.create_oval(x(p['date']) - 3, y(p['numero']) - 3, x(p['date']) + 3, y(p['numero']) + 3,
                          fill=couleur, outline=couleur)
        if estime:
            xe, ye = x(jour), y(estime[0])
            if retenus:
                dernier = retenus[-1]
                if dernier['date'] < jour:
                    t.create_line(x(dernier['date']), y(dernier['numero']), xe, ye, fill='#F59E0B', dash=(4, 3), width=2)
            t.create_oval(xe - 5, ye - 5, xe + 5, ye + 5, outline='#F59E0B', width=2)
            t.create_text(xe - 8, ye - 12, text=f'probable {estime[0]}', anchor='e', fill='#B45309',
                          font=(theme.POLICE, 10, 'bold'))
