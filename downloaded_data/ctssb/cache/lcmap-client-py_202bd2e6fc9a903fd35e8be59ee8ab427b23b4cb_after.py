import logging
import subprocess
import sys

import click

from lcmap.client.scripts.cl_tool import query
from lcmap.client.scripts.cl_tool.command import lcmap


log = logging.getLogger(__name__)


@lcmap.group()
@click.pass_obj
def model(config):
    "Execute science models in the LCMAP Science Execution Environment."


@model.command()
@click.pass_obj
# Rod query options:
@click.option('--spectra', '-s', multiple=True, type=query.spectra_choices)
@click.option('--x', '-x', type=int)
@click.option('--y', '-y', type=int)
@click.option('--t1')
@click.option('--t2')
@click.option('--mask/--no-mask', is_flag=True, default=True)
@click.option('--shape/--no-shape', is_flag=True, default=True)
@click.option('--unscale/--scale', is_flag=True, default=True)
@click.option('--format', default="plain-text", type=query.format_choices)
# CCDC options:
@click.option('--row', type=int)
@click.option('--col', type=int)
@click.option('--out-dir', default="stdout")
@click.option('--scene-list', default="stdin")
@click.option('--verbose', is_flag=True, default=False)
# Model cli options
@click.option('--local', is_flag=True, default=False)
@click.option('--stdout', is_flag=True, default=True)
def ccdc(config, spectra, x, y, t1, t2, mask, shape, unscale, format,
    row, col, out_dir, scene_list, verbose, local, stdout):
    if local == False:
        print("Renmote execution of models not yet supported.")
        sys,exit(1)
    if verbose:
        verbose = "--verbose"
    query_results = query.rod_query(
        spectra, x, y, t1, t2, mask, shape, unscale, format)
    stdin = io.StringIO()
    stdin.write(query_results)

    p = subprocess.Popen(
        ["ccdc",
         "--row=" + row
         "--col=" + col
         "--outDir" + out_dir
         "--sceneList" + scene_list
         verbose],
        stdin=stdin,
        stdout=subprocess.PIPE)
    ccdc_results = p.communicate()[0]
    if stdout:
        print(ccdc_results)
    else:
        return ccdc_results
