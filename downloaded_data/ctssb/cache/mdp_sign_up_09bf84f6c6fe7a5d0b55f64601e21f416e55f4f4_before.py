from flask import Flask, request, render_template, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from views.forms import SignUp, SignIn
from flask_bootstrap import Bootstrap
from datetime import datetime
from sqlalchemy_utils import PhoneNumberType

app  = Flask(__name__)
app.config.from_object('config')
#app.config.from_pyfile('config.py')
db = SQLAlchemy(app)
app.jinja_env.add_extension('pyjade.ext.jinja.PyJadeExtension')
Bootstrap(app)

class SignInRecord(db.Model):
    __tablename__ = 'sign_in'
    id = db.Column(db.Integer, primary_key=True)
    event = db.Column(db.Text)
    first_name = db.Column(db.Text)
    last_name = db.Column(db.Text)
    phone_number = db.Column(PhoneNumberType())
    email = db.Column(db.String(100))
    sign_in_time = db.Column(db.DateTime)

    def __init__(self, event, first_name, last_name, phone_number, email, sign_in_time):
        self.event = event
        self.first_name = first_name
        self.last_name = last_name
        self.phone_number = phone_number
        self.email = email
        self.sign_in_time = sign_in_time

    def __repr__(self):
        return "{'first_name': '%s', 'last_name': '%s', 'email': '%s'}" %(self.first_name, self.last_name, self.email)

class SignUpRecord(db.Model):
    __tablename__ = 'sign_up'
    id = db.Column(db.Integer, primary_key=True)
    event = db.Column(db.Text)
    first_name = db.Column(db.Text)
    last_name = db.Column(db.Text)
    phone_number = db.Column(PhoneNumberType())
    email = db.Column(db.String(100))
    address = db.Column(db.Text)
    city = db.Column(db.Text)
    zip_code = db.Column(db.Text)
    receive_emails = db.Column(db.Boolean)
    receive_texts = db.Column(db.Boolean)
    already_signed_up = db.Column(db.Boolean)
    sign_up_time = db.Column(db.DateTime)

    def __init__(self, event, first_name, last_name, phone_number, email, address, city, zip_code, receive_emails, receive_texts, already_signed_up, sign_up_time):
        self.event = event
        self.first_name = first_name
        self.last_name = last_name
        self.phone_number = phone_number
        self.email = email
        self.address = address
        self.city = city
        self.zip_code = zip_code
        self.receive_emails = receive_emails
        self.receive_texts = receive_texts
        self.already_signed_up = already_signed_up
        self.sign_up_time = sign_up_time

    def __repr__(self):
        return "{'first_name': '%s', 'last_name': '%s', 'email': '%s'}" %(self.first_name, self.last_name, self.email)

@app.route('/', methods = ['GET', 'POST'])
def home():
    if request.method == 'POST':
        if request.form['submit'] == 'Sign In':
            return redirect(url_for('signin'))
        elif request.form['submit'] == 'Sign Up':
            return redirect(url_for('signup'))
        else:
            flash("Probably an error. Here's the sign-in page")
            return redirect(url_for('signin'))
    else:
        return render_template('/home.jade')

@app.route("/signup", methods=['GET', 'POST'])
def signup():
    signup = SignUp(csrf_enable=False)
    event = session.get('event')
    if signup.validate_on_submit():
        session['event'] = signup.event.data
        time = datetime.now()
        new_sign_in = SignUpRecord(signup.event.data,
                                   signup.first_name.data,
                                   signup.last_name.data,
                                   signup.phone_number.data,
                                   signup.email.data,
                                   signup.address.data,
                                   signup.city.data,
                                   signup.zip_code.data,
                                   signup.receive_emails.data,
                                   signup.receive_texts.data,
                                   False,
                                   time)
        db.session.add(new_sign_in)
        db.session.commit()
        flash('Thank you for signing up!')
        return redirect(url_for('signin'))
    return render_template('/index.jade', response=signup, event = event, title = "Michigan for Revolution Sign-up")

@app.route("/signin", methods=['GET', 'POST'])
def signin():
    signin = SignIn()
    form_data = session.get('form_data')
    if form_data:
        event = form_data['event']
    else:
        event = None
    if signin.validate_on_submit():
        time = datetime.now()
        new_sign_in = SignInRecord(signin.event.data,
                                   signin.first_name.data,
                                   signin.last_name.data,
                                   signin.phone_number.data,
                                   signin.email.data,
                                   time)
        db.session.add(new_sign_in)
        db.session.commit()
        session['form_data'] = {'event': signin.event.data,
                                'first_name': signin.first_name.data,
                                'last_name': signin.last_name.data,
                                'email': signin.email.data
                                }
        records = SignInRecord.query.filter((SignUpRecord.first_name == signin.first_name.data) & (SignUpRecord.last_name == signin.last_name.data) & (SignUpRecord.email == signin.email.data)).all()
        if len(records) > 0:
            flash('Thank you for signing in!')
            return redirect(url_for('signin'))
        else:
            return redirect(url_for('question'))
    return render_template('/index.jade', response=signin, event = event, title = "Michigan for Revolution Sign-in")


@app.route('/question', methods = ['GET', 'POST'])
def question():
    if request.method == 'POST':
        if request.form['submit'] == 'Yes':
            form_data = session.get('form_data', None)
            if form_data:
                time = datetime.now()
                new_sign_up = SignUpRecord(form_data['event'],
                                           form_data['first_name'],
                                           form_data['last_name'],
                                           None,
                                           form_data['email'],
                                           None,
                                           None,
                                           None,
                                           False,
                                           False,
                                           False,
                                           time
                                           )
                db.session.add(new_sign_up)
                db.session.commit()
                flash("We've recorded your membership")
            else:
                flash("Please sign in first")
            return redirect(url_for('signin'))
        elif request.form['submit'] == 'Sign-up':
            flash("Please fill out the form below")
            return redirect(url_for('signup'))
        else:
            flash("Thank you for coming today!")
            return redirect(url_for('signin'))
    else:
        return render_template('/question.jade')
