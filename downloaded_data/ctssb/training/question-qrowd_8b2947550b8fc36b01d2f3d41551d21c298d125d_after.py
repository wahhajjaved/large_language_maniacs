from peewee import *

db = SqliteDatabase(None)

class Citizen(Model):
    citizen_id = CharField(primary_key=True)
    collection_mode = CharField() #CONTINUOUS or ON-OFF
    question_preference = CharField(null=True) #SEGMENT or POINTS

    class Meta:
        database = db

class MultiModalTrip(Model):
    multimodaltrip_id = IntegerField(primary_key=True)

    class Meta:
        database = db

class Trip(Model):
    trip_id = IntegerField(primary_key=True)
    citizen_id = ForeignKeyField(Citizen, backref = 'trips')
    start_coordinate = CharField()
    start_address = CharField()
    stop_coordinate = CharField()
    stop_address = CharField()
    start_timestamp = DateTimeField()
    stop_timestamp = DateTimeField()
    transportation_mode = CharField(null=True)
    segment_confidence = FloatField(null=True)
    transportation_confidence = FloatField(null=True)
    path = TextField(null=True)
    multimodal_trip_id = ForeignKeyField(MultiModalTrip,backref= 'trips', null=True)

    class Meta:
        database = db


class Stop_answer(Model):
    stop_answer_id = IntegerField(primary_key=True)
    label_machine = CharField()
    label_en = CharField()
    label_it = CharField()

    @classmethod
    def get_machine_label(cls,human_label):
        #TODO: Make indepdendent of number of labels
        result = cls.select().where((cls.label_en == human_label) | cls.label_it == human_label)
        return result


    class Meta:
        database = db

class Question(Model):
    question_id = AutoField(primary_key=True)
    citizen_id = ForeignKeyField(Citizen, backref = 'questions')
    task_id = CharField()
    trip_id = ForeignKeyField(Trip, backref='questions')
    #All the JSON
    question_json = TextField()
    mode_answer = CharField(null=True)
    start_answer = CharField(null=True)
    stop_answer = ForeignKeyField(Stop_answer,backref='stop-answers',null=True)
    #stop_answer = CharField(null=True)
    question_type = CharField(null=True)

    class Meta:
        database = db

class Message(Model):
    message_id = AutoField(primary_key=True)
    citizen_id = ForeignKeyField(Citizen, backref = 'messages')
    message_json = TextField()
    message_type = CharField() #[COLLECTFAIL,MACHINEFAIL]
    answer = CharField(null=True) # [NOTUSE,NOTCONNECT,ERROR,NOTRIP,TRIPMADE]

    class Meta:
        database = db

class Transport_mode(Model):
    transport_mode_id = IntegerField(primary_key=True)
    label_en = CharField()
    label_it = CharField()

    class Meta:
        database = db

def initialize(dbname):
    db.init(dbname)
    db.connect()
    db.create_tables([Citizen,Trip,Question,Message,MultiModalTrip,Stop_answer,Transport_mode])
    db.close()

def main():
    db.init('pilot2.sqlite')
    db.connect()
    db.create_tables([Citizen,Trip,Question,Message,Stop_answer,Transport_mode])
    db.close()


if __name__ == "__main__": main()
