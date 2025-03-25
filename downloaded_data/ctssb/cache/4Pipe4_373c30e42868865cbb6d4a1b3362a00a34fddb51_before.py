#!/usr/bin/python3
# Copyright 2011-2013 Francisco Pina Martins <f.pinamartins@gmail.com>
# This file is part of 4Pipe4.
# 4Pipe4 is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# 4Pipe4 is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with 4Pipe4.  If not, see <http://www.gnu.org/licenses/>.

from math import ceil

def ListParser(infile_name,minqual,mincov):
    """Discards every line in the TCS file with a coverage below mincov and a qual
    below minqual"""
    TCS = open(infile_name,'r')
    if TCS.readline().startswith("#TCS") == False:
        quit("Invalid input file. Use a TCS file as input.")
    else:
        for i in range(3): TCS.readline() #Skip header
        
    passed = []
    for lines in TCS:
        line = lines.split('|')
        tcov = int(line[2][:5])
        covs = line[2][5:].strip().split()
        covs = sorted(list(map(int, covs)))
        if tcov <= mincov: #Discard positions with less than mincov
            pass
        elif int(lines.split()[12]) >= tcov/2: #Discard positions with many gaps
            pass 
        elif covs[-2] <= (ceil(tcov*0.2)): #Discard insufficient second variant
            pass
        else:
            quals = line[3].replace('--','0')
            quallist = quals.strip().split()
            quallist = sorted(list(map(int, quallist)))
            if quallist[-2] >= minqual: #Filter by quality
                passed.append(lines)

    TCS.close()
    return passed

def ListWriter(infile_name,passed):
    """Write the selected list into a file."""
    outfile = open((infile_name[0:-4] + '.short.tcs'),'w')
    outfile.write("#TCS V1.0\n")
    outfile.write("#\n")
    outfile.write("# contig name\t\t\tpadPos\tupadPos| B  Q |\ttcov covA covC covG covT cov* | qA qC qG qT q* |  S |\tTags\n")
    outfile.write("#\n")
    for lines in passed:
        outfile.write(lines)
    outfile.close()

def RunModule(infile_name,minqual,mincov):
    """Run the module."""
    ShortList = ListParser(infile_name,minqual,mincov)
    ListWriter(infile_name,ShortList)

#RunModule("/home/francisco/Programming/454/Scripts/ORF/test.tcs", 70, 15)