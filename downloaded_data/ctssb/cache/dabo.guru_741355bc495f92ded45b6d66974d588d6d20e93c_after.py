import logging
import time
from datetime import datetime

from flask import render_template
from flask import request

from content import app, redis

PLUGIN_SET = "statistics:plugins"
# (plugin_name): set(plugin_version)
PLUGIN_VERSION_LIST = "statistics:live:{}:versions"
# (plugin_name, plugin_version): zset(server_guid: expiration_time)
VERSION_SERVER_HASH = "statistics:live:{}:version:{}:servers"
# (plugin_name, server_guid): hash("players": player_count, "server": server_version)
SERVER_DATA_SET = "statistics:live:{}:server:{}:data"
# (plugin_name): list(recorded_time)
RECORD_LIST = "statistics:{}:record-list"
# (plugin_name, recorded_time): hash(plugin_version: plugin_count)
RECORD_PLUGIN_VERSION_PLUGIN_COUNTS = "statistics:{}:record:{}:version-counts"
# (plugin_name, recorded_time): int
RECORD_TOTAL_PLAYERS = "statistics:{}:record:{}:total-player-count"
# (plugin_name, recorded_time): set(plugin_version)
RECORD_PLUGIN_VERSIONS = "statistics:{}:record:{}:versions"
# (plugin_name, recorded_time, plugin_version): hash(server_version: plugin_count)
RECORD_SERVER_VERSION_PLUGIN_COUNTS = "statistics:{}:record:{}:version:{}:server-version-counts"


@app.route("/statistics/v1/<plugin>/post", methods=["POST"])
def post_statistics(plugin):
    if request.content_length > 512:
        return """Error: too large of a message""", 400
    json = request.get_json()
    if json is None:
        logging.info("Non-json data sent to plugin/skywars/post: {}", request.get_data().decode())
        return """Error: invalid data""", 400

    guid = json.get("instance_uuid")
    plugin_version = json.get("plugin_version")
    server_version = json.get("server_version")
    player_count = json.get("online_players")

    if (guid is None or plugin_version is None or player_count is None
        or server_version is None or not isinstance(player_count, int)):
        logging.info("Invalid request to skywars statistics: {}", json)
        return """Error: invalid data""", 400

    plugin = plugin.lower().strip()

    pipe = redis.pipeline(transaction=True)

    pipe.sadd(PLUGIN_SET, plugin)
    pipe.sadd(PLUGIN_VERSION_LIST.format(plugin), plugin_version)

    servers_hash_key = VERSION_SERVER_HASH.format(plugin, plugin_version)
    expiration_time = int(time.time()) + 2 * 60 * 60  # expires in two hours
    pipe.zadd(servers_hash_key, expiration_time, guid)

    data_key = SERVER_DATA_SET.format(plugin, guid)
    pipe.hmset(data_key, {"players": player_count, "server": server_version})
    pipe.expire(data_key, 2 * 61 * 60)  # one minute after key above expires

    pipe.execute()
    return """Data successfully submitted"""


@app.route("/statistics/<plugin>/")
def get_statistics(plugin):
    if "page" in request.args:
        try:
            page = int(request.args["page"])
        except ValueError:
            page = 0
        else:
            if page < 0:
                page = 0
    else:
        page = 0

    plugin = plugin.lower().strip()

    if not redis.sismember(PLUGIN_SET, plugin):
        return """No data gathered for plugin '{}'""".format(plugin)

    first_record = page * 10
    last_record = first_record + 9

    rl_key = RECORD_LIST.format(plugin)
    record_name_list = redis.lrange(rl_key, first_record, last_record)

    while not record_name_list:
        if page <= 0:
            return """Plugin '{}' known, but no records have yet been generated.""".format(plugin)
        else:
            page = page - 1
            record_name_list = redis.lrange(rl_key, first_record, last_record)

    total_record_count = redis.llen(rl_key)

    prev_page_available = page > 0
    next_page_available = total_record_count > last_record + 1

    record_list = []

    for index, record in enumerate(record_name_list):
        record = record.decode('utf-8')
        record_time = datetime.fromtimestamp(int(record)).strftime("%b %d %Y %H:%M")

        total_players = int(redis.get(RECORD_TOTAL_PLAYERS.format(plugin, record)).decode('utf-8'))
        total_servers = 0
        version_list = []

        plugin_version_counts = redis.hgetall(RECORD_PLUGIN_VERSION_PLUGIN_COUNTS.format(plugin, record))

        for version, server_count in sorted(plugin_version_counts.items(), key=lambda i: i[0]):
            version = version.decode('utf-8')
            server_count = int(server_count.decode('utf-8'))
            total_servers += server_count

            svc_key = RECORD_SERVER_VERSION_PLUGIN_COUNTS.format(plugin, record, version)
            server_version_counts = {key.decode('utf-8'): int(value.decode('utf-8'))
                                     for key, value in redis.hgetall(svc_key).items()}

            version_list.append({
                "version": version,
                "server_count": server_count,
                "server_version_counts": server_version_counts,
            })
        record_list.append({
            "date": record_time,
            "total_servers": total_servers,
            "total_players": total_players,
            "plugin_versions": version_list
        })

    return render_template("display-statistics.html",
                           plugin=plugin,
                           records=record_list,
                           page=page,
                           next_page_available=next_page_available,
                           prev_page_available=prev_page_available)
