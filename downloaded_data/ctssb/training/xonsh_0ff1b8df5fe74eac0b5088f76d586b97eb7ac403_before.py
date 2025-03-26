#!/usr/bin/env python
# coding=utf-8
"""The xonsh installer."""
from __future__ import print_function, unicode_literals
import os
import sys
try:
    from setuptools import setup
    from setuptools.command.sdist import sdist
    from setuptools.command.install import install
    HAVE_SETUPTOOLS = True
except ImportError:
    from distutils.core import setup
    from distutils.command.sdist import sdist as sdist
    from distutils.command.install import install as install
    HAVE_SETUPTOOLS = False

VERSION = '0.1.2'

TABLES = ['xonsh/lexer_table.py', 'xonsh/parser_table.py']

def clean_tables():
    for f in TABLES:
        if os.path.isfile(f):
            os.remove(f)
            print('Remove ' + f)

def build_tables():
    print('Building lexer and parser tables.')
    sys.path.insert(0, os.path.dirname(__file__))
    from xonsh.parser import Parser
    Parser(lexer_table='lexer_table', yacc_table='parser_table',
           outputdir='xonsh')
    sys.path.pop(0)

class xinstall(install):
    def run(self):
        clean_tables()
        build_tables()
        install.run(self)

class xsdist(sdist):
    def make_release_tree(self, basedir, files):
        clean_tables()
        build_tables()
        sdist.make_release_tree(self, basedir, files)

def main():
    if sys.version_info[0] < 3:
        sys.exit('xonsh currently requires Python 3.4+')
    print(logo)
    with open('README.rst', 'r') as f:
        readme = f.read()
    skw = dict(
        name='xonsh',
        description='an exotic, usable shell',
        long_description=readme,
        license='BSD',
        version=VERSION,
        author='Anthony Scopatz',
        maintainer='Anthony Scopatz',
        author_email='scopatz@gmail.com',
        url='https://github.com/scopatz/xonsh',
        platforms='Cross Platform',
        classifiers = ['Programming Language :: Python :: 3'],
        packages=['xonsh'],
        scripts=['scripts/xonsh'],
        cmdclass={'install': xinstall, 'sdist': xsdist},
        )
    if HAVE_SETUPTOOLS:
        skw['setup_requires'] = ['ply']
        skw['install_requires'] = ['ply']
    setup(**skw)

logo = """
                           ╓██▄                                              
                          ╙██▀██╕                                            
                         ▐██4Φ█▀█▌                                           
                       ²██▄███▀██^██                                         
                     -███╩▀ " ╒▄█████▀█                                      
                      ║██▀▀W╤▄▀ ▐║█╘ ╝█                                      
                 ▄m▀%Φ▀▀  ╝*"    ,α█████▓▄,▄▀Γ"▀╕                            
                 "▀██¼"     ▄═╦█╟║█▀ ╓ `^`   ,▄ ╢╕                           
                  ,▀╫M█▐j╓╟▀ ╔▓▄█▀  '║ ╔    ╣║▌  ▀▄                          
               ▄m▀▀███╬█╝▀  █▀^      "ÜM  j▐╟╫╨▒   ╙▀≡═╤═m▀╗                 
               █æsæ╓  ╕, ,▄Ä   ▐'╕H   LU  ║║╠╫Å^2=⌐         █                
            ▄æ%Å███╠█ª╙▄█▀      $1╙       ║║╟╫╩*T▄           ▌               
           ╙╗%▄,╦██▌█▌█╢M         ╕      M║║║║█═⌐ⁿ"^         ╫               
             ╙╣▀████@█░█    ▌╕╕   `      ▌║▐▐║█D═≈⌐¬ⁿ      s ║⌐              
               ╙╬███▓║█`     ▌╚     ╕   ╕▌║▐▐╣▌⌐*▒▒Dù`       ▐▌              
                ╙╬██╨U█      ╟      $ ▌ ▌▌▐▐▐M█▄═≤⌐%       ╓⌐ ▌              
                 ║║█▄▌║             ╟ ▌ ▌M▐▐▐M█▀▒▒▒22,       ▐▌              
                  ███╙^▌            ║ ▌ ⌐M▐▐▐M█≤⌐⌐¬──        ▐M              
                  ║██ ▌╙   ╓       H║ ▌╒ M║▐▐M█"^^^^^"ⁿ      ║               
                   ██╕╙@▓   ╕      ▌║ H'  ║▐▐▐█══=.,,,       █               
                   ╙█▓╔╚╚█     ╠   ▌└╒ ▌▐ ╚║║║▀****ⁿ -      ╓▌               
                    ╙█▌¼V╚▌   ▌  ╕ ▌ ║╒ ║ ▌▒╠█▀≤≤≤≤≤⌐       █                
                     ╙█▌╔█╚▌     ┘ M ▌║ ╫ UUM██J^^"        ▐▌                
                      ╙██╙█╙▌  ╕$j  ▐⌐▌ ▌║╝╟█Å%%%≈═        █                 
                       ╙╣█╣█^▌ ╠║▐  ║ ▌▐.DU██^[""ⁿ       -╒▌                 
                         ▀█▄█`▌ ░M▀ ▌▐ Å£╝╝█╜%≈═╓""w   ⁿ⌐ █                  
                          `▀▄▀`▌ ▌█▐⌐║▐UW╖██%≤═░*─    =z ▄Γ                  
                            ╙██╙▄▌█  ▌Å╛╣██╨%╤ƒⁿ=    -` ▄┘                   
                              █▌╢▓▌▌ W £6█╤,"ⁿ `   ▄≡▀▀▀                     
                               █"█▌▌╟Å╓█╓█▀%`    ▄▀                          
                               ╙▌██`▒U▓U█%╗*     █                           
                                ▌╫║ ▌ÅÅ║▀╛¬`      `"█                        
                                ▌╫  ╫╟ █▄     ~╦%▒╥4^                        
                                ▌▌  "M█ `▀╕ X╕"╗▄▀^                          
                                █▌   ╓M   ╙▀e▀▀^                             
                                ╙██▄▄▀                                       
                                  ^^                                         
"""

if __name__ == '__main__':
    main()

