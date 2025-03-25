import sqlalchemy
import sqlalchemy.orm as orm
import sqlalchemy.ext.declarative as declarative
import util
import csv
import os
import re
import people

Base = declarative.declarative_base()

class District(Base):
    __tablename__ = 'districts'
    id = sqlalchemy.Column('rowid', sqlalchemy.Integer, primary_key=True)
    name = sqlalchemy.Column(sqlalchemy.String)
    state = sqlalchemy.Column(sqlalchemy.String)
    classification = sqlalchemy.Column(sqlalchemy.String)
    household_total = sqlalchemy.Column(sqlalchemy.Integer)
    population_total = sqlalchemy.Column(sqlalchemy.Integer)
    #population_male = sqlalchemy.Column(sqlalchemy.Integer) 
    #population_female =  sqlalchemy.Column(sqlalchemy.Integer) 
    
    def __init__(self, name, state, classification, household_total,
            population_total):
        self.name=name
        self.state=state
        self.classification=classification
        self.household_total=household_total
        self.population_total=population_total

    def __repr__(self):
        return 'District({0}, {1}, {2}, {3}, {4})'.format(self.name, self.state,
                self.classification, self.household_total,
                self.population_total)

class State(Base):
    __tablename__ = 'states'
    id = sqlalchemy.Column('rowid', sqlalchemy.Integer, primary_key=True)
    name = sqlalchemy.Column(sqlalchemy.String)
    abbreviation = sqlalchemy.Column(sqlalchemy.String)
    classification = sqlalchemy.Column(sqlalchemy.String)
    household_total = sqlalchemy.Column(sqlalchemy.Integer)
    population_total = sqlalchemy.Column(sqlalchemy.Integer)
    gsp = sqlalchemy.Column(sqlalchemy.Integer)

    def __init__(self, name, abbreviation, classification, household_total,
            population_total, gsp = 0):
        self.name=name
        self.abbreviation=abbreviation
        self.classification=classification
        self.household_total=household_total
        self.population_total=population_total
        self.gsp=gsp

    def __repr__(self):
        return 'State({0}, {1}, {2}, {3}, {4}, {5})'.format(self.name,
                self.abbreviation, self.classification, self.household_total,
                self.population_total, self.gsp)

    def to_dict(self):
        return {'name': self.name, 'abbreviation': self.abbreviation, 
                'classification': self.classification,
                'household_total': self.household_total,
                'population_total': self.population_total,
                'gsp': self.gsp}

class Mpce(Base):
    __tablename__ = 'mpce'
    id = sqlalchemy.Column('rowid', sqlalchemy.Integer, primary_key = True)
    #urban or rural
    classification = sqlalchemy.Column(sqlalchemy.String)
    #those funky mpce acronyms
    mpce_type = sqlalchemy.Column(sqlalchemy.String)
    state = sqlalchemy.Column(sqlalchemy.String)
    d1 = sqlalchemy.Column(sqlalchemy.Integer)
    d2 = sqlalchemy.Column(sqlalchemy.Integer)
    d3 = sqlalchemy.Column(sqlalchemy.Integer)
    d4 = sqlalchemy.Column(sqlalchemy.Integer)
    d5 = sqlalchemy.Column(sqlalchemy.Integer)
    d6 = sqlalchemy.Column(sqlalchemy.Integer)
    d7 = sqlalchemy.Column(sqlalchemy.Integer)
    d8 = sqlalchemy.Column(sqlalchemy.Integer)
    d9 = sqlalchemy.Column(sqlalchemy.Integer)
    mpce_average = sqlalchemy.Column(sqlalchemy.Integer)
    household_total = sqlalchemy.Column(sqlalchemy.Integer)
    household_sample = sqlalchemy.Column(sqlalchemy.Integer)

    def __init__(self, mpce_type, classification, state, 
            d1, d2, d3, d4, d5, d6, d7, d8, d9,
            mpce_average, household_total, household_sample):
        self.mpce_type = mpce_type
        self.classification = classification
        self.state = state
        self.d1 = d1
        self.d2 = d2
        self.d3 = d3
        self.d4 = d4
        self.d5 = d5
        self.d6 = d6
        self.d7 = d7
        self.d8 = d8
        self.d9 = d9
        self.mpce_average = mpce_average
        self.household_total = household_total
        self.household_sample = household_sample

    def get_d_all(self, add_zero=False):
        d_all = list()
        if add_zero:
            d_all.append(0)
        d_all.append(self.d1)
        d_all.append(self.d2)
        d_all.append(self.d3)
        d_all.append(self.d4)
        d_all.append(self.d5)
        d_all.append(self.d6)
        d_all.append(self.d7)
        d_all.append(self.d8)
        d_all.append(self.d9)
        return d_all

    def __repr__(self):
        return 'MPCE({0}, {1}, {2})'.format(self.mpce_type, 
                self.classification, self.state)

class Person(Base):
    __tablename__ = 'people'
    id = sqlalchemy.Column('rowid', sqlalchemy.Integer, primary_key = True)
    money = sqlalchemy.Column(sqlalchemy.Integer)
    #currently assuming 0-1 ranking for health measures
    #the data type may change laters
    diabetes = sqlalchemy.Column(sqlalchemy.Float)
    cardio = sqlalchemy.Column(sqlalchemy.Float)
    district = sqlalchemy.Column(sqlalchemy.String, index=True)
    state = sqlalchemy.Column(sqlalchemy.String)
    #urban or rural
    classification = sqlalchemy.Column(sqlalchemy.String)

    def __init__(self, money, diabetes, cardio, district, state,
            classification):
        self.money = money
        self.diabetes = diabetes
        self.cardio = cardio
        self.district = district
        self.state = state
        self.classification = classification

    def to_dict(self):
        return {'money': self.money, 
                'diabetes': self.diabetes,
                'cardio': self.cardio,
                'district': self.district,
                'state': self.state,
                'classification': self.classification}

    #missing proper __repr__

class Database(object):

    def __init__(self, db_filename = 'database.sqlite3', import_data=False):
        self.engine, self.session = fetch_session(db_filename)
        self.connection = self.session.connection()
        self.states = list()
        if import_data:
            #Creates tables if they don't exist.
            Base.metadata.create_all(self.engine)
            self._init_mpce()
            self._init_districts()
            self._init_states()
            self._perform_insertions()
            self.session.commit()

    def _perform_insertions(self):
        table = State.__table__
        insert = table.insert()
        for state in self.states:
            self.connection.execute(insert, name = state.name,
                    abbreviation = state.abbreviation, 
                    classification = state.classification, 
                    population_total = state.population_total,
                    household_total = state.household_total,
                    gsp = state.gsp)
            

    def _init_states(self):
        self._wipe_states()
        for i, state_name in enumerate(util.state_names):
            population_urban = self._get_district_population_by_state(
                    state_name, 'urban', District.population_total)
            household_urban = self._get_district_population_by_state(
                    state_name, 'urban', District.household_total)
            population_rural = self._get_district_population_by_state(
                    state_name, 'rural', District.population_total)
            household_rural = self._get_district_population_by_state(
                    state_name, 'rural', District.household_total)
            population_total = population_urban + population_rural
            household_total = household_urban + household_rural
            self._add_state(state_name, util.state_abbreviations[i], 'urban',
                    population_urban, household_urban)
            self._add_state(state_name, util.state_abbreviations[i], 'rural',
                    population_rural, household_rural)
            self._add_state(state_name, util.state_abbreviations[i], 'total',
                    population_total, household_total)
        data_directory = 'data/'
        with open(data_directory+'gsp.csv') as gsp_file:
            self._import_gsp_file(gsp_file)

    def _get_district_population_by_state(self, state_name, classification, population_type):
        query = self.session.query(sqlalchemy.func.sum(population_type)) \
                .filter(District.state == state_name) \
                .filter(District.classification == classification) \
                .group_by(District.state).first()
        return query[0]

    def _wipe_states(self):
        table = State.__table__
        delete = table.delete()
        self.connection.execute(delete)

    def _add_state(self, name, abbreviation, classification,
            population_total, household_total):
        self.states.append(State(name, abbreviation, classification,
            household_total, population_total))

    #import all MPCE data
    #single underscore implies that the method is private
    def _init_mpce(self):
        #wipe the existing MPCE table so we don't have duplicates
        delete = Mpce.__table__.delete()
        self.connection.execute(delete)

        mpce_directory = 'data/mpce/'
        for filename in os.listdir(mpce_directory):
            if filename.endswith('.csv'):
                mpce_type, classification = extract_mpce_info(filename)
                with open(mpce_directory + filename, 'r') as input_file:
                    self._import_mpce_file(input_file, mpce_type,
                            classification)

    def _import_mpce_file(self, input_file, mpce_type, classification):
        #http://www.blog.pythonlibrary.org/2014/02/26/python-101-reading-and-writing-csv-files/
        reader = csv.reader(input_file)
        for row in reader:
            #The first row is just the headers, so we skip it 
            if row[0] == 'state':
                continue
            #remove extra spaces around each element in the row
            row = [value.strip() for value in row]
            #Create a Mpce object - makes things easier to insert
            #This is not a very efficient method, but it works
            mpce = Mpce(mpce_type, classification, *row)
            #add the row to the mpce table
            insert = Mpce.__table__.insert()
            self.connection.execute(insert, mpce.__dict__)

    #todo - NOT FINISHED
    def _init_districts(self):
        #wipe the existing districts table so we don't have duplicates
        delete = District.__table__.delete()
        self.connection.execute(delete)

        district_directory = 'data/districts/'
        for filename in os.listdir(district_directory):
            if filename.endswith('.CSV'):
                state_name = util.clean_state_filename(filename)
                with open(district_directory + filename, 'r') as input_file:
                    self._import_district_file(input_file, state_name)
                """
                with open(district_directory + filename, 'r') as input_file:
                    self._import_mpce_file(input_file, mpce_type,
                            classification)
                """

    def _import_district_file(self, input_file, state_name):
        #http://stackoverflow.com/questions/3122206/how-to-define-column-headers-when-reading-a-csv-file-in-python
        #http://courses.cs.washington.edu/courses/cse140/13wi/csv-parsing.html
        reader = csv.DictReader(input_file)
        headers = reader.next()
        insert = District.__table__.insert()
        for row in reader:
            #we only care about districts
            if row['Level'] == 'STATE': continue
            name = row['Name'].strip()
            classification = row['TRU'].lower()
            households = int(row['No of Households'])
            population = int(row['Total Population Person'])
            district = District(name, state_name, classification, 
                    households, population)
            self.connection.execute(insert, district.__dict__)

    #year_span indicates which year of gdp data we want to add to the database
    def _import_gsp_file(self, input_file, year_span='2012-13'):
        reader = csv.DictReader(input_file)
        headers = reader.next()
        for row in reader:
            #we only care about the GSP (Gross State Product)
            #which is mislabeled as GSDP 
            if not row['Sector'] == 'GSDP (2004-05 Prices)':
                continue
            state_name = util.clean_state_name(row['State Name'])
            gsp = row[year_span]
            #add the gsp information to the relevant State
            for state in self.states:
                if state.name == state_name and state.classification == 'total':
                    state.gsp = gsp

    def get_all_states(self):
        return self.session.query(State).all()

    #The function specifies that it will return a single state, but
    #the database contains three states (urban, rural, and total)
    #Assume that if no other classification is specified, the total
    #for the whole state is desired
    def get_state_by_name(self, name, classification = 'total'):
        return self.session.query(State).filter(State.name == name)\
                .filter(State.classification == classification).first()

    def get_state_by_abbreviation(self, abbreviation):
        return self.session.query(State).filter(
                State.abbreviation == abbreviation).first()

    def get_districts_by_state_name(self, state_name):
        return self.session.query(District).filter(
                District.state == state_name).all()

    def get_districts_by_state(self, state):
        return self.session.query(District).filter(
                District.state == state.name).all()

    def get_district_by_name(self, district_name):
        return self.session.query(District).filter(
                District.name == district_name).first()

    #check whether a district already has population data 
    def exist_people_from_district(self, district_name):
        return bool(self.session.query(Person).filter(
                Person.district == district_name).first())

    #This will take a long time
    def populate_all(self):
        for state in data.session.query(State):
            generate_state_population(data, state)

    def populate_state(self, state, force=False):
        #get only the "total population" entry for each district
        for district in data.session.query(District).filter(
                District.state == state.name).filter(
                District.classification == 'total'):
            populate_district(data, district, state, force)

    #Create a population distribution for the population of a given district
    def populate_district(self, district, state = None, force=False):
        #If the district already has people in it, don't insert more
        # unless forced to
        if self.exist_people_from_district(district.name) and not force:
            return
        #wipe the existing distribution; don't generate double people 
        self._delete_population_district(district)
        if state is None:
            state = self.get_state_by_name(district.state)

        mpce = self.session.query(Mpce).filter_by(state=state.name).first()
        #Bulk insert as per http://docs.sqlalchemy.org/en/rel_0_8/faq.html
        #split into multiple insertion waves due to memory limitations
        insertions_per_wave = 1000000
        #insert the population in waves of 1000000 people 
        for i in xrange(district.population_total/insertions_per_wave):
            self._insert_population_wave(data, state, district, mpce,
                    insertions_per_wave)
            print 'wave inserted'
        #insert the last few people
        self._insert_population_wave(state, district, mpce, district.population_total % insertions_per_wave)
        #commit the changes; otherwise, they will be wasted!
        self.session.commit()
        print 'Population of', district.name, 'inserted'

    def _insert_population_wave(self, state, district, mpce, insertion_count):
        insert = Person.__table__.insert()
        self.engine.execute(insert, 
                [people.generate_person_dict(self, state, district, mpce)
                for j in xrange(insertion_count)])

    def _delete_population_district(self, district):
        table = Person.__table__
        delete = table.delete().where(
                table.c.district == district.name)
        self.connection.execute(delete)
        self.session.commit()

    def get_population_district(self, district_name, limit=None):
        return self.session.query(Person).filter(
                Person.district == district_name).limit(limit).all()

#given a filename, determine classification and mpce_type
#filename is assumed to be of a format like "mmrp_rural.csv" 
#because that's how I named them.
def extract_mpce_info(filename):
    filename = re.sub('.csv', '', filename)
    filename_split = filename.split('_')
    mpce_type = filename_split[0]
    classification = filename_split[1]
    return mpce_type, classification

def fetch_session(db_filename):
    engine = sqlalchemy.create_engine('sqlite:///{0}'.format(db_filename))
    session = orm.sessionmaker(bind=engine)
    return engine, orm.scoped_session(session)

def demonstrate_queries(data):
    mizoram = data.get_state_by_name('Mizoram')
    karnataka = data.get_state_by_abbreviation('KA')

    print mizoram
    print karnataka

    mizoram_districts = data.get_districts_by_state_name('Mizoram')
    same_mizoram_districts = data.get_districts_by_state_name(mizoram.name)
    also_same_mizoram_districts = data.get_districts_by_state(mizoram)
    
    print mizoram_districts
    print mizoram_districts == also_same_mizoram_districts

    #for state in data.get_all_states():
    #    print state.to_dict()

if __name__ == '__main__':
    data = Database()
    print data.session.query(Mpce).filter(Mpce.state=='Andhra Pradesh').limit(10).all()
