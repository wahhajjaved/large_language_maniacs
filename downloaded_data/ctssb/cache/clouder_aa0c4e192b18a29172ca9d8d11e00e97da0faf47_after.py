# -*- coding: utf-8 -*-
##############################################################################
#
#    Author: Yannick Buron
#    Copyright 2013 Yannick Buron
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from openerp import models, fields, api, _
from openerp.exceptions import except_orm
from openerp import modules
import re

import time
from datetime import datetime, timedelta

import logging
_logger = logging.getLogger(__name__)


class ClouderServer(models.Model):
    _name = 'clouder.server'
    _inherit = ['clouder.model']

    @api.multi
    def _create_key(self):

        if not self.env.ref('clouder.clouder_settings').email_sysadmin:
            raise except_orm(_('Data error!'),
                _("You need to specify the sysadmin email in configuration"))

        self.execute_local(['mkdir', '/tmp/key_' + self.env.uid])
        self.execute_local(['ssh-keygen', '-t', 'rsa', '-C',
                            self.email_sysadmin, '-f',
                            '/tmp/key_' + self.env.uid + '/key', '-N', ''])
        return True

    @api.multi
    def _destroy_key(self):
        self.execute_local(['rm', '-rf', '/tmp/key_' + self.env.uid])
        return True

    @api.multi
    def _default_private_key(self):
        self = self.env['clouder.server']
        self.env.uid = str(self.env.uid)

        destroy = True
        if not self.local_dir_exist('/tmp/key_' + self.env.uid):
            self._create_key()
            destroy = False

        key = self.execute_local(['cat', '/tmp/key_' + self.env.uid + '/key'])

        if destroy:
            self._destroy_key()
        return key

    @api.multi
    def _default_public_key(self):
        self = self.env['clouder.server']
        self.env.uid = str(self.env.uid)

        destroy = True
        if not self.local_dir_exist('/tmp/key_' + self.env.uid):
            self._create_key()
            destroy = False

        key = self.execute_local(['cat',
                                  '/tmp/key_' + self.env.uid + '/key.pub'])

        if destroy:
            self._destroy_key()
        return key

    name = fields.Char('Domain name', size=64, required=True)
    ip = fields.Char('IP', size=64, required=True)
    ssh_port = fields.Integer('SSH port', required=True)

    private_key = fields.Text(
        'SSH Private Key', required=True,
        default=_default_private_key)
    public_key = fields.Text(
        'SSH Public Key', required=True,
        default=_default_public_key)
    start_port = fields.Integer('Start Port', required=True)
    end_port = fields.Integer('End Port', required=True)
    public = fields.Boolean('Public?')
    partner_id = fields.Many2one(
        'res.partner', 'Manager',
        default=lambda self: self.user_partner)
    supervision_id = fields.Many2one('clouder.container', 'Supervision Server')

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'Name must be unique!'),
    ]

    @api.one
    @api.constrains('name', 'ip')
    def _validate_data(self) :
        if not re.match("^[\w\d.-]*$", self.name):
            raise except_orm(
                _('Data error!'),
                _("Name can only contains letters, digits, - and ."))
        if not re.match("^[\d:.]*$", self.ip):
            raise except_orm(
                _('Data error!'),
                _("Admin name can only contains digits, dots and :"))

    @api.multi
    def start_containers(self):
        containers = self.env['clouder.container'].search(
            [('server_id', '=', self.id)])
        for container in containers:
            container.start()

    @api.multi
    def stop_containers(self):
        containers = self.env['clouder.container'].search(
            [('server_id', '=', self.id)])
        for container in containers:
            container.stop()

    @api.multi
    def deploy(self):
        self.purge()
        key_file = self.home_directory + '/.ssh/keys/' + self.name
        self.execute_write_file(key_file, self.private_key)
        self.execute_local(['chmod', '700', key_file])
        self.execute_write_file(self.home_directory +
                                '/.ssh/config', 'Host ' + self.name)
        self.execute_write_file(self.home_directory +
                                '/.ssh/config', '\n  HostName ' + self.name)
        self.execute_write_file(self.home_directory +
                                '/.ssh/config', '\n  Port ' +
                                str(self.ssh_port))
        self.execute_write_file(self.home_directory +
                                '/.ssh/config', '\n  User root')
        self.execute_write_file(self.home_directory +
                                '/.ssh/config', '\n  IdentityFile ' +
                                self.home_directory + '/.ssh/keys/' +
                                self.name)
        self.execute_write_file(self.home_directory + '/.ssh/config',
                                '\n#END ' + self.name + '\n')

    @api.multi
    def purge(self):
        self.execute_local([modules.get_module_path('clouder') +
                            '/res/sed.sh', self.name,
                            self.home_directory + '/.ssh/config'])
        self.execute_local(['rm', '-rf', self.home_directory +
                            '/.ssh/keys/' + self.name])


class ClouderContainer(models.Model):
    _name = 'clouder.container'
    _inherit = ['clouder.model']

    @api.one
    def _get_ports(self):
        self.ports_string = ''
        first = True
        for port in self.port_ids:
            if not first:
                self.ports_string += ', '
            if port.hostport:
                self.ports_string += port.name + ' : ' + port.hostport
            first = False

    name = fields.Char('Name', size=64, required=True)
    application_id = fields.Many2one('clouder.application',
                                     'Application', required=True)
    image_id = fields.Many2one('clouder.image', 'Image', required=True)
    server_id = fields.Many2one('clouder.server', 'Server', required=True)
    image_version_id = fields.Many2one('clouder.image.version',
                                       'Image version', required=True)
    save_repository_id = fields.Many2one('clouder.save.repository',
                                         'Save repository')
    time_between_save = fields.Integer('Minutes between each save')
    saverepo_change = fields.Integer('Days before saverepo change')
    saverepo_expiration = fields.Integer('Days before saverepo expiration')
    save_expiration = fields.Integer('Days before save expiration')
    date_next_save = fields.Datetime('Next save planned')
    save_comment = fields.Text('Save Comment')
    nosave = fields.Boolean('No Save?')
    privileged = fields.Boolean('Privileged?')
    port_ids = fields.One2many('clouder.container.port',
                               'container_id', 'Ports')
    volume_ids = fields.One2many('clouder.container.volume',
                                 'container_id', 'Volumes')
    option_ids = fields.One2many('clouder.container.option',
                                 'container_id', 'Options')
    link_ids = fields.One2many('clouder.container.link',
                               'container_id', 'Links')
    service_ids = fields.One2many('clouder.service',
                                  'container_id', 'Services')
    ports_string = fields.Text('Ports', compute='_get_ports')
    backup_ids = fields.Many2many(
        'clouder.container', 'clouder_container_backup_rel',
        'container_id', 'backup_id', 'Backup containers')
    public = fields.Boolean('Public?')
    partner_id = fields.Many2one(
        'res.partner', 'Manager',
        default=lambda self: self.user_partner)
    partner_ids = fields.Many2many(
        'res.partner', 'clouder_container_partner_rel',
        'container_id', 'partner_id', 'Users')

    @property
    def fullname(self):
        return self.name + '_' + self.server_id.name

    @property
    def volumes_save(self):
        return ','.join([volume.name for volume in self.volume_ids
                         if not volume.nosave])

    @property
    def ssh_port(self):
        return self.ports['ssh']['hostport'] or 22

    @property
    def root_password(self):
        root_password = ''
        for option in self.option_ids:
            if option.name.name == 'root_password':
                root_password = option.value
        return root_password

    @property
    def ports(self):
        ports = {}
        for port in self.port_ids:
            ports[port.name] = {
                'id': port.id, 'name': port.name,
                'hostport': port.hostport, 'localport': port.localport}
        return ports

    @property
    def options(self):
        options = {}
        for option in self.application_id.type_id.option_ids:
            if option.type == 'container':
                options[option.name] = {'id': option.id, 'name': option.id, 'value': option.default}
        for option in self.option_ids:
            options[option.name.name] = {'id': option.id, 'name': option.name.id, 'value': option.value}
        return options

    _sql_constraints = [
        ('name_uniq', 'unique(server_id,name)',
         'Name must be unique per server!'),
    ]

    @api.one
    @api.constrains('name')
    def _validate_data(self):
        if not re.match("^[\w\d-]*$", self.name):
            raise except_orm(
                _('Data error!'),
                _("Name can only contains letters, digits and underscore"))

    @api.one
    @api.constrains('application_id')
    def _check_backup(self):
        if not self.backup_ids and self.application_id.type_id.name \
                not in ['backup','backup_upload','archive','registry']:
            raise except_orm(
                _('Data error!'),
                _("You need to specify at least one backup container."))

    @api.one
    @api.constrains('image_id','image_version_id')
    def _check_config(self):
        if self.image_id.id != self.image_version_id.image_id.id:
            raise except_orm(_('Data error!'),
                _("The image of image version must be "
                  "the same than the image of container."))

    @api.one
    @api.constrains('option_ids')
    def _check_option_ids(self):
        for type_option in self.application_id.type_id.option_ids:
            if type_option.type == 'container' and type_option.required:
                test = False
                for option in self.option_ids:
                    if option.name == type_option and option.value:
                        test = True
                if not test:
                    raise except_orm(_('Data error!'),
                        _("You need to specify a value for the option " +
                          type_option.name + " for the container " +
                          self.name + "."))

    @api.one
    @api.constrains('link_ids')
    def _check_link_ids(self):
        for app_link in self.application_id.link_ids:
            if app_link.container and app_link.required:
                test = False
                for link in self.link_ids:
                    if link.name == app_link and link.target:
                        test = True
                if not test:
                    raise except_orm(_('Data error!'),
                        _("You need to specify a link to " + app_link.name.name
                          + " for the container " + self.name))

    @api.multi
    @api.onchange('application_id')
    def onchange_application_id(self):
        if self.application_id:
            self.server_id = self.application_id.next_server_id
            self.image_id = self.application_id.default_image_id
            self.privileged = self.application_id.default_image_id.privileged
            self.image_version_id = \
                self.application_id.default_image_id.version_ids \
                and self.application_id.default_image_id.version_ids[0]

            options = []
            for type_option in self.application_id.type_id.option_ids:
                if type_option.type == 'container' and type_option.auto:
                    test = False
                    for option in self.option_ids:
                        if option.name == type_option:
                            test = True
                    if not test:
                        options.append((0, 0,
                                        {'name': type_option,
                                         'value': type_option.default}))
            self.option_ids = options

            links = []
            for app_link in self.application_id.link_ids:
                if app_link.container and app_link.auto or app_link.make_link:
                    test = False
                    for link in self.link_ids:
                        if link.name == app_link:
                            test = True
                    if not test:
                        links.append((0,0,{'name': app_link,
                                           'target': app_link.next}))
            self.link_ids = links


            self.backup_ids = [(6,0,[
                b.id for b in self.application_id.container_backup_ids])]

            self.time_between_save = \
                self.application_id.container_time_between_save
            self.saverepo_change = \
                self.application_id.container_saverepo_change
            self.saverepo_expiration = \
                self.application_id.container_saverepo_expiration
            self.save_expiration = \
                self.application_id.container_save_expiration

    @api.multi
    @api.onchange('image_id')
    def onchange_image_id(self):
        if self.image_id:
            ports = []
            for port in self.image_id.port_ids:
                if port.expose != 'none':
                    ports.append(((0,0,{
                        'name':port.name,'localport':port.localport,
                        'expose':port.expose,'udp':port.udp})))
            self.port_ids = ports

            volumes = []
            for volume in self.image_id.volume_ids:
                volumes.append(((0,0,{
                    'name':volume.name, 'hostpath':volume.hostpath,
                    'user':volume.user, 'readonly':volume.readonly,
                    'nosave':volume.nosave})))
            self.volume_ids = volumes

    @api.model
    def write(self, vals):
        version_obj = self.env['clouder.image.version']
        flag = False
        if 'image_version_id' in vals or 'port_ids' in vals \
                or 'volume_ids' in vals:
            flag = True
            self = self.with_context(self.create_log('upgrade version'))
            if 'image_version_id' in vals:
                new_version = version_obj.browse(vals['image_version_id'])
                self = self.with_context(
                    save_comment='Before upgrade from ' +
                                 self.image_version_id.name +
                                 ' to ' + new_version.name)
            else:
                self = self.with_context(
                    save_comment='Change on port or volumes')
        res = super(ClouderContainer, self).write(vals)
        if flag:
            self.reinstall()
            self.end_log()
        if 'nosave' in vals:
            self.deploy_links()
        return res

    @api.one
    def unlink(self):
        self.service_ids and self.service_ids.unlink()
        self = self.with_context(save_comment='Before unlink')
        self.save()
        return super(ClouderContainer, self).unlink()

    @api.multi
    def reinstall(self):
        if not 'save_comment' in self.env.context:
            self = self.with_context(save_comment='Before reinstall')
        self = self.with_context(forcesave=True)
        self.save()
        self = self.with_context(forcesave=False)
        self = self.with_context(nosave=True)
        super(ClouderContainer, self).reinstall()

    @api.multi
    def save(self):

        save = False
        now = datetime.now()
        repo_obj = self.env['clouder.save.repository']

        if not self.save_repository_id:
            repo_ids = repo_obj.search(
                [('container_name','=',self.name),
                 ('container_server','=',self.server_id.name)])
            if repo_ids:
                self.save_repository_id = repo_ids[0]

        if not self.save_repository_id \
                or datetime.strptime(self.save_repository_id.date_change,
                                     "%Y-%m-%d") < now or False:
            repo_vals ={
                'name': now.strftime("%Y-%m-%d") + '_' +
                        self.name + '_' + self.server_id.name,
                'type': 'container',
                'date_change': (now + timedelta(
                    days=self.saverepo_change
                         or self.application_id.container_saverepo_change
                )).strftime("%Y-%m-%d"),
                'date_expiration': (now + timedelta(
                    days=self.saverepo_expiration
                         or self.application_id.container_saverepo_expiration
                )).strftime("%Y-%m-%d"),
                'container_name': self.name,
                'container_server': self.server_id.name,
            }
            repo_id = repo_obj.create(repo_vals)
            self.save_repository_id = repo_id

        if 'nosave' in self.env.context \
                or (self.nosave and not 'forcesave' in self.env.context):
            self.log('This base container not be saved '
                     'or the backup isnt configured in conf, '
                     'skipping save container')
            return
        self = self.with_context(self.create_log('save'))

        for backup_server in self.backup_ids:
            save_vals = {
                'name': self.now_bup + '_' + self.fullname,
                'backup_id': backup_server.id,
                'repo_id': self.save_repository_id.id,
                'date_expiration': (now + timedelta(
                    days=self.save_expiration
                         or self.application_id.container_save_expiration
                )).strftime("%Y-%m-%d"),
                'comment': 'save_comment' in self.env.context
                           and self.env.context['save_comment']
                           or self.save_comment or 'Manual',
                'now_bup': self.now_bup,
                'container_id': self.id,
            }
            save = self.env['clouder.save.save'].create(save_vals)
        next = (datetime.now() + timedelta(
            minutes=self.time_between_save
                    or self.application_id.container_time_between_save
        )).strftime("%Y-%m-%d %H:%M:%S")
        self.write({'save_comment': False, 'date_next_save': next})
        self.end_log()
        return save

    @api.multi
    def deploy_post(self):
        return

    @api.multi
    def deploy(self):

        self.purge()

        ssh = self.connect(self.server_id.name)

        cmd = ['sudo','docker', 'run', '-d']
        nextport = self.server_id.start_port
        for port in self.port_ids:
            if not port.hostport:
                while not port.hostport \
                        and nextport != self.server_id.end_port:
                    ports = self.env['clouder.container.port'].search(
                        [('hostport','=',nextport),
                         ('container_id.server_id','=',self.server_id.id)])
                    if not ports and not self.execute(ssh, [
                        'netstat', '-an', '|', 'grep', str(nextport)]):
                        port.hostport = nextport
                    nextport += 1
            udp = ''
            if port.udp:
                udp = '/udp'
            cmd.extend(['-p', str(port.hostport) + ':' + port.localport + udp])
        for volume in self.volume_ids:
            if volume.hostpath:
                arg = volume.hostpath + ':' + volume.name
                if volume.readonly:
                    arg += ':ro'
                cmd.extend(['-v', arg])
        for link in self.link_ids:
            if link.name.make_link and link.target.server_id == self.server_id:
                cmd.extend(['--link', link.target.name +
                            ':' + link.name.name.code])
        if self.privileged:
            cmd.extend(['--privileged'])
        cmd.extend(['-v', '/opt/keys/' + self.fullname +
                    ':/opt/keys', '--name', self.name])

        if self.image_id.name == 'img_registry':
            cmd.extend([self.image_version_id.fullname])
        elif self.server_id == self.image_version_id.registry_id.server_id:
            cmd.extend([self.image_version_id.fullpath_localhost])
        else:
            folder = '/etc/docker/certs.d/' +\
                     self.image_version_id.registry_address
            certfile = folder + '/ca.crt'
            tmp_file = '/tmp/' + self.fullname
            self.execute(ssh, ['rm', certfile])
            ssh_registry = self.connect(
                self.image_version_id.registry_id.fullname)
            self.get(ssh_registry,
                     '/etc/ssl/certs/docker-registry.crt', tmp_file)
            ssh_registry.close()
            self.execute(ssh, ['mkdir','-p', folder])
            self.send(ssh, tmp_file, certfile)
            self.execute_local(['rm', tmp_file])
            cmd.extend([self.image_version_id.fullpath])

        # Deploy key now, otherwise the container will be angry
        # to not find the key.
        # We can't before because self.ssh_port may not be set
        self.deploy_key()

        #Run container
        self.execute(ssh, cmd)

        time.sleep(3)

        self.deploy_post()

        self.start()

        ssh.close()

        #For shinken
        self.save()

        return

    @api.multi
    def purge(self):

        self.purge_key()

        ssh = self.connect(self.server_id.name)
        self.stop()
        self.execute(ssh, ['sudo','docker', 'rm', self.name])
        self.execute(ssh, ['rm', '-rf', '/opt/keys/' + self.fullname])
        ssh.close()

        return

    @api.multi
    def stop(self):
        ssh = self.connect(self.server_id.name)
        self.execute(ssh, ['docker', 'stop', self.name])
        ssh.close()

    @api.multi
    def start(self):
        self.stop()
        ssh = self.connect(self.server_id.name)
        self.execute(ssh, ['docker', 'start', self.name])
        ssh.close()
        time.sleep(3)

    @api.multi
    def deploy_key(self):

        self.purge_key()
        self.execute_local(['ssh-keygen', '-t', 'rsa', '-C',
                            self.email_sysadmin, '-f', self.home_directory +
                            '/.ssh/keys/' + self.fullname, '-N', ''])
        self.execute_write_file(self.home_directory + '/.ssh/config',
                                'Host ' + self.fullname)
        self.execute_write_file(self.home_directory + '/.ssh/config',
                                '\n  HostName ' + self.server_id.name)
        self.execute_write_file(self.home_directory + '/.ssh/config',
                                '\n  Port ' + str(self.ssh_port))
        self.execute_write_file(self.home_directory + '/.ssh/config',
                                '\n  User root')
        self.execute_write_file(self.home_directory + '/.ssh/config',
                                '\n  IdentityFile ~/.ssh/keys/' + self.fullname)
        self.execute_write_file(self.home_directory + '/.ssh/config',
                                '\n#END ' + self.fullname + '\n')
        ssh = self.connect(self.server_id.name)
        self.execute(ssh, ['mkdir', '-p', '/opt/keys/' + self.fullname])
        self.send(ssh, self.home_directory + '/.ssh/keys/' +
                  self.fullname + '.pub', '/opt/keys/' +
                  self.fullname + '/authorized_keys')
        ssh.close()

    @api.multi
    def purge_key(self):
        self.execute_local([
            modules.get_module_path('clouder') + '/res/sed.sh',
            self.fullname, self.home_directory + '/.ssh/config'])
        self.execute_local([
            'rm', '-rf', self.home_directory +
            '/.ssh/keys/' + self.fullname])
        self.execute_local([
            'rm', '-rf', self.home_directory +
            '/.ssh/keys/' + self.fullname + '.pub'])
        ssh = self.connect(self.server_id.name)
        self.execute(ssh, [
            'rm', '-rf', '/opt/keys/' + self.fullname + '/authorized_keys'])
        ssh.close()


class ClouderContainerPort(models.Model):
    _name = 'clouder.container.port'

    container_id = fields.Many2one(
        'clouder.container', 'Container', ondelete="cascade", required=True)
    name = fields.Char('Name', size=64, required=True)
    localport = fields.Char('Local port', size=12, required=True)
    hostport = fields.Char('Host port', size=12)
    expose = fields.Selection(
        [('internet','Internet'),('local','Local')],'Expose?',
        required=True, default='local')
    udp = fields.Boolean('UDP?')

    _sql_constraints = [
        ('name_uniq', 'unique(container_id,name)',
         'Port name must be unique per container!'),
    ]


class ClouderContainerVolume(models.Model):
    _name = 'clouder.container.volume'

    container_id = fields.Many2one(
        'clouder.container', 'Container', ondelete="cascade", required=True)
    name = fields.Char('Path', size=128, required=True)
    hostpath = fields.Char('Host path', size=128)
    user = fields.Char('System User', size=64)
    readonly = fields.Boolean('Readonly?')
    nosave = fields.Boolean('No save?')


    _sql_constraints = [
        ('name_uniq', 'unique(container_id,name)',
         'Volume name must be unique per container!'),
    ]

class ClouderContainerOption(models.Model):
    _name = 'clouder.container.option'

    container_id = fields.Many2one(
        'clouder.container', 'Container', ondelete="cascade", required=True)
    name = fields.Many2one(
        'clouder.application.type.option', 'Option', required=True)
    value = fields.Text('Value')

    _sql_constraints = [
        ('name_uniq', 'unique(container_id,name)',
         'Option name must be unique per container!'),
    ]

    @api.one
    @api.constrains('container_id')
    def _check_required(self):
        if self.name.required and not self.value:
            raise except_orm(
                _('Data error!'),
                _("You need to specify a value for the option " +
                  self.name.name + " for the container " +
                  self.container_id.name + "."))


class ClouderContainerLink(models.Model):
    _name = 'clouder.container.link'
    _inherit = ['clouder.model']

    container_id = fields.Many2one(
        'clouder.container', 'Container', ondelete="cascade", required=True)
    name = fields.Many2one(
        'clouder.application.link', 'Application Link', required=True)
    target = fields.Many2one('clouder.container', 'Target')

    @api.one
    @api.constrains('container_id')
    def _check_required(self):
        if self.name.required and not self.target:
            raise except_orm(
                _('Data error!'),
                _("You need to specify a link to " +
                  self.name.application_id.name + " for the container " +
                  self.container_id.name))

    @api.multi
    def deploy_link(self):
        return

    @api.multi
    def purge_link(self):
        return

    @api.multi
    def control(self):
        if not self.target:
            self.log('The target isnt configured in the link, '
                     'skipping deploy link')
            return False
        if not self.name.container:
            self.log('This application isnt for container, '
                     'skipping deploy link')
            return False
        return True

    @api.multi
    def deploy_(self):
        self.purge_()
        self.control() and self.deploy_link()

    @api.multi
    def purge_(self):
        self.control() and self.purge_link()

