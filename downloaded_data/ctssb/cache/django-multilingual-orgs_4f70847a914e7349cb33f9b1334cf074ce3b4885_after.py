"""django-cms plugins for the ``multilingual_orgs`` app."""
from django.utils.translation import ugettext_lazy as _

from cms.plugin_base import CMSPluginBase
from cms.plugin_pool import plugin_pool

from .models import OrganizationPluginModel


class OrganizationPlugin(CMSPluginBase):
    model = OrganizationPluginModel
    name = _("Organization Plugin")
    render_template = "multilingual_orgs/organization_plugin.html"

    def render(self, context, instance, placeholder):
        context.update({
            'plugin': instance,
            'organization': instance.organization,
            'display_type': instance.display_type,
        })
        return context


plugin_pool.register_plugin(OrganizationPlugin)
