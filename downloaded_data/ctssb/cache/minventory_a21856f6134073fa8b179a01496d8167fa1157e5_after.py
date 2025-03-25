from django.db import models
from django.db.models import Q

from core.mixins import ObjectUrlMixin, CoreDisplayMixin
from mozdns.domain.models import Domain
from core.utils import networks_to_Q

from core.keyvalue.models import KeyValue


class Vlan(models.Model, ObjectUrlMixin, CoreDisplayMixin):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    number = models.PositiveIntegerField()

    search_fields = ('name', 'number')

    template = (
        "{name:$lhs_just} {rdtype:$rdtype_just} {number:$rhs_just}"
    )

    class Meta:
        db_table = "vlan"
        unique_together = ("name", "number")

    def __str__(self):
        return "{0} {1}".format(self.number, self.name)

    def __repr__(self):
        return "<Vlan {0}>".format(str(self))

    @classmethod
    def get_api_fields(cls):
        return ['name', 'number']

    @property
    def rdtype(self):
        return 'VLAN'

    def details(self):
        return (
            ("Name", self.name),
            ("Number", self.number),
        )

    def compile_Q(self):
        """Compile a Django Q that will match any IP inside this vlan."""
        return networks_to_Q(self.network_set.all())

    def compile_network_Q(self):
        """
        Compile a Django Q that will match all networks that relate to this
        vlan.
        """
        def combine(q, n):
            return q | Q(pk=n.pk)
        return reduce(combine, self.network_set.all(), Q(pk__lt=-1))

    def find_domain(self):
        """
        This memeber function will look at all the Domain objects and attempt
        to find an approriate domain that corresponds to this VLAN.
        """
        for network in self.network_set.all():
            if network.site:
                expected_name = "{0}.{1}.mozilla.com".format(
                    self.name, network.site.get_site_path())
                try:
                    domain = Domain.objects.get(name=expected_name)
                except Domain.DoesNotExist:
                    continue
                return domain.name

        return None


class VlanKeyValue(KeyValue):
    obj = models.ForeignKey(Vlan, related_name='keyvalue_set', null=False)

    class Meta:
        db_table = "vlan_key_value"
        unique_together = ("key", "value")

    def _aa_description(self):
        return
