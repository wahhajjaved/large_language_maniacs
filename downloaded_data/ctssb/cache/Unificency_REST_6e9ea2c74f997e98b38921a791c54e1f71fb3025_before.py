import os, sys
from flask import Blueprint, send_file, request, jsonify
from flask_restful import Api, Resource, reqparse, marshal
from app import db
import model
import config
from app.user import model as user_model
from app.group import model as group_model
from app.resources import response, upload
from app.validation import auth
from app.note import model as note_model


note_blueprint = Blueprint('note', __name__)
api = Api(note_blueprint)


class NoteCRUD(Resource):

    def post_parser(self):
        parser = reqparse.RequestParser()
        parser.add_argument('content', default=None, help='you have to provide some content for this note')
        parser.add_argument('name', required=True, help='you have to provide a name for this note')
        parser.add_argument('topic', required=True, help='you have to provide a topic for this note')
        return parser

    @auth.token_required
    def post(self, group_id, *args, **kwargs):
        """
        @apiVersion 0.1.0
        @api {post} /groups/{group_id}/notes/ Create a note.
        @apiName CreateNote
        @apiGroup Notes
        @apiDescription Create a new Note.
        @apiUse TokenRequired
        @apiUse BadRequest
        @apiUse SuccessfullyCreated
        @apiParam {String} name The notes name.
        @apiParam {String} topic The notes topic.
        @apiParam {String} [content] The notes content.
        @apiParam {image} [file] An optional image.
        @apiUse NoSuchUserError
        @apiUse CouldNotBeSavedError
        """

        user_id = kwargs.get('user')['user_id']
        parser = self.post_parser()
        args = parser.parse_args()
        post_in_group = group_model.Group.query.get(group_id)
        parent_user = user_model.User.query.get(user_id)
        if not parent_user or not post_in_group:
            return response.simple_response('no such user or group', status=404)
        if not parent_user.is_member_of(post_in_group):
            return response.simple_response('you must be a member of this group', status=401)
        new_note = model.Note(
            args['name'], args['topic'], args['content']
        )
        if 'file' in request.files:
            path_ = upload.get_uploaded_image_and_save(
                save_to=config.Config().UPLOAD_FOLDER_NOTES_IMAGES)
            new_note.image_path = path_
        new_note.creator = parent_user
        new_note.group = post_in_group
        db.session.add(new_note)
        db.session.commit()
        return response.simple_response('note created ' + str(new_note.id), status=201)

    @auth.token_required
    def get(self, group_id, *args, **kwargs):
        """
        @apiVersion 0.1.0
        @api {get} /groups/{group_id}/notes/ Get a groups notes.
        @apiName GetGroupNotes
        @apiGroup Notes
        @apiUse TokenRequired
        @apiDescription Get a groups notes.
        @apiUse BadRequest
        @apiSuccess 200 Success-Response:
        @apiSuccessExample Success-Response
          HTTP/1.1 200 OK
          {
            [
            {
            'id': the notes id,
            'creator': the creators name,
            'group': the groups name the note was posted in,
            'name': the groups name,
            'topic': the groups topic,
            'content': the groups content
            'has_image': true/false
            }, ...]
            }

        """
        user_id = kwargs.get('user')['user_id']
        user = user_model.User.query.get(user_id)
        group = group_model.Group.query.get(group_id)
        if user and group:
            if user.is_member_of(group):
                # explicitly load because of lazy relationship
                notes = group.notes.all()
                marshalled = marshal(notes, model.Note.fields)
                UM = user_model.User
                for note_marshalled in marshalled:
                    count = UM.query.filter(
                        UM.favorite_notes.any(
                            model.Note.id == note_marshalled['id']
                        )).count()
                    note_marshalled.update({'favorite_count': count})
                return jsonify(marshalled)
            else:
                return response.simple_response('no you are not a member of this group', status=404)
        return response.simple_response('no notes found', status=404)


class NoteById(Resource):
    def put_parser(self):
        parser = reqparse.RequestParser()
        parser.add_argument('name', default=None)
        parser.add_argument('content', default=None)
        parser.add_argument('topic', default=None)
        return parser

    @auth.token_required
    def delete(self, id_, *args, **kwargs):
        """
        @apiVersion 0.1.0
        @api {delete} /notes/{note_id}/ Delete a note.
        @apiName DeleteNote
        @apiGroup Notes
        @apiUse TokenRequired
        @apiDescription Delete a note.
        @apiUse BadRequest
        @apiSuccess 200 Success-Response:
        @apiUse NoSuchResourceError
        @apiUse SuccessfullyDeleted
        """
        user_id = kwargs.get('user')['user_id']
        user = user_model.User.query.get(user_id)
        note_to_delete = model.Note.query.get(id_)
        if not user or not note_to_delete:
            return response.simple_response('no such note or user', status=404)
        if note_to_delete in user.notes:
            if note_to_delete.image_path:
                APP_ROOT = config.Config().PROJECT_ROOT
                upload.delete_if_exists(os.path.join(APP_ROOT, note_to_delete.image_path))
            db.session.delete(note_to_delete)
            db.session.commit()
            return response.simple_response('note deleted')
        return response.simple_response('you must be the creator of this note in order to delete it', status=401)

    @auth.token_required
    def put(self, id_, *args, **kwargs):
        """
        @apiVersion 0.1.0
        @api {put} /notes/{note_id}/ Modify a note.
        @apiName ModifyNote
        @apiGroup Notes
        @apiUse TokenRequired
        @apiDescription Modify a note.
        @apiUse BadRequest
        @apiParam {String} name The notes name.
        @apiParam {String} topic The notes topic.
        @apiParam {String} content The notes content.
        @apiUse NoSuchResourceError
        @apiUse SuccessfullyModified
        """
        parser = self.put_parser()
        args = parser.parse_args()
        user_id = kwargs.get('user')['user_id']
        user = user_model.User.query.get(user_id)
        note_to_modify = model.Note.query.get(id_)
        if not user or not note_to_modify:
            return response.simple_response('no such note or user', status=404)
        if note_to_modify in user.notes:
            message = ""
            for key, value in args.items():
                if key and value:
                    setattr(note_to_modify, key, value)
                    message += '{key} set to {value} | '.format(key=key, value=value)
            db.session.commit()
            return response.simple_response(message)
        return response.simple_response('you must be the creator of this note in order to modify it', status=401)

    @auth.token_required
    def get(self, id_, *args, **kwargs):
        """
        @apiVersion 0.1.0
        @api {get} /notes/{id}?image=[true|false] Get a note by id
        @apiName NoteById
        @apiGroup Notes
        @apiUse TokenRequired
        @apiDescription  Get a note by id.
        @apiUse BadRequest
        @apiSuccess 200 Success-Response:
        @apiUse NoSuchUserError
        @apiUse NoSuchResourceError
        @apiSuccessExample Success-Response
          HTTP/1.1 200 OK
        [
          {
            "content": "Der B-Baum ist so schoen! ",
            "group": {
              "topic_area": "Machine Learning",
              "protected": true,
              "id": 9,
              "name": "The Royals"
            },
            "name": "B-Baum",
            "creator": {
              "username": "Roberto"
            },
            "topic": "Algorithmen",
            "id": 1,
            "has_image": true/false,
            "is_creator": true,
            "if_favorite": false,
            "favorite_count": 42
          }
        ]
        """
        user_id = kwargs.get('user')['user_id']
        user = user_model.User.query.get(user_id)
        note_to_return = model.Note.query.get(id_)
        if not user or not note_to_return:
            return response.simple_response('no such note or user', status=404)
        image = request.args.get('image')
        users_note_check = note_to_return.group_id in [group.id for group in user.groups]
        if not users_note_check:
            return response.simple_response('this is not your note', status=401)
        if image:
            if not note_to_return.image_path:
                return response.simple_response('this note has no image', 404)
            if image.lower() == 'true':
                APP_ROOT = config.Config().PROJECT_ROOT
                return send_file(os.path.join(APP_ROOT, note_to_return.image_path))
            if image.lower() not in ['true', 'false']:
                return response.simple_response('expected ?image=[true|false], got {0}'.format(image))
        additional_info = {
            'is_favorite': True if note_to_return in user.favorite_notes else False,
            'is_creator': True if note_to_return in user.notes else False
        }
        UM = user_model.User
        count = UM.query.filter(
            UM.favorite_notes.any(
                model.Note.id == note_to_return.id
        )).count()
        marshalled = marshal(note_to_return, note_model.Note.fields)
        marshalled_ = marshalled.copy()
        marshalled_.update(additional_info)
        marshalled_.update({'favorite_count': count})
        return jsonify(marshalled_)


class UsersNotes(Resource):
    @auth.token_required
    def get(self, *args, **kwargs):
        """
        @apiVersion 0.1.0
        @api {get} /users/notes?favorites={true/false} Get a users (favorite) notes.
        @apiName UsersNotes
        @apiGroup Notes
        @apiUse TokenRequired
        @apiDescription Get a users note. If onlyFavorites is provided, this will return the users favorite notes.
        @apiUse BadRequest
        @apiSuccess 200 Success-Response:
        @apiUse NoSuchUserError
        @apiSuccessExample Success-Response
          HTTP/1.1 200 OK
        [
          {
            "content": "Der B-Baum ist so schoen! ",
            "group": {
              "topic_area": "Machine Learning",
              "protected": true,
              "id": 9,
              "name": "The Royals"
            },
            "name": "B-Baum",
            "creator": {
              "username": "Roberto"
            },
            "topic": "Algorithmen",
            "id": 1
          }, .....
        ]
        """
        def with_count(notes):
            UM = user_model.User
            all_notes = notes
            marshalled = marshal(all_notes, note_model.Note.fields)
            for note in marshalled:
                count = UM.query.filter(
                    UM.favorite_notes.any(
                        model.Note.id == note['id']
                    )).count()
                note.update({'favorite_count': count})
            return jsonify(marshalled)

        user_id = kwargs.get('user')['user_id']
        user = user_model.User.query.get(user_id)
        if not user:
            response.simple_response('no such user')
        favorites = request.args.get('favorites')
        if favorites:
            if favorites.lower() == 'true':
                return with_count(user.favorite_notes.all())
            if favorites.lower() not in ['true', 'false']:
                return response.simple_response('expected ?favorites=[true|false], got {0}'.format(favorites))
        return with_count(user.notes.all())



class FavoriteNotes(Resource):
    @auth.token_required
    def post(self, id_, *args, **kwargs):
        """
        @apiVersion 0.1.0
        @api {post} /notes/{id}/favor/ Favor a note.
        @apiName FavorNote
        @apiGroup Notes
        @apiUse TokenRequired
        @apiDescription Favor a note.
        @apiUse BadRequest
        @apiSuccess 200 Success-Response:
        @apiUse NoSuchUserError
        @apiSuccessExample Success-Response
          HTTP/1.1 200 OK
          {
            "message": "added note {note_name} to your favorites"
          }
        """
        user_id = kwargs.get('user')['user_id']
        user = user_model.User.query.get(user_id)
        note = note_model.Note.query.get(id_)
        if not user or not note:
            return response.simple_response('no such user or note', status=404)
        success = user.add_favorite(note)
        if not success:
            return response.simple_response('you dont need to favor this note again :-)', status=401)
        db.session.commit()
        return response.simple_response('added note {0} to your favorites'. format(note.name))

    @auth.token_required
    def delete(self, id_, *args, **kwargs):
        """
        @apiVersion 0.1.0
        @api {delete} /notes/{id}/favor/ Unfavor a note.
        @apiName UnfavorNote
        @apiGroup Notes
        @apiUse TokenRequired
        @apiDescription Unfavor a note.
        @apiUse BadRequest
        @apiSuccess 200 Success-Response:
        @apiUse NoSuchUserError
        @apiSuccessExample Success-Response
          HTTP/1.1 200 OK
          {
            "message": "removed note from your favorites"
          }
        """
        user_id = kwargs.get('user')['user_id']
        user = user_model.User.query.get(user_id)
        note = note_model.Note.query.get(id_)
        if not user or not note:
            return response.simple_response('no such user or note', status=404)
        if not note in user.favorite_notes:
            return response.simple_response('you did not favor this note', status=400)
        user.favorite_notes.remove(note)
        db.session.commit()
        return response.simple_response('removed note {0} from your favorites'.format(note.name), status=200)






api.add_resource(NoteCRUD, '/groups/<int:group_id>/notes/')
api.add_resource(NoteById, '/notes/<int:id_>/')
api.add_resource(FavoriteNotes, '/notes/<int:id_>/favor/')
api.add_resource(UsersNotes, '/users/notes/')
