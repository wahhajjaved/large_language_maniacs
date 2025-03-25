#!/usr/bin/env python
import os
import re
import tempfile
from zlib import adler32
import logging

import markdown
from markdown.util import etree
import plantuml

logger = logging.getLogger('MARKDOWN')


# For details see https://pythonhosted.org/Markdown/extensions/api.html#blockparser
class PlantUMLBlockProcessor(markdown.blockprocessors.BlockProcessor):
    # Regular expression inspired by the codehilite Markdown plugin
    RE = re.compile(r'::plantuml::', re.VERBOSE)
    # Regular expression for identify end of UML script
    RE_END = re.compile(r'::endplantuml::\s*$')
    IMAGES_DIR = 'images/'

    def test(self, parent, block):
        return self.RE.search(block)

    def run(self, parent, blocks):
        block = blocks.pop(0)
        text = block

        # Parse configuration params
        m = self.RE.search(block)

        # Read blocks until end marker found
        while blocks and not self.RE_END.search(block):
            block = blocks.pop(0)
            text += '\n' + block
        else:
            if not blocks:
                raise RuntimeError("UML block not closed")

        # Remove block header and footer
        text = re.sub(self.RE, "", re.sub(self.RE_END, "", text))

        abs_target_dir = os.path.abspath(os.path.join(self.config['target'], self.config['image_folder']))
        #print "abs_target_dir " + abs_target_dir
        if not os.path.exists(abs_target_dir):
            os.makedirs(abs_target_dir)

        # Generate image from PlantUML script
        imageurl = self.config['siteurl'] + os.path.join(self.config['image_folder'], self.generate_uml_image(abs_target_dir, text))
        # Create image tag and append to the document
        etree.SubElement(parent, "img", src=imageurl)

    def generate_uml_image(self, abs_target_dir, plantuml_code):
        plantuml_code = plantuml_code.encode('utf8')
        tf = tempfile.NamedTemporaryFile(delete=False)
        tf.write('@startuml\n'.encode('utf8'))
        tf.write(plantuml_code)
        tf.write('\n@enduml'.encode('utf8'))
        tf.flush()
        print "uml_code" + plantuml_code
        #print "tfname " + tf.name

        imgext = '.png'

        pl = puml.PlantUML()

        newname = os.path.join(abs_target_dir, "%08x" % (adler32(plantuml_code) & 0xffffffff))+imgext

        if os.path.exists(newname):
            os.remove(newname)

        if pl.processes_file(tf.name, newname):
            os.remove(tf.name)
            return os.path.basename(newname)
        else:
            # the temporary file is still available as aid understanding errors
            raise RuntimeError('Error in "uml" directive')


# For details see https://pythonhosted.org/Markdown/extensions/api.html#extendmarkdown
class PlantUMLMarkdownExtension(markdown.Extension):
    # For details see https://pythonhosted.org/Markdown/extensions/api.html#configsettings
    def __init__(self, *args, **kwargs):
        self.config = {
            'image_folder': ["images", "Directory where to put generated images. Defaults to 'images'."],
            'target': ["", "Directory where to put the image_folder. Defaults to empty string."],
            'siteurl': ["", "URL of document, used as a prefix for the image diagram. Defaults to empty string."]
        }

        super(PlantUMLMarkdownExtension, self).__init__(*args, **kwargs)

    def extendMarkdown(self, md, md_globals):
        blockprocessor = PlantUMLBlockProcessor(md.parser)
        blockprocessor.config = self.getConfigs()
        md.parser.blockprocessors.add('plantuml', blockprocessor, '>code')


def makeExtension(*args, **kwargs):
    return PlantUMLMarkdownExtension(*args, **kwargs)
