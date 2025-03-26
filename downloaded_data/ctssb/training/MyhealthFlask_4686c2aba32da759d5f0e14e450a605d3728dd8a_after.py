# !/usr/bin/env python
# -*-coding:UTF-8-*-
# __author__ = pighui
# __time__ = 2019-11-20 上午9:25

import uuid

from common.cache import set_code, valid_code, get_code, remove_token, add_token
from db.serializers import dumps
from settings import BASE_DIR
from common.file import change_filename, base64_to_bytes, save_file
from common.token_ import new_token
from models import User, UserAddres, FollowGood, FollowDoc, Good, Doctor, UserInfo
from common.encrypt import encode4md5
import db
from flask import Blueprint, jsonify, request
from common.aliyun_sms import send_code

user_blue = Blueprint("user_blue", __name__)


# 获取验证码
@user_blue.route('/phone/', methods=('POST',))
def send():
    try:
        req_data = request.get_json()
        phone = req_data['u_tel']
    except:
        return jsonify({
            'status': 400,
            'msg': '请求参数错误'
        })
    else:
        code = send_code(phone)
        set_code(phone, code)
        return jsonify({
            'status': 200,
            'msg': '获取验证码成功'
        })


# 注册
@user_blue.route('/register/', methods=('POST',))
def register():
    try:
        req_data = request.get_json()
        u_phone, u_passwd, u_code = req_data['u_tel'], req_data['u_password'], req_data['u_code']
    except:
        return jsonify({
            'status': 400,
            'msg': '请求参数错误'
        })
    else:
        query = db.session.query(User).filter(User.u_tel == u_phone)
        if query.count() == 0:
            result = valid_code(u_phone)
            if not result:
                return jsonify({
                    'status': 300,
                    'msg': '验证码已过期'
                })
            else:
                code = get_code(u_phone)
                if code == u_code:
                    password = encode4md5(u_passwd)
                    new_user = User(u_tel=u_phone, u_password=password)
                    db.session.add(new_user)
                    db.session.commit()
                    return jsonify({
                        'status': 200,
                        'msg': '注册成功'
                    })
                else:
                    return jsonify({
                        'status': 400,
                        'msg': '验证码错误'
                    })
        else:
            return jsonify({
                'status': 300,
                'msg': '手机号已存在'
            })


# 用户登录的接口
@user_blue.route('/login/', methods=('POST',))
def login():
    # 获取请求上传的json数据
    try:
        req_data = request.get_json()
        phone, pwd = req_data['u_tel'], req_data['u_password']
        if any((len(pwd.strip()), len(phone.strip()))) == 0:
            raise Exception()
    except:
        return jsonify({
            'status': 400,
            'msg': '请求参数错误'
        })
    else:
        query = db.session.query(User).filter(User.u_tel == phone)
        if query.count() == 0:
            return jsonify({
                'status': 300,
                'msg': '查无此用户'
            })
        else:
            login_user = query.first()
            if encode4md5(pwd) == login_user.u_password:
                token = new_token()
                add_token(phone, token)
                data = dumps(login_user)
                return jsonify({
                    'status': 200,
                    'msg': '登录成功',
                    'token': token,
                    'data': {
                        'user': data
                    }
                    #     {
                    #     'u_id': login_user.id,
                    #     'u_name': login_user.u_name,
                    #     'u_tel': login_user.u_tel,
                    #     'u_image': login_user.u_image
                    # }
                })
            else:
                return jsonify({
                    'status': 500,
                    'msg': '登录失败，用户名或密码错误'
                })


# 用户登出的接口
@user_blue.route('/logout/', methods=('POST',))
def logout():
    try:
        req_data = request.get_json()
        u_phone = req_data['u_tel']
    except:
        return jsonify({
            'status': 400,
            'msg': '请求参数错误'
        })
    else:
        remove_token(u_phone)
        return jsonify({
            'status': 200,
            'msg': '退出登录成功'
        })


# 用户忘记密码的接口，即找回密码
@user_blue.route('/forget_pwd/', methods=('POST',))
def forget_pwd():
    try:
        req_data = request.get_json()
        u_phone, u_passwd, u_code = req_data['u_tel'], req_data['u_password'], req_data['u_code']
    except:
        return jsonify({
            'status': 400,
            'msg': '请求参数错误'
        })
    else:
        query = db.session.query(User).filter(User.u_tel == u_phone)
        if query.count() != 0:
            result = valid_code(u_phone)
            if not result:
                return jsonify({
                    'status': 300,
                    'msg': '验证码已过期'
                })
            else:
                code = get_code(u_phone)
                if code == u_code:
                    new_password = encode4md5(u_passwd)
                    user = query.first()
                    user.u_password = new_password
                    db.session.commit()
                    return jsonify({
                        'status': 200,
                        'msg': '重置密码成功'
                    })
                else:
                    return jsonify({
                        'status': 400,
                        'msg': '验证码错误'
                    })
        else:
            return jsonify({
                'status': 300,
                'msg': '该手机号未注册'
            })


# 用户修改密码的接口，即更新密码
@user_blue.route('/new_pwd/', methods=('POST',))
def new_pwd():
    try:
        req_data = request.get_json()
        u_tel, u_passwd, new_password = req_data['u_tel'], req_data['u_password'], req_data['new_password']
    except:
        return jsonify({
            'status': 400,
            'msg': '请求参数错误'
        })
    else:
        query = db.session.query(User).filter(User.u_tel == u_tel)
        if query.count() != 0:
            user = query.first()
            old_password = encode4md5(u_passwd)
            if old_password != user.u_password:
                return jsonify({
                    'status': 400,
                    'msg': '旧密码错误'
                })
            else:
                new_pwd = encode4md5(new_password)
                user.u_password = new_pwd
                db.session.commit()
                return jsonify({
                    'status': 200,
                    'msg': '修改密码成功'
                })
        else:
            return jsonify({
                'status': 300,
                'msg': "手机号错误"
            })


# 用户更新头像的接口
@user_blue.route('/head/', methods=('POST',))
def head_image():
    try:
        req_data = request.get_json()
        u_id, base_str = req_data['u_id'], req_data['files']
    except:
        return jsonify({
            "status": 400,
            'msg': "请求参数错误"
        })
    else:
        try:
            file_str = base_str.split(",")[1]
            file_ext = base_str.split("/")[1].split(";")[0]
        except:
            file_str = base_str
            file_ext = 'jpg'
        try:
            savepath = "/static/imgs/"
            uuid_str = uuid.uuid4().hex
            filename = uuid_str + "." + file_ext
            filepath = BASE_DIR + savepath
            file = base64_to_bytes(file_str)
            save_file(filepath, filename, file)
        except:
            return jsonify({
                'status': 500,
                'msg': "上传失败，请重新上传"
            })
        else:
            query = db.session.query(User).filter(User.id == u_id)
            if query.count() != 0:
                user = query.first()
                user.u_image = savepath + filename
                db.session.commit()
                return jsonify({
                    "status": 200,
                    'msg': "修改头像成功",
                    'data': {
                        'u_image': savepath + filename
                    }
                })
            else:
                return jsonify({
                    "status": 300,
                    'msg': "查无此用户"
                })


# 获取用户所有收货地址的接口
@user_blue.route('/all_address/', methods=('POST',))
def get_address():
    try:
        req_data = request.get_json()
        u_id = req_data['u_id']
    except:
        return jsonify({
            'status': 400,
            'msg': '请求参数错误'
        })
    else:
        query_user = db.session.query(User).filter(User.id == u_id)
        if query_user.count() != 0:
            query = db.session.query(UserAddres).filter(UserAddres.id == u_id)
            if query.count() != 0:
                all_addr = dumps(query.all())
                return jsonify({
                    'status': 200,
                    'msg': '获取用户所有收货地址成功',
                    'data': {
                        'alladdr': all_addr
                    }
                })
            else:
                return jsonify({
                    'status': 300,
                    "msg": '该用户暂无收货地址'
                })
        else:
            return jsonify({
                'status': 500,
                "msg": '查无此用户'
            })


# 用户添加收货地址的接口
@user_blue.route('/add_address/', methods=('POST',))
def add_address():
    try:
        req_data = request.get_json()
        u_id, p_id, c_id, d_addr, u_name, u_tel, is_default = req_data['u_id'], req_data['provinceid'], req_data[
            'cityid'], req_data['detail_address'], req_data['user_name'], req_data['user_tel'], req_data['is_default']
    except:
        return jsonify({
            'status': 400,
            'msg': '请求参数错误'
        })
    else:
        query = db.session.query(User).filter(User.id == u_id)
        if query.count() != 0:
            new_address = UserAddres(id=u_id, provinceid=p_id, cityid=c_id, user_name=u_name, user_tel=u_tel,
                                     detail_address=d_addr, is_default=is_default)
            db.session.add(new_address)
            db.session.commit()
            return jsonify({
                'status': 200,
                'msg': "添加收货地址成功"
            })
        else:
            return jsonify({
                'status': 300,
                'msg': '查无此用户'
            })


# 用户修改收货地址的接口
@user_blue.route('/alter_address/', methods=('POST',))
def alter_address():
    try:
        req_data = request.get_json()
        a_id, u_id, p_id, c_id, d_addr, u_name, u_tel, is_default = req_data['a_id'], req_data['u_id'], req_data[
            'provinceid'], req_data['cityid'], req_data['detail_address'], req_data['user_name'], req_data['user_tel'], \
                                                                    req_data['is_default']
    except:
        return jsonify({
            'status': 400,
            'msg': '请求参数错误'
        })
    else:
        query = db.session.query(UserAddres).filter(UserAddres.a_id == a_id)
        if query.count() != 0:
            addr = query.first()
            if is_default == True:
                default = db.session.query(UserAddres).filter(UserAddres.id == u_id,
                                                              UserAddres.is_default == True).first()
                default.is_default = False
                db.session.commit()
            addr.provinceid = p_id,
            addr.cityid = c_id,
            addr.detail_address = d_addr
            addr.user_name = u_name
            addr.user_tel = u_tel
            addr.is_default = is_default
            db.session.commit()
            return jsonify({
                'status': 200,
                'msg': "修改收货地址成功"
            })
        else:
            return jsonify({
                'status': 300,
                'msg': '记录不存在'
            })


# 用户添加关注药品的接口
@user_blue.route('/follow_goods/', methods=('POST',))
def follow_goods():
    try:
        req_data = request.get_json()
        u_id, g_id = req_data['u_id'], req_data['goods_id']
    except:
        return jsonify({
            'status': 400,
            'msg': '请求参数错误'
        })
    else:
        query_good = db.session.query(Good).filter(Good.goods_id == g_id)
        if query_good.count != 0:
            query = db.session.query(FollowGood).filter(FollowGood.u_id == u_id, FollowGood.goods_id == g_id)
            if query.count() == 0:
                new_follow_goods = FollowGood(u_id=u_id, goods_id=g_id)
                db.session.add(new_follow_goods)
                db.session.commit()
                return jsonify({
                    'status': 200,
                    'msg': "关注药品成功"
                })
            else:
                return jsonify({
                    'status': 300,
                    'msg': "该用户已关注该商品"
                })
        else:
            return jsonify({
                "status": 500,
                "msg": "关注失败，商品不存在"
            })


# 用户取消关注药品接口
@user_blue.route('/disfollow_goods/', methods=('POST',))
def disfollow_goods():
    try:
        req_data = request.get_json()
        u_id, g_id = req_data['u_id'], req_data['goods_id']
    except:
        return jsonify({
            'status': 400,
            'msg': '请求参数错误'
        })
    else:
        query = db.session.query(FollowGood).filter(u_id == u_id, FollowGood.goods_id == g_id)
        if query.count() != 0:
            db.session.delete(query.first())
            db.session.commit()
            return jsonify({
                'status': 200,
                'msg': "取消关注药品成功"
            })
        else:
            return jsonify({
                'status': 300,
                'msg': "查无此记录"
            })


# 用户添加关注医生的接口
@user_blue.route('/follow_doctor/', methods=('POST',))
def follow_doctor():
    try:
        req_data = request.get_json()
        u_id, d_id = req_data['u_id'], req_data['d_id']
    except:
        return jsonify({
            'status': 400,
            'msg': '请求参数错误'
        })
    else:
        query_doctor = db.session.query(Doctor).filter(Doctor.d_id == d_id)
        if query_doctor.count() != 0:
            query = db.session.query(FollowDoc).filter(FollowDoc.u_id == u_id, FollowDoc.d_id == d_id)
            if query.count() == 0:
                new_follow_doctor = FollowDoc(u_id=u_id, d_id=d_id)
                db.session.add(new_follow_doctor)
                db.session.commit()
                return jsonify({
                    'status': 200,
                    'msg': "关注医生成功"
                })
            else:
                return jsonify({
                    'status': 300,
                    'msg': "该用户已关注该医生"
                })
        else:
            return jsonify({
                "status": 500,
                "msg": "关注失败，医生不存在"
            })


# 用户取消关注医生接口
@user_blue.route('/disfollow_doctor/', methods=('POST',))
def disfollow_doctor():
    try:
        req_data = request.get_json()
        u_id, d_id = req_data['u_id'], req_data['d_id']
    except:
        return jsonify({
            'status': 400,
            'msg': '请求参数错误'
        })
    else:
        query = db.session.query(FollowDoc).filter(d_id == d_id, u_id == u_id)
        if query.count() != 0:
            db.session.delete(query.first())
            db.session.commit()
            return jsonify({
                'status': 200,
                'msg': "取消关注医生成功"
            })
        else:
            return jsonify({
                'status': 300,
                'msg': "查无此记录"
            })


# 获取用户所有关注的商品
@user_blue.route('/follow_allgoods/', methods=('POST',))
def follow_allgoods():
    try:
        req_data = request.get_json()
        u_id = req_data['u_id']
    except:
        return jsonify({
            'status': 400,
            'msg': '请求参数错误'
        })
    else:
        query = db.session.query(FollowGood).filter(FollowGood.u_id == u_id)
        if query.count() != 0:
            data = dumps(query.all())
            return jsonify({
                'status': 200,
                'msg': "获取所有关注商品成功",
                'data': {
                    "followed_goods": data
                }
            })
        else:
            return jsonify({
                'status': 300,
                'msg': "该用户暂未关注任何商品"
            })


# 获取用户所有关注的医生
@user_blue.route('/follow_alldoctors/', methods=('POST',))
def follow_alldoctors():
    try:
        req_data = request.get_json()
        u_id = req_data['u_id']
    except:
        return jsonify({
            'status': 400,
            'msg': '请求参数错误'
        })
    else:
        query = db.session.query(FollowDoc).filter(FollowDoc.u_id == u_id)
        if query.count() != 0:
            data = dumps(query.all())
            return jsonify({
                'status': 200,
                'msg': "获取所有关注医生成功",
                'data': {
                    "followed_doctors": data
                }
            })
        else:
            return jsonify({
                'status': 300,
                'msg': "该用户暂未关注任何医生"
            })


# 用户添加信息的接口
@user_blue.route('/add_info/', methods=('POST',))
def add_info():
    try:
        req_data = request.get_json()
        u_id = req_data["u_id"]
        u_name = req_data["u_name"]
        u_sex = req_data["u_sex"]
        u_height = req_data["u_height"]
        u_weight = req_data["u_weight"]
    except:
        return jsonify({
            "status": 400,
            "msg": "请求参数错误"
        })
    else:
        query = db.session.query(UserInfo).filter(UserInfo.u_id == u_id)
        if query.count() == 0:
            new_info = UserInfo(u_id=u_id, u_height=u_height, u_weight=u_weight, u_name=u_name, u_sex=u_sex)
            db.session.add(new_info)
            db.session.commit()
            return jsonify({
                "status": 200,
                "msg": "添加用户详细信息成功"
            })
        else:
            return jsonify({
                "status": 300,
                "msg": "记录已存在"
            })
