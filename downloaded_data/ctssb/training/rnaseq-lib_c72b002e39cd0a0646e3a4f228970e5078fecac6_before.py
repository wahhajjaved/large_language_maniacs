import holoviews as hv
import numpy as np
import pandas as pd

from rnaseq_lib.diff_exp import log2fc
from rnaseq_lib.dim_red import run_tsne, run_tete
from rnaseq_lib.plot.opts import gene_curves_opts, gene_kde_opts, gene_distribution_opts, gene_de_opts
from rnaseq_lib.tissues import subset_by_dataset


class Holoview:
    """
    Object for Holoviews plots of gene expression data. Created for use with Holomap and DynamicMap which cannot
    accept dataframes as arguments. This class circumvents that limitation by referencing
    the dataframe internally.
    """

    def __init__(self, df):
        """
        :param pd.DataFrame df: Dataframe containing metadata / expression values (Synapse.org: syn11515015)
        """
        self.df = df
        self.df_cols = ['id', 'tissue', 'dataset', 'tumor', 'type']

        # Style attributes - used in conjunction with '.opts()'
        self.gene_curves_opts = gene_curves_opts
        self.gene_kde_opts = gene_kde_opts
        self.gene_distribution_opts = gene_distribution_opts
        self.gene_de_opts = gene_de_opts

    @staticmethod
    def l2norm(x):
        """
        Log2 noramlization function for gene counts

        :param float x: Input value
        :return: log2(x+1) normalized value
        :rtype: float
        """
        return np.log2(x + 1)

    def _subset(self, gene, tissue):
        """
        Subset dataframe by gene and tissue with default columns `self.df_cols`

        :param str gene: Gene (ex: ERBB2) to select
        :param str tissue: Tissue (ex: Breast) to select
        :return: Subset dataframe
        :rtype: pd.DataFrame
        """
        df = self.df[self.df_cols + [gene]].sort_values(gene, ascending=False)
        return df[df.tissue == tissue]

    def _gene_cutoff(self, gene, tissue, percent):
        # Subset dataframe by tissue and gene
        df = self._subset(tissue, gene)

        # Subset by dataset
        tumor, normal, gtex = subset_by_dataset(df)

        # Calculate gene expression cutoffs for each dataset
        cutoffs = [x[gene].sort_values(ascending=False).iloc[int(len(x) * percent) - 1]
                   for x in [tumor, normal, gtex]]

        # Return mapping of dataset to cutoff
        return {x: y for x, y in zip(['tumor', 'normal', 'gtex'], cutoffs)}

    def gene_kde(self, gene, tissue):
        """
        Returns KDE of gene expression (log2) for given tissue

        :param str gene: Gene (ex: ERBB2) to select
        :param str tissue: Tissue (ex: Breast) to select
        :return: Returns holoviews Overlay object of gene KDE
        :rtype: hv.Overlay
        """
        # Subset dataframe by tissue and gene
        df = self._subset(tissue, gene)

        # Subset by dataset
        tumor, normal, gtex = subset_by_dataset(df)

        # Define x dimension for labeling
        x = hv.Dimension('Gene Expression', unit='log2(x+1)')

        # Create KDE objects
        t = hv.Distribution(tumor[gene].apply(self.l2norm), kdims=[x], label='Tumor-{}'.format(tissue))
        g = hv.Distribution(gtex[gene].apply(self.l2norm), kdims=[x], label='GTEx-{}'.format(tissue))

        return hv.Overlay([t, g], label='{} Expression'.format(gene))

    def multiple_tissue_gene_kde(self, gene, *tissues):
        return hv.Overlay([self.gene_kde(gene, t) for t in tissues],
                          label='{} Expression'.format(gene))

    def gene_distribution(self, gene, tissue_subset=None, extents=None):
        """
        Box and Whisker expression distribution across tissues

        :param str gene: Gene (ex: ERBB2) to select
        :param list tissue_subset: List of tissues to subset by
        :param tuple extents: xmin/ymin/xmax/ymax values
        :return: Returns holoviews BoxWhisker object
        :rtype: hv.BoxWhisker
        """
        # Subset dataframe by gene
        df = self.df[self.df_cols + [gene]].sort_values(gene, ascending=False)

        # Subset by tissues
        if tissue_subset:
            df = df[df.tissue.isin(tissue_subset)]

        # Normalize gene expression
        df[gene] = df[gene].apply(lambda x: np.log2(x + 1))

        # Subset for Tumor and GTEx
        df = df[((df.tumor == 'yes') | (df.dataset == 'gtex'))]

        # return grouped box and whiskers:
        return hv.BoxWhisker((df.tissue, df.dataset, df[gene]), kdims=['tissue', 'dataset'],
                             vdims='gene', label='{} Expression'.format(gene))

    def gene_DE(self, gene, extents=None):
        """
        Scatter plot of differential expression across all tissues

        :param str gene: Gene (ex: ERBB2) to select
        :param tuple extents: xmin/ymin/xmax/ymax values
        :return: Scatterplot of values
        :rtype: hv.Scatter
        """
        # Subset dataframe by gene
        df = self.df[self.df_cols + [gene]].sort_values(gene, ascending=False)

        # Subset by dataset
        tumor, normal, gtex = subset_by_dataset(df)

        # For each tissue, calculate L2FC and mean expression
        records = []
        for tissue in sorted(df.tissue.unique()):
            # Calculate mean expression for TCGA tumor and GTEx
            exp = df[(df.tissue == tissue) & ((df.tumor == 'yes') | (df.dataset == 'gtex'))][gene].apply(
                self.l2norm).median()

            # Calculate tumor and normal expression
            t = tumor[tumor.tissue == tissue][gene].median()
            g = gtex[gtex.tissue == tissue][gene].median()

            # Calculate log2 fold change
            l2fc = log2fc(t, g)

            # Store as record
            records.append((exp, l2fc, tissue))

        # Define dimensions of plot
        kdims = ['Expression']
        vdims = ['L2FC', 'Tissue']

        # Create dataframe
        plot = pd.DataFrame.from_records(records, columns=kdims + vdims)

        if extents:
            return hv.Scatter(plot, kdims=kdims, vdims=vdims, extents=extents)
        else:
            return hv.Scatter(plot, kdims=kdims, vdims=vdims)

    def gene_curves(self, gene, tissue):
        """
        Returns set of 3 plots for tissue / gene given a dataframe of metadata and expression values

        :param str gene: Gene (ex: ERBB2) to select
        :param str tissue: Tissue (ex: Breast) to select
        :return: Returns holoviews Layout object containing 3 plots for selected Tisssue / Gene
        :rtype: hv.Layout
        """
        # Subset dataframe for gene and tissue
        df = self._subset(tissue, gene)

        # Logscale gene for calculations
        df[gene] = df[gene].apply(lambda x: np.log2(x + 1))

        # Subset by dataset
        tumor, normal, gtex = subset_by_dataset(df)

        # Get values for plot
        records = []
        for perc_tumor in [x * 0.1 for x in xrange(1, 11)]:
            # Get log2 expression value for top x% tumor samples
            exp = float(tumor.iloc[int(len(tumor) * perc_tumor) - 1][gene])

            # Get percentage of samples in GTEx
            perc_normal = (len(gtex[gtex[gene] > exp]) * 1.0) / len(gtex)

            # Compute L2FC for tumor sample subset vs GTEx
            tumor_mean = tumor.iloc[:int(len(tumor) * perc_tumor) - 1][gene].apply(lambda x: 2 ** x - 1).median()
            gtex_mean = gtex[gene].apply(lambda x: 2 ** x - 1).median()
            l2fc = log2fc(tumor_mean, gtex_mean)

            # Store
            records.append((tissue, exp, l2fc, perc_tumor, perc_normal, len(gtex), len(tumor), 'GTEx'))

        # Create dataframe from records
        info = pd.DataFrame.from_records(records, columns=['tissue', 'expression',
                                                           'l2fc',
                                                           'percent_tumor',
                                                           'percent_normal',
                                                           'num_normals', 'num_tumors',
                                                           'normal_dataset'])

        # Define dimensions
        tissue_dim = hv.Dimension('tissue', label='Tissue')
        ptumor_dim = hv.Dimension('percent_tumor', label='% Tumor')
        pnormal_dim = hv.Dimension('percent_normal', label='percent')
        l2fc_dim = hv.Dimension('l2fc', label='log2FC')
        exp_dim = hv.Dimension('expression', label='log2(x+1)')

        # First plot - Percentage of Normal Samples
        c1 = hv.Curve(data=info, kdims=[ptumor_dim],
                      vdims=[pnormal_dim, tissue_dim], group='Percentage of Normal Samples',
                      extents=(None, 0, None, 1))

        s1 = hv.Scatter(data=info, kdims=[ptumor_dim],
                        vdims=[pnormal_dim, tissue_dim], group='Percentage of Normal Samples')

        # Second Plot - Expression
        c2 = hv.Curve(data=info, kdims=[ptumor_dim],
                      vdims=[exp_dim, tissue_dim], group='Gene Expression',
                      extents=(None, 0, None, 16))

        s2 = hv.Scatter(data=info, kdims=[ptumor_dim],
                        vdims=[exp_dim, tissue_dim], group='Gene Expression')

        # Third Plot - Log2 Fold Change
        c3 = hv.Curve(data=info, kdims=[ptumor_dim],
                      vdims=[l2fc_dim, tissue_dim], group='Log2 Fold Change',
                      extents=(None, -0.5, None, 8))

        s3 = hv.Scatter(data=info, kdims=[ptumor_dim],
                        vdims=[l2fc_dim, tissue_dim], group='Log2 Fold Change')

        return (c1 * s1 + c2 * s2 + c3 * s3).cols(1)

    def trimap(self, genes, title, tissue_subset=None, num_neighbors=50):
        """
        Dimensionality reduction via Trimap

        :param list(str) genes: List of genes to subset by
        :param list(str) tissue_subset: List of tissues to subset by
        :return: Scatterplot of dimensionality reduction
        :rtype: hv.Scatter
        """
        # Subset dataframe by genes (keeping some metadata)
        df = self.df[self.df_cols + genes]

        # Subset by tissues
        if tissue_subset:
            df = df[df.tissue.isin(tissue_subset)]

        # Run Trimap (used to be called t-ETE)
        z = run_tete(df[genes], num_dims=2, num_neighbors=num_neighbors)

        # Add results to dataframe
        df['x'] = z[:, 0]
        df['y'] = z[:, 1]

        return hv.Scatter(df, kdims=['x'], vdims=['y'] + self.df_cols,
                          group=title)

    def tsne(self, genes, title, tissue_subset=None, perplexity=50, learning_rate=1000):
        """
        Dimensionality reduction via t-SNE

        :param list(str) genes: List of genes to subset by
        :param list(str) tissue_subset: List of tissues to subset by
        :return: Scatterplot of dimensionality reduction
        :rtype: hv.Scatter
        """
        # Subset dataframe by genes (keeping some metadata)
        df = self.df[self.df_cols + genes]

        # Subset by tissues
        if tissue_subset:
            df = df[df.tissue.isin(tissue_subset)]

        # Run t-SNE
        z = run_tsne(df[genes], num_dims=2, perplexity=perplexity, learning_rate=learning_rate)

        # Add results to dataframe
        df['x'] = z[:, 0]
        df['y'] = z[:, 1]

        return hv.Scatter(df, kdims=['x'], vdims=['y'] + self.df_cols,
                          group=title)
