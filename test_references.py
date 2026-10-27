import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import base_references as B
import import_references as I


def item(code='6309', nom='Friperie', poids='100', fob='150', colis='10', taxes=(('DDI', '1000', '10.0', '100'),), total=None):
    lignes = ''.join(f'<Taxation_line><Duty_tax_code>{c}</Duty_tax_code><Duty_tax_Base>{b}</Duty_tax_Base>'
                     f'<Duty_tax_rate>{r}</Duty_tax_rate><Duty_tax_amount>{m}</Duty_tax_amount></Taxation_line>'
                     for c, b, r, m in taxes)
    total = total if total is not None else sum(int(t[3]) for t in taxes)
    return (f'<Item><Packages><Number_of_packages>{colis}</Number_of_packages></Packages>'
            f'<Tarification><HScode><Commodity_code>{code}</Commodity_code></HScode><Item_price>{fob}</Item_price></Tarification>'
            f'<Goods_description><Description_of_goods>{nom}</Description_of_goods></Goods_description>'
            f'<Taxation><Item_taxes_amount>{total}</Item_taxes_amount>{lignes}'
            f'<Taxation_line><Duty_tax_code/><Duty_tax_amount/></Taxation_line></Taxation>'
            f'<Valuation_item><Weight_itm><Gross_weight_itm>{poids}</Gross_weight_itm></Weight_itm></Valuation_item></Item>')


def declaration(items, fob='150', poids='100', colis='10', globales='50', totales='150', cif='2.83125E7', reference='R1'):
    return (f'<ASYCUDA><Property><Nbers><Total_number_of_packages>{colis}</Total_number_of_packages></Nbers></Property>'
            f'<Identification><Registration><Serial_number>E</Serial_number><Number>12</Number><Date>10/1/26</Date></Registration></Identification>'
            f'<Traders><Consignee><Consignee_name>IMPORT A\nADRESSE</Consignee_name></Consignee></Traders>'
            f'<Declarant><Reference><Number>{reference}</Number></Reference></Declarant>'
            f'<Financial><Amounts><Total_manual_taxes/><Global_taxes>{globales}</Global_taxes><Totals_taxes>{totales}</Totals_taxes></Amounts></Financial>'
            f'<Valuation><Total_CIF>{cif}</Total_CIF><Gs_Invoice><Currency_code>USD</Currency_code><Currency_rate>2265.5</Currency_rate></Gs_Invoice>'
            f'<Total><Total_invoice>{fob}</Total_invoice><Total_weight>{poids}</Total_weight></Total></Valuation>'
            f'{"".join(items)}<Item/><Global_taxes><Global_tax_item/></Global_taxes></ASYCUDA>').encode()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dossier = Path(self.tmp.name)
        self.conn = B.ouvrir(self.dossier / 'base' / 'asydec.db')

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def fichier(self, nom, contenu):
        p = self.dossier / nom
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(contenu)
        return p

    def compter(self, table):
        return self.conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]


class StockageTest(Base):
    def test_decimal_canonique_exact(self):
        self.assertEqual(B.decimal_canonique('2.83125E7'), '28312500')
        self.assertEqual(B.decimal_canonique('30.0'), '30')
        self.assertEqual(B.decimal_canonique(' 19000.250 '), '19000.25')
        self.assertEqual(B.decimal_canonique('0.10769230769231'), '0.10769230769231')
        self.assertIsNone(B.decimal_canonique(''))
        self.assertIsNone(B.decimal_canonique(None))
        for invalide in ('abc', 'NaN', 'Infinity'):
            with self.assertRaises(ValueError):
                B.decimal_canonique(invalide)

    def test_migrations_versionnees_et_idempotentes(self):
        derniere = len(B.MIGRATIONS)
        self.assertEqual(B.version(self.conn), derniere)
        B.migrer(self.conn)
        self.assertEqual(self.compter('schema_versions'), derniere)
        B.migrer(self.conn, B.MIGRATIONS + [(99, 'essai', 'CREATE TABLE essai (x INTEGER)')])
        self.assertEqual(B.version(self.conn), 99)
        with self.assertRaises(sqlite3.OperationalError):  # migration invalide : rien n'est appliqué
            B.migrer(self.conn, B.MIGRATIONS + [(100, 'cassée', 'CREATE TABLE t3 (x); CREATE TABLE ???')])
        self.assertEqual(B.version(self.conn), 99)
        self.assertFalse(self.conn.execute("SELECT 1 FROM sqlite_master WHERE name='t3'").fetchone())

    def test_persistance_apres_fermeture(self):
        I.importer_lot([self.fichier('a.xml', declaration([item()]))], self.conn)
        chemin = self.conn.execute('PRAGMA database_list').fetchone()['file']
        self.conn.close()
        self.conn = B.ouvrir(chemin)
        self.assertEqual(self.compter('documents'), 1)
        self.assertEqual(self.compter('tax_lines'), 1)

    def test_sauvegarde_et_restauration(self):
        I.importer_lot([self.fichier('a.xml', declaration([item()]))], self.conn)
        sauvegarde = B.sauvegarder(self.conn)
        I.importer_lot([self.fichier('b.xml', declaration([item()], reference='R2'))], self.conn)
        chemin = Path(self.conn.execute('PRAGMA database_list').fetchone()['file'])
        self.conn.close()
        precedente = B.restaurer(sauvegarde, chemin)
        self.conn = B.ouvrir(chemin)
        self.assertEqual(self.compter('documents'), 1)              # état de la sauvegarde
        self.assertTrue((precedente / 'asydec.db').exists())       # état remplacé conservé
        archive = self.conn.execute('SELECT archive FROM documents').fetchone()['archive']
        self.assertTrue(Path(archive).exists())

    def test_sauvegarde_endommagee_refusee(self):
        endommagee = self.dossier / 'endommagee'
        endommagee.mkdir()
        (endommagee / 'asydec.db').write_bytes(b'pas une base sqlite' * 100)
        with self.assertRaises(Exception):
            B.restaurer(endommagee, self.dossier / 'autre' / 'asydec.db')
        self.assertFalse((self.dossier / 'autre' / 'asydec.db').exists())


class ExtractionTest(unittest.TestCase):
    def test_valeurs_exactes_et_absences(self):
        d = I.extraire(declaration([item(poids='100.5', fob='150.75')], fob='150.75', poids='100.5'))
        v, a = d['valorisation'], d['articles'][0]
        self.assertEqual(v['cif_total'], '28312500')
        self.assertEqual(v['taux_change'], '2265.5')
        self.assertIsNone(v['taxes_manuelles'])       # absent : reste absent, pas zéro
        self.assertIsNone(v['fret_externe_montant'])
        self.assertEqual((a['poids_brut'], a['fob']), ('100.5', '150.75'))   # décimales conservées
        self.assertEqual(a['ratio'], '1.5')
        self.assertEqual(d['document']['importateur'], 'IMPORT A')
        self.assertEqual(d['document']['enregistrement_date_brute'], '10/1/26')
        self.assertEqual(len(d['articles']), 1)       # ligne <Item/> vide ignorée
        self.assertEqual(a['taxes'], [{'rang': 1, 'code': 'DDI', 'base': '1000', 'taux': '10', 'montant': '100',
                                       'mode_paiement': None, 'type_calcul': None}])
        self.assertEqual(d['taxes_globales'], [])     # détail vide : seul le total est gardé
        self.assertEqual(d['diagnostics'], [])

    def test_position_et_designation_normalisee(self):
        d = I.extraire(declaration([item(nom='  AUTRES   Articles ')]))
        self.assertEqual(d['articles'][0]['designation_normalisee'], 'autres articles')
        self.assertEqual(d['articles'][0]['designation'], 'AUTRES   Articles')

    def test_diagnostics_de_coherence(self):
        d = I.extraire(declaration([item(fob='0', taxes=(('DDI', '1', '1', '40'),), total='99'),
                                    item(colis='5'), item(code='', fob='abc')],
                                   fob='999', globales='1', totales='2'))
        codes = {c for _, c, *_ in d['diagnostics']}
        self.assertTrue({'article_partiel', 'taxes_article', 'total_colis', 'taxes_totales', 'article_repete',
                         'identification_incomplete', 'valeur_invalide'} <= codes)
        partiel = d['articles'][0]
        self.assertIsNone(partiel['ratio'])           # ratio exclu, données conservées
        self.assertEqual(partiel['poids_brut'], '100')

    def test_formats_refuses(self):
        for contenu in (b'<autre/>', b'<ASYCUDA', b'<a:ASYCUDA xmlns:a="urn:x"/>', b'<ASYCUDA><Item/></ASYCUDA>'):
            with self.assertRaises(ValueError):
                I.extraire(contenu)


class ImportTest(Base):
    def test_doublons_provenance_et_homonymes(self):
        contenu = declaration([item()])
        a = self.fichier('lot1/a.xml', contenu)
        copie = self.fichier('lot2/copie renommee.xml', contenu)
        homonyme = self.fichier('lot3/a.xml', declaration([item()], reference='R2'))
        bilan = I.importer_lot([a, copie, homonyme, a], self.conn)
        self.assertEqual((bilan.importes, bilan.doublons, bilan.refuses, bilan.etat), (2, 2, 0, 'termine'))
        self.assertEqual(self.compter('documents'), 2)
        self.assertEqual(self.compter('articles'), 2)
        self.assertEqual(self.compter('document_sources'), 3)   # a, copie, homonyme
        relance = I.importer_lot([a, copie, homonyme], self.conn)
        self.assertEqual((relance.importes, relance.doublons), (0, 3))

    def test_fichiers_refuses_dans_le_bilan(self):
        bon = self.fichier('bon.xml', declaration([item()]))
        mauvais = self.fichier('mauvais.xml', b'<pas du xml')
        bilan = I.importer_lot([mauvais, bon], self.conn)
        self.assertEqual((bilan.importes, bilan.refuses), (1, 1))
        self.assertEqual(bilan.refus[0][0], 'mauvais.xml')
        lot = self.conn.execute('SELECT * FROM import_batches WHERE id = ?', (bilan.lot_id,)).fetchone()
        self.assertEqual((lot['etat'], lot['importes'], lot['refuses']), ('termine', 1, 1))
        self.assertEqual(self.compter("diagnostics WHERE code = 'fichier_refuse'"), 1)

    def test_aucun_document_a_moitie_importe(self):
        original = I._inserer

        def panne(conn, table, valeurs):
            if table == 'tax_lines':
                raise sqlite3.OperationalError('disque plein')
            return original(conn, table, valeurs)

        with patch.object(I, '_inserer', panne):
            with self.assertRaises(sqlite3.OperationalError):
                I.importer_fichier(self.conn, self.fichier('a.xml', declaration([item()])))
        for table in ('documents', 'articles', 'valuations', 'document_sources'):
            self.assertEqual(self.compter(table), 0, table)
        bilan = I.importer_lot([self.dossier / 'a.xml'], self.conn)   # nouvel essai : import complet
        self.assertEqual(bilan.importes, 1)

    def test_annulation_entre_deux_documents(self):
        fichiers = [self.fichier(f'{k}.xml', declaration([item()], reference=f'R{k}')) for k in range(3)]
        bilan = I.importer_lot(fichiers, self.conn, annulation=lambda: self.compter('documents') >= 2)
        self.assertEqual((bilan.etat, bilan.importes), ('annule', 2))
        reprise = I.importer_lot(fichiers, self.conn)
        self.assertEqual((reprise.importes, reprise.doublons), (1, 2))

    def test_import_ne_marque_jamais_accepte(self):
        I.importer_lot([self.fichier('a.xml', declaration([item()]))], self.conn)
        I.importer_lot([self.fichier('genere.xml', declaration([item()], reference='G'))], self.conn, origine='genere')
        self.assertEqual(self.compter('status_events'), 0)
        statuts = self.conn.execute('SELECT d.origine, s.statut FROM documents d '
                                    'JOIN document_statuts s ON s.document_id = d.id ORDER BY d.id').fetchall()
        self.assertEqual([tuple(r) for r in statuts], [('importe', 'non_verifie'), ('genere', 'non_verifie')])


class StatutsTest(Base):
    def setUp(self):
        super().setUp()
        import service_references as S
        self.S = S
        I.importer_lot([self.fichier('a.xml', declaration([item()]))], self.conn)
        self.doc = self.conn.execute('SELECT id FROM documents').fetchone()[0]

    def test_acceptation_exige_une_preuve(self):
        with self.assertRaises(ValueError):
            self.S.enregistrer_statut(self.conn, self.doc, 'accepte', preuve='  ')
        with self.assertRaises(sqlite3.IntegrityError):   # la base refuse aussi, même sans le service
            self.conn.execute("INSERT INTO status_events (document_id, type, nouveau, saisi_le) "
                              "VALUES (?, 'changement', 'accepte', 'x')", (self.doc,))
        e = self.S.enregistrer_statut(self.conn, self.doc, 'accepte', preuve='Enregistrement E 12',
                                      commentaire='Quittance reçue', auteur='agent', date_effective='2026-10-01')
        self.assertEqual((e['ancien'], e['nouveau'], e['date_effective'], e['auteur']),
                         ('non_verifie', 'accepte', '2026-10-01', 'agent'))
        self.assertEqual(self.S.statut(self.conn, self.doc), 'accepte')

    def test_rejet_exclusion_et_retour_exigent_un_motif(self):
        for statut in ('rejete', 'exclu'):
            with self.assertRaises(ValueError):
                self.S.enregistrer_statut(self.conn, self.doc, statut)
        self.S.enregistrer_statut(self.conn, self.doc, 'rejete', commentaire='Valeur contestée')
        with self.assertRaises(ValueError):
            self.S.enregistrer_statut(self.conn, self.doc, 'rejete', commentaire='encore')   # déjà rejeté
        with self.assertRaises(ValueError):
            self.S.enregistrer_statut(self.conn, self.doc, 'non_verifie')
        self.S.enregistrer_statut(self.conn, self.doc, 'non_verifie', commentaire='Erreur de saisie')
        self.assertEqual([e['nouveau'] for e in self.S.historique_statuts(self.conn, self.doc)],
                         ['rejete', 'non_verifie'])

    def test_dates_effectives_controlees(self):
        for date in ('10/1/26', '2026-13-01', '2999-01-01'):
            with self.assertRaises(ValueError):
                self.S.enregistrer_statut(self.conn, self.doc, 'accepte', preuve='P', date_effective=date)
        self.assertEqual(self.S.historique_statuts(self.conn, self.doc), [])

    def test_historique_en_ajout_seul_et_corrections(self):
        e = self.S.enregistrer_statut(self.conn, self.doc, 'accepte', preuve='Quittance Q 4437', date_effective='2026-10-01')
        for sql in ('UPDATE status_events SET preuve = NULL', 'DELETE FROM status_events'):
            with self.assertRaises(sqlite3.IntegrityError):
                self.conn.execute(sql)
        with self.assertRaises(ValueError):
            self.S.corriger_evenement(self.conn, e['id'], commentaire='', date_effective='2026-10-02')
        c = self.S.corriger_evenement(self.conn, e['id'], commentaire='Date de la quittance', date_effective='2026-10-02')
        self.assertEqual((c['type'], c['corrige_id'], c['nouveau'], c['preuve'], c['date_effective']),
                         ('correction', e['id'], 'accepte', 'Quittance Q 4437', '2026-10-02'))
        self.assertEqual(self.S.evenement(self.conn, e['id'])['date_effective'], '2026-10-01')   # original intact
        self.S.enregistrer_statut(self.conn, self.doc, 'exclu', commentaire='Dossier atypique')
        self.S.corriger_evenement(self.conn, e['id'], commentaire='Précision', preuve='Quittance Q 4437 bis')
        self.assertEqual(self.S.statut(self.conn, self.doc), 'exclu')   # une correction ne change pas le statut
        with self.assertRaises(sqlite3.IntegrityError):    # un document avec historique ne se supprime pas
            self.conn.execute('DELETE FROM documents WHERE id = ?', (self.doc,))

    def test_nouvelle_version_n_herite_pas_du_statut(self):
        self.S.enregistrer_statut(self.conn, self.doc, 'accepte', preuve='Enregistrement E 12')
        I.importer_lot([self.fichier('a modifie.xml', declaration([item(fob='151')], fob='151'))], self.conn)
        nouveau = self.conn.execute('SELECT MAX(id) FROM documents').fetchone()[0]
        self.assertEqual(self.S.statut(self.conn, nouveau), 'non_verifie')
        self.assertEqual(self.S.statut(self.conn, self.doc), 'accepte')

    def test_preuve_suggeree_sans_acceptation(self):
        self.assertEqual(self.S.preuve_suggeree(self.conn, self.doc), 'Enregistrement E 12 du 10/1/26')
        self.assertEqual(self.S.statut(self.conn, self.doc), 'non_verifie')

    def test_liste_filtree_par_statut(self):
        I.importer_lot([self.fichier('b.xml', declaration([item()], reference='R2'))], self.conn)
        self.S.enregistrer_statut(self.conn, self.doc, 'accepte', preuve='P')
        self.assertEqual([d['id'] for d in self.S.lister_documents(self.conn, statut='accepte')], [self.doc])
        self.assertEqual(len(self.S.lister_documents(self.conn, statut='non_verifie')), 1)
        self.assertEqual(len(self.S.lister_documents(self.conn, recherche='b.xml')), 1)


if __name__ == '__main__':
    unittest.main()
