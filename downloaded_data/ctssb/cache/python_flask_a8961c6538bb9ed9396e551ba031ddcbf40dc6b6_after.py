from flask_restful import Resource, request
from models.Group import GroupModel
from models.ItemGroup import ItemGroupModel
from models.Item import ItemModel
from models.Error import Error
from controllers.Validator import validate
import json


class GroupsResource(Resource):

    def get(self):
        all_groups = GroupModel.find_all() or []
        all_in_json = [group.to_json() for group in all_groups]
        return {"groups": all_in_json}, 200

    def post(self):
        if 'name' in request.form.keys():
            name = request.form['name']
            is_module = request.form['is_module']
        else:
            request_data = json.loads(request.data)
            name = request_data['name']
            is_module = request_data['is_module']

        errors = validate(group_name=name)
        if len(errors) > 0:
            all_errors_in_json = [error.to_json() for error in errors]
            return {'errors': all_errors_in_json}, 400

        group = GroupModel(name, is_module)
        group.save_to_db()
        return group.to_json(), 201


class GroupResource(Resource):

    def get(self, group_id):
        errors = validate(group_id=group_id)
        if len(errors) > 0:
            all_errors_in_json = [error.to_json() for error in errors]
            return {'errors': all_errors_in_json}, 500

        group = GroupModel.find_by_id(group_id)
        return group.to_json()

    def put(self, group_id):
        if 'name' in request.form.keys():
            name = request.form['name']
        else:
            request_data = json.loads(request.data)
            name = request_data['name']
        errors = validate(
            group_id=group_id,
            group_name=name
        )
        if len(errors) > 0:
            all_errors_in_json = [error.to_json() for error in errors]
            return {'errors': all_errors_in_json}, 500

        group = GroupModel.find_by_id(group_id)
        group = group.update_name(name)
        return group.to_json()

    def delete(self, group_id):
        errors = validate(group_id=group_id)
        if len(errors) > 0:
            all_errors_in_json = [error.to_json() for error in errors]
            return {'errors': all_errors_in_json}, 500
        group = GroupModel.find_by_id(group_id)
        group.delete_from_db()
        return "Group with id: {} was successfully deleted.".format(group_id), 200


class GroupItemsResource(Resource):
    def get(self, group_id):
        errors = validate(group_id=group_id)
        if len(errors) > 0:
            all_errors_in_json = [error.to_json() for error in errors]
            return {'errors': all_errors_in_json}, 500

        item_groups_from_group = ItemGroupModel.find_by_group_id(group_id)or []
        all_in_json = [ItemModel.find_by_id(item_group.item_id).to_json() for item_group in item_groups_from_group]
        return {"items": all_in_json}, 200

    def post(self, group_id):
        if 'item_id' in request.form.keys():
            item_id = request.form['item_id']
        else:
            request_data = json.loads(request.data)
            item_id = request_data['item_id']
        errors = validate(
            group_id=group_id,
            item_id=item_id,
            method="GroupItemsResource.post"
        )

        if len(errors) > 0:
            all_errors_in_json = [error.to_json() for error in errors]
            return {'errors': all_errors_in_json}, 422

        item_group = ItemGroupModel(item_id, group_id)
        item_group.save_to_db()
        group = GroupModel.find_by_id(group_id)
        return group.to_json()


class GroupItemResource(Resource):
    def get(self, group_id, item_id):
        errors = validate(group_id=group_id, item_id=item_id, method="GroupItemResource.get")
        if len(errors) > 0:
            all_errors_in_json = [error.to_json() for error in errors]
            return {'errors': all_errors_in_json}, 500
        item = ItemModel.find_by_id(item_id)
        return item.to_json(), 200

    def delete(self, group_id, item_id):
        errors = validate(group_id=group_id, item_id=item_id, method="GroupItemResource.delete")
        if len(errors) > 0:
            all_errors_in_json = [error.to_json() for error in errors]
            return {'errors': all_errors_in_json}, 500

        item_group = ItemGroupModel.find_by_item_id_and_group_id(item_id, group_id)
        item_group.delete_from_db()
        item_group = ItemGroupModel.find_by_item_id_and_group_id(item_id, group_id)
        if item_group is not None:
            errors.append(Error("An unexpected error occurred item was not removed from group.",
                                "ItemGroupModel.find_by_item_id_and_group_id({}, {}) did not return None".format(item_id, group_id),
                                500,
                                "https://en.wikipedia.org/wiki/HTTP_500"))
        else:
            group = GroupModel.find_by_id(group_id)
            return group.to_json(), 200

