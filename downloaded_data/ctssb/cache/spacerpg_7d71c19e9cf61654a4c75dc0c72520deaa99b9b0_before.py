import os

from flask import Flask, request, session, g, redirect, url_for, abort, render_template, flash
import flask_login
from urllib.parse import urlparse, urljoin
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_admin import Admin

app = Flask(__name__)
app.config.from_object(os.environ['APP_SETTINGS'])
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

bcrypt = Bcrypt(app)
db = SQLAlchemy(app)

admin = Admin(app, name='Deimos 2147')

from models import News,User,Character,Item,NPC,Room,AdminModelView,CustomModelView,Weapon,Armor,RoomModelView,ItemModelView
from login import login_manager
from forms import RegistrationForm,LoginForm,CharacterCreationForm


admin.add_view(CustomModelView(User, db.session))
admin.add_view(AdminModelView(Character, db.session))
admin.add_view(ItemModelView(Item, db.session))
admin.add_view(RoomModelView(Room, db.session))
admin.add_view(AdminModelView(NPC, db.session))
admin.add_view(AdminModelView(Armor, db.session))
admin.add_view(AdminModelView(Weapon, db.session))

INEBRIATION_PER_DRINK = 3

def is_safe_url(target):
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http','https') and ref_url.netloc == test_url.netloc

#Display the room description, image, etc
@app.route('/')
@flask_login.login_required
def index():
    character = flask_login.current_user.character
    if character is None:
        return redirect(url_for('character_profile'))
    if character.opponent:
        return redirect(url_for('attack'))
    current_loc = character.location
    nearest_exits = current_loc.exits + current_loc.linked_rooms

    return render_template('index.html', character=character,nearest_exits=nearest_exits)

@app.route('/register', methods=['POST','GET'])
def register():
    form = RegistrationForm()
    if request.method == 'GET':
        return render_template('register.html', form=form)
    elif request.method == 'POST':
        if form.validate_on_submit():
            if User.query.filter_by(email=form.email.data).first():
                flash('Email address already exists','error')
                return redirect(url_for('register'))
            else:
                user = User(
                        email = form.email.data,
                        password = form.password.data
                        )
                db.session.add(user)
                db.session.commit()
                flash('Registered succesfully!','error')
                flask_login.login_user(user)
                return redirect(url_for('index'))
        else:
            flash('Form failed to validate','error')
            return redirect(url_for('register'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if request.method == 'POST':
        if form.validate_on_submit():
            user = User.query.filter_by(email=form.email.data).first()
            if user is None:
                flash('Email address not found','error')
                return redirect(url_for('login'))
            if bcrypt.check_password_hash(user.password, form.password.data):
                flask_login.login_user(user,remember=True)
                flash('You were logged in','error')
                next = request.args.get('next')
                if not is_safe_url(next):
                    return abort(400)
                return redirect(next or url_for('index'))
            else:
                flash('Incorrect password','error')
                return redirect(url_for('login'))
    return render_template('login.html',form=form)

@app.route('/logout')
def logout():
    flask_login.logout_user()
    flash('You were logged out','error')
    return redirect(url_for('index'))

@app.route('/character', methods=['GET', 'POST'])
@flask_login.login_required
def character_profile():
    form = CharacterCreationForm()
    if request.method == 'GET':
        char = flask_login.current_user.character
        if char is None:
            return render_template('character_profile.html',form=form)    
        else:
            return render_template('character_profile.html',character=char)
    elif request.method == 'POST':
        if form.validate_on_submit():
            if Character.query.filter_by(name=form.name.data).first():
                flash('Character name already in use. Try again.','error')
                return redirect(url_for('character_profile'))
            else:
                character = Character(name=form.name.data)
                character.title = 'the newly landed'
                character.location = Room.query.first()
                db.session.add(character)
                flask_login.current_user.character = character
                db.session.add(flask_login.current_user)
                db.session.commit()
                generate_starter_equipment(character)
                flash('Character created! Welcome to Deimos 2147!','error')
                return redirect(url_for('character_profile'))
        else:
            flash('Failed to validate form','error')
            return redirect(url_for('character_profile'))


@app.route('/inventory')
@flask_login.login_required
def inventory():
    char = flask_login.current_user.character
    if char is None:
        return redirect(url_for('character_profile'))    
    else:
        inv=char.inventory
        worn_items = char.body
        return render_template('inventory.html',inventory=inv,worn_items=worn_items)


@app.route('/move/<int:destination_id>')
@flask_login.login_required
def move_character(destination_id,char=None):
    if char is None: 
        if flask_login.current_user.character is None:
            return redirect(url_for('character_profile'))
        else:
            char = flask_login.current_user.character


    if char.opponent:
        return redirect(url_for('attack'))

    destination = Room.query.get(destination_id)
    current_loc = char.location

    monster_pool = []

    #for demo purposes
    monster = NPC(name="Testy")
    db.session.add(monster)
    db.session.commit()

    monster_pool.append(monster)

    if destination != current_loc:
        nearest_exits = current_loc.exits + current_loc.linked_rooms
        if destination in nearest_exits:
            if monster_pool:
                if monster_pool[0].dexterity_roll() > char.dexterity_roll():
                    char.opponent = monster_pool[0]            
                    db.session.add(char)
                    db.session.commit()
                    flash('You have encountered {}! Prepare for combat!'.format(char.opponent.name),'error')
                else:
                    char.location = destination
                    db.session.add(char)
                    db.session.commit()
                    flash('Successfully moved to {}.'.format(char.location.name),'error')
            else:
                char.location = destination
                db.session.add(char)
                db.session.commit()
                flash('Successfully moved to {}.'.format(char.location.name),'error')
            char.update_character()
        else:
            flash('Failed to move. Destination not close enough.','error')
    else:
        flash('Failed to move. Destination is current location.','error')

    return redirect(url_for('index'))

@app.route('/attack')
@flask_login.login_required
def attack():
    character = flask_login.current_user.character
    if character is None:
        flash('You cannot attack without a character.','error')
        return redirect(url_for('character_profile'))

    opponent = character.opponent

    if opponent is None:
        flash('Your opponent is dead so you move on.', 'error')
        return redirect(url_for('index'))

    player_attack_result = character.attack(character.opponent)
    npc_attack_result = opponent.attack(character)

    if player_attack_result is None:
        flash('Something broke. Inform a dev that we did not get a player attack result.', 'error')
        return redirect(url_for('index'))

    if npc_attack_result is None:
        flash('Something broke. Inform a dev that we did not get an npc attack result.','error')
        return redirect(url_for('index'))

    player_combat_msg = ''
    npc_combat_msg = ''

    if player_attack_result > 0:
        player_combat_msg = 'You hit {} for {} damage.'.format(opponent.name, player_attack_result)
    elif player_attack_result == 0:
        player_combat_msg = 'You hit {} for no damage.'.format(opponent.name)
    else:
        player_combat_msg = 'You missed your attack on {}.'.format(opponent.name)

    if npc_attack_result > 0:
        npc_combat_msg = '{} hit you for {} damage.'.format(opponent.name, npc_attack_result)
    elif npc_attack_result == 0:
        npc_combat_msg = '{} hit you for no damage.'.format(opponent.name)
    else:
        npc_combat_msg = '{} missed their attack.'.format(opponent.name)

    combat_results = player_combat_msg+' '+npc_combat_msg

    if opponent.hps < 1:
        combat_results += " "+opponent.die(character)
    
    weapon_id = character.body['weapon']
    if weapon_id:
        weapon = Weapon.query.get(weapon_id)
    else:
        weapon = None

    return render_template('attack.html',character=character,combat_results=combat_results,weapon=weapon)

@app.route('/equip/<int:item_id>')
@flask_login.login_required
def equip(item_id):
    character = flask_login.current_user.character
    if character is None:
        flash('You have not created a character yet!', 'error')
        return redirect(url_for('character_profile'))
    
    if item_id is None:
        flash('Nothing specified to equip.','error')
        return redirect(url_for('inventory'))

    item = Item.query.get(item_id)
    if item is None:
        flash('That item does not exist. Oops! Tell a dev.', 'error')
        return redirect(url_for('inventory'))

    if item not in character.inventory:
        flash('You are not carrying that item and therefore cannot equip it.', 'error')
        return redirect(url_for('inventory'))

    if character.body[item.slot] == item.id:
        flash('You unequip {}.'.format(item.name),'error')
        character.body[item.slot] = None
        db.session.add(character)
        db.session.commit()
        return redirect(url_for('inventory'))

    if character.body[item.slot] is not None:
        flash('That equipment slot is occupied already.','error')
        return redirect(url_for('inventory'))

    character.equip(item)
    flash('You equipped {}.'.format(item.name))
    return redirect(url_for('inventory'))

@app.route('/run_away')
@flask_login.login_required
def run_away():
    return redirect(url_for('index'))

@app.route('/drink')
@flask_login.login_required
def drink_alcohol():
    character = flask_login.current_user.character
    if character is None:
        flash("You can't drink without a body.",'error')
        return redirect(url_for('character_profile'))

    if character.location.room_type != 'bar':
        flash('You are not in a drinking establishment.','error')
        return redirect(url_for('index'))

    if character.inebriation >= 100:
        flash('You cannot consume any more booze. You are very drunk.', 'error')

    if character.inebriation + INEBRIATION_PER_DRINK > 100:
        character.inebriation = 100
        db.session.add(character)
        db.commit()
    else:
        character.inebriation += INEBRIATION_PER_DRINK
        db.session.add(character)
        db.commit()

    flash('You knock back a drink and feel your health improving already!', 'error')
    return redirect(url_for('index'))

@login_manager.unauthorized_handler
def unauthorized_handler():
    return redirect(url_for('login'))

#Game Logic Stuff

def generate_starter_equipment(character):
    chest = Armor(name='Cheap Combat Armor',slot='chest',ac=10,value=100)
    head = Armor(name='Cheap Combat Helmet',slot='head',ac=10,value=100)
    hands = Armor(name='Cheap Combat Gloves',slot='hands',ac=10,value=100)
    legs = Armor(name='Cheap Combat Legplates',slot='legs',ac=10,value=100)
    feet = Armor(name='Cheap Combat Boots',slot='feet',ac=10,value=100)
    weapon = Weapon(name='Cheap Martian M16 Knockoff',damage_dice='2d4',value=100)
    db.session.add(chest)
    db.session.add(head)
    db.session.add(hands)
    db.session.add(legs)
    db.session.add(feet)
    db.session.add(weapon)
    db.session.commit()
    character.inventory.extend([chest,head,legs,feet,weapon,hands])
    db.session.add(character)
    db.session.commit()


