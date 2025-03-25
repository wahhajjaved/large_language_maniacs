# -*- coding: utf-8 -*-

from datetime import datetime, timedelta
import logging
import re

from celery import Celery
from celery.schedules import crontab

import config
from log import init_log
from model import User
from shike import ShikeClient
from wechat import post_template_message, WeChatApiClient

app = Celery("tasks", broker=config.broker, backend=config.backend)
app.conf.CELERYBEAT_SCHEDULE = {
    "monitor": {
        "task": "tasks.monitor",
        "schedule": crontab(minute="*/5")
    }
}
app.conf.CELERY_REDIRECT_STDOUTS_LEVEL = "DEBUG"

@app.task(bind=True)
def run(self, client, user):
    logger = logging.getLogger("shike." + user.uid)
    delay = config.req_break
    try:
        apps = client.load_apps()
        availables = client.filter_apps(apps)
        # 先判断是否有正在处理的app
        processing = list(filter(lambda o: int(o["status"])==0, availables))
        if processing:
            # 正在处理的app查询是否已经可以打开
            app = processing[0]
            flg = client.get_app_status(app)
            if flg == "waitOpen":
                send_wechat_msg(user.openid, config.down_template, "",
                    first=app["name"],
                    remark="请及时打开！")
                delay = config.down_break
        elif availables:
            # 有应用可供下载
            availables = client.sort_app(availables)
            app = availables[0]
            logger.info("Got! " + app["name"])
            
            collected = client.collect_app(app)
            if collected:
                logging.getLogger("stat." + user.uid).info(app["down_price"] + "\t" + app["name"])
            remark = "，任务已自动领取了哦！ " if collected else ""
            send_wechat_msg(user.openid, config.got_template, "",
                first=app["name"],
                keyword1=app["name"],
                keyword2=str(int(app["file_size_bytes"])/1024/1024) + "MB",
                keyword3=app["order_status_disp"],
                remark="一共" + str(len(availables)) + "个应用可供下载" + remark)
                
            if collected:
                delay = config.success_break
        run.apply_async((client, user), countdown=delay)
    except Exception as e:
        logger.error("An error occured: " + str(e))
        self.retry(exe=e, countdown=delay)

@app.task
def monitor():
    pattern = r"^\[(?P<level>\w+)\]\s+(?P<name>[^\s]+)\s+(?P<date>\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(?P<msg>.+)"
    now = datetime.now()
    with open("errlog.txt") as f:
        lines = f.readlines()
        records = list(map(lambda o: re.search(pattern, o).groupdict(), lines))
        for record in records:
            record["date"] = datetime.strptime("2016-" + record["date"], "%Y-%m-%d %H:%M:%S")

        # 检查过去5分钟的异常数
        excs = list(filter(lambda o: now - o["date"] < timedelta(minutes=5) and o["level"] != "WARNING", records))
        num = len(excs)
        if num > config.alert_num1:
            send_wechat_msg(config.alert_openid, config.alert_template, "",
                keyword1="error", keyword2=num, keyword3=excs[-1]["msg"])
        # 检查过去30分钟的日志数
        excs = filter(lambda o: now - o["date"] < timedelta(minutes=30), records)
        num = len(list(excs))
        if num > config.alert_num2:
            send_wechat_msg(config.alert_openid, config.alert_template, "",
                keyword1="warning", keyword2=num, keyword3=excs[-1]["msg"])
                
    with open("debuglog.txt") as f:
        lines = f.readlines()
        records = list(map(lambda o: re.search(pattern, o).groupdict(), lines))
        for record in records:
            record["date"] = datetime.strptime("2016-" + record["date"], "%Y-%m-%d %H:%M:%S")
        
        # 检查过去5分钟的日志数
        excs = list(filter(lambda o: now - o["date"] < timedelta(minutes=5) and o["level"] != "WARN", records))
        num = len(excs)
        if num < 10:
            # 过去5分钟日志数少于10条
            send_wechat_msg(config.alert_openid, config.alert_template, "",
                keyword1="terminal", keyword2=num, keyword3=excs[-1]["msg"])

def send_wechat_msg(openid, template_id, url="", **kwargs):
    """发送微信消息"""
    resp, code = post_template_message(wechat,
        openid, template_id, url, **kwargs)
    if code:
        main_logger.error("WeChatError: " + str(resp))
    else:
        main_logger.info("WeChatSendSuccess: " + str(resp))
  
# 初始化微信ApiClient  
wechat = WeChatApiClient(config.appid, config.appsecret)
wechat.on_servererror = lambda resp, *args, **kwargs: main_logger.error("WeChatServerError: " + str(args[1]))
wechat.on_wechaterror = lambda resp, *args, **kwargs: main_logger.error("WeChatClientError: " + str(resp.text))
wechat.on_wechatgranted = lambda resp, *args, **kwargs: main_logger.info("微信token更新: " + str(resp.text))

# 初始化日志
init_log()
main_logger = logging.getLogger("shike")