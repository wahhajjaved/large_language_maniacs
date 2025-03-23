##############################################################################
#
# Copyright (c) 2006 Nexedi SARL and Contributors. All Rights Reserved.
#                    Aurelien Calonne <aurel@nexedi.com>
#
# WARNING: This program as such is intended to be used by professional
# programmers who take the whole responsability of assessing all potential
# consequences resulting from its eventual inadequacies and bugs
# End users who are looking for a ready-to-use solution with commercial
# garantees and support are strongly adviced to contract a Free Software
# Service Company
#
# This program is Free Software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
#
##############################################################################

from DateTime import DateTime


def isSameSet(a, b):
  for i in a:
    if not(i in b) : return 0
  for i in b:
    if not(i in a): return 0
  if len(a) != len(b) : return 0
  return 1


class TestERP5BankingMixin:
  """
  Mixin class for unit test of banking operations
  """


  def enableLightInstall(self):
    """
      Return if we should do a light install (1) or not (0)
      Light install variable is used at installation of categories in business template
      to know if we wrap the category or not, if 1 we don't use and installation is faster
    """
    return 1 # here we want a light install for a faster installation

  def enableActivityTool(self):
    """
      Return if we should create (1) or not (0) an activity tool
      This variable is used at the creation of the site to know if we use
      the activity tool or not
    """
    return 1 # here we want to use the activity tool

  def checkUserFolderType(self):
    """
      Check the type of user folder to let the test working with both NuxUserGroup and PAS.
    """
    self.user_folder = self.getUserFolder()
    self.PAS_installed = 0
    if self.user_folder.meta_type == 'Pluggable Auth Service':
      # we use PAS
      self.PAS_installed = 1

  def updateRoleMappings(self, portal_type_list=''):
    """Update the local roles in existing objects.
    """
    portal_catalog = self.portal.portal_catalog
    for portal_type in portal_type_list:
      for brain in portal_catalog(portal_type = portal_type):
        obj = brain.getObject()
        userdb_path, user_id = obj.getOwnerTuple()
        obj.assignRoleToSecurityGroup(user_name = user_id)

  def assignPASRolesToUser(self, user_name, role_list):
    """
      Assign a list of roles to one user with PAS.
    """
    for role in role_list:
      if role not in self.user_folder.zodb_roles.listRoleIds():
        self.user_folder.zodb_roles.addRole(role)
      self.user_folder.zodb_roles.assignRoleToPrincipal(role, user_name)

  def createManagerAndLogin(self):
    """
      Create a simple user in user_folder with manager rights.
      This user will be used to initialize data in the method afterSetup
    """
    self.getUserFolder()._doAddUser('manager', '', ['Manager'], [])
    self.login('manager')

  def createERP5Users(self, user_dict):
    """
      Create all ERP5 users needed for the test.
      ERP5 user = Person object + Assignment object in erp5 person_module.
    """
    for user_login, user_data in user_dict.items():
      user_roles = user_data[0]
      # Create the Person.
      person = self.person_module.newContent(id=user_login,
          portal_type='Person', reference=user_login, career_role="internal")
      # Create the Assignment.
      assignment = person.newContent( portal_type       = 'Assignment'
                                    , destination_value = user_data[1]
                                    , function          = "function/%s" %user_data[2]
                                    , group             = "group/%s" %user_data[3]
                                    , site              = "site/%s" %user_data[4]
                                    , start_date        = '01/01/1900'
                                    , stop_date         = '01/01/2900'
                                    )
      if self.PAS_installed and len(user_roles) > 0:
        # In the case of PAS, if we want global roles on user, we have to do it manually.
        self.assignPASRolesToUser(user_login, user_roles)
      elif not self.PAS_installed:
        # The user_folder counterpart of the erp5 user must be
        #   created manually in the case of NuxUserGroup.
        self.user_folder.userFolderAddUser( name     = user_login
                                          , password = ''
                                          , roles    = user_roles
                                          , domains  = []
                                          )
      # User assignment to security groups is also required, but is taken care of
      #   by the assignment workflow when NuxUserGroup is used and
      #   by ERP5Security PAS plugins in the context of PAS use.
      assignment.open()

    if self.PAS_installed:
      # reindexing is required for the security to work
      get_transaction().commit()
      self.tic()



  def getUserFolder(self):
    """
    Return the user folder
    """
    return getattr(self.getPortal(), 'acl_users', None)

  def getPersonModule(self):
    """
    Return the person module
    """
    return getattr(self.getPortal(), 'person_module', None)

  def getOrganisationModule(self):
    """
    Return the organisation module
    """
    return getattr(self.getPortal(), 'organisation_module', None)

  def getCurrencyCashModule(self):
    """
    Return the Currency Cash Module
    """
    return getattr(self.getPortal(), 'currency_cash_module', None)

  def getCashInventoryModule(self):
    """
    Return the Cash Inventory Module
    """
    return getattr(self.getPortal(), 'cash_inventory_module', None)

  def getBankAccountInventoryModule(self):
    """
    Return the Bank Account Inventory Module
    """
    return getattr(self.getPortal(), 'bank_account_inventory_module', None)

  def getCurrencyModule(self):
    """
    Return the Currency Module
    """
    return getattr(self.getPortal(), 'currency_module', None)

  def getCategoryTool(self):
    """
    Return the Category Tool
    """
    return getattr(self.getPortal(), 'portal_categories', None)

  def getWorkflowTool(self):
    """
    Return the Worklfow Tool
    """
    return getattr(self.getPortal(), 'portal_workflow', None)

  def getSimulationTool(self):
    """
    Return the Simulation Tool
    """
    return getattr(self.getPortal(), 'portal_simulation', None)

  def getCheckPaymentModule(self):
    """
    Return the Check Payment Module
    """
    return getattr(self.getPortal(), 'check_payment_module', None)

  def getCheckDepositModule(self):
    """
    Return the Check Deposit Module
    """
    return getattr(self.getPortal(), 'check_deposit_module', None)

  def getCheckbookModule(self):
    """
    Return the Checkbook Module
    """
    return getattr(self.getPortal(), 'checkbook_module', None)


  def getCounterDateModule(self):
    """
    Return the Counter Date Module
    """
    return getattr(self.getPortal(), 'counter_date_module', None)


  def getCounterModule(self):
    """
    Return the Counter Date Module
    """
    return getattr(self.getPortal(), 'counter_module', None)


  def stepTic(self, **kwd):
    """
    The is used to simulate the zope_tic_loop script
    Each time this method is called, it simulates a call to tic
    which invoke activities in the Activity Tool
    """
    # execute transaction
    get_transaction().commit()
    self.tic()


  def createCurrency(self, id='EUR', title='Euro'):
    # create the currency document for euro inside the currency module
    return self.currency_module.newContent(id=id, title=title)


  def createBanknotesAndCoins(self):
    """
    Create some banknotes and coins
    """
    # Define static values (only use prime numbers to prevent confusions like 2 * 6 == 3 * 4)
    # variation list is the list of years for banknotes and coins
    self.variation_list = ('variation/1992', 'variation/2003')
    # quantity of banknotes of 10000 :
    self.quantity_10000 = {}
    # 2 banknotes of 10000 for the year 1992
    self.quantity_10000[self.variation_list[0]] = 2
    # 3 banknotes of 10000 for the year of 2003
    self.quantity_10000[self.variation_list[1]] = 3

    # quantity of coin of 200
    self.quantity_200 = {}
    # 5 coins of 200 for the year 1992
    self.quantity_200[self.variation_list[0]] = 5
    # 7 coins of 200 for the year 2003
    self.quantity_200[self.variation_list[1]] = 7

    # quantity of banknotes of 5000
    self.quantity_5000 = {}
    # 11 banknotes of 5000 for hte year 1992
    self.quantity_5000[self.variation_list[0]] = 11
    # 13 banknotes of 5000 for the year 2003
    self.quantity_5000[self.variation_list[1]] = 13

    # Now create required category for banknotes and coin
    self.cash_status_base_category = getattr(self.category_tool, 'cash_status')
    # add the category valid in cash_status which define status of banknotes and coin
    self.cash_status_valid = self.cash_status_base_category.newContent(id='valid', portal_type='Category')
    self.cash_status_to_sort = self.cash_status_base_category.newContent(id='to_sort', portal_type='Category')
    self.cash_status_cancelled = self.cash_status_base_category.newContent(id='cancelled', portal_type='Category')
    self.cash_status_not_defined = self.cash_status_base_category.newContent(id='not_defined', portal_type='Category')
    self.cash_status_mutilated = self.cash_status_base_category.newContent(id='mutilated', portal_type='Category')
    self.cash_status_retired = self.cash_status_base_category.newContent(id='retired', portal_type='Category')
    self.cash_status_new_not_emitted = self.cash_status_base_category.newContent(id='new_not_emitted', portal_type='Category')

    self.emission_letter_base_category = getattr(self.category_tool, 'emission_letter')
    # add the category k in emission letter that will be used fo banknotes and coins
    self.emission_letter_p = self.emission_letter_base_category.newContent(id='p', portal_type='Category')
    self.emission_letter_s = self.emission_letter_base_category.newContent(id='s', portal_type='Category')
    self.emission_letter_b = self.emission_letter_base_category.newContent(id='b', portal_type='Category')
    self.emission_letter_not_defined = self.emission_letter_base_category.newContent(id='not_defined', portal_type='Category')

    self.variation_base_category = getattr(self.category_tool, 'variation')
    # add the category 1992 in variation
    self.variation_1992 = self.variation_base_category.newContent(id='1992', portal_type='Category')
    # add the category 2003 in varitation
    self.variation_2003 = self.variation_base_category.newContent(id='2003', portal_type='Category')

    # Create Resources Document (Banknotes & Coins)
    # get the currency cash module
    self.currency_cash_module = self.getCurrencyCashModule()
    # Create Resources Document (Banknotes & Coins)
    self.currency_1 = self.createCurrency()
    # create document for banknote of 10000 euros from years 1992 and 2003
    self.billet_10000 = self.currency_cash_module.newContent(id='billet_10000', portal_type='Banknote', base_price=10000, price_currency_value=self.currency_1, variation_list=('1992', '2003'), quantity_unit_value=self.unit)
    # create document for banknote of 500 euros from years 1992 and 2003
    self.billet_5000 = self.currency_cash_module.newContent(id='billet_5000', portal_type='Banknote', base_price=5000, price_currency_value=self.currency_1, variation_list=('1992', '2003'), quantity_unit_value=self.unit)
    # create document for coin of 200 euros from years 1992 and 2003
    self.piece_200 = self.currency_cash_module.newContent(id='piece_200', portal_type='Coin', base_price=200, price_currency_value=self.currency_1, variation_list=('1992', '2003'), quantity_unit_value=self.unit)
    # create document for banknote of 200 euros from years 1992 and 2003
    self.billet_200 = self.currency_cash_module.newContent(id='billet_200', portal_type='Banknote', base_price=200, price_currency_value=self.currency_1, variation_list=('1992', '2003'), quantity_unit_value=self.unit)

  def createFunctionGroupSiteCategory(self):
    """
    Create site group function category that can be used for security
    """
    # add category unit in quantity_unit which is the unit that will be used for banknotes and coins
    self.variation_base_category = getattr(self.category_tool, 'quantity_unit')
    self.unit = self.variation_base_category.newContent(id='unit', title='Unit')

    # get the base category function
    self.function_base_category = getattr(self.category_tool, 'function')
    # add category banking in function which will hold all functions neccessary in a bank (at least for this unit test)
    self.banking = self.function_base_category.newContent(id='banking', portal_type='Category', codification='BNK')
    self.caissier_principal = self.banking.newContent(id='caissier_principal', portal_type='Category', codification='CCP')
    self.controleur_caisse = self.banking.newContent(id='controleur_caisse', portal_type='Category', codification='CCT')
    self.void_function = self.banking.newContent(id='void_function', portal_type='Category', codification='VOID')
    self.gestionnaire_caisse_courante = self.banking.newContent(id='gestionnaire_caisse_courante', portal_type='Category', codification='CCO')
    self.gestionnaire_caveau = self.banking.newContent(id='gestionnaire_caveau', portal_type='Category', codification='CCV')
    self.caissier_particulier = self.banking.newContent(id='caissier_particulier', portal_type='Category', codification='CGU')
    self.controleur_caisse_courante = self.banking.newContent(id='controleur_caisse_courante', portal_type='Category', codification='CCC')
    self.controleur_caveau = self.banking.newContent(id='controleur_caveau', portal_type='Category', codification='CCA')
    self.comptable = self.banking.newContent(id='comptable', portal_type='Category', codification='FXF')
    self.chef_section = self.banking.newContent(id='chef_section_comptable', portal_type='Category', codification='FXS')
    self.chef_comptable = self.banking.newContent(id='chef_comptable', portal_type='Category', codification='CCB')
    self.chef_de_tri = self.banking.newContent(id='chef_de_tri', portal_type='Category', codification='CTR')

    # get the base category group
    self.group_base_category = getattr(self.category_tool, 'group')
    # add the group baobab in the group category
    self.baobab = self.group_base_category.newContent(id='baobab', portal_type='Category', codification='BAOBAB')

    # get the base category site
    self.site_base_category = getattr(self.category_tool, 'site')
    # add the category testsite in the category site which hold vaults situated in the bank
    self.testsite = self.site_base_category.newContent(id='testsite', portal_type='Category')
    self.paris = self.testsite.newContent(id='paris', portal_type='Category', codification='P1',  vault_type='site')
    self.madrid = self.testsite.newContent(id='madrid', portal_type='Category', codification='S1',  vault_type='site')

    for c in self.testsite.getCategoryChildValueList():
      # create bank structure for each agency
      site = c.getId()
      # surface
      surface = c.newContent(id='surface', portal_type='Category', codification='',  vault_type='site/surface')
      caisse_courante = surface.newContent(id='caisse_courante', portal_type='Category', codification='',  vault_type='site/surface/caisse_courante')
      caisse_courante.newContent(id='encaisse_des_billets_et_monnaies', portal_type='Category', codification='',  vault_type='site/surface/caisse_courante')
      # create counter for surface
      for s in ['banque_interne', 'gros_versement', 'gros_payement']:
        s = surface.newContent(id='%s' %(s,), portal_type='Category', codification='',  vault_type='site/surface/%s' %(s,))
        for ss in ['guichet_1', 'guichet_2', 'guichet_3']:
          ss =  s.newContent(id='%s' %(ss,), portal_type='Category', codification='',  vault_type='site/surface/%s/guichet' %(s.getId(),))
          for sss in ['encaisse_des_billets_et_monnaies',]:
            sss =  ss.newContent(id='%s' %(sss,), portal_type='Category', codification='',  vault_type='site/surface/%s/guichet' %(s.getId(),))
            for ssss in ['entrante', 'sortante']:
              sss.newContent(id='%s' %(ssss,), portal_type='Category', codification='',  vault_type='site/surface/%s/guichet' %(s.getId(),))
      # create sort room
      salle_tri = surface.newContent(id='salle_tri', portal_type='Category', codification='',  vault_type='site/surface/salle_tri')
      for ss in ['encaisse_des_billets_et_monnaies', 'encaisse_des_billets_recus_pour_ventilation']:
        ss =  salle_tri.newContent(id='%s' %(ss,), portal_type='Category', codification='',  vault_type='site/surface/salle_tri')
        if 'ventilation' in ss.getId():
          for country in ['France', 'Spain']:
            if country[0] != c.getCodification()[0]:
              ss.newContent(id='%s' %(country,), portal_type='Category', codification='',  vault_type='site/caveau/%s' %(s.getId(),))
      # caveau
      caveau =  c.newContent(id='caveau', portal_type='Category', codification='',  vault_type='site/caveau')
      for s in ['auxiliaire', 'reserve', 'externes', 'serre']:
        s = caveau.newContent(id='%s' %(s,), portal_type='Category', codification='',  vault_type='site/caveau/%s' %(s,))
        if s.getId() == 'serre':
          for ss in ['encaisse_des_billets_neufs_non_emis', 'encaisse_des_billets_retires_de_la_circulation','encaisse_des_billets_detruits']:
            ss =  s.newContent(id='%s' %(ss,), portal_type='Category', codification='',  vault_type='site/caveau/%s' %(s.getId(),))
        else:
          for ss in ['encaisse_des_billets_et_monnaies', 'encaisse_des_externes',
                     'encaisse_des_billets_recus_pour_ventilation','encaisse_des_devises']:
            ss =  s.newContent(id='%s' %(ss,), portal_type='Category', codification='',  vault_type='site/caveau/%s' %(s.getId(),))
            if 'ventilation' in ss.getId():
              for country in ['France', 'Spain']:
                if country[0] != c.getCodification()[0]:
                  ss.newContent(id='%s' %(country,), portal_type='Category', codification='',  vault_type='site/caveau/%s' %(s.getId(),))
            #if ss.getId()=='encaisse_des_devises':
            #  for
          if s.getId() == 'auxiliaire':
            for ss in ['encaisse_des_billets_a_ventiler_et_a_detruire', 'encaisse_des_billets_ventiles_et_detruits']:
              s.newContent(id='%s' %(ss,), portal_type='Category', codification='',  vault_type='site/caveau/%s' %(s.getId(),))


  def openCounterDate(self, date=None, site=None):
    """
    open a couter date fort the given date
    by default use the current date
    """
    if date is None:
      date = DateTime().Date()
    if site is None:
      site = self.testsite
    # create a counter date
    self.counter_date_module = self.getCounterDateModule()
    self.counter_date = self.counter_date_module.newContent(id='counter_date_1', portal_type="Counter Date",
                                                            site_value = site,
                                                            start_date = date)
    # open the counter date
    self.counter_date.open()


  def openCounter(self, site=None):
    """
    open a counter for the givent site
    """
    # create a counter
    self.counter_module = self.getCounterModule()
    self.counter = self.counter_module.newContent(id='counter_1', site_value=site)
    # open it
    self.counter.open()


  def initDefaultVariable(self):
    """
    init some default variable use in all test
    """
    # the erp5 site
    self.portal = self.getPortal()
    # the person module
    self.person_module = self.getPersonModule()
    # the organisation module
    self.organisation_module = self.getOrganisationModule()
    # the category tool
    self.category_tool = self.getCategoryTool()
    # the workflow tool
    self.workflow_tool = self.getWorkflowTool()
    # nb use for bank account inventory
    self.account_inventory_number = 0
    # the cash inventory module
    self.cash_inventory_module = self.getCashInventoryModule()
    # the bank inventory module
    self.bank_account_inventory_module = self.getBankAccountInventoryModule()
    # simulation tool
    self.simulation_tool = self.getSimulationTool()
    # get the currency module
    self.currency_module = self.getCurrencyModule()



  def createPerson(self, id, first_name, last_name):
    """
    Create a person
    """
    return self.person_module.newContent(id = id,
                                         portal_type = 'Person',
                                         first_name = first_name,
                                         last_name = last_name)


  def createBankAccount(self, person, account_id, currency, amount):
    """
    Create and initialize a bank account for a person
    """
    bank_account = person.newContent(id = account_id,
                                          portal_type = 'Bank Account',
                                          price_currency_value = currency)
    # validate this bank account for payment
    bank_account.validate()
    if amount == 0:
      return bank_account
    # we need to put some money on this bank account
    if not hasattr(self, 'bank_account_inventory'):
      self.bank_account_inventory = self.bank_account_inventory_module.newContent(id='account_inventory',
                                                                                portal_type='Bank Account Inventory',
                                                                                source=None,
                                                                                destination_value=self.testsite,
                                                                                stop_date=DateTime().Date())

    account_inventory_line_id = 'account_inventory_line_%s' %(self.account_inventory_number,)
    inventory = self.bank_account_inventory.newContent(id=account_inventory_line_id,
                                           portal_type='Bank Account Inventory Line',
                                           resource_value=currency,
                                           destination_payment_value=bank_account,
                                           inventory=amount)

    # deliver the inventory
    inventory.deliver()
    self.account_inventory_number += 1
    return bank_account


  def createCheckbook(self, id, vault, bank_account, min, max, date=None):
    """
    Create a checkbook for the given bank account
    """
    if date is None:
      date = DateTime().Date()
    return self.checkbook_module.newContent(id = id,
                                            portal_type = 'Checkbook',
                                            destination_value = vault,
                                            destination_payment_value = bank_account,
                                            reference_range_min = min,
                                            reference_range_max = max,
                                            start_date = date)


  def createCheck(self, id, reference, checkbook):
    """
    Create Check in a checkbook
    """
    check = checkbook.newContent(id=id,
                                 portal_type = 'Check',
                                 reference=reference
                                )

    # mark the check as issued
    check.confirm()
    return check


  def createCashContainer(self, document, container_portal_type, global_dict, line_list, delivery_line_type='Cash Delivery Line'):
    """
    Create a cash container
    global_dict has keys :
      emission_letter, variation, cash_status, resource
    line_list is a list od dict with keys:
      reference, range_start, range_stop, quantity, aggregate
    """
    # Container Creation
    base_list=('emission_letter', 'variation', 'cash_status')
    category_list =  ('emission_letter/'+global_dict['emission_letter'], 'variation/'+global_dict['variation'], 'cash_status/'+global_dict['cash_status'] )
    resource_total_quantity = 0
    # create cash container
    for line_dict in line_list:
      movement_container = document.newContent(portal_type          = container_portal_type
                                               , reindex_object     = 1
                                               , reference                 = line_dict['reference']
                                               , cash_number_range_start   = line_dict['range_start']
                                               , cash_number_range_stop    = line_dict['range_stop']
                                               )
      if line_dict.has_key('aggregate'):
        movement_container.setAggregateValueList([line_dict['aggregate'],])
      # create a cash container line
      container_line = movement_container.newContent(portal_type      = 'Container Line'
                                                     , reindex_object = 1
                                                     , resource_value = global_dict['resource']
                                                     , quantity       = line_dict['quantity']
                                                     )
      container_line.setResourceValue(global_dict['resource'])
      container_line.setVariationCategoryList(category_list)
      container_line.updateCellRange(script_id='CashDetail_asCellRange',base_id="movement")
      for key in container_line.getCellKeyList(base_id='movement'):
        if isSameSet(key,category_list):
          cell = container_line.newCell(*key)
          cell.setCategoryList(category_list)
          cell.setQuantity(line_dict['quantity'])
          cell.setMappedValuePropertyList(['quantity','price'])
          cell.setMembershipCriterionBaseCategoryList(base_list)
          cell.setMembershipCriterionCategoryList(category_list)
          cell.edit(force_update = 1,
                    price = container_line.getResourceValue().getBasePrice())


      resource_total_quantity += line_dict['quantity']
    # create cash delivery movement
    movement_line = document.newContent(id               = "movement"
                                        , portal_type    = delivery_line_type
                                        , resource_value = global_dict['resource']
                                        , quantity_unit_value = self.getCategoryTool().quantity_unit.unit
                                        )
    movement_line.setVariationBaseCategoryList(base_list)
    movement_line.setVariationCategoryList(category_list)
    movement_line.updateCellRange(script_id="CashDetail_asCellRange", base_id="movement")
    for key in movement_line.getCellKeyList(base_id='movement'):
      if isSameSet(key,category_list):
        cell = movement_line.newCell(*key)
        cell.setCategoryList(category_list)
        cell.setQuantity(resource_total_quantity)
        cell.setMappedValuePropertyList(['quantity','price'])
        cell.setMembershipCriterionBaseCategoryList(base_list)
        cell.setMembershipCriterionCategoryList(category_list)
        cell.edit(force_update = 1,
                  price = movement_line.getResourceValue().getBasePrice())


  def createCashInventory(self, source, destination, currency, line_list=[]):
    """
    Create a cash inventory group
    """
    # we need to have a unique inventory group id by destination
    inventory_group_id = 'inventory_group_%s_%s' % \
                         (destination.getParentValue().getUid(),destination.getId())
    if not hasattr(self, inventory_group_id):
      inventory_group =  self.cash_inventory_module.newContent(id=inventory_group_id,
                                                               portal_type='Cash Inventory Group',
                                                               source=None,
                                                               destination_value=destination)
      setattr(self, inventory_group_id, inventory_group)
    else:
      inventory_group = getattr(self, inventory_group_id)

    # get/create the inventory based on currency
    inventory_id = '%s_inventory_%s' %(inventory_group_id,currency.getId())
    if not hasattr(self, inventory_id):
      inventory = inventory_group.newContent(id=inventory_id,
                                             portal_type='Cash Inventory',
                                             price_currency_value=currency)
      setattr(self, inventory_id, inventory)
    else:
      inventory = getattr(self, inventory_id)

    # line data are given by a list of dict, dicts must have this key :
    # id :  line id
    # resource : banknote or coin
    # variation_id : list of variation id
    # variation_value : list of variation value (must be in the same order as variation_id
    # quantity
    for line in line_list:
      self.addCashLineToDelivery(inventory,
                                 line['id'],
                                 "Cash Inventory Line",
                                 line['resource'],
                                 line['variation_id'],
                                 line['variation_value'],
                                 line['quantity'],)
    # deliver the inventory
    inventory.deliver()
    return inventory_group


  def addCashLineToDelivery(self, delivery_object, line_id, line_portal_type, resource_object,
          variation_base_category_list, variation_category_list, resource_quantity_dict):
    """
    Add a cash line to a delivery
     """
    base_id = 'movement'
    line_kwd = {'base_id':base_id}
    # create the cash line
    line = delivery_object.newContent( id                  = line_id
                                     , portal_type         = line_portal_type
                                     , resource_value      = resource_object # banknote or coin
                                     , quantity_unit_value = self.unit
                                     )
    # set base category list on line
    line.setVariationBaseCategoryList(variation_base_category_list)
    # set category list line
    line.setVariationCategoryList(variation_category_list)
    line.updateCellRange(script_id='CashDetail_asCellRange', base_id=base_id)
    cell_range_key_list = line.getCellRangeKeyList(base_id=base_id)
    if cell_range_key_list <> [[None, None]] :
      for k in cell_range_key_list:
        category_list = filter(lambda k_item: k_item is not None, k)
        c = line.newCell(*k, **line_kwd)
        mapped_value_list = ['price', 'quantity']
        c.edit( membership_criterion_category_list = category_list
              , mapped_value_property_list         = mapped_value_list
              , category_list                      = category_list
              , force_update                       = 1
              )
    # set quantity on cell to define quantity of bank notes / coins
    for variation in self.variation_list:
      v1, v2 = variation_category_list[:2]
      cell = line.getCell(v1, variation, v2)
      if cell is not None:
        cell.setQuantity(resource_quantity_dict[variation])


  def checkResourceCreated(self):
    """
    Check that all have been create after setup
    """
    # check that Categories were created
    self.assertEqual(self.paris.getPortalType(), 'Category')

    # check that Resources were created
    # check portal type of billet_10000
    self.assertEqual(self.billet_10000.getPortalType(), 'Banknote')
    # check value of billet_10000
    self.assertEqual(self.billet_10000.getBasePrice(), 10000)
    # check currency value  of billet_10000
    self.assertEqual(self.billet_10000.getPriceCurrency(), 'currency_module/EUR')
    # check years  of billet_10000
    self.assertEqual(self.billet_10000.getVariationList(), ['1992', '2003'])

    # check portal type of billet_5000
    self.assertEqual(self.billet_5000.getPortalType(), 'Banknote')
    # check value of billet_5000
    self.assertEqual(self.billet_5000.getBasePrice(), 5000)
    # check currency value  of billet_5000
    self.assertEqual(self.billet_5000.getPriceCurrency(), 'currency_module/EUR')
    # check years  of billet_5000
    self.assertEqual(self.billet_5000.getVariationList(), ['1992', '2003'])

    # check portal type of billet_200
    self.assertEqual(self.billet_200.getPortalType(), 'Banknote')
    # check value of billet_200
    self.assertEqual(self.billet_200.getBasePrice(), 200)
    # check currency value  of billet_200
    self.assertEqual(self.billet_200.getPriceCurrency(), 'currency_module/EUR')
    # check years  of billet_200
    self.assertEqual(self.billet_200.getVariationList(), ['1992', '2003'])
