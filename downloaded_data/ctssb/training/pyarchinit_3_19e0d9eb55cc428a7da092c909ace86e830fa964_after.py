#! /usr/bin/env python
# -*- coding: utf-8 -*-
"""
/***************************************************************************
        pyArchInit Plugin  - A QGIS plugin to manage archaeological dataset
        					 stored in Postgres
                             -------------------
    begin                : 2007-12-01
    copyright            : (C) 2008 by Luca Mandolesi
    email                : mandoluca at gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
import os
try:
    import pygraphviz as p
except:
    pass


class HARRIS_MATRIX_EXP:
    HOME = os.environ['PYARCHINIT_HOME']

    def __init__(self, sequence, periodi):
        self.sequence = sequence
        self.periodi = periodi

    def export_matrix(self):
        G = p.AGraph(directed=True)
        G.graph_attr['dpi'] = 300
        G.graph_attr['splines'] = 'ortho'
        G.graph_attr['label'] = 'pyArchInit - Harris Matrix Exportation System'

        elist = []

        for i in self.sequence:
            a = (i[0], i[1])
            elist.append(a)

        G.add_edges_from(elist)

        G.node_attr['shape'] = 'box'
        G.node_attr['style'] = 'strocked'
        G.node_attr['color'] = 'red'

        for i in self.periodi:
            G.subgraph(nbunch=i[0],
                       name=i[1],
                       style='strocked',
                       shape='square',
                       color='blue',
                       label=i[2],
                       font_color='Blue')

        try:
            data_to_plot = G.tred()
        except:
            data_to_plot = G

        Matrix_path = '{}{}{}'.format(self.HOME, os.sep, "pyarchinit_Matrix_folder")

        filename_svg = '{}{}{}'.format(Matrix_path, os.sep, 'Harris_matrix.svg')
        filename_png = '{}{}{}'.format(Matrix_path, os.sep, 'Harris_matrix.png')
        filename_dot = '{}{}{}'.format(Matrix_path, os.sep, 'Harris_matrix_win.dot')

        G.draw(filename_svg, prog='dot')
        G.draw(filename_png, prog='dot')
        G.write(filename_dot)

        return data_to_plot


if __name__ == "__main__":
    data = [(1, 2), (2, 4), ]
    Harris_matrix_exp = HARRIS_MATRIX_EXP(data)
    Harris_matrix_exp.export_matrix()