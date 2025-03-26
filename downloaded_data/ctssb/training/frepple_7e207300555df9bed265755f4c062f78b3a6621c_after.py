#
# Copyright (C) 2016 by frePPLe bvba
#
# This library is free software; you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero
# General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from datetime import datetime, timedelta
import importlib
from optparse import make_option

from django.conf import settings
from django.core import management
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction, DEFAULT_DB_ALIAS
from django.db.models import Sum, Max, Count, F

from freppledb.common.models import User, Parameter
from freppledb.execute.models import Task
from freppledb.input.models import PurchaseOrder, DistributionOrder, Buffer, Demand, Item
from freppledb.input.models import OperationPlan, Location


def load_class(full_class_string):
    """
    dynamically load a class from a string
    """
    try:
      class_data = full_class_string.split(".")
      module_path = ".".join(class_data[:-1])
      class_str = class_data[-1]

      module = importlib.import_module(module_path)
      # Finally, we retrieve the Class
      return getattr(module, class_str)
    except:
      raise CommandError("Can't load class %s" % full_class_string)


class Command(BaseCommand):
  option_list = BaseCommand.option_list + (
    make_option(
      '--user', dest='user', type='string',
      help='User running the command'
      ),
    make_option(
      '--horizon', dest='horizon', type='int', default='60',
      help='Number of days into the future to simulate'
      ),
    make_option(
      '--step', dest='step', type='int', default='1',
      help='Time increments for the current_date within the simulation horizon. Set to 1 for daily plans, and 7 for weekly plans.'
      ),
    make_option(
      '--database', action='store', dest='database',
      default=DEFAULT_DB_ALIAS,
      help='Nominates a specific database to load data from and export results into'
      ),
    make_option(
      '--task', dest='task', type='int',
      help='Task identifier (generated automatically if not provided)'
      ),
    make_option(
      '--simulator', dest='simulator', type='string', default=None,
      help='Class implementation the logic to simlate the activity in a bucket'
      ),
    make_option(
      '--initial', dest='initial', type='string', default=None,
      help='Fixture to load the initial state of the model'
      ),
    make_option(
      '--pause', dest='pause', action="store_true", default=False,
      help='Allows to stop the simulation at the end of each step'
      ),
  )
  help = '''
  Runs a simulation to measure the plan performance.

  If the parameter "initial" is specified, we first load the initial
  status for the simulation from a fixture.

  Next, we loop through the following steps for every period in the simulation horizon.
  The parameter "step" and "horizon" determine the buckets in this loop.
  For each bucket, we execute:
     a. Advance the current date
     b. Call a custom function "start_bucket"
     c. Open new sales orders from customers
     d. Generate a constrained frePPLe plan
     e. Confirm new purchase orders from the frePPLe plan
     f. Confirm new production orders from the frePPLe plan
     g. Confirm new distribution orders from the frePPLe plan
     h. Receive material from purchase orders
     i. Finish production from manufacturing orders
     j. Receive material from distribution orders
     k. Ship open sales orders to customers
     l. Call a custom function "end_bucket"

  To allow easy customization of the simulation process, these steps are
  coded in a dedicated simulation class. A default implementation is
  provided, which can easily be extended in a subclass.

  Warning: The simulation run will update the data in the database.
  Make a backup if you can't afford loosing the current contents.
  '''

  requires_system_checks = False

  def handle(self, **options):
    # Pick up the options
    if 'database' in options:
      database = options['database'] or DEFAULT_DB_ALIAS
    else:
      database = DEFAULT_DB_ALIAS
    if database not in settings.DATABASES:
      raise CommandError("No database settings known for '%s'" % database )
    if 'user' in options and options['user']:
      try:
        user = User.objects.all().using(database).get(username=options['user'])
      except:
        raise CommandError("User '%s' not found" % options['user'] )
    else:
      user = None

    now = datetime.now()
    task = None
    param = None
    try:
      # Initialize the task
      if 'task' in options and options['task']:
        try:
          task = Task.objects.all().using(database).get(pk=options['task'])
        except:
          raise CommandError("Task identifier not found")
        if task.started or task.finished or task.status != "Waiting" or task.name != 'plan simulation':
          raise CommandError("Invalid task identifier")
        task.status = '0%'
        task.started = now
      else:
        task = Task(name='plan simulation', submitted=now, started=now, status='0%', user=user)

      # Validate options
      if 'horizon' in options:
        horizon = int(options['horizon'])
        if horizon < 0:
          raise ValueError("Invalid horizon: %s" % options['horizon'])
        task.arguments = "--horizon=%d" % horizon
      else:
        horizon = 60
      if 'step' in options:
        step = int(options['step'])
        if step < 0:
          raise ValueError("Invalid step: %s" % options['step'])
        task.arguments = "--step=%d" % step
      else:
        step = 1
      if 'verbosity' in options:
        verbosity = int(options['verbosity'])
      else:
        verbosity = 0

      # Log task
      task.save(using=database)

      # Load the initial status
      if options.get('initial', None):
        if verbosity > 0:
          print("Erasing simulation database")
        management.call_command('frepple_flush', database=database, verbosity=verbosity)
        if verbosity > 0:
          print("Loading initial data")
        management.call_command('loaddata', options.get('initial'), database=database, verbosity=verbosity)

      # Get current date
      param = Parameter.objects.all().using(database).get_or_create(name='currentdate')[0]
      try:
        curdate = datetime.strptime(param.value, "%Y-%m-%d %H:%M:%S")
      except:
        curdate = datetime.now()
      curdate = curdate.date()

      # Compute how many simulation steps we need
      bckt_list = []
      tmp = 0
      while tmp <= horizon:
        bckt_list.append( curdate + timedelta(days=tmp) )
        tmp += step
      bckt_list_len = len(bckt_list)

      # Create the simulator class
      if options.get('simulator', None):
        cls = load_class(options['simulator'])
        simulator = cls(database=database, verbosity=verbosity)
      else:
        simulator = Simulator(database=database, verbosity=verbosity)
      simulator.buckets = 1

      # The simulation only support complete shipments for the full quantity.
      # We enforce that the generated plan respects this as well.
      Demand.objects.all().using(database).update(minshipment=F('quantity'))

      # Loop over all dates in the simulation horizon
      idx = 0
      strt = None
      nd = None
      for bckt in bckt_list:
        if nd:
          strt = nd
          nd = bckt
        else:
          nd = bckt
          continue

        # Start message
        task.status = "%.0f%%" % (100.0 * idx / bckt_list_len)
        task.message = 'Simulating bucket from %s to %s ' % (strt, nd)
        task.save(using=database)
        idx += 1
        simulator.buckets += 1

        if verbosity > 0:
          print("\nStart simulating bucket from %s to %s (%s out of %s)" % (strt, nd, idx, bckt_list_len))

        # Update currentdate parameter
        param.value = strt.strftime("%Y-%m-%d %H:%M:%S")
        param.save(using=database)

        # Initialization of the bucket
        if verbosity > 1:
          print("  Starting the bucket")
        with transaction.atomic(using=database):
          simulator.start_bucket(strt, nd)

        # Generate new demand records
        if verbosity > 1:
          print("  Receive new orders from customers")
        with transaction.atomic(using=database):
          simulator.generate_customer_demand(strt, nd)

        # Generate the constrained plan
        if verbosity > 1:
          print("  Generating plan...")
        management.call_command('frepple_run', database=database)

        if options['pause']:
          print("\nYou can analyze the plan in the bucket in the user interface now...")
          input("\nPress Enter to continue the simulation...\n")

        # Release new purchase orders
        if verbosity > 1:
          print("  Create new purchase orders")
        with transaction.atomic(using=database):
          simulator.create_purchase_orders(strt, nd)

        # Release new manufacturing orders
        if verbosity > 1:
          print("  Create new manufacturing orders")
        with transaction.atomic(using=database):
          simulator.create_manufacturing_orders(strt, nd)

        # Release new distribution orders
        if verbosity > 1:
          print("  Create new distribution orders")
        with transaction.atomic(using=database):
          simulator.create_distribution_orders(strt, nd)

        # Receive open purchase orders
        if verbosity > 1:
          print("  Receive open purchase orders")
        with transaction.atomic(using=database):
          simulator.receive_purchase_orders(strt, nd)

        # Receive open distribution orders
        if verbosity > 1:
          print("  Receive open distribution orders")
        with transaction.atomic(using=database):
          simulator.receive_distribution_orders(strt, nd)

        # Finish open manufacturing orders
        if verbosity > 1:
          print("  Finish open manufacturing orders")
        with transaction.atomic(using=database):
          simulator.finish_manufacturing_orders(strt, nd)

        # Ship demand to customers
        if verbosity > 1:
          print("  Ship orders to customers")
        with transaction.atomic(using=database):
          simulator.ship_customer_demand(strt, nd)

        # Finish of the bucket
        if verbosity > 1:
          print("  Ending the bucket")
        with transaction.atomic(using=database):
          simulator.end_bucket(strt, nd)

      # Report statistics from the simulation.
      # The simulator class collected these results during its run.
      if verbosity > 1:
        print("Displaying final simulation metrics")
      with transaction.atomic(using=database):
        simulator.show_metrics()

      # Task update
      task.status = 'Done'
      task.message = "Simulated from %s till %s" % (bckt_list[0], bckt_list[-1])
      task.finished = datetime.now()

    except Exception as e:
      if task:
        task.status = 'Failed'
        task.message = '%s' % e
        task.finished = datetime.now()
      raise e

    finally:
      # Final task status
      if task:
        task.save(using=database)


class Simulator(object):

  def __init__(self, database=DEFAULT_DB_ALIAS, verbosity=0):
    self.database = database
    self.verbosity = verbosity
    self.demand_number = Demand.objects.all().using(self.database).count()
    self.mo_number = OperationPlan.objects.all().using(self.database).aggregate(Max('id'))['id__max']
    if not self.mo_number:
      self.mo_number = 0
    self.mo_number += 10000 # A bit of a trick to avoid duplicate IDs with POs and DOs

    # Metrics for on-time delivery
    self.demand_shipped = 0
    self.demand_late = 0
    self.demand_lateness = timedelta(0)

    # Metrics for inventory value
    self.inventory_value = 0
    self.inventory_quantity = 0

    # Metrics for work in progress
    self.wip_quantity = 0

    # Metrics for demand
    self.demand_quantity = 0
    self.demand_value = 0
    self.demand_count = 0


  def start_bucket(self, strt, nd):
    '''
    A method called at the start of each simulation bucket.

    It can be used to gather performance metrics, or initialize some variables.
    '''
    return


  def end_bucket(self, strt, nd):
    '''
    A method called at the end of each simulation bucket.

    It can be used to gather performance metrics, or initialize some variables.
    '''
    if self.verbosity > 2:
      self.printStatus()

    # Measure the current inventory
    inv = Buffer.objects.all().using(self.database).filter(onhand__gt=0).aggregate(
      val=Sum(F('onhand') * F('item__price')),
      qty=Sum(F('onhand'))
      )
    if inv['val']:
      self.inventory_value += inv['val']
    if inv['qty']:
      self.inventory_quantity += inv['qty']

    # Measure the current work-in-progress
    wip = OperationPlan.objects.all().using(self.database).filter(status='confirmed').aggregate(
      qty=Sum(F('quantity'))
      )
    if wip['qty']:
      self.wip_quantity += wip['qty']

    # Measure the current order book
    dmd = Demand.objects.all().using(self.database).filter(status='open').aggregate(
      val=Sum(F('quantity') * F('item__price')),
      qty=Sum(F('quantity')),
      cnt=Count(F('name'))
      )
    if dmd['val']:
      self.demand_value += dmd['val']
    if dmd['qty']:
      self.demand_quantity += dmd['qty']
    if dmd['cnt']:
      self.demand_count += dmd['cnt']


  def finish_manufacturing_orders(self, strt, nd):
    '''
    Find all confirmed manufacturing orders scheduled to finish in this bucket.

    For each of these manufacturing orders:
      - delete the record
      - execute all material flows at the end of the operation
    '''
    for op in OperationPlan.objects.select_for_update().using(self.database).filter(status="confirmed", enddate__lte=nd):
      buf = None
      for fl in op.operation.flows.all():
        if fl.quantity > 0:
          buf = fl.thebuffer
          break
      if not buf:
        continue
      if self.verbosity > 2:
        print("      Closing MO %s - %d of %s" % (op.id, op.quantity, op.operation.name))
      op.status = "closed"
      op.save(using=self.database)
      for fl in op.operation.flows.all():
        if fl.type == 'end':
          fl.thebuffer.onhand += fl.quantity * op.quantity
          fl.thebuffer.save(using=self.database)
        elif fl.type == 'fixed_end':
          fl.thebuffer.onhand += fl.quantity
          fl.thebuffer.save(using=self.database)


  def create_manufacturing_orders(self, strt, nd):
    '''
    Find proposed operationplans within the time bucket.
    For each of these operationplans:
      - change the status to "confirmed"
      - execute all material flows at the start of the operation
    '''
    for op in OperationPlan.objects.select_for_update().using(self.database).filter(status="proposed", startdate__lte=nd):
      if self.verbosity > 2:
        print("      Opening MO %s - %d of %s" % (op.id, op.quantity, op.operation.name))
      for fl in op.operation.flows.all():
        if fl.type == 'start':
          fl.thebuffer.onhand += fl.quantity * op.quantity
          fl.thebuffer.save(using=self.database)
        elif fl.type == 'fixed_start':
          fl.thebuffer.onhand += fl.quantity
          fl.thebuffer.save(using=self.database)
      op.status = 'confirmed'
      op.save(using=self.database)


  def receive_purchase_orders(self, strt, nd):
    '''
    Find all confirmed purchase orders with an expected delivery date within the simulation bucket.
    For each of these purchase orders:
      - change the status to "closed"
      - add the received quantity into the onhand of the buffer
    '''
    for po in PurchaseOrder.objects.select_for_update().using(self.database).filter(status="confirmed", enddate__lte=nd):
      if self.verbosity > 2:
        print("      Closing PO %s - %d of %s@%s" % (po.id, po.quantity, po.item.name, po.location.name))
      try:
        buf = Buffer.objects.select_for_update().using(self.database).get(item=po.item, location=po.location)
        buf.onhand += po.quantity
        buf.save(using=self.database)
        po.status = 'closed'
        po.save(using=self.database)
      except Buffer.DoesNotExist:
        print("        ERROR: can't find the buffer to receive the PO")


  def create_purchase_orders(self, strt, nd):
    '''
    Find proposed purchase orders within the time bucket.
    For each of these purchase orders:
      - change the status to "confirmed"
    '''
    for po in PurchaseOrder.objects.select_for_update().using(self.database).filter(status="proposed", startdate__lte=nd):
      if self.verbosity > 2:
        print("      Opening PO %s - %d of %s@%s" % (po.id, po.quantity, po.item.name, po.location.name))
      po.status = 'confirmed'
      po.save(using=self.database)


  def create_distribution_orders(self, strt, nd):
    '''
    Find proposed distribution orders due to be shipped within the time bucket.
    For each of these distribution orders:
      - change the status to "confirmed"
      - consume the material from the source location
    '''
    for do in DistributionOrder.objects.select_for_update().using(self.database).filter(status="proposed", startdate__lte=nd):
      if self.verbosity > 2:
        print("      Opening DO %s - %d from %s@%s to %s@%s" % (do.id, do.quantity, do.item.name, do.origin.name, do.item.name, do.destination.name))
      try:
        buf = Buffer.objects.select_for_update().using(self.database).get(item=do.item, location=do.origin)
        buf.onhand -= do.quantity
        buf.save(using=self.database)
        do.status = 'confirmed'
        do.save(using=self.database)
      except Buffer.DoesNotExist:
        print("        ERROR: can't find the buffer to create the DO")


  def receive_distribution_orders(self, strt, nd):
    '''
    Find all confirmed distribution orders with an expected delivery date within the simulation buckets.
    For each of these purchase orders:
      - change the status to "closed"
      - add the received quantity into the onhand of the buffer
    '''
    for do in DistributionOrder.objects.select_for_update().using(self.database).filter(status="confirmed", enddate__lte=nd):
      if self.verbosity > 2:
        print("      Closing DO %s - %d of %s@%s" % (do.id, do.quantity, do.item.name, do.destination.name))
      try:
        buf = Buffer.objects.select_for_update().using(self.database).get(item=do.item, location=do.destination)
        buf.onhand += do.quantity
        buf.save(using=self.database)
        do.status = 'closed'
        do.save(using=self.database)
      except Buffer.DoesNotExist:
        print("        ERROR: can't find the buffer to receive the DO")


  def generate_customer_demand(self, strt, nd):
    '''
    Simulate new customers orders being received.
    This function creates new records in the demand table.

    The default implementation doesn't create any new demands. We only
    simulate the execution of the current open sales orders.

    A simplistic, hardcoded example of creating demands is shown.
    TODO A more generic mechanism to have a data-driven automatic demand generation would be nice.
    Eg use some "template records" in the demand table which we use to
    automatically create new demands with a specific frequency.
    '''
    return

    self.demand_number += 1
    dmd = Demand.objects.using(self.database).create(
      name="Demand #%s" % self.demand_number,
      item=Item.objects.all().using(self.database).get(name='product'),
      location=Location.objects.all().using(self.database).get(name='factory 1'),
      quantity=100,
      status='open',
      due=strt + timedelta(days=14)
      )
    if self.verbosity > 2:
      print("      Opening demand %s - %d of %s@%s due on %s" % (dmd.name, dmd.quantity, dmd.item.name, dmd.location.name, dmd.due))


  def checkAvailable(self, qty, oper, consume):
    '''
    Verify whether an operationplan of a given quantity is material-feasible.
    '''
    for fl in oper.flows.all():
      if fl.quantity > 0 and not consume:
        continue
      if fl.type in ('start', 'end') or not fl.type:
        if consume:
          fl.thebuffer.onhand += qty * fl.quantity
          fl.thebuffer.save(using=self.database)
        elif fl.thebuffer.onhand < - fl.quantity * qty:
          return False
      if fl.type in ('fixed_start', 'fixed_end'):
        if consume:
          fl.thebuffer.onhand += qty
          fl.thebuffer.save(using=self.database)
        elif fl.thebuffer.onhand < - qty:
          return False
    if oper.type == 'routing':
      # All routing suboperations must return an ok
      for suboper in oper.suboperations.all().order_by("priority"):
        if not self.checkAvailable(qty, suboper.suboperation, consume):
          return False
    elif oper.type == 'alternate':
      # An ok from a single suboperation suffices
      for suboper in oper.suboperations.all().order_by("priority"):
        if consume:
          if self.checkAvailable(qty, suboper.suboperation, False):
            self.checkAvailable(qty, suboper.suboperation, True)
            return True
        elif self.checkAvailable(qty, suboper.suboperation, consume):
          return True
      return False
    return True


  def ship_customer_demand(self, strt, nd):
    '''
    Deliver customer orders to customers.

    We search for open demand records with a due date earlier than the end of the bucket.
    The records found are ordered by priority and due date.
    For each record found:
      - we check if the order can be shipped from end item inventory
      - if no:
          - skip the demand (hopefully we can ship it when simulating the next bucket...)
      - if yes:
          - change the demand status to 'closed'
          - reduce the inventory of the product

    We don't account for partial deliveries and max_lateness.
    '''
    for dmd in Demand.objects.using(self.database).filter(due__lt=nd, status='open').order_by('priority', 'due'):
      oper = dmd.operation
      if not oper:
        oper = dmd.item.operation
      if oper:
        # Case 1: Delivery operation specified
        if self.checkAvailable(dmd.quantity, oper, False):
          # Execute all flows on the delivery operation
          self.checkAvailable(dmd.quantity, oper, True)
        else:
          # We can't ship the order
          continue
      else:
        # Case 2: Automatically generated delivery operation
        try:
          buf = Buffer.objects.select_for_update().using(self.database).get(item=dmd.item, location=dmd.location)
        except Buffer.DoesNotExist:
          continue
        if buf.onhand < dmd.quantity:
          # We can't ship the order
          continue
        else:
          buf.onhand -= dmd.quantity
          buf.save(using=self.database)

      # We can satisfy this order
      dmd.status = 'closed'
      self.demand_shipped += 1
      if strt > dmd.due.date():
        self.demand_late += 1
        self.demand_lateness += strt - dmd.due.date()
        dmd.category = 'delivered late on %s' % strt
      else:
        dmd.category = 'delivered on time on %s' % dmd.due
      if self.verbosity > 2:
        print("      Closing demand %s - %d of %s@%s due on %s - delay %s" % (
          dmd.name, dmd.quantity, dmd.item.name,
          dmd.location.name if dmd.location else None, dmd.due,
          max(strt - dmd.due.date(), timedelta(0))
          ))
      dmd.save(using=self.database)


  def printStatus(self):
    '''
    This is an auxilary method useful during debugging.

    It prints the list of all open transactions:
      - open customer demands
      - confirmed purchase orders
      - confirmed operationplans
      - confirmed distribution orders
      - current inventory
    '''
    print("  Current status:")
    for dmd in Demand.objects.all().using(self.database).filter(status='open').order_by('due', 'name'):
      print("    Demand '%s': %d %s@%s due on %s" % (
        dmd.name, dmd.quantity, dmd.item.name, dmd.location.name if dmd.location else 'None', dmd.due
        ))
    for po in PurchaseOrder.objects.all().using(self.database).filter(status='confirmed').order_by('enddate', 'startdate'):
      print("    Purchase order '%s': %d %s@%s delivery on %s" % (
        po.id, po.quantity, po.item.name, po.location.name, po.enddate
        ))
    for do in DistributionOrder.objects.all().using(self.database).filter(status='confirmed').order_by('enddate', 'startdate'):
      print("    Distribution order '%s': %d %s@%s arriving on %s" % (
        do.id, do.quantity, do.item.name, do.destination.name, do.enddate
        ))
    for op in OperationPlan.objects.all().using(self.database).filter(status='confirmed').order_by('enddate', 'startdate'):
      print("    Operation plan '%s': %d %s finishing on %s" % (
        op.id, op.quantity, op.operation.name, op.enddate
        ))
    for buf in Buffer.objects.all().using(self.database).filter(onhand__gt=0).order_by('name'):
      print("    Inventory '%s': %d" % (
        buf.name, buf.onhand
        ))


  def show_metrics(self):
    if not self.verbosity:
      return
    print("   Average open demands: %.2f for %.2f units with value %.2f" % (
      self.demand_count/self.buckets, self.demand_quantity/self.buckets, self.demand_quantity/self.buckets
      ))
    print("   Shipped %s demands" % self.demand_shipped)
    print("   Shipped %d demands late, average lateness %.2f days" % (
      self.demand_late, self.demand_lateness.total_seconds()/ 3600.0 / 24.0 / max(1, self.demand_late)
      ))
    print("   Average inventory: %.2f units with value %.2f" % (
      self.inventory_quantity/self.buckets, self.inventory_value/self.buckets
      ))
    print("   Average work in progress: %.2f units" % (self.wip_quantity/self.buckets))
