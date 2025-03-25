import uuid
from cms.utils.compat.dj import python_2_unicode_compatible
from cms.utils.copy_plugins import copy_plugins_to
from django.contrib.sites.models import Site

from django.db import models
from django.utils.translation import ugettext_lazy as _

from cms.models.fields import PlaceholderField
from cms.models.pluginmodel import CMSPlugin



def static_slotname(instance):
    """
    Returns a string to be used as the slot
    for the static placeholder field.
    """
    return instance.code


@python_2_unicode_compatible
class StaticPlaceholder(models.Model):
    CREATION_BY_TEMPLATE = 'template'
    CREATION_BY_CODE = 'code'
    CREATION_METHODS = (
        (CREATION_BY_TEMPLATE, _('by template')),
        (CREATION_BY_CODE, _('by code')),
    )
    name = models.CharField(
        verbose_name=_(u'static placeholder name'), max_length=255, blank=True, default='',
        help_text=_(u'Descriptive name to identify this static placeholder. Not displayed to users.'))
    code = models.CharField(
        verbose_name=_(u'placeholder code'), max_length=255, blank=True,
        help_text=_(u'To render the static placeholder in templates.'))
    draft = PlaceholderField(static_slotname, verbose_name=_(u'placeholder content'), related_name='static_draft')
    public = PlaceholderField(static_slotname, editable=False, related_name='static_public')
    dirty = models.BooleanField(default=False, editable=False)
    creation_method = models.CharField(
        verbose_name=_('creation_method'), choices=CREATION_METHODS,
        default=CREATION_BY_CODE, max_length=20, blank=True,
    )
    site = models.ForeignKey(Site, editable=False)

    class Meta:
        verbose_name = _(u'static placeholder')
        verbose_name_plural = _(u'static placeholders')
        app_label = 'cms'
        unique_together = (('code', 'site'),)

    def __str__(self):
        return self.name

    def clean(self):
        # TODO: check for clashes if the random code is already taken
        if not self.code:
            self.code = u'static-%s' % uuid.uuid4()

    def publish(self, request, language, force=False):
        if force or self.has_publish_permission(request):
            for plugin in CMSPlugin.objects.filter(placeholder=self.public, language=language).order_by('-level'):
                inst, cls = plugin.get_plugin_instance()
                if inst and getattr(inst, 'cmsplugin_ptr', False):
                    inst.cmsplugin_ptr._no_reorder = True
                    inst.delete()
                else:
                    plugin._no_reorder = True
                    plugin.delete()
            plugins = self.draft.get_plugins_list(language=language)
            copy_plugins_to(plugins, self.public, no_signals=True)
            self.dirty = False
            self.save()
            return True
        return False

    def has_change_permission(self, request):
        if request.user.is_superuser:
            return True
        opts = self._meta
        return request.user.has_perm(opts.app_label + '.' + "change")

    def has_publish_permission(self, request):
        if request.user.is_superuser:
            return True
        opts = self._meta
        return request.user.has_perm(opts.app_label + '.' + "change") and \
               self.has_generic_permission(request, "publish")
