from zope.interface import implementer

from TimeClock.ITimeClock.IDatabase.IEntryType import IEntryType
from TimeClock.ITimeClock.IDatabase.IPerson import IPerson
from TimeClock.ITimeClock.IDatabase.ITimePeriod import ITimePeriod
from TimeClock.Util import NULL
from ...ITimeClock.IDateTime import IDateTime

from TimeClock.Database.Commands.CommandEvent import CommandEvent
from TimeClock.Exceptions import PermissionDenied
from TimeClock.ITimeClock.ICommand import ICommand
from TimeClock.ITimeClock.IDatabase.IAdministrator import IAdministrator
from TimeClock.ITimeClock.IDatabase.IEmployee import IEmployee
from TimeClock.ITimeClock.IDatabase.IItem import IItem
from TimeClock.ITimeClock.IDatabase.IPermission import IPermission
from TimeClock.ITimeClock.IDatabase.ISupervisee import ISupervisee
from TimeClock.ITimeClock.IDatabase.ISupervisor import ISupervisor
from TimeClock.ITimeClock.IDatabase.ITimeEntry import ITimeEntry
from TimeClock.ITimeClock.IEvent.IEventBus import IEventBus
from TimeClock.Utils import overload
from axiom.item import Item
from axiom.attributes import text


@implementer(ICommand, IItem)
class ScheduleTimeOff(Item):
    typeName = 'timeclock_database_commands_schedulevacation_schedulevacation'
    name = text(default="Schedule Time Off")
    @overload
    def hasPermission(self, caller: IPerson) -> bool:
        return True

    @overload
    def hasPermission(self, caller: ISupervisor, employee: ISupervisee) -> bool:
        return caller is employee or IAdministrator(caller, None) or employee in caller.powerupsFor(ISupervisee)
    @overload
    def hasPermission(self, permissions: [IPermission]) -> bool:
        return False
    @overload
    def execute(self, caller: IPerson, employee: ISupervisee, start: IDateTime=None, end: IDateTime=None) -> ITimeEntry:
        if self.hasPermission(caller, employee):
            c = CommandEvent(caller, self, employee, start, end)
            if IEventBus("Commands").postEvent(c):
                entry = ITimeEntry(NULL)
                entry.type = IEntryType("Vacation")
                entry.employee = employee
                if start:
                    entry.start(start)
                if end:
                    entry.end(end)
                employee.powerUp(entry, ITimeEntry)
                return entry
        else:
            raise PermissionDenied()
    @overload
    def execute(self, caller: IPerson, start: IDateTime = None, end: IDateTime = None) -> ITimeEntry:
        return self.execute(caller, caller, start, end)

    @overload
    def execute(self, caller: IEmployee, *parameters: object):
        raise NotImplementedError("%s called with invalid parameters" % self.name)
