# ------------------------------------------------------------------------------
# Copyright (c) 2010-2013, EVEthing team
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without modification,
# are permitted provided that the following conditions are met:
#
#     Redistributions of source code must retain the above copyright notice, this
#       list of conditions and the following disclaimer.
#     Redistributions in binary form must reproduce the above copyright notice,
#       this list of conditions and the following disclaimer in the documentation
#       and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
# IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT,
# INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT
# NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
# PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
# WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY
# OF SUCH DAMAGE.
# ------------------------------------------------------------------------------

from django.db import models

from thing.models.character import Character
from thing.models.corporation import Corporation
from thing.models.station import Station
from thing.models.alliance import Alliance


class Contract(models.Model):
    character = models.ForeignKey(Character)
    corporation = models.ForeignKey(Corporation, blank=True, null=True)

    contract_id = models.IntegerField(db_index=True)
    name = models.CharField(max_length=128, default="")

    issuer_char = models.ForeignKey(Character, blank=True, null=True, related_name='+')
    issuer_corp = models.ForeignKey(Corporation, related_name='+')
    assignee_id = models.IntegerField(default=0)
    acceptor_id = models.IntegerField(default=0)

    start_station = models.ForeignKey(Station, blank=True, null=True, related_name='+')
    end_station = models.ForeignKey(Station, blank=True, null=True, related_name='+')

    type = models.CharField(max_length=16)
    status = models.CharField(max_length=24)
    title = models.CharField(max_length=64)
    for_corp = models.BooleanField(default=False)
    public = models.BooleanField(default=False)

    date_issued = models.DateTimeField()
    date_expired = models.DateTimeField()
    date_accepted = models.DateTimeField(blank=True, null=True)
    date_completed = models.DateTimeField(blank=True, null=True)
    num_days = models.IntegerField()

    price = models.DecimalField(max_digits=15, decimal_places=2)
    reward = models.DecimalField(max_digits=15, decimal_places=2)
    collateral = models.DecimalField(max_digits=15, decimal_places=2)
    buyout = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    volume = models.DecimalField(max_digits=16, decimal_places=4)

    retrieved_items = models.BooleanField(default=False)

    class Meta:
        app_label = 'thing'
        ordering = ('-date_issued',)


    def __unicode__(self):
        if self.type == 'Courier':
            return '#%d (%s, %s -> %s)' % (self.contract_id, self.type, self.start_station.short_name, self.end_station.short_name)
        else:
            return '#%d (%s, %s)' % (self.contract_id, self.type, self.start_station.short_name)


    def get_issuer_name(self):
        if self.for_corp:
            return self.issuer_corp.name
        else:
            return self.issuer_char.name


    def availability(self):
        return self._entity_from_id(self.assignee_id)

    def contractor(self):
        return self._entity_from_id(self.acceptor_id)


    def _entity_from_id(self, id):
        char = Character.objects.filter(id=id).first()
        if char != None:
            return {
                "fa": "fa-user",
                "name": char.name
            }

        corp = Corporation.objects.filter(id=id).first()
        if corp != None:
            return {
                "fa": "fa-group",
                "name": corp.name
            }

        alliance = Alliance.objects.filter(id=id).first()
        if alliance != None:
            return {
                "fa": "fa-hospital-o",
                "name": alliance.name
            }

    def save(self, *args, **kwargs):
        self._make_name()
        super(Contract, self).save(*args, **kwargs)

    def _make_name(self):
        if self.type in ["Item Exchange", "Auction"]:
            item_count = self.items.filter(included=True).count()

            if item_count == 0:
                self.name = "Empty Item Exchange"
            elif item_count == 1:
                item = self.items.filter(included=True).first()
                self.name = "%s x %s" % (item.name, item.quantity)
            else:
                self.name = "[Multiple Items]"

        if self.type == "Courier":
            self.name = "%s >> %s (%s m3)" % (
                self.start_station.system.name,
                self.end_station.system.name,
                int(self.volume)
            )
