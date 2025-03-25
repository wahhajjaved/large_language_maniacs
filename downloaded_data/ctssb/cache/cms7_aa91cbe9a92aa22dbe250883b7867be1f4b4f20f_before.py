from pathlib2 import PurePosixPath
import logging

from jinja2 import Environment, ChoiceLoader, FileSystemLoader, ModuleLoader, StrictUndefined

from .error import CMS7Error

logger = logging.getLogger(__name__)

class Generator:
    def __init__(self, config):
        self.config = config
        self.pages = {}

        loaders = [FileSystemLoader(str(self.config.theme))]
        if self.config.compiled_theme is not None:
            loaders.append(ModuleLoader(str(self.config.compiled_theme)))
        self.env = Environment(autoescape=True,
                               loader=ChoiceLoader(loaders),
                               undefined=StrictUndefined,
                               extensions=['jinja2.ext.with_'])

    def add_render(self, link, target, generator):
        self.pages[str(link)] = (target, generator)

    def build_url(self, location, name):
        location = location.parent
        suffix = None
        try:
            target = self.pages[str(name)][0]
            logger.debug('look up for %s: rendered output: %s', name, target)
            suffix = '.html'
        except KeyError:
            for r in self.config.resources:
                t = r.lookup_target(str(name))
                if t is not None:
                    target = t
                    logger.debug('look up for %s: resources: %s', name, target)
                    break
            else:
                logger.warning('look up for %s: nothing found!', name)
                return None
        n = 0
        for a, b in zip(location.parts, target.parts):
            if a != b:
                break
            n += 1
        newpath = ('..',) * (len(location.parts) - n) + target.parts[n:]
        p = PurePosixPath(*newpath)
        if suffix is not None:
            p = p.with_suffix(suffix)
        if p.name == 'index.html':
            return p.parent / '.'
        if p.suffix == '.html' and self.config.htmlless:
            p = p.with_suffix('')
        return p

    def open_target(self, path):
        p = self.config.output / path
        p.parent.mkdir(parents=True, exist_ok=True)
        return p.open('w')

    def run(self):
        for link, v in sorted(self.pages.items(), key=lambda x: str(x[0])):
            target, generator = v
            tf = target.with_suffix('.html')
            logger.info('Rendering %s -> %s', link, tf)
            try:
                data = generator(GeneratorState(self, target))
            except CMS7Error as e:
                logger.error('fatal error while rendering %r', link)
                logger.error(e.message)
            except Exception as e:
                raise CMS7Error('{} while rendering {!r}'.format(type(e).__name__, link)) from e
            with self.open_target(target.with_suffix('.html')) as f:
                f.write(data)


class GeneratorState:
    def __init__(self, gen, targetpath):
        self.gen = gen
        self.targetpath = targetpath

    def url_for(self, name):
        return self.gen.build_url(self.targetpath, name) or \
                self.env.undefined('url_for({!r})'.format(str(name)))

    def get_module(self, name):
        return self.gen.config.module_id[name].get_api(self)

    def render_template(self, template, **kw):
        template = self.gen.env.get_template(template)
        return template.render(config=self.gen.config,
                               url_for=self.url_for,
                               get_module=self.get_module,
                               **kw)
