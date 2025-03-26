import uuid
import jwt
from werkzeug.utils import secure_filename
from flask import render_template, url_for, request, flash, jsonify
from moneyapp.models import User, Organization, Task, Receiver_Task, Organization_Member, Transaction, Customer_Review, Feedback_Review
from moneyapp.db_user import *
from moneyapp.db_organization import *
from moneyapp.db_task import *
from moneyapp.db_review import *
from moneyapp.utils import *
from moneyapp.db_feedback import *
from flask_jwt import JWT, jwt_required, current_identity
from functools import wraps
from . import routes
from .home import token_required


@routes.route('/users/<user_id>/tasks/<task_id>/feedback/<receiver_id>',methods = ['POST'])
@token_required
def  create_User_Feedback_Review(current_user,user_id,task_id,receiver_id):
    if current_user.id != int(user_id):
        return jsonify({"error_code": "404", "error_msg": "user Not Found"}), 404

    #检查是否已有评论
    
    if checkCommentCreated(receiver_id,task_id) :
        return jsonify({"error_code": "500", "error_msg": "The receiver have not created a comment"}), 500
    

    #检查是否已有回评
    if not checkFeedbackCreated(user_id,task_id,receiver_id):
            

        task = Task.query.filter_by(id = task_id, user_id = user_id)

        #检查是否是创建task的人
        if task:
            
            d = request.get_json()
            items = {'title', 'content', 'rate'}
            for item in items:
                if item not in d:
                    d[item] = None

            d['user_id'] = int(user_id)
            d['task_id'] = int(task_id)
            d['receiver_id'] = int(receiver_id)
            feedback_review = createFeedbackReview(d)

            return jsonify({"user_id": current_user.id,
                                "task_id": feedback_review.task.id,
                                "feedback_title": feedback_review.title,
                                "feedback_content": feedback_review.content,
                                "feedback_rate": feedback_review.rate}), 201
        else:
            return jsonify({"error_code":500,"error_msg":"It is not your task"}),500

    else:
        return jsonify({"error_code": "500", "error_msg": "You have created a feedback"}), 500
# 组织创建的任务回评
@routes.route('/users/<user_id>/organization/<organization_id>/tasks/<task_id>/feedback/<receiver_id>',methods = ['POST'])
@token_required
def create_Organization_Feedback_Review(current_user,user_id,task_id,receiver_id,organization_id):
    if current_user.id != int(user_id):
        return jsonify({"error_code": "404", "error_msg": "user Not Found"}), 404

    #检查是否已有回评
    if checkFeedbackCreated(user_id,task_id,receiver_id):
        return jsonify({"error_code": "500", "error_msg": "You have created a feedback"}), 500

    task = Task.query.filter_by(organization_id = organization_id , user_id = user_id)

    #检查是否是创建task的人
    if task:

        d = request.get_json()
        items = {'title', 'content', 'rate'}
        for item in items:
            if item not in d:
                d[item] = None

        d['user_id'] = int(user_id)
        d['task_id'] = int(task_id)
        d['receiver_id'] = int(receiver_id)
        feedback_review = createFeedbackReview(d)

        return jsonify({"user_id": current_user.id,
                            "task_id": feedback_review.task.id,
                            "feedback_title": feedback_review.title,
                            "feedback_content": feedback_review.content,
                            "feedback_rate": feedback_review.rate}), 200
    else :
        return jsonify({"error_code":500,"error_msg":"It is not your task"}),500


# 用户创建的任务修改回评
@routes.route('/users/<user_id>/tasks/<task_id>/feedback/feedback/<receiver_id>',methods = ['POST'])
@token_required
def modify_user_Feedback_Review(current_user,user_id,task_id,receiver_id):
    if current_user.id != int(user_id):
        return jsonify({"error_code": "404", "error_msg": "user Not Found"}), 404

    feedback_review = Feedback_Review.query.filter_by(user_id=user_id,task_id=task_id).first()
    if feedback_review:
        

        d = request.get_json()

        feedback_review = modifyFeedbackReview(d)

        return jsonify({"message":"modify successfully"}),200
    
    else:
        return jsonify({"error_code": "404", "error_msg": "Feedback Review is Not Found"}), 404   


# 组织创建的任务修改回评
@routes.route('/users/<user_id>/organization/<organization_id>/tasks/<task_id>/feedback/<receiver_id>',methods = ['POST'])
@token_required
def modify_organization_Feedback_Review(current_user,user_id,task_id,receiver_id,organization_id):
    if current_user.id != int(user_id):
        return jsonify({"error_code": "404", "error_msg": "user Not Found"}), 404

    feedback_review = Feedback_Review.query.filter_by(user_id=user_id,task_id=task_id).first()
    if feedback_review:
        

        d = request.get_json()

        feedback_review = modifyFeedbackReview(d)

        return jsonify({"message":"modify successfully"}),200
    else:
        return jsonify({"error_code": "404", "error_msg": "Feedback Review is Not Found"}), 404

# 用户创建的任务删除回评
@routes.route('/users/<user_id>/tasks/<task_id>/feedback/feedback/<receiver_id>',methods = ['POST'])
@token_required
def delete_user_Feedback_Review(current_user,user_id,task_id,receiver_id):
    if current_user.id != int(user_id):
        return jsonify({"error_code": "404", "error_msg": "user Not Found"}), 404

    feedback_review = Feedback_Review.query.filter_by(user_id=user_id,task_id=task_id).first()
    if feedback_review:
        
        deleteFeedbackReview(user_id,task_id)

        return jsonify({"message":"modify successfully"}),200
    else:
        return jsonify({"error_code": "404", "error_msg": "Feedback Review is Not Found"}), 404



# 组织创建的任务删除回评
@routes.route('/users/<user_id>/organization/<organization_id>/tasks/<task_id>/feedback/<receiver_id>',methods = ['POST'])
@token_required
def delete_organization_Feedback_Review(current_user,user_id,task_id,receiver_id,organization_id):
    if current_user.id != int(user_id):
        return jsonify({"error_code": "404", "error_msg": "user Not Found"}), 404

    feedback_review = Feedback_Review.query.filter_by(user_id=user_id,task_id=task_id).first()
    if feedback_review:
        
        deleteFeedbackReview(user_id,task_id)

        return jsonify({"message":"modify successfully"}),200

    else:
        return jsonify({"error_code": "404", "error_msg": "Feedback Review is Not Found"}), 404