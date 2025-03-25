# coding=utf-8
import os
import time
import sys
from wechat_analyzer.basic_class.Article import Article
from wechat_analyzer.basic_class.Reaction import Reaction
from wechat_analyzer.basic_class.WechatUser import WechatUser

__author__ = 'jayvee'
apath = os.path.dirname(__file__)
sys.path.append(apath)
reload(sys)
sys.setdefaultencoding('utf-8')


class DAOException(Exception):
    ExceptionTypes = {'NO_RESULT_EXCEPTION'}

    def __init__(self, msg):
        self.message = msg

    def __str__(self):
        return str(self.message)


def get_article_tagsdict(a_id):
    """
    根据文章id获取
    API: /api/v1/atags    [POST]
    :param a_id: 文章id
    :return:
    """
    pass
    # /api/atags/<id>    [GET]


def get_article_by_id(article_id):
    """
    根据文章id获取一个Article实例
    后端交互API: /api/v1/article [POST]
    :param article_id:
    :return:Article实例
    """
    pass
    # /api/article/<article_id> [GET]


def get_reactions_by_userid(user_id, start_time, end_time=time.time()):
    """
    根据user_id和起止时间，返回该用户在某一时间段内的交互记录
    后端API: /api/v1/reaction [POST]
    :param user_id:
    :param start_time:
    :param end_time:
    :return: Reaction实例的list
    """
    pass


def get_reactions_by_articleid(article_id, start_time, end_time=time.time()):
    """
    根据文章id和起止时间，返回该文章在某时间段内的交互记录
    :param article_id:
    :param start_time:
    :param end_time:
    :return:Reaction实例的list
    """
    pass


def get_user_by_id(user_id):
    """
    根据user_id获取一个WechatUser实例
    后端API: /api/v1/user [POST]
    :param user_id:
    :return:
    """


def get_global_user_tags():
    """
    获取全局user_tags
    :return:
    """
    pass


def get_global_article_tags():
    """
    获取全局article_tags
    :return:
    """
    pass


def get_a_u_map():
    """
    获取所有article_tag到user_tag的映射值，map
    :return:
    """
    pass


# ------------ directly DAO utils --------------

# init mongoDB
import pymongo

client = pymongo.MongoClient('112.126.80.78', 27017)
wechat_analysis_collection = client['wechat_analysis']
a_db = wechat_analysis_collection['Articles']
u_db = wechat_analysis_collection['Users']
re_db = wechat_analysis_collection['Reactions']
conf_db = wechat_analysis_collection['Configs']


# todo add logging system
# TODO try/except

def mongo_insert_article(inst_article, admin_id, article_db=a_db, is_overwrite=False):
    """
    直接连接mongo数据库，插入文章数据
    :param inst_article: Article实例
    :return:
    """

    article = {'admin_id': admin_id, 'title': inst_article.a_title, 'article_id': inst_article.a_id,
               'tags': inst_article.a_tags,
               'content': inst_article.a_content, 'post_date': inst_article.post_date,
               'post_user': inst_article.post_user, 'article_url': inst_article.a_url}
    if not article_db.find_one({'article_id': inst_article.a_id}):
        article_db.insert(article)
    elif is_overwrite:
        article_db.update_one({'article_id': inst_article.a_id}, {'$set': article})
    else:
        print 'article already existed!'
        raise DAOException({'code': 1, 'msg': 'article already existed!'})


def mongo_get_article(a_id, article_db=a_db):
    """
    根据文章id获取article实例
    :param a_id:
    :return:
    """

    find_result = article_db.find_one({'article_id': a_id})
    if find_result:
        article = Article(a_id, a_title=find_result['title'], post_user=find_result['post_user'],
                          a_tags=find_result['tags'], post_date=find_result['post_date'],
                          a_url=find_result['article_url'])
        return article
    else:
        print 'article not found.'
        raise DAOException({'code': 1, 'msg': 'article not found.'})


def mongo_insert_user(inst_user, user_db=u_db, is_overwrite=False):
    """

    :param inst_user:
    :param user_db:
    :return:
    """
    user = {'user_id': inst_user.user_id, 'user_name': inst_user.user_name, 'article_vec': inst_user.user_atag_vec,
            'user_tag_vec': inst_user.user_tag_score_vec, 'admin_id': inst_user.admin_id}
    if not user_db.find_one({'user_id': inst_user.user_id, 'admin_id': inst_user.admin_id}):
        user_db.insert(user)
    elif is_overwrite:
        user_db.update_one({'user_id': inst_user.user_id}, {'$set': user})
    else:
        print 'user already existed!'
        raise DAOException({'code': 1, 'msg': 'user already existed!'})
        # user_db.save()


def mongo_get_user(user_id, admin_id=None, user_db=u_db):
    """

    :param user_id:
    :param user_db:
    :return:
    """
    if admin_id:
        find_result = u_db.find_one({'user_id': user_id, 'admin_id': admin_id})
    else:
        find_result = u_db.find_one({'user_id': user_id})
    if find_result:
        user = WechatUser(user_id=user_id, user_name=find_result['user_name'], user_atag_vec=find_result['article_vec'],
                          user_tag_score_vec=find_result['user_tag_vec'], admin_id=find_result['admin_id'])
        return user
    else:
        raise DAOException({'code': 1, 'msg': 'user not found.'})


def mongo_insert_reactions(inst_reaction, reaction_db=re_db, is_overwrite=False):
    """
    保存一条交互记录
    :param inst_reaction:
    :param reaction_db:
    :return:
    """
    reaction = {'reaction_id': inst_reaction.reaction_id, 'reaction_type': inst_reaction.reaction_type,
                'reaction_a_id': inst_reaction.reaction_a_id, 'reaction_user_id': inst_reaction.reaction_user_id,
                'reaction_date': inst_reaction.reaction_date, 'is_checked': inst_reaction.is_checked}
    find_result = reaction_db.find_one({'reaction_id': inst_reaction.reaction_id})
    if not find_result:
        reaction_db.insert(reaction)
        # reaction_db.save()
    elif is_overwrite:
        reaction_db.update_one({'reaction_id': inst_reaction.reaction_id}, {'$set': reaction})
    else:
        DAOException({'code': 1, 'msg': 'reaction already existed!'})
        print 'reaction already existed!'


def mongo_get_reactions(reaction_db=re_db, **kwargs):
    """
    根据条件获取交互记录，默认为is_checked=False的所有记录
    :param kwargs: 可选参数，包括time_range-一个元组（start_time,end_time）
    :return:交互记录实例列表
    """
    find_result = re_db.find({"is_checked": False})
    reaction_list = []
    for item in find_result:
        reaction_id = item['reaction_id']
        reaction_type = item['reaction_type']
        reaction_a_id = item['reaction_a_id']
        reaction_user_id = item['reaction_user_id']
        reaction_date = item['reaction_date']
        is_checked = item['is_checked']
        reaction = Reaction(reaction_id=reaction_id, reaction_type=reaction_type, reaction_a_id=reaction_a_id,
                            reaction_user_id=reaction_user_id, reaction_date=reaction_date, is_checked=is_checked)
        reaction_list.append(reaction)
    return reaction_list


# TODO add try/except to get config func
def mongo_get_global_user_tags(config_db=conf_db):
    """

    :return:
    """
    find_result = config_db.find_one({'name': 'global_user_tags'})
    return find_result['value']


def mongo_get_global_article_tags(config_db=conf_db):
    """

    :return:
    """
    find_result = config_db.find_one({'name': 'global_articles_tags'})
    return find_result['value']


def mongo_get_reaction_type_weight(config_db=conf_db):
    """

    :return:
    """
    find_result = config_db.find_one({'name': 'reaction_type_weight'})
    return find_result['value']


def mongo_get_a_u_tagmap(config_db=conf_db):
    find_result = config_db.find_one({'name': 'a_u_tagmap'})
    return find_result['value']


def mongo_set_conf(config_name, config_value, config_db=conf_db, is_overwrite=False):
    if not conf_db.find_one({'name': config_name}):
        conf_db.insert({'name': config_name, 'value': config_value})
    elif is_overwrite:
        conf_db.update_one({'name': config_name}, {'$set': {'name': config_name, 'value': config_value}})
    else:
        return -1
    # conf_db.save()
    return 0


def mongo_get_openid_by_tags(tags, user_db=u_db):
    openid_list = set()
    conditions = []
    for tag in tags:
        conditions.append('user_tag_vec.%s' % tag)
    find_filter = {}
    for condition in conditions:
        find_filter[condition] = {'$exists': True}
    if tags:
        find_result = u_db.find(find_filter)
        for item in find_result:
            openid_list.add(item['user_id'])
    return list(openid_list)


def mongo_get_all_taglist(config_db=conf_db):
    find_result = config_db.find_one({'name': 'a_u_tagmap'})
    taglist = set()
    for atag in find_result['value']:
        for utag in find_result['value'][atag]:
            taglist.add(utag)
    return list(taglist)


if __name__ == '__main__':
    print mongo_get_openid_by_tags([u'军事新闻', u'军事历史'])
    print mongo_get_all_taglist()
