# RNAseq modules


def fqc(raw_file):
    import os

    os.system('mkdir fqc_result')
    os.system('fastqc -o fqc_result --extract ./' + raw_file)

# Creates a adapters-list, extracted out of a FastQC analysis.
# The results must be stored in a folder called fqc_results
# and the results folder itself must be called according to file_name
# with the extension _fastqc


def extract_adapters(file_name):
    # Getting the file-path to the fastQC-results
    file_path = './fqc_result/' + file_name + '_fastqc/fastqc_data.txt'

    ad_seq = []
    saving = 0
    for line in open(file_path):
        line_dat = line.split(' ')

        # Starting saving the lines when a line starts with >>Overrepresented
        if line_dat[0] == '>>Overrepresented':
            saving = 1

        # Saving the lines in the list ad_seq
        if saving == 1:
            seq = line_dat[0]
            seq = seq.split('\t')[0]
            ad_seq.append(seq)

            # Stopping the saving after a line with >>End_Module\n appears
            if line_dat[0] == '>>END_MODULE\n':
                saving = 0

    # Removing the first two lines consisting
    # of descriptive headlines and the last line
    # with >>END_MODULE/n
    ad_seq = ad_seq[2:len(ad_seq) - 1]
    return ad_seq

# Creates a fasta file out of a adapters list which was extracted
# out of FastQC results by extract_adapters


def make_ad_fasta(adapters_list, sample_name, no_adapters=80):
    import os

    # Storing the adapters in the folder adapters
    if not is_dir('adapters'):
        os.system('mkdir adapters')
    # Generating the fasta list
    i = 1
    fasta = []
    for seq in adapters_list:
        # Creating only as much adapters in the fasta file
        # as are specified in no_adapters
        if i > no_adapters:
            break
        fasta.append('>Adapter ' + str(i))
        fasta.append(seq)
        i += 1

    # Saving the fasta file in the folder adapters
    # with the name extension _adapters.fasta
    fasta_file = './adapters/' + sample_name + '_adapters.fasta'
    with open(fasta_file, 'w') as ff:
        for item in fasta:
            ff.write(item + '\n')


# Cutadapt is run with files specified by
# filename (w/o extension), the extension
# the site used by the flag (-g/-a/-b) and the minimal length of the sequence
# which should be kept
def cutadapt(filenames, ext, site, seq_min_len):
    import os
    command = []
    summary = []
    for fname in filenames:
        # Creating the folder rm_adapt, where all results will be saved
        if not is_dir('rm_adapt'):
            os.system('mkdir rm_adapt')
        # Creating the corresponding folder for result storage
        os.system('mkdir ./rm_adapt/' + fname)
        # specifying the name of the trimmed reads
        trim_name = './rm_adapt/' + fname + '/' + fname + '_trimmed.fastq'
        # specifying the name of untrimmed reads
        untr_name = './rm_adapt/' + fname + '/' + fname + '_untrimmed.fastq'

        # Trimming the data
        ##print('\n' + fname + ' processing.')
        command.append('cutadapt -' + site + ' file:./adapters/' + fname + '_adapters.fasta' + ' -m ' +
                  seq_min_len + ' --untrimmed-output ' + untr_name +
                  ' -o ' + trim_name + ' ./' + fname + '.' + ext)
        ##print(fname + ' finished')

        ##print('Packing the trimmed and untrimmed in a summary file.')
        summary.append('cat ./rm_adapt/' + fname + '/*.fastq >./rm_adapt/' +
                  fname + '/' + fname + '_processed.fastq')
    return(command, summary)

# Running with the data, specified by filename and filepath, in bowtie2
# The genome index for bowtie is stored unter bow_index
# bow_index consists of the absolute path and the prefix of the indices
# eg. Tbgenome
def bowtie(filename, filepath, bow_index, no_threads = '2'):
    import os
    if not is_dir('bowalign'):
        os.system('mkdir bowalign')

    # aligning the reads to the genome using bowtie
    # 4 threads (-p 4) are assigned to speed up alignment
    # the maximum threads need to be below the CPU count of your computer.
    # If your computer runs too slow, decrease the integer after -p.
    # Besides it saves the statistics of each alignment to a file trailed by
    # _log.txt
    os.system('bowtie2 -k 20 -t -p ' + no_threads + ' -x ' + bow_index + ' ' + filepath +
              ' -S ./bowalign/' + filename +
              '_bow.sam 2> ./bowalign/' + filename + '_log.txt')


def sam_process(filename, filepath, no_threads):
    import os
    if not is_dir('bam_files'):
        os.system('mkdir bam_files')
    os.system('samtools view -u -S ' + filepath +
              ' | samtools sort -m 2G -@ '+ no_threads +' - -o ./bam_files/' +
              filename + '_sorted.bam')


def sam_index(filepath):
    import os

    os.system('samtools index ' + filepath)


def check_dir():
    import os

    user_dir = raw_input('Please specify the location of the raw-files: ')

    while not os.path.isdir(user_dir):
        print('This directory does not exist, or the path points to a file!')
        user_dir = raw_input('Please specify the correct path: ')

    return user_dir


def cufflinks(filepath, genome, fname):
    import os

    os.system('mkdir cufflinks')
    os.system('mkdir ./cufflinks/' + fname)
    os.system('cufflinks -p 4 -o ./cufflinks/' + fname + '/ -G ' + genome + ' ' + filepath)


def batch_cufflinks(ext, genome):
    import glob
    import Rseq

    files = glob.glob('./*.' + ext)

    for f in files:
        fname = f.split('.')[1]
        fname = fname[1:]
        fpath = './bam_files/' + fname + '_sorted.bam'

        print('Using cufflinks for read counting: \n')
        Rseq.cufflinks(fpath, genome, fname)


def cds_only_counts(genome, SORTED_BAM, fname):
    import os
    # import sys

    if not is_dir('reads'):
        os.system('mkdir reads')
    fout = './reads/'+fname + '_gene_read.txt'

    output_file = open(fout, 'a')
    gene_file = open(genome, "rU")
    #bam_file = open(SORTED_BAM, "rU")
    output_file.write("geneID\tGene_size\treads_count\n")
    while 1:
        line = gene_file.readline()
        if not line:
            break

        gene = line.split('\t')[0]
        chr = line.split('\t')[1]
        start = line.split('\t')[3]
        end = line.split('\t')[4]
        length = float(line.split('\t')[5][:-1])

        reads_count = int(os.popen(" samtools view -c "+ SORTED_BAM +" "+ chr+":"+start+"-"+end).read())
        output_file.write(gene+"\t"+str(length)+"\t"+str(reads_count)+'\n')


def identify_classes(fname, gene_read, gene_classes):
    file_input = gene_read

    hits = open(file_input, 'r')
    ref = open(gene_classes, 'r')
    hit_output = open('./GeneID_reads/' + fname + '_classes.txt', 'a')

    hit_output.write('GeneID\tGene_size\treads_count\tClass\n')

    classes = {}
    while 1:
        line = ref.readline()
        if not line:
            break
        key = line.split('\t')[0]
        classinfo = line.split('\t')[1]
        classes[key] = classinfo

    skip_first = hits.readline()
    while 1:
        line = hits.readline()
        if not line:
            break
        key = line.split('\t')[0]
        g_size = line.split('\t')[1]
        g_count = line.split('\t')[2].rstrip()
        if key in classes:
            hit_class = classes[key]
        else:
            hit_class = 'NotDefined\n'
        hit_output.write(key + '\t' + g_size + '\t' + g_count + '\t' + hit_class + '\n')


# Information about the terminal size
def terminal_size():
    import fcntl, termios, struct
    h, w, hp, wp = struct.unpack('HHHH',
        fcntl.ioctl(0, termios.TIOCGWINSZ,
        struct.pack('HHHH', 0, 0, 0, 0)))
    return w, h

def print_line():
    tw, th = terminal_size()
    print(tw * '-')


def gz_process(gz_file, ext):
    import os
    fname = gz_file.split('.')[1]
    fname = fname[1:]
    second_ext = gz_file.split('.')[-2]
    os.system('cp ' + gz_file + ' gzipped_reads\\')
    os.system('gzip -d ' + gz_file)
    os.system('mv ' + fname + '.' + second_ext + ' ' + fname + '.' + ext)

def is_dir(dir_path):
    import os

    if os.path.isdir(dir_path):
        present = True
    else:
        present = False

    return(present)

def read_reads(fpath):
    reads_file = {}
    with open(fpath, 'r') as filehandle:
        skip_first = filehandle.readline()
        for line in filehandle:
            line = line.rstrip()
            geneID, gene_size, gene_count = line.split('\t')

            if geneID in reads_file.keys():
                g_count = reads_file[geneID]
                g_count = str( int(g_count) + int(gene_count))
                reads_file[geneID] = g_count
            else:
                reads_file[geneID] = gene_count
    return(reads_file)


def create_reads_table(reads_dicts, folder):
    with open('./' + folder + '/reads_matrix.txt', 'w') as fout:
        first_sample = list(reads_dicts.keys())[1]
        geneIDs = list(reads_dicts[first_sample].keys()) # fixes order of IDs
        samples = list(reads_dicts.keys()) # fixes order of samples
        fout.write('GeneID' + '\t' + '\t'.join(samples) + '\n')
        for ID in geneIDs:
            fout.write(ID + '\t')
            for sample in samples:
                fout.write(reads_dicts[sample][ID])
                if sample == samples[-1]:
                    fout.write('\n')
                else:
                    fout.write('\t')

# Read in commandline options and return the object to main
def terminal_options(script_path):
    from optparse import OptionParser
    
    parser = OptionParser()
    parser.add_option('-i', '--extension',
        help = 'defines read files extension without \'.\' [fastq]')

    parser.add_option('-u', '--ext-unzip',
        help = 'file-extension after unzipping. Only required, if -ext = gz [fastq]',
        default = 'fastq')

    parser.add_option('-x', '--bow-index',
        help = 'bowtie2 index path with prefix (eg. \'bowtieindex/TbGenome\')',
        default = script_path + '/bowtieindex/TbGenome')

    parser.add_option('-g', '--gtf',
        help = 'gtf file path for read count',
        default = script_path + '/Tb_cds.gtf')

    parser.add_option('-a', '--remove-adapters',
        help = 'should identified adapters be removed? [y/n]',
        dest = 'remove_adapters',
        default = 'y')

    parser.add_option('-q', '--fastqc',
        help = 'analyse raw files with FastQC [y/n]',
        dest = 'fastqc',
        default = 'y')

    parser.add_option('-s', '--adapter-site',
        default = 'b',
        help = 'defines the site where adapters are expected (3(a), 5(g) or both possible(b))')

    parser.add_option('-l', '--min-length',
        default = '30',
        help = 'minimal read length, being kept after adapter removal')

    parser.add_option('--max-adapters',
        default = 'all',
        help = 'number of adapters which should be removed')

    parser.add_option('-t', '--threads',
        default = '4',
        help = 'number of threads')

    (options, args) = parser.parse_args()
    return(options)
