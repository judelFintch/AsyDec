import tempfile
from pathlib import Path
from unittest import TestCase, mock

from asydec.declarations import impression_dossier as I
from asydec.systeme import impression


class ImpressionDossierTest(TestCase):
    def licence(self, dossier):
        def f(nom):
            chemin = Path(dossier) / nom
            chemin.write_bytes(b'x')
            return str(chemin)
        return {
            'factures_parts': {
                'parts': [{'part': i, 'fichiers': {'facture': f(f'f{i}.docx'), 'packing list': f(f'p{i}.docx')}} for i in (1, 2)],
                'globale': {'fichiers': {'facture': f('fg.docx'), 'packing list': f('pg.docx')}}},
            'cvi_parts': {'fichiers': [f('cvi.docx'), str(Path(dossier) / 'absent.docx')]},
            'declarations': {'fichiers': [{'part': 2, 'fichier': f('d2.docx')}, {'part': 1, 'fichier': f('d1.docx')}]},
        }

    def test_documents_presents_seulement(self):
        with tempfile.TemporaryDirectory() as d:
            docs = I.documents(self.licence(d))
            self.assertEqual({k: len(v) for k, v in docs.items()},
                             {'fiche': 0, 'factures': 2, 'packing': 2, 'facture_globale': 1, 'packing_globale': 1,
                              'cvi': 1, 'declarations': 2})

    def test_ordre_par_part_et_par_type(self):
        with tempfile.TemporaryDirectory() as d:
            docs = I.documents(self.licence(d))
            tout = {c for c, _ in I.GROUPES}
            par_part = [l for l, _ in I.ordonner(docs, tout, True)]
            self.assertEqual(par_part, ['Fiche du dossier', 'Facture globale', 'Packing list globale', 'CVI + BL',
                                        'Facture part 1', 'Packing list part 1', 'Déclaration part 1',
                                        'Facture part 2', 'Packing list part 2', 'Déclaration part 2'])
            par_type = [l for l, _ in I.ordonner(docs, {'factures', 'declarations'}, False)]
            self.assertEqual(par_type, ['Facture part 1', 'Facture part 2', 'Déclaration part 1', 'Déclaration part 2'])

    def test_choix_par_defaut(self):
        # Factures des parts et packing list globale décochées ; packing lists des parts, facture globale,
        # CVI + BL et déclarations cochées.
        with tempfile.TemporaryDirectory() as d:
            docs = I.documents(self.licence(d))
            libelles = [l for l, _ in I.ordonner(docs, I.PAR_DEFAUT, True)]
            self.assertEqual(libelles, ['Facture globale', 'CVI + BL', 'Packing list part 1', 'Déclaration part 1',
                                        'Packing list part 2', 'Déclaration part 2'])

    def test_impression_cups_sans_dialogue(self):
        with tempfile.NamedTemporaryFile(suffix='.pdf') as pdf, \
                mock.patch.object(impression.sys, 'platform', 'darwin'), \
                mock.patch.object(impression, '_executer') as executer:
            executer.return_value = mock.Mock(returncode=0, stdout='request id is Canon-12', stderr='')
            message = impression.imprimer(pdf.name, 'Canon', copies=2, recto_verso=True, titre='DOSSIER')
            commande = executer.call_args[0][0]
            self.assertEqual(commande[0], 'lp')
            self.assertIn('Canon', commande)
            self.assertIn('2', commande)
            self.assertIn('sides=two-sided-long-edge', commande)
            self.assertIn('Canon', message)

    def test_imprimante_refuse(self):
        with tempfile.NamedTemporaryFile(suffix='.pdf') as pdf, \
                mock.patch.object(impression.sys, 'platform', 'darwin'), \
                mock.patch.object(impression, '_executer') as executer:
            executer.return_value = mock.Mock(returncode=1, stdout='', stderr='lp: erreur')
            with self.assertRaises(impression.ImpressionImpossible):
                impression.imprimer(pdf.name)
