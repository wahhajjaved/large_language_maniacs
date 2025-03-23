import csv
import requests
import json
import logging
import os
from datetime import date, datetime, time, timedelta
from dateutil.relativedelta import relativedelta
from urllib import urlencode

from django.contrib.auth.models import Group
from django.conf import settings  # for access to MEDIA_ROOT
from django.contrib import messages
from django_countries import countries
from django.db.models.signals import pre_save
from django.dispatch import receiver

from accounts.models import Trainee, TrainingAssistant, User, UserMeta
from aputils.models import Address, City, Vehicle
from houses.models import House
from localities.models import Locality
from teams.models import Team
from terms.models import Term
from schedules.models import Schedule

from aputils.trainee_utils import is_trainee

log = logging.getLogger("apimport")
MONDAY, SATURDAY, SUNDAY = (0, 5, 6)
TERM_LENGTH_MINUS_SEMIANNUAL = 20 - 1


def date_for_day_of_week(date, day):
  """ returns the date of the specified day in the week identified by date.
    For example, if date 4/9/2016 (Saturday) and 0 (Monday) are passed in,
    4/4/2016 will be returned. """
  return date + relativedelta(days=day - date.weekday())


def term_seed_date_from_semiannual(season, year):
  if season == "Winter":
    seed_date = date(year, 12, 25)
  else:
    seed_date = date(year, 7, 4)
  # Because Monday == 0, if these are on Sunday, we incorrectly get the previous week, so adjust
  if seed_date.weekday() == SUNDAY:
    seed_date += relativedelta(days=1)
  seed_date = date_for_day_of_week(seed_date, MONDAY)
  return seed_date


def term_start_date_from_semiannual(season, year):
  """ This returns the best-guess term start date for the given semi-annual.
    Input should follow the form of ("Winter"/"Summer", year) """
  seed_date = term_seed_date_from_semiannual(season, year)
  # return date of 19 weeks previous-- one week for semi-annual
  return datetime.combine(seed_date + timedelta(weeks=-19, days=0), time(0, 0))

def term_end_date_from_semiannual(season, year):
  """ This returns the best-guess term start date for the given semi-annual.
    Input should follow the form of ("Winter"/"Summer", year) """
  start_date = term_start_date_from_semiannual(season, year)
  # returns date 6 days after semi-annual starts
  return start_date + timedelta(weeks=19, days=5)


def next_term_start_date(date):
  """ returns the next possible start term date (best guess)"""

  # Not really worth it to be smart here--just start in Spring of this year and keep
  # going until we have a workable date.
  season = "Summer"
  year = date.year

  while True:
    start_date = term_start_date_from_semiannual(season, year)

    # give a week lee-way in case we guessed the wrong semi-annual week
    if (start_date + timedelta(7)) > date:
      return start_date

    # increment semiannual
    if season == "Summer":
      season = "Winter"
    else:
      season = "Summer"
      year = year + 1


def previous_term():
  current_term = Term.current_term()
  if current_term is not None:
    return current_term.season, current_term.year
  return None, None


def generate_term():
  season, year = previous_term()

  if season == "Fall":
    season = "Spring"
    year = year + 1
  elif season == "Spring":
    season = "Fall"
  else:
    # No term found, use today's date to identify what term we are hoping to create
    today = datetime.now().date()
    start_date = next_term_start_date(today)
    if start_date.month <= 4:  # month chosen semi-arbitrarily
      return "Spring", start_date.year
    else:
      return "Fall", start_date.year
  return (season, year)


def deactivate_user(user):
  if is_trainee(user):
    # There might be other things we need to deactivate as well.  Our other option here
    # is to, in all of these places, also filter on active=True.  There's at least
    # one place already that doesn't do this, though.
    user.is_active = False
    user.team = None
    user.house = None
    user.save()


def deactivate_previous_term():
  # Mark all trainees as inactive
  # TODO (import2): Probably should consider doing this only on trainees related to the
  # current term.  Though I kind of prefer doing this on all trainees, so we can start
  # every term in a very clean state.
  for u in User.objects.all():
    deactivate_user(u)

    # TODO(import2): are there permissions that we care to deactivate here?  Team
    # monitors maybe?  HCs should be taken care of on a trainee by trainee basis
    # as they are reactivated.


def create_term(season, year, start_date, end_date):
  """ Creates a new term after deactivating the previous term.  This function
    DOES NOT CHECK to see if the data you're passing in is good or not.
    MAKE THE PROPER CHECKS FIRST."""

  deactivate_previous_term()

  try:
    term = Term.objects.get(season=season, year=year)
    term.start = start_date
    term.end = end_date
    term.save()
  except Term.DoesNotExist:
    term = Term(current=currently_in_term(start_date, end_date), season=season, year=year, start=start_date, end=end_date)
    term.save()

  Term.set_current_term(term)


def currently_in_term(term_start, term_end):
  today = datetime.today()
  return today >= term_start and today <= term_end


def mid_term():
  """ Returns true if we are still in the current term or if the current term hasn't yet
    started yet """
  term = Term.current_term()
  if term:
    return term.currently_in_term()
  else:
    return False


def validate_term(start, end, c_init, c_grace, c_periods, c_totalweeks, request):
  """ Validates the provided information.  Returns true/false based
      on the validity of the data """
  is_success = True

  # Start needs to be a Monday and end needs to be a Sunday
  if start.weekday() != 0:
    messages.add_message(request, messages.ERROR,
                         'Term start date needs to be a Monday.')
    log.error("Start date, " + str(start) + ", is not a Monday.")
    is_success = False

  if end.weekday() != 6:
    messages.add_message(request, messages.ERROR,
                         'Term end date needs to be a Lord\'s Day.')
    log.error("End date, " + str(end) + ", is not a Lord's Day.")
    is_success = False

  if (end - start).days != (7 * c_totalweeks - 1):
    messages.add_message(request, messages.ERROR,
                         'Term length does not match requested number of weeks (' + str(c_totalweeks) + ').')
    log.error("Term length as defined by start date, " + start + ", and end date, " + end + ", is not " + str(c_totalweeks) + "weeks.")
    is_success = False

  if (int(c_init) + int(c_grace) + int(c_periods) * 2) != c_totalweeks:
    messages.add_message(request, messages.ERROR,
                         'Total number of weeks incorrect.  Total number of weeks should be: ' + str(c_totalweeks) + '.')
    log.error("The sum of the number of initial weeks--" + str(c_init) + ", grace weeks--" + str(c_grace) + ", and period weeks--2 * " + str(c_periods) + "--does not total to " + str(c_totalweeks) + " weeks.")
    is_success = False

  # Is the current term finished yet?
  if mid_term():
    messages.add_message(request, messages.ERROR,
                         'Cannot start a new term before previous term has ended!')
    log.error("Attempt to start a new term before the previous term had ended.")
    is_success = False

  return is_success


def save_file(f, path):
  """ Saves file with the same filename at the given path relative to the media folder """
  file_path = os.path.join(settings.MEDIA_ROOT, path)
  full_path = os.path.join(file_path, f.name)

  dir = os.path.dirname(full_path)
  if not os.path.isdir(dir):
    os.makedirs(dir)

  with open(full_path, 'wb+') as destination:
    for chunk in f.chunks():
      destination.write(chunk)

  return full_path


def check_sending_locality(locality):
  return Locality.objects.filter(city__name=locality).exists()


def check_team(team):
  return Team.objects.filter(code=team).exists()


def check_residence(residence):
  if residence == 'COMMUTER':
    return True
  else:
    return House.objects.filter(name=residence).exists()


def check_office_id(id):
  # TODO: Eventually, we probably want to sanity check that the first name hasn't changed.
  # Perhaps other fields also need to be checked.
  pass


def save_locality(city_name, state_id, country_code):
  if country_code == 'US' and state_id:
    state = state_id
  else:
    state = None

  city, created = City.objects.get_or_create(name=city_name, state=state, country=country_code)
  if created:
    log.info("Created city " + str(city) + ".")

  locality, created = Locality.objects.get_or_create(city=city)
  if created:
    log.info("Created locality for " + str(city) + ".")


def save_team(name, code, type, locality):
  team, created = Team.objects.get_or_create(name=name, code=code, locality_id=locality, type=type)
  if created:
    locality_obj = Locality.objects.get(id=locality)
    log.info("Created team with name=" + name + ", code=" + code + ", locality=" + locality_obj.city.name + ", and type=" + type + ".")


def save_residence(name, gender, address, city, zip):
    address_obj, created = Address.objects.get_or_create(address1=address, city_id=city, zip_code=zip)
    if created:
        log.info("Created address: " + str(address_obj) + ".")

    house, created = House.objects.get_or_create(name=name, address=address_obj, gender=gender)
    if created:
        log.info("Created house with name=" + name + ", gender=" + gender +
                 ", and at address " + str(address_obj) + ".")


def check_csvfile(file_path):
  """ Does the necessary verification of the csvfile, returns lists of potentially new
      objects that require further processing before the csv file can be imported """

  log.debug("Checking CSV File.")

  fake = False

  # new entries
  localities = []
  locality_states = []
  locality_countries = []
  teams = []
  residences = []
  with open(file_path, 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
      # is this an empty row?
      if not row['stName']:
        continue

      # TODO (import2): we need to think about what happens when multiple sending
      # localities share a city name.  Potential upcoming one: Vancouver, WA versus
      # Vancouver, BC
      if (not check_sending_locality(row['sendingLocality'])) and (row['sendingLocality'] not in localities):
        city_norm, state_norm, country_norm = normalize_city(row['sendingLocality'], row['state'], row['country'])

        if fake:
          save_locality(city_norm, state_norm, country_norm)
        else:
          # TODO(import2): Is a check on the normalized values enough?  Probably since
          # that's what we use anyways.
          if (not check_sending_locality(city_norm)) and (city_norm not in localities):
            localities.append(city_norm)
            locality_states.append("" if state_norm is None else state_norm)
            locality_countries.append("" if country_norm is None else country_norm)

      if row['teamID'] == '':
        row['teamID'] = "NO TEAM"
      if (not check_team(row['teamID'])) and (not row['teamID'] in teams):
        teams.append(row['teamID'])

      if (not check_residence(row['residenceID'])) and (not row['residenceID'] in residences):
        residences.append(row['residenceID'])

  localities_zip = zip(localities, locality_states, locality_countries)

  # Generate some strings for logging
  locality_str = ""
  for locality in localities_zip:
    if locality_str != "":
      locality_str = locality_str + "\n\t"
    else:
      locality_str = locality_str + "\t"
    locality_str = locality_str + locality[0] + ", " + locality[1] + ", " + locality[2]

  if locality_str != "":
    log.info(str(len(localities_zip)) + " new localities found (state and country are guess-data): \n" + locality_str)

  team_str = ""
  for team in teams:
    if team_str != "":
      team_str = team_str + "\n\t"
    else:
      team_str = team_str + "\t"
    team_str = team_str + team

  if team_str != "":
    log.info(str(len(teams)) + " new teams: \n" + team_str)

  residence_str = ""
  for residence in residences:
    if residence_str != "":
      residence_str = residence_str + "\n\t"
    else:
      residence_str = residence_str + "\t"
    residence_str = residence_str + residence

  if residence_str != "":
    log.info(str(len(residences)) + " new residences: \n" + residence_str)
  return localities_zip, teams, residences


def normalize_city(city, state, country):
  addr = city + ", " + state + ", " + country
  # Key used is related to haileyl's github account
  args = {'text': addr, 'api_key': 'search-G5ETZ3Y'}
  url = 'http://search.mapzen.com/v1/search?' + urlencode(args)

  r = requests.get(url)
  r_json = r.json()
  confidence = 0
  best = None
  for item in r_json['features']:
    if item['properties']['confidence'] > confidence:
      best = item['properties']
      confidence = best['confidence']

  if best is None:
    log.warning("Unable to normalize city defined by " + city + ", " + state + ", " + country + ".")
    return city, None, None

  code = best['country_a']
  if len(code) == 3:
    code = countrycode_from_alpha3(code)

  state_code = None
  if code == "US":
    if best['region'] == "Puerto Rico":
      state_code = "PR"
    elif best['region'] == "District of Columbia":
      state_code = "DC"
    elif 'region_a' in best:
      state_code = best['region_a']

  if state_code:
    log.debug("City defined by " + city + ", " + state + ", and " + country + " normalized to " + best['name'] + ", " + state_code + ", " + code + ".")
  else:
    log.debug("City defined by " + city + ", " + state + ", and " + country + " normalized to " + best['name'] + ", " + code + ".")
  return best['name'], state_code, code


def countrycode_from_alpha3(code3):
  """Converts from a three-letter country code to a 2-letter country code if such a
     matching exists.
  """
  for country in countries:
    if countries.alpha3(country[0]) == code3:
      return country[0]

  return None


def import_address(address, city, state, zip, country):
  try:
    address_obj = Address.objects.get(address1=address)
    return address_obj
  except Address.DoesNotExist:
    pass

  city_norm, state_norm, country_norm = normalize_city(city, state, country)

  # TODO (import2): graceful fail if could not find best-->state_norm and country_norm are None
  if city_norm is None or country_norm is None:
    return None

  city_obj, created = City.objects.get_or_create(name=city_norm, state=state_norm, country=country_norm)

  try:
    zip_int = int(zip)
  except ValueError:
    zip_int = None

  address_obj, created = Address.objects.get_or_create(
      address1=address,
      city=city_obj,
      zip_code=zip_int)

  return address_obj


def gospel_code(choice):
  if choice.lower() == "campus":
    return "CP"
  elif choice.lower() == "yp":
    return "YP"
  elif choice.lower() == "children":
    return "CH"
  elif choice.lower() == "community":
    return "CM"
  elif choice.lower() == "i-dcp":
    return "ID"

  return None


def lrhand_code(choice):
  return 'R' if choice == 'right' else 'L'


def import_row(row):
  """ Creates or updates a user based on the given row.  Matches user first by office_id
      and then by email address
  """
  if not row['stName']:
    return

  log.info("Importing row for user " + row['stName'] + " " + row["lastName"] + ".")

  # First create/update user -- Assume Csv is correct, all information gets overriden
  try:
    user = User.objects.get(office_id=row['officeID'])
    log.info("Existing user found by officeID=" + row['officeID'] + ".")

    user.email = row['email']
  except User.DoesNotExist:
    try:
      user = User.objects.get(email=row['email'])
      log.info("Existing user found by email=" + row['email'] + ".")

      user.office_id = row['officeID']
    except User.DoesNotExist:
      user = User(email=row['email'], office_id=row['officeID'])
      log.info("New User created with email=" + row['email'] + " and office_id=" + row['officeID'])

  user.save()

  if row['residenceID'] == 'COMMUTER':
    user.type = 'C'
  else:
    user.type = 'R'

  user.firstname = row.get('stName', user.firstname)
  user.lastname = row.get('lastName', user.lastname)
  user.middlename = row.get('middleName', user.middlename)
  user.nickname = row.get('nickName', user.nickname)

  user.gender = row.get('gender', user.gender)
  user.lrhand = lrhand_code(row.get('LRHand'))  # TODO: This is prone to errors
  if row.get('birthDate') != "":
    user.date_of_birth = datetime.strptime(row.get('birthDate'), "%m/%d/%Y %H:%M").date()
  user.is_active = True

  term = Term.current_term()
  user.terms_attended.add(term)

  user.current_term = int(row['termsCompleted']) + 1

  if user.date_begin is None:
    user.date_begin = term.start
  else:
    user.date_begin = datetime.strptime(row['dateBegin'], "%d-%b-%y").date()
  user.date_end = term.end

  # TA
  ta = TrainingAssistant.objects.filter(firstname=row.get('trainingAssistantID', "")).first()
  if ta:
    user.TA = ta
  else:
    log.warning("Unable to set TA [%s] for trainee: %s %s" % (row['trainingAssistantID'], row['stName'], row['lastName']))

  # Mentor
  if row.get('mentor', "") != "":
    lname, fname = row.get('mentor').split(", ")
    mentor = User.objects.filter(firstname=fname, lastname=lname).first()
    if mentor:
      user.mentor = mentor
    else:
      log.warning("Unable to set mentor [%s] for trainee: %s %s" % (row['mentor'], row['stName'], row['lastName']))

  # TODO: This needs to be done better, once we get more information about localities
  locality = Locality.objects.filter(city__name=row['sendingLocality']).first()
  if locality:
    user.locality.add(locality)
  else:
    # Try to find a city that corresponds
    city = City.objects.filter(name=row['sendingLocality']).first()
    if city:
      locality, created = Locality.objects.get_or_create(city=city)
      user.locality.add(locality)
    else:
      log.warning("Unable to set locality [%s] for trainee: %s %s" % (row['sendingLocality'], row['stName'], row['lastName']))

  if row['teamID'] == "":
    row['teamID'] = "NO TEAM"
  team = Team.objects.filter(code=row['teamID']).first()
  if team:
    user.team = team
  else:
    log.warning("Unable to set team for trainee: %s %s" % (row['teamID'], row['stName'], row['lastName']))

  if row['HouseCoor'] is "1" or row['couples'] is "1":
    hc_group = Group.objects.get(name='HC')
    hc_group.user_set.add(user)

  if row['residenceID'] != 'COMMUTER':
    residence = House.objects.filter(name=row['residenceID']).first()
    if residence:
      user.house = residence
    else:
      log.warning("Unable to set house [%s] for trainee: %s %s" % (row['residenceID'], row['stName'], row['lastName']))

  user.self_attendance = user.current_term > 2
  user.save()

  # META
  try:
    meta = user.meta
  except UserMeta.DoesNotExist:
    meta = UserMeta(user=user)
  meta.phone = row['cellPhone']
  meta.home_phone = row['homePhone']
  meta.work_phone = row['workPhone']

  meta.maidenName = row['maidenName']
  meta.is_married = row['maritalStatus'] in ["Couple", "Married"]
  meta.is_couple = row['couples'] is "1"

  meta.address = import_address(
      row['address'],
      row['city'],
      row['state'],
      row['zip'],
      row['country'])

  meta.college = row['college']
  meta.major = row['major']
  meta.degree = row['degree']

  meta.emergency_name = row['emergencyContact']
  meta.emergency_address = row['emergencyAddress']
  meta.emergency_phone = row['emergencyPhoneNumber']
  meta.emergency_phone2 = row['emergencyPhoneNumber2']

  meta.gospel_pref1 = gospel_code(row['gospelPreference1'])
  meta.gospel_pref2 = gospel_code(row['gospelPreference2'])

  meta.readOT = row['readOldTestament'] is "1"
  meta.readNT = row['readNewTestament'] is "0"

  meta.save()

  if row['vehicleYesNo'] == "No":
    user.vehicles.all().delete()
  else:
    if row['vehicleCapacity'] == "":
      log.warning("Invalid vehicle capacity for trainee: %s %s" % (row['stName'], row['lastName']))
    else:
      Vehicle.objects.get_or_create(
          color=row['vehicleColor'],
          model=row['vehicleModel'],
          license_plate=row['vehicleLicense'],
          capacity=row['vehicleCapacity'],
          user=user)


def import_csvfile(file_path):
  # sanity check
  localities, teams, residences = check_csvfile(file_path)
  if localities or teams or residences:
    return False

  log.info("Beginning CSV File Import")

  # TODO(import2): Remove this
  # count = 0;
  with open(file_path, 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
      # count = count + 1
      # if count > 10:
      #     return
      import_row(row)
  term = Term.current_term()
  schedules = Schedule.objects.filter(term=term)

  # TODO(import2) -- this needs to be smarter eventually
  for schedule in schedules:
      schedule.assign_trainees_to_schedule()

  log.info("Import complete")
  return True


def term_before(term):
  if not term:
    return None

  season = "Spring" if term.season == "Fall" else "Fall"
  year = term.year if term.season == "Fall" else term.year - 1

  try:
    term_minus = Term.objects.get(season=season, year=year)
  except Term.DoesNotExist:
    term_minus = None

  return term_minus


def migrate_schedule(schedule):
  if schedule is None:
    return

  schedule2 = schedule
  schedule2.pk = None
  schedule2.date_created = datetime.now()
  schedule2.is_locked = False
  schedule2.term = Term.current_term()
  schedule2.save()
  schedule2.events.add(*schedule.events.all())
  schedule2.save()
  return schedule2


def migrate_schedules():
  term = Term.current_term()
  term_minus_one = term_before(term)
  term_minus_two = term_before(term_minus_one)

  schedule_set = []

  schedules = Schedule.objects.filter(term=term_minus_one, import_to_next_term=True, season="All")
  schedule_set.extend(schedules)

  schedules = Schedule.objects.filter(term=term_minus_two, import_to_next_term=True, season=term.season)
  schedule_set.extend(schedules)

  for schedule in schedule_set:
    s_new = migrate_schedule(schedule)


@receiver(pre_save, sender=User)
def log_changes(sender, instance, **kwargs):
  try:
    user = sender.objects.get(pk=instance.pk)
  except sender.DoesNotExist:
    log.info("New user being created with email=%s and office_id=%s." % (instance.email, instance.office_id))
  else:
    for field in User._meta.get_fields():
      if hasattr(instance, field.name) and (getattr(user, field.name) != getattr(instance, field.name)):
        # try:
        log.info("%s - %s changed from %s to %s." % (user.full_name, field.name, str(getattr(user, field.name)), str(getattr(instance, field.name))))
        # except TypeError:
        #   log.info("%s - %s changed." % (user.full_name, field.name))
        #   log.warning(field.name + " has no string rendering.")
