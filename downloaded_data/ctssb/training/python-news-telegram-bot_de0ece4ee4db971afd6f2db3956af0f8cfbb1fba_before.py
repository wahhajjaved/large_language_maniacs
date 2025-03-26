import os
import getpass
import argparse
import sys
import vk
import json


def try_to_fetch_existing_session():
    token = os.environ.get('VK_ACCESS_TOKEN')
    if token is None:
        return None
    return vk.AuthSession(access_token=token)


def ask_for_password_and_get_session():
    app_id = os.environ['VK_API_APP_ID']
    login = input('VK login: ')
    password = getpass.getpass('Password: ')
    return vk.AuthSession(user_login=login, user_password=password, app_id=app_id)


def get_vk_public_page_list(vk_api, search_queries, results_per_query=20):
    public_pages = []
    for query in search_queries:
        search_res = vk_api.groups.search(q=query, type='page', offset=results_per_query)  #FIXME: substitute offset with count
        public_pages += search_res[1:]
    return public_pages


def get_vk_public_page_id_set(public_page_list):
    return {page['gid'] for page in public_page_list}


def get_last_vk_community_posts(vk_api, community_id, count=5):
    # for additional info, see https://vk.com/dev/wall.get
    owner_id = -1 * community_id  # indicate that this is a community
    posts = vk_api.wall.get(owner_id=owner_id, filter='owner', count=count)
    return posts[1:]


def get_argument_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('-o', '--outfile', type=argparse.FileType('w'), default=sys.stdout)
    return parser


if __name__ == '__main__':
    args = get_argument_parser().parse_args()
    search_queries = ['программист', 'программирование', 'Python']
    session = try_to_fetch_existing_session() or ask_for_password_and_get_session()
    api = vk.API(session)
    pages = get_vk_public_page_list(api, search_queries)
    page_ids = get_vk_public_page_id_set(pages)
    print(page_ids)
