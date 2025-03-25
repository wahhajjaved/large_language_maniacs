import urllib.request
import urllib.error
import json
import time
from datetime import datetime, timedelta

PATH_TO_LATEST_BUILD = "http://localhost:8010/json/builders/%s/builds/-1?as_text=0"

class NotificationSource:
    def get_build_status(self, build_name):
        try:
            data = urllib.request.urlopen(PATH_TO_LATEST_BUILD % build_name).read()
        except urllib.error.URLError:
            return {"error": "Can't get status", "name": build_name}

        j = json.loads(data.decode('utf8'))
        duration = datetime.fromtimestamp(j["times"][1]) - datetime.fromtimestamp(j["times"][0])
        start_date = datetime.fromtimestamp(j["times"][0])
        diff_date = datetime.fromtimestamp(time.time()) - start_date
        too_long = diff_date > timedelta(hours=24)

        steps = j["steps"]
        success = 0
        skipped = 0
        failed = []
        for step in steps:
            name = step["text"][0]
            res = step["results"][0]
            if res == 0:
                success += 1
            elif res == 3:
                skipped += 1
            else:
                failed.append(name)

        return {"name": build_name, "success": success, "skipped": skipped,
                "failed": failed, "too_long": too_long, "duration": duration,
                "start_date": start_date}

    def format_td(self, td):
        h = td.seconds // 3600
        m = (td.seconds - h * 3600) // 60
        if h == 0:
            return "%dmin" % m
        return "%dh%02d" % (h, m)


    def get_text(self):

        r1 = self.get_build_status("backup_work")
        r1["name"] = "wrk"
        r2 = self.get_build_status("backup_salon")
        r2["name"] = "sal"

        full_res_prio = ""
        res = ""

        res = ""
        for results in [r1, r2]:
            # res prio has data to be displayed first (crashes, errors)
            res_prio = ""
            res += results["name"] + " "
            if "error" in results:
                res_prio += "FATAL:%s" % (results["error"])
            else:
                failed = results["failed"]
                if len(failed) > 0:
                    res_prio += "FAIL:%d(%s) " % (len(failed), ",".join(failed))
                if results["too_long"]:
                    res_prio += "WARN: Backup too old!"
                res += "OK:%d SKIP:%d dur:%s %s" % (results["success"], results["skipped"],
                                                  self.format_td(results["duration"]),
                                                  results["start_date"].strftime("%d%b"))
            if res_prio:
                full_res_prio = results["name"] + " " + res_prio + "\n"
            res += "\n"

        return full_res_prio + res
