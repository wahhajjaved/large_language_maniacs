from flask import render_template, flash, redirect, session, url_for, request, g, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, logout_user, current_user, login_required
from app import app, db, lm
from forms import LoginForm, FeedbackForm
from models import User, Feedback, Applicant
from decorators import role_required
from tempfile import NamedTemporaryFile
from xlwt import Workbook

@app.before_request
def before_request():
  g.user = current_user

@app.route('/home')
@login_required
def index():
  applicants = Applicant.query.all()
  context = {
    'title': 'Home',
    'applicants': applicants
  }
  template = 'index.html'
  if g.user.has_role('staff'):
    template = 'review.html'
  return render_template(template, **context)

@app.route('/alpha')
@login_required
def alpha():
  applicants = Applicant.query.order_by(Applicant.last_name).all()
  context = {
    'title': 'Finalists Sorted by Last Name',
    'applicants': applicants
  }
  template = 'index.html'
  if g.user.has_role('staff'):
    template = 'review.html'
  return render_template(template, **context)

@app.route('/men')
@login_required
def men():
  applicants = Applicant.query.filter_by(title='Mr.').all()
  context = {
    'title': 'Male Finalists',
    'applicants': applicants
  }
  template = 'index.html'
  if g.user.has_role('staff'):
    template = 'review.html'
  return render_template(template, **context)

@app.route('/women')
@login_required
def women():
  applicants = Applicant.query.filter_by(title='Ms.').all()
  context = {
    'title': 'Female Finalists',
    'applicants': applicants
  }
  template = 'index.html'
  if g.user.has_role('staff'):
    template = 'review.html'
  return render_template(template, **context)

@app.route('/texas')
@login_required
def texas():
  applicants = Applicant.query.filter_by(home_state='Texas').all()
  context = {
    'title': 'Finalists from Texas',
    'applicants': applicants
  }
  template = 'index.html'
  if g.user.has_role('staff'):
    template = 'review.html'
  return render_template(template, **context)

@app.route('/least_feedback')
@login_required
def least_feedback():
  applicants = Applicant.query.order_by(Applicant.last_name).all()
  applicants = sorted(applicants, key=lambda x: x.feedback_count)
  context = {
    'title': 'Finalists Sorted by Least Feedback',
    'applicants': applicants
  }
  template = 'index.html'
  if g.user.has_role('staff'):
    template = 'review.html'
  return render_template(template, **context)

@app.route('/most_feedback')
@login_required
def most_feedback():
  applicants = Applicant.query.order_by(Applicant.last_name).all()
  applicants = sorted(applicants, key=lambda x: x.feedback_count,
    reverse=True)
  context = {
    'title': 'Finalists Sorted by Most Feedback',
    'applicants': applicants
  }
  template = 'index.html'
  if g.user.has_role('staff'):
    template = 'review.html'
  return render_template(template, **context)

@app.route('/group1')
@login_required
def group1():
  applicants = Applicant.query.filter_by(group='1').all()
  context = {
    'title': 'Finalists in Group 1',
    'applicants': applicants
  }
  template = 'index.html'
  if g.user.has_role('staff'):
    template = 'review.html'
  return render_template(template, **context)

@app.route('/group2')
@login_required
def group2():
  applicants = Applicant.query.filter_by(group='2').all()
  context = {
    'title': 'Finalists in Group 2',
    'applicants': applicants
  }
  template = 'index.html'
  if g.user.has_role('staff'):
    template = 'review.html'
  return render_template(template, **context)

@app.route('/group3')
@login_required
def group3():
  applicants = Applicant.query.filter_by(group='3').all()
  context = {
    'title': 'Finalists in Group 3',
    'applicants': applicants
  }
  template = 'index.html'
  if g.user.has_role('staff'):
    template = 'review.html'
  return render_template(template, **context)

@app.route('/group4')
@login_required
def group4():
  applicants = Applicant.query.filter_by(group='4').all()
  context = {
    'title': 'Finalists in Group 4',
    'applicants': applicants
  }
  template = 'index.html'
  if g.user.has_role('staff'):
    template = 'review.html'
  return render_template(template, **context)

@app.route('/export')
@login_required
@role_required('staff')
def export():
  applicants = Applicant.query.order_by(Applicant.last_name).all()
  book = Workbook()
  sheet1 = book.add_sheet('Sheet 1')
  sheet1.write(0, 0, 'Finalists')
  sheet1.write(0, 1, 'Freshman-Juniors Average')
  sheet1.write(0, 2, 'Seniors Average')
  sheet1.write(0, 3, 'Alumni Average')
  for i, applicant in enumerate(applicants):
    sheet1.write(i+1, 0, '%s, %s' % (applicant.last_name, applicant.first_name))
    sheet1.write(i+1, 1, applicant.calculate_average('other'))
    sheet1.write(i+1, 2, applicant.calculate_average('senior'))
    sheet1.write(i+1, 3, applicant.calculate_average('alumni'))
  with NamedTemporaryFile() as f:
    book.save(f)
    f.seek(0)
    return send_file(f.name, as_attachment=True, attachment_filename='ratings.xls')

# GET gets information from the server (server -> client)
# POST sends info to the server (client -> server)
@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
  #If the user exists and is logged in, redirect us to the homepage
  #The homepage is the index method
  if g.user is not None and g.user.is_authenticated():
    return redirect(url_for('index'))
  #Initialize the login form
  form = LoginForm()
  #If the request was a POST request (user hit Login) and the fields were valid
  if form.validate_on_submit():
    #Find the user with the email that was specified
    user = User.query.filter_by(email=form.email.data).first()
    #If the email is found in the database, check the password
    if user:
      #If the password is correct, login the user
      if check_password_hash(user.password, form.password.data):
        login_user(user, remember=True)
        #Send them to the index page, or whatever page they were trying to access
        return redirect(request.args.get('next') or url_for('index'))
      flash('Wrong Password')
    else:
      flash('No Email Found')
  return render_template('login.html', title='Sign In', form=form)

@app.route('/logout')
@login_required
def logout():
  logout_user()
  return redirect(url_for('login'))

@app.route('/feedback/<int:applicant_id>', methods=['GET', 'POST'])
@login_required
def applicant(applicant_id):
  feedback = Feedback.query.filter_by(user_id=g.user.id, applicant_id=applicant_id).first()
  if feedback:
    form = FeedbackForm(notes=feedback.notes, feedback=feedback.feedback,
                        rating=feedback.rating)
  else:
    form = FeedbackForm()
  if form.validate_on_submit():
    if not form.notes.data and not form.feedback.data and form.rating.data == 'None':
      if feedback:
        db.session.delete(feedback)
        db.session.commit()
      return redirect(url_for('index'))
    if not feedback:
      feedback = Feedback(user_id=g.user.id, applicant_id=applicant_id)
    
    feedback.notes = form.notes.data
    feedback.feedback = form.feedback.data
    feedback.rating = form.rating.data
    db.session.add(feedback)
    db.session.commit()
    return redirect(url_for('index'))

  applicant = Applicant.query.get(applicant_id)
  context = {
    'title': applicant.name,
    'applicant': applicant,
    'form': form
  }
  return render_template('applicant.html', **context)

@app.route('/admin')
@login_required
def admin():
  #Get all of the users using a query.
  users = User.query.order_by(User.name).all()
  #Send users to template
  return render_template('admin.html', users=users)


@lm.user_loader
def load_user(id):
  return User.query.get(int(id))
