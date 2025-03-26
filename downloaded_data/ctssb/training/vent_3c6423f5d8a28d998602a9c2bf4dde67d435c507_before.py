import os

from vent.api.plugins import Plugin
from vent.api.templates import Template

def test_add():
    """ Test the add function """
    instance = Plugin(base_dir=os.getcwd()+'/', meta_dir=os.getcwd()+'/.vent')
    status = instance.add('https://github.com/cyberreboot/vent', build=False)
    assert status[0] == True
    status = instance.add('https://github.com/cyberreboot/vent.git', build=True)
    assert status[0] == True
    bad_instance = Plugin()
    status = bad_instance.add('https://github.com/cyberreboot/vent', build=False)
    assert status[0] == False
    instance = Plugin(base_dir=os.getcwd()+'/', meta_dir=os.getcwd()+'/.vent')
    status = instance.add('https://github.com/cyberreboot/vent', build=False, user='foo', pw='bar')
    assert status[0] == True
    instance = Plugin(base_dir=os.getcwd()+'/', meta_dir=os.getcwd()+'/.vent')
    status = instance.add('https://github.com/cyberreboot/vent', build=False, overrides=[('.', 'HEAD')])
    assert status[0] == True
    instance = Plugin(base_dir=os.getcwd()+'/', meta_dir=os.getcwd()+'/.vent')
    status = instance.add('https://github.com/cyberreboot/vent', build=False, tools=[('vent/', 'HEAD')], overrides=[('vent', 'HEAD')])
    assert status[0] == True

def test_get_tool_matches():
    """ Test the get_tool_matches function """
    instance = Plugin(base_dir=os.getcwd()+'/', meta_dir=os.getcwd()+'/.vent')
    instance.tools = []
    matches = instance.get_tool_matches()
    assert matches == []

def test_add_image():
    """ Test the add_image function """
    Plugin.add_image('foo')

def test_builder():
    """ Test the builder function """
    instance = Plugin(base_dir=os.getcwd()+'/', meta_dir=os.getcwd()+'/.vent')
    template = Template(instance.manifest)
    template = instance.builder(template, os.getcwd()+'/plugins/cyberreboot/vent', 'image_name', 'section')
    template = instance.builder(template, 'bad_path', 'image_name', 'section', build=True, branch='master', version='HEAD')

def test_build_tools():
    """ Test the _build_tools function """
    instance = Plugin(base_dir=os.getcwd()+'/', meta_dir=os.getcwd()+'/.vent')
    status = instance._build_tools(256)
    assert status[0] == False

def test_tools():
    """ Test the tools function """
    instance = Plugin(base_dir=os.getcwd()+'/', meta_dir=os.getcwd()+'/.vent')
    tools = instance.tools()

def test_remove():
    """ Test the remove function """
    instance = Plugin(base_dir=os.getcwd()+'/', meta_dir=os.getcwd()+'/.vent')
    status = instance.remove()
    assert status[0] == True

def test_versions():
    """ Test the versions function """
    instance = Plugin(base_dir=os.getcwd()+'/', meta_dir=os.getcwd()+'/.vent')
    status = instance.add('https://github.com/cyberreboot/vent', build=False, branch='experimental')
    assert status[0] == True
    versions = instance.versions('elasticsearch', branch='experimental')
    assert versions == [('cyberreboot:vent:/vent/core/elasticsearch:experimental:HEAD', ['HEAD'])]

def test_current_version():
    """ Test the current_version function """
    instance = Plugin(base_dir=os.getcwd()+'/', meta_dir=os.getcwd()+'/.vent')
    versions = instance.current_version('elasticsearch', branch='experimental')
    assert versions == [('cyberreboot:vent:/vent/core/elasticsearch:experimental:HEAD', 'HEAD')]

def test_state():
    """ Test the state function """
    instance = Plugin(base_dir=os.getcwd()+'/', meta_dir=os.getcwd()+'/.vent')
    states = instance.state('elasticsearch', branch='experimental')
    assert states == [('cyberreboot:vent:/vent/core/elasticsearch:experimental:HEAD', 'enabled')]

def test_enable():
    """ Test the enable function """
    instance = Plugin(base_dir=os.getcwd()+'/', meta_dir=os.getcwd()+'/.vent')
    status = instance.enable('elasticsearch', branch='experimental')
    assert status[0] == True

def test_disable():
    """ Test the disable function """
    instance = Plugin(base_dir=os.getcwd()+'/', meta_dir=os.getcwd()+'/.vent')
    status = instance.disable('elasticsearch', branch='experimental')
    assert status[0] == True
