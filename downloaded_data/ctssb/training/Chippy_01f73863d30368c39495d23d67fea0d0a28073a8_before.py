"""test design of the express.db module"""
import sys
sys.path.append('..')

import warnings
warnings.filterwarnings('ignore', 'Not using MPI as mpi4py not found')

import numpy
from cogent.util.unit_test import TestCase, main

import datetime
from sqlalchemy import create_engine, and_, or_
from sqlalchemy.exc import IntegrityError

from chippy.express.db_schema import Gene, Exon, \
            TargetGene, Expression, ExpressionDiff, ReferenceFile, Sample, \
            make_session
from chippy.express.db_query import get_total_gene_counts, \
        get_ranked_expression, get_ranked_genes_per_chrom, get_genes,\
        get_expression_diff_genes, get_ranked_expression_diff

from chippy.express.db_populate import add_expression_diff_study, add_sample
from chippy.parse.r_dump import SimpleRdumpToTable

__author__ = "Gavin Huttley"
__copyright__ = "Copyright 2011, Anuj Pahwa, Gavin Huttley"
__credits__ = ["Gavin Huttley"]
__license__ = "GPL"
__maintainer__ = "Gavin Huttley"
__email__ = "Gavin.Huttley@anu.edu.au"
__status__ = "alpha"
__version__ = '0.1'

now = datetime.datetime.now()
today = datetime.date(now.year, now.month, now.day)

def add_all_gene_exons(session, genes):
    data = []
    for record in genes:
        gene_data = record['gene']
        exons_data = record['exons']
        gene = Gene(**gene_data)
        data.append(gene)
        for e_data in exons_data:
            exon = Exon(**e_data)
            exon.gene = gene
            data.append(exon)
    session.add_all(data)
    session.commit()


class TestDbBase(TestCase):
    def setUp(self):
        self.session = make_session("sqlite:///:memory:")

class TestRefFiles(TestDbBase):
    a = 'reffile-a.txt'
    b = 'reffile-b.txt'
    d = 'reffile-depends.txt'
    
    def test_depends(self):
        """a reference file with dependencies should correctly link"""
        reffile_a = ReferenceFile(self.a, today)
        reffile_b = ReferenceFile(self.b, today)
        reffile_d = ReferenceFile(self.d, today, ref_a_name=self.a,
                                ref_b_name=self.b)
        self.assertEqual(str(reffile_d),
        "ReferenceFile('reffile-depends.txt', depends=['reffile-a.txt', 'reffile-b.txt'])")
    
    def test_sample_association(self):
        """correctly associate a reference file with a sample"""
        sample = Sample('A', 'a sample')
        reffile_a = ReferenceFile(self.a, today)
        reffile_a.sample = sample
        self.session.add_all([reffile_a, sample])
        self.session.commit()
        reffiles = self.session.query(ReferenceFile).all()
        self.assertEqual(reffiles[0].sample.name, 'A')


class TestGene(TestDbBase):
    """test gene properties"""
    plus_coords_one_exons = dict(gene=dict(ensembl_id='PLUS-1',
        symbol='agene', biotype='protein_coding', status='fake',
        description='a fake gene',
        coord_name='1', start=1000, end=2000, strand=1),
        exons=[dict(ensembl_id='exon-1', rank=1, start=1050, end=1950)]
        )
    
    plus_coords_many_exons = dict(gene=dict(ensembl_id='PLUS-3',
        symbol='agene', biotype='protein_coding', status='fake',
        description='a fake gene',
        coord_name='2', start=1000, end=2000, strand=1), 
        exons=[dict(ensembl_id='exon-1', rank=1, start=1050, end=1400),
               dict(ensembl_id='exon-2', rank=2, start=1600, end=1700),
               dict(ensembl_id='exon-3', rank=3, start=1800, end=1900)]
        )
    
    # 
    minus_coords_one_exons = dict(gene=dict(ensembl_id='MINUS-1',
        symbol='agene', biotype='protein_coding', status='fake',
        description='a fake gene',
        coord_name='2', start=1000, end=2000, strand=-1),
        exons=[dict(ensembl_id='exon-1', rank=1, start=1050, end=1950)]
        )
    
    minus_coords_many_exons = dict(gene=dict(ensembl_id='MINUS-3',
        symbol='agene', biotype='protein_coding', status='fake',
        description='a fake gene',
        coord_name='3', start=1000, end=2000, strand=-1), 
        exons=[dict(ensembl_id='exon-3', rank=3, start=1050, end=1400),
               dict(ensembl_id='exon-2', rank=2, start=1600, end=1700),
               dict(ensembl_id='exon-1', rank=1, start=1800, end=1900)]
        )
    
    genes = [plus_coords_one_exons, plus_coords_many_exons,
            minus_coords_one_exons, minus_coords_many_exons]
    
    def test_add_genes(self):
        """exercise adding a gene"""
        data = [Gene(**self.plus_coords_many_exons['gene']),
                Gene(**self.plus_coords_one_exons['gene']),
                Gene(**self.minus_coords_many_exons['gene']),
                Gene(**self.minus_coords_one_exons['gene'])]
        
        self.session.add_all(data)
        self.session.commit()
    
    def test_unique_constraint_gene(self):
        """adding same gene/ensembl release should raise IntegrityError"""
        data = [Gene(**self.plus_coords_many_exons['gene']),
                Gene(**self.plus_coords_many_exons['gene']),
                Gene(**self.plus_coords_one_exons['gene'])]
        
        self.session.add_all(data)
        self.assertRaises(IntegrityError, self.session.commit)
    
    def test_unique_constraint_exon(self):
        """adding same exon/rank for a gene should raise IntegrityError"""
        data = []
        gene = Gene(**self.plus_coords_many_exons['gene'])
        data.append(gene)
        for e_data in self.plus_coords_many_exons['exons']:
            exon = Exon(**e_data)
            exon.gene = gene
            data.append(exon)
            
        for e_data in self.plus_coords_many_exons['exons']:
            exon = Exon(**e_data)
            exon.gene = gene
            data.append(exon)
        
        self.session.add_all(data)
        self.assertRaises(IntegrityError, self.session.commit)
    
    def test_get_gene_exon_coords(self):
        """Gene instances correctly derive coords for their exons"""
        add_all_gene_exons(self.session, self.genes)
        genes = self.session.query(Gene).all()
        
        expect = {'PLUS-1': [(1050, 1950)],
            'PLUS-3': [(1050, 1400),(1600, 1700),(1800, 1900)],
            'MINUS-1': [(1050, 1950)],
            'MINUS-3': [(1050, 1400),(1600, 1700),(1800, 1900)],}
        for gene in genes:
            self.assertEqual(gene.ExonCoords, expect[gene.ensembl_id])
    
    def test_get_gene_exon_coords_by_rank(self):
        """return exon coordinates in correct exon.rank order"""
        add_all_gene_exons(self.session, self.genes)
        genes = self.session.query(Gene).all()
        
        expect = {'PLUS-1': [(1050, 1950)],
            'PLUS-3': [(1050, 1400),(1600, 1700),(1800, 1900)],
            'MINUS-1': [(1050, 1950)],
            'MINUS-3': [(1800, 1900),(1600, 1700),(1050, 1400)],}
        
        for gene in genes:
            self.assertEqual(gene.ExonCoordsByRank, expect[gene.ensembl_id])
    
    def test_get_gene_intron_coords(self):
        """Gene instances correctly derive coords for their intron"""
        add_all_gene_exons(self.session, self.genes)
        genes = self.session.query(Gene).all()
        expect = {'PLUS-1': [],
            'PLUS-3': [(1400, 1600),(1700, 1800)],
            'MINUS-1': [],
            'MINUS-3': [(1400, 1600),(1700, 1800)],}
        for gene in genes:
            self.assertEqual(gene.IntronCoords, expect[gene.ensembl_id])
    
    def test_get_gene_intron_coords_by_rank(self):
        """get intron coords by exon.rank"""
        add_all_gene_exons(self.session, self.genes)
        genes = self.session.query(Gene).all()
        expect = {'PLUS-1': [],
            'PLUS-3': [(1400, 1600),(1700, 1800)],
            'MINUS-1': [],
            'MINUS-3': [(1700, 1800),(1400, 1600)],}
        for gene in genes:
            self.assertEqual(gene.IntronCoordsByRank, expect[gene.ensembl_id])
    
    def test_gene_tss(self):
        """return correct TSS coordinate"""
        genes = self.session.query(Gene).all()
        expect = {'PLUS-1': 1000,
            'PLUS-3': 1000,
            'MINUS-1': 2000,
            'MINUS-3': 2000}
        for gene in genes:
            self.assertEqual(gene.Tss, expect[gene.ensembl_id])
    
    def test_tss_centred_coords(self):
        """coordinates centred on the TSS correctly slice numpy array"""
        counts = numpy.arange(3000)
        plus = counts[500:1500]
        minus = counts[2500:1500:-1]
        expected_counts = {1:plus, -1:minus}
        add_all_gene_exons(self.session, self.genes)
        genes = self.session.query(Gene).all()
        expect = {'PLUS-1': (500, 1500, 1),
            'PLUS-3': (500, 1500, 1),
            'MINUS-1': (2500, 1500, -1),
            'MINUS-3': (2500, 1500, -1)}
        for gene in genes:
            got_start, got_end, got_strand = gene.getTssCentredCoords(500)
            self.assertEqual((got_start, got_end, got_strand),
                            expect[gene.ensembl_id])
            self.assertEqual(counts[got_start:got_end:got_strand],
                            expected_counts[got_strand])
        
    
    def test_gene_upstream(self):
        """return correct coordinates ending at TSS"""
        add_all_gene_exons(self.session, self.genes)
        genes = self.session.query(Gene).all()
        expect = {'PLUS-1': (500,1000),
            'PLUS-3': (500, 1000),
            'MINUS-1': (2000, 2500),
            'MINUS-3': (2000, 2500)}
        for gene in genes:
            self.assertEqual(gene.getUpstreamCoords(500),
                            expect[gene.ensembl_id])

    def test_anchored_exons_all(self):
        """return correct 3' coords for all exons"""
        add_all_gene_exons(self.session, self.genes)
        plus1 = self.session.query(Gene).filter_by(ensembl_id='PLUS-1').one()
        plus3 = self.session.query(Gene).filter_by(ensembl_id='PLUS-3').one()
        minus1 = self.session.query(Gene).filter_by(ensembl_id='MINUS-1').one()
        minus3 = self.session.query(Gene).filter_by(ensembl_id='MINUS-3').one()
        # no min_spacing returns all for 3 exons cases
        win_size = 100
        expect = {'PLUS-1': None, 'PLUS-3': [(c-win_size, c+win_size)
                                                for c in [1400, 1700, 1900]],
                 'MINUS-1': None, 'MINUS-3': [(c-win_size, c+win_size)
                                                for c in [1800, 1600, 1050]]}

        for gene in (plus1, plus3, minus1, minus3):
            got = gene.getAllExon3primeWindows(win_size)
            self.assertEqual(got, expect[gene.ensembl_id])


    def test_anchored_introns_all(self):
        """return correct 3' coords for all intron"""
        add_all_gene_exons(self.session, self.genes)
        plus1 = self.session.query(Gene).filter_by(ensembl_id='PLUS-1').one()
        plus3 = self.session.query(Gene).filter_by(ensembl_id='PLUS-3').one()
        minus1 = self.session.query(Gene).filter_by(ensembl_id='MINUS-1').one()
        minus3 = self.session.query(Gene).filter_by(ensembl_id='MINUS-3').one()
        # no min_spacing returns all for 3 intron cases
        win_size = 100
        expect = {'PLUS-1': None, 'PLUS-3': [(c-win_size, c+win_size)
                                                    for c in [1600, 1800]],
                 'MINUS-1': None, 'MINUS-3': [(c-win_size, c+win_size)
                                                    for c in [1700, 1400]]}

        for gene in (plus1, plus3, minus1, minus3):
            got = gene.getAllIntron3primeWindows(win_size)
            self.assertEqual(got, expect[gene.ensembl_id])


    def test_anchored_exons_numbered(self):
        """return correct 3' coords for numbered exon"""
        add_all_gene_exons(self.session, self.genes)
        plus1 = self.session.query(Gene).filter_by(ensembl_id='PLUS-1').one()
        plus3 = self.session.query(Gene).filter_by(ensembl_id='PLUS-3').one()
        minus1 = self.session.query(Gene).filter_by(ensembl_id='MINUS-1').one()
        minus3 = self.session.query(Gene).filter_by(ensembl_id='MINUS-3').one()
        # no min_spacing returns all for 3 exons cases, when looping
        win_size = 100
        expect = {'PLUS-1': [(1, None)],
                 'PLUS-3': [(i+1,(c-win_size, c+win_size))
                                for i, c in enumerate([1400, 1700, 1900])],
                 'MINUS-1': [(1, None)],
                 'MINUS-3': [(i+1,(c-win_size, c+win_size))
                                for i,c in enumerate([1800, 1600, 1050])]}
        #
        for gene in (plus1, plus3, minus1, minus3):
            for rank, expect_val in expect[gene.ensembl_id]:
                got = gene.getExon3primeByRank(rank, win_size)
                self.assertEqual(got, expect_val)


    def test_anchored_introns_numbered(self):
        """return correct 3' coords for numbered intron"""
        add_all_gene_exons(self.session, self.genes)
        plus1 = self.session.query(Gene).filter_by(ensembl_id='PLUS-1').one()
        plus3 = self.session.query(Gene).filter_by(ensembl_id='PLUS-3').one()
        minus1 = self.session.query(Gene).filter_by(ensembl_id='MINUS-1').one()
        minus3 = self.session.query(Gene).filter_by(ensembl_id='MINUS-3').one()
        win_size = 100
        expect = {'PLUS-1': [(1, None)],
                  'PLUS-3': [(i+1,(c-win_size, c+win_size))
                                        for i, c in enumerate([1600, 1800])],
                 'MINUS-1': [(1, None)],
                 'MINUS-3': [(i+1,(c-win_size, c+win_size))
                                        for i, c in enumerate([1700, 1400])]}

        for gene in (plus1, plus3, minus1, minus3):
            for rank, expect_val in expect[gene.ensembl_id]:
                got = gene.getIntron3primeByRank(rank, win_size)
                self.assertEqual(got, expect_val)


    def test_anchored_exons_last(self):
        """returns genes last exon3' boundary"""
        add_all_gene_exons(self.session, self.genes)
        plus1 = self.session.query(Gene).filter_by(ensembl_id='PLUS-1').one()
        plus3 = self.session.query(Gene).filter_by(ensembl_id='PLUS-3').one()
        minus1 = self.session.query(Gene).filter_by(ensembl_id='MINUS-1').one()
        minus3 = self.session.query(Gene).filter_by(ensembl_id='MINUS-3').one()
        win_size = 100
        expect = {'PLUS-1': (1950-win_size, 1950+win_size),
                  'PLUS-3': (1900-win_size, 1900+win_size),
                 'MINUS-1': (1050-win_size, 1050+win_size),
                 'MINUS-3': (1050-win_size, 1050+win_size)}
        for gene in (plus1, plus3, minus1, minus3):
            got = gene.getLastExon3prime(win_size)
            self.assertEqual(got, expect[gene.ensembl_id])

    def test_anchored_introns_last(self):
        """returns genes last intron 3' boundary"""
        add_all_gene_exons(self.session, self.genes)
        plus1 = self.session.query(Gene).filter_by(ensembl_id='PLUS-1').one()
        plus3 = self.session.query(Gene).filter_by(ensembl_id='PLUS-3').one()
        minus1 = self.session.query(Gene).filter_by(ensembl_id='MINUS-1').one()
        minus3 = self.session.query(Gene).filter_by(ensembl_id='MINUS-3').one()
        win_size = 100
        expect = {'PLUS-1': None,
                  'PLUS-3': (1800-win_size, 1800+win_size),
                 'MINUS-1': None,
                 'MINUS-3': (1400-win_size, 1400+win_size)}
        for gene in (plus1, plus3, minus1, minus3):
            got = gene.getLastIntron3prime(win_size)
            self.assertEqual(got, expect[gene.ensembl_id])
    

class TestExpression(TestDbBase):
    reffiles = [('file-1.txt', today),
                ('file-2.txt', today)]
    
    samples = [('sample 1', 'fake sample 1'),
               ('sample 2', 'fake sample 2')]
    
    proccessed = False
    
    def setUp(self):
        """docstring for add_files_samples"""
        super(TestExpression, self).setUp()
        
        if not self.proccessed:
            add_all_gene_exons(self.session, TestGene.genes)
        
        data = [ReferenceFile(*r) for r in self.reffiles]
        data += [Sample(*s) for s in self.samples]
        self.session.add_all(data)
        self.session.commit()
        self.proccessed = True
    
    def test_unique_constraint_expression(self):
        """expression records unique by probeset and reference file"""
        gene = self.session.query(Gene).filter_by(ensembl_id='PLUS-1').one()
        sample = self.session.query(Sample).filter_by(name='sample 1').one()
        reffile = self.session.query(ReferenceFile).filter_by(name='file-1.txt').all()
        reffile = reffile[0]
        data = []
        # adding multiple copies with same reffile and transcript
        for probesets, scores in [((1024, 1026), (12.3,)), ((1024, 1026), (12.3,))]:
            expressed = Expression(probesets, scores)
            expressed.reffile_id = reffile.reffile_id
            expressed.sample = sample
            expressed.gene = gene
            data.append(expressed)
        
        self.session.add_all(data)
        self.assertRaises(IntegrityError, self.session.commit)
    
    def test_unique_constraint_expressiondiff(self):
        """expression diff records unique by gene and reffile"""
        gene = self.session.query(Gene).filter_by(ensembl_id='PLUS-1').one()
        
        samples = self.session.query(Sample).all()
        reffiles = self.session.query(ReferenceFile).all()
        
        values = ((12345,), (13,), 0.1, 0)
        ediffs = []
        # now add 2 copies of one expressiondiff
        for i in range(2):
            ed = ExpressionDiff(*values)
            ed.sample_a = samples[0]
            ed.sample_b = samples[1]
            ed.reference_file = reffiles[0]
            ed.gene = gene
            ediffs.append(ed)
        
        self.session.add_all(ediffs)
        self.assertRaises(IntegrityError, self.session.commit)
    

class TestTargetGene(TestDbBase):
    reffiles = [('file-1.txt', today),
                ('file-2.txt', today)]
    
    samples = [('sample 1', 'fake sample 1'),
               ('sample 2', 'fake sample 2')]
    
    proccessed=False
    
    def setUp(self):
        """docstring for add_files_samples"""
        super(TestTargetGene, self).setUp()
        
        if not self.proccessed:
            add_all_gene_exons(self.session, TestGene.genes)
        
        data = [ReferenceFile(*r) for r in self.reffiles]
        data += [Sample(*s) for s in self.samples]
        self.session.add_all(data)
        self.session.commit()
        self.proccessed = True
    
    def test_unique_constraint_target(self):
        """study target genes can only map to single genes"""
        gene = self.session.query(Gene).filter_by(ensembl_id='PLUS-1').one()
        sample = self.session.query(Sample).filter_by(name='sample 1').one()
        reffile = self.session.query(ReferenceFile).filter_by(name='file-1.txt').one()
        data = []
        # adding multiple copies with same reffile and gene
        for i in range(2):
            e = TargetGene()
            e.reference_file = reffile
            e.gene = gene
            e.sample = sample
            data.append(e)
        
        self.session.add_all(data)
        self.assertRaises(IntegrityError, self.session.commit)
    

class TestQueryFunctions(TestDbBase):
    """test the db querying functions"""
    reffiles = [('file-1.txt', today),
                ('file-2.txt', today)]
    
    samples = [('sample 1', 'fake sample 1'),
               ('sample 2', 'fake sample 2')]
    
    proccessed = False
    
    def populate_db(self, **kwargs):
        singleton = kwargs.get('singleton', False)
        data = [ReferenceFile(*r) for r in self.reffiles]
        data += [Sample(*s) for s in self.samples]
        self.session.add_all(data)
        genes = self.session.query(Gene).all()
        if singleton:
            samples = self.session.query(Sample).filter_by(name='sample 1').all()
            reffiles = self.session.query(ReferenceFile).filter_by(name='file-1.txt').all()
        else:
            samples = self.session.query(Sample).all()
            reffiles = self.session.query(ReferenceFile).all()
        
        # adding multiple copies with same reffile and transcript
        for sample, reffile in zip(samples, reffiles):
            for i, gene in enumerate(genes):
                probeset, score = (1024, 21.0+i)
                expressed = Expression((probeset+i,), (score,))
                expressed.reffile_id = reffile.reffile_id
                expressed.sample = sample
                expressed.gene = gene
                self.session.add(expressed)
                
        # add a file with nothing related to it
        reffile = ReferenceFile('file-no-data.txt', today)
        self.session.add(reffile)
        self.session.commit()
    
    def setUp(self, force=False, singleton=False):
        """docstring for add_files_samples"""
        super(TestQueryFunctions, self).setUp()
        
        if not self.proccessed or force:
            add_all_gene_exons(self.session, TestGene.genes)
        
        self.populate_db(singleton=singleton)
        self.proccessed = True

    def _build_target_gene(self, reffile, gene_name, target_sample_name):
        """ helper method to simplify code for creating new TargetGene instances
        """
        tg = TargetGene()
        tg.reference_file = self.session.query(ReferenceFile).\
                filter_by(name=reffile).one()
        tg.gene = self.session.query(Gene).\
                filter_by(ensembl_id=gene_name).one()
        tg.sample = self.session.query(Sample).\
                filter_by(name=target_sample_name).one()
        return tg

    def populate_target_data(self):
        """ populates db for inclusion/exclusion tests in get_ranked_expression
        """
        # Create an extra gene which will be used by TargetGene but not in Sample
        extra_gene_dict = dict(gene=dict(ensembl_id='TARGET-1',
            symbol='agene', biotype='protein_coding', status='fake',
            description='a fake gene',
            coord_name='5', start=3000, end=5000, strand=1),
            exons=[dict(ensembl_id='exon-3', rank=3, start=3050, end=4400)]
        )
        data = [Gene(**extra_gene_dict['gene'])]
        self.session.add_all(data)
        self.session.commit()

        # Create Target reference file
        reffile1 = ReferenceFile('target1.txt', today)
        reffile2 = ReferenceFile('target2.txt', today)
        reffile3 = ReferenceFile('target3.txt', today)
        data=[reffile1, reffile2, reffile3]
        self.session.add_all(data)
        self.session.commit()

        ### Create Target samples
        # target1 = Test 1 overlap, 4 sample and 2 target genes (1 match)
        target_sample1 = Sample('target 1', 'fake target 1')
        # target2 = Test 4 overlap, 4 sample and 4 target genes (4 matches)
        target_sample2 = Sample('target 2', 'fake target 2')
        # target3 = Test 0 overlap, 4 sample and 1 target gene (0 matches)
        target_sample3 = Sample('target 3', 'fake target 3')
        targets = [target_sample1, target_sample2, target_sample3]
        self.session.add_all(targets)
        self.session.commit()

        # Create one matching and one non-matching TargetGenes for target 1
        t1 = self._build_target_gene('target1.txt', 'PLUS-1', 'target 1')
        t2 = self._build_target_gene('target1.txt', 'TARGET-1', 'target 1')
        data = [t1, t2]
        self.session.add_all(data)
        self.session.commit()

        # Create four matching TargetGenes for target 2
        t1 = self._build_target_gene('target2.txt', 'PLUS-1', 'target 2')
        t2 = self._build_target_gene('target2.txt', 'PLUS-3', 'target 2')
        t3 = self._build_target_gene('target2.txt', 'MINUS-1', 'target 2')
        t4 = self._build_target_gene('target2.txt', 'MINUS-3', 'target 2')
        data = [t1, t2, t3, t4]
        self.session.add_all(data)
        self.session.commit()

        # Create 1 non-matching TargetGene for target 3
        t1 = self._build_target_gene('target3.txt', 'TARGET-1', 'target 3')

    
    def test_counting_genes(self):
        """correctly return number of genes for a sample"""
        # return correct number with/without filename
        self.assertEqual(get_total_gene_counts(self.session, 'sample 1'), 4)
        self.assertEqual(get_total_gene_counts(self.session, 'sample 1', 
            data_path='file-1.txt'), 4)
        # return correct number if no records, no file
        self.assertEqual(get_total_gene_counts(self.session,
            'sample 1', data_path='file-no-data.txt'), 0)
        # return correct number if no records, wrong biotype
        self.assertEqual(get_total_gene_counts(self.session,
            'sample 1', biotype='miRNA'), 0)
    
    def test_get_expressed_genes_from_chrom(self):
        """should return the correct number of expressed genes from a chrom"""
        ranked = get_ranked_genes_per_chrom(self.session,
            'sample 1', '2')
        for i in range(1, len(ranked)):
            self.assertTrue(ranked[i-1].Rank < ranked[i].Rank)
        
        for gene in ranked:
            self.assertTrue(gene.coord_name == '2')
    
    def test_get_ranks_scores(self):
        """return correct gene mean ranks and mean scores"""
        self.setUp(force=True, singleton=True)
        genes = get_ranked_expression(self.session,
            'sample 1')
        expected_ranks = {'PLUS-1':4, 'PLUS-3':3, 'MINUS-1':2, 'MINUS-3':1}
        expected_scores = {'PLUS-1':21, 'PLUS-3':22, 'MINUS-1':23, 'MINUS-3':24}
        for gene in genes:
            self.assertEqual(gene.Rank,
                        expected_ranks[gene.ensembl_id])
            self.assertEqual(gene.MeanScore,
                        expected_scores[gene.ensembl_id])
    
    def test_get_ranked_genes(self):
        """return correct gene order"""
        self.setUp(force=True, singleton=True)
        ranked = get_ranked_expression(self.session,
            'sample 1')
        for i in range(1, len(ranked)):
            self.assertTrue(ranked[i-1].Rank < ranked[i].Rank)
        
    
    def test_query_genes_release(self):
        """return correct genes for a release"""
        genes = get_genes(self.session) # returns all genes
        self.assertEqual(len(genes.all()), 4)
        genes = get_genes(self.session, 2) # returns chrom2 genes
        self.assertEqual(len(genes.all()), 2)
        genes = get_genes(self.session, biotype='miRNA') # returns none
        self.assertEqual(len(genes.all()), 0)

    def test_query_expressed_genes_with_inclusive_target_genes(self):
        """ return only those genes which overlap with target """
        # Need to test when we have 100% overlap, 0% overlap and something in between

        self.populate_target_data()

        # Test 1 overlap, 4 sample and 2 target genes
        remaining_genes = get_ranked_expression(self.session, 'sample 1',
                include_target='target 1')
        self.assertTrue(len(remaining_genes) == 1)
        self.assertTrue(remaining_genes[0].ensembl_id == 'PLUS-1')

        # Test 4 overlap, 4 sample and 4 target genes
        remaining_genes = get_ranked_expression(self.session, 'sample 1',
                include_target='target 2')
        self.assertTrue(len(remaining_genes) == 4)
        self.assertTrue(remaining_genes[0].ensembl_id == 'MINUS-3')
        self.assertTrue(remaining_genes[1].ensembl_id == 'MINUS-1')
        self.assertTrue(remaining_genes[2].ensembl_id == 'PLUS-3')
        self.assertTrue(remaining_genes[3].ensembl_id == 'PLUS-1')

        # Test 0 overlap, 4 sample and 1 non-matching target gene
        remaining_genes = get_ranked_expression(self.session, 'sample 1',
                include_target='target 3')
        self.assertTrue(len(remaining_genes) == 0)

    def test_query_expressed_genes_with_exclusive_target_genes(self):
        """ return only those genes which DON'T overlap with target """
        # Need to test when we have 100% overlap, 0% overlap and something in between

        self.populate_target_data()

        # Test 1 overlap, 4 sample and 2 target genes
        remaining_genes = get_ranked_expression(self.session, 'sample 1',
            exclude_target='target 1')
        self.assertTrue(len(remaining_genes) == 3)
        self.assertTrue(remaining_genes[0].ensembl_id == 'MINUS-3')
        self.assertTrue(remaining_genes[1].ensembl_id == 'MINUS-1')
        self.assertTrue(remaining_genes[2].ensembl_id == 'PLUS-3')

        # Test 4 overlap, 4 sample and 4 target genes
        remaining_genes = get_ranked_expression(self.session, 'sample 1',
            exclude_target='target 2')
        self.assertTrue(len(remaining_genes) == 0)

        # Test 0 overlap, 4 sample and 1 non-matching target gene
        remaining_genes = get_ranked_expression(self.session, 'sample 1',
            exclude_target='target 3')
        self.assertTrue(len(remaining_genes) == 4)
        self.assertTrue(remaining_genes[0].ensembl_id == 'MINUS-3')
        self.assertTrue(remaining_genes[1].ensembl_id == 'MINUS-1')
        self.assertTrue(remaining_genes[2].ensembl_id == 'PLUS-3')
        self.assertTrue(remaining_genes[3].ensembl_id == 'PLUS-1')


class TestQueryFunctionsExpDiff(TestDbBase):
    """test the db querying functions"""
    reffiles = [('file-1.txt', today),
                ('file-2.txt', today)]
    
    samples = [('sample 1', 'fake sample 1'),
               ('sample 2', 'fake sample 2')]
    
    dpath = 'data/expression-diff-sample.txt'
    sample = ('sample1', 'blah')
    reffile_path1 = 'sample1.txt'
    reffile_path2 = 'sample2.txt'
    
    def populate_db(self, **kwargs):
        # setting up some starting values
        reffile1 = ReferenceFile(self.reffile_path1, today)
        reffile2 = ReferenceFile(self.reffile_path2, today)
        name, desc = self.sample
        success, rr = add_sample(self.session, name, desc)
        self.assertTrue(success)
        self.session.add_all([reffile1, reffile2])
        self.session.commit()
        table, rr = SimpleRdumpToTable(self.dpath, stable_id_label='gene',
                        probeset_label='probeset', exp_label='exp')
        rr = add_expression_diff_study(self.session, 'sample1', self.dpath, table,
            self.reffile_path1, self.reffile_path2, ensembl_id_label='gene',
            run_record=rr, show_progress=False)
    
    def setUp(self):
        """docstring for add_files_samples"""
        super(TestQueryFunctionsExpDiff, self).setUp()
        add_all_gene_exons(self.session, TestGene.genes)
        self.populate_db()

    def _build_target_gene(self, reffile, gene_name, target_sample_name):
        """ helper method to simplify code for creating new TargetGene instances
        """
        tg = TargetGene()
        tg.reference_file = self.session.query(ReferenceFile).\
        filter_by(name=reffile).one()
        tg.gene = self.session.query(Gene).\
        filter_by(ensembl_id=gene_name).one()
        tg.sample = self.session.query(Sample).\
        filter_by(name=target_sample_name).one()
        return tg

    def populate_target_data(self):
        """ populates db for inclusion/exclusion tests in get_ranked_expression
        """
        # Create an extra gene which will be used by TargetGene but not in Sample
        extra_gene_dict = dict(gene=dict(ensembl_id='TARGET-1',
            symbol='agene', biotype='protein_coding', status='fake',
            description='a fake gene',
            coord_name='5', start=3000, end=5000, strand=1),
            exons=[dict(ensembl_id='exon-3', rank=3, start=3050, end=4400)]
        )
        data = [Gene(**extra_gene_dict['gene'])]
        self.session.add_all(data)
        self.session.commit()

        # Create Target reference file
        reffile1 = ReferenceFile('target1.txt', today)
        reffile2 = ReferenceFile('target2.txt', today)
        reffile3 = ReferenceFile('target3.txt', today)
        data=[reffile1, reffile2, reffile3]
        self.session.add_all(data)
        self.session.commit()

        ### Create Target samples
        # target1 = Test 1 overlap, 4 sample and 2 target genes (1 match)
        target_sample1 = Sample('target 1', 'fake target 1')
        # target2 = Test 4 overlap, 4 sample and 4 target genes (4 matches)
        target_sample2 = Sample('target 2', 'fake target 2')
        # target3 = Test 0 overlap, 4 sample and 1 target gene (0 matches)
        target_sample3 = Sample('target 3', 'fake target 3')
        targets = [target_sample1, target_sample2, target_sample3]
        self.session.add_all(targets)
        self.session.commit()

        # Create one matching and one non-matching TargetGenes for target 1
        t1 = self._build_target_gene('target1.txt', 'PLUS-1', 'target 1')
        t2 = self._build_target_gene('target1.txt', 'TARGET-1', 'target 1')
        data = [t1, t2]
        self.session.add_all(data)
        self.session.commit()

        # Create four matching TargetGenes for target 2
        t1 = self._build_target_gene('target2.txt', 'PLUS-1', 'target 2')
        t2 = self._build_target_gene('target2.txt', 'PLUS-3', 'target 2')
        t3 = self._build_target_gene('target2.txt', 'MINUS-1', 'target 2')
        t4 = self._build_target_gene('target2.txt', 'MINUS-3', 'target 2')
        data = [t1, t2, t3, t4]
        self.session.add_all(data)
        self.session.commit()

        # Create 1 non-matching TargetGene for target 3
        t1 = self._build_target_gene('target3.txt', 'TARGET-1', 'target 3')
    
    def test_add_expression_diff_data(self):
        """correctly add expression difference data"""
        # add the expression diff data
        # do we get it back?
        query = get_expression_diff_genes(self.session, self.sample[0])
        expect = dict([('PLUS-1', [10600707]),
                  ('PLUS-3', [10408081]),
                  ('MINUS-1', [10494402]),
                  ('MINUS-3', [10408083])])
        
        express_diffs = query.all()
        self.assertTrue(len(express_diffs) > 0)
        for diff in express_diffs:
            expect_probeset = expect[diff.gene.ensembl_id]
            self.assertEqual(diff.probesets, expect_probeset)
    
    def test_query_exp_diff(self):
        """return correct records from query when filtered"""
        name_start = {-1: 'MINUS', 1: 'PLUS'}
        for multitest_signif_val in [-1, 1]:
            query = get_expression_diff_genes(self.session, self.sample[0],
                multitest_signif_val=multitest_signif_val)
            
            records = query.all()
            self.assertEqual(len(records), 2)
            # should only get records with the correct test significance
            # direction
            for record in records:
                self.assertEqual(record.multitest_signif,
                    multitest_signif_val)
                # gene names designed to match the test significance
                self.assertTrue(record.gene.ensembl_id.startswith(
                    name_start[multitest_signif_val]))
    
    def test_query_exp_diff_genes(self):
        """return genes ranked by foldchange"""
        genes = get_ranked_expression_diff(self.session, self.sample[0])
        self.assertTrue(len(genes) == 4)
        for i in range(3):
            self.assertTrue(genes[i].Rank < genes[i+1].Rank)
        
        # sample up genes
        genes = get_ranked_expression_diff(self.session, self.sample[0],
            multitest_signif_val=1)
        self.assertTrue(len(genes) == 2)
        expect_order = ['PLUS-1', 'PLUS-3']
        for i in range(2):
            self.assertEqual(genes[i].ensembl_id, expect_order[i])
        
        # sample down genes
        genes = get_ranked_expression_diff(self.session, self.sample[0],
            multitest_signif_val=-1)
        self.assertTrue(len(genes) == 2)
        expect_order = ['MINUS-1', 'MINUS-3']
        for i in range(2):
            self.assertEqual(genes[i].ensembl_id, expect_order[i])

    def test_query_expressed_diff_genes_with_inclusive_target_genes(self):
        """ return only those genes which overlap with target """
        # Need to test when we have 100% overlap, 0% overlap and something in between

        self.populate_target_data()

        # Test 1 overlap, 4 sample and 2 target genes
        remaining_genes = get_ranked_expression_diff(self.session, 'sample1',
            include_target='target 1')
        self.assertTrue(len(remaining_genes) == 1)
        self.assertTrue(remaining_genes[0].ensembl_id == 'PLUS-1')

        # Test 4 overlap, 4 sample and 4 target genes
        remaining_genes = get_ranked_expression_diff(self.session, 'sample1',
            include_target='target 2')
        self.assertTrue(len(remaining_genes) == 4)
        self.assertTrue(remaining_genes[0].ensembl_id == 'PLUS-1')
        self.assertTrue(remaining_genes[1].ensembl_id == 'PLUS-3')
        self.assertTrue(remaining_genes[2].ensembl_id == 'MINUS-1')
        self.assertTrue(remaining_genes[3].ensembl_id == 'MINUS-3')

        # Test 0 overlap, 4 sample and 1 non-matching target gene
        remaining_genes = get_ranked_expression_diff(self.session, 'sample1',
            include_target='target 3')
        self.assertTrue(len(remaining_genes) == 0)

    def test_query_expressed_diff_genes_with_exclusive_target_genes(self):
        """ return only those genes which DON'T overlap with target """
        # Need to test when we have 100% overlap, 0% overlap and something in between

        self.populate_target_data()

        # Test 1 overlap, 4 sample and 2 target genes
        remaining_genes = get_ranked_expression_diff(self.session, 'sample1',
            exclude_target='target 1')
        self.assertTrue(len(remaining_genes) == 3)
        self.assertTrue(remaining_genes[0].ensembl_id == 'PLUS-3')
        self.assertTrue(remaining_genes[1].ensembl_id == 'MINUS-1')
        self.assertTrue(remaining_genes[2].ensembl_id == 'MINUS-3')

        # Test 4 overlap, 4 sample and 4 target genes
        remaining_genes = get_ranked_expression_diff(self.session, 'sample1',
            exclude_target='target 2')
        self.assertTrue(len(remaining_genes) == 0)

        # Test 0 overlap, 4 sample and 1 non-matching target gene
        remaining_genes = get_ranked_expression_diff(self.session, 'sample1',
            exclude_target='target 3')
        self.assertTrue(len(remaining_genes) == 4)
        self.assertTrue(remaining_genes[0].ensembl_id == 'PLUS-1')
        self.assertTrue(remaining_genes[1].ensembl_id == 'PLUS-3')
        self.assertTrue(remaining_genes[2].ensembl_id == 'MINUS-1')
        self.assertTrue(remaining_genes[3].ensembl_id == 'MINUS-3')

if __name__ == '__main__':
    main()
