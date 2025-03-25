from django.db import models
import requests
# Create your models here.


class UserIpInfo(models.Model):
    ip_address = models.IPAddressField()
    real_address = models.CharField(max_length=256, blank=True)
    visit_time = models.DateTimeField(auto_now_add=True)

    def get_real_address(self):
        r = requests.get(
            "http://ip.taobao.com//service/getIpInfo.php",
            params={"ip": self.ip_address})
        res = r.json()
        if res["code"] == "0":
            return res["city"]
        return "Unknown"

    def before_save(self):
        self.real_address = self.get_real_address()

    @property
    def protected_ip(self):
        parts = self.ip_address.split(".")
        parts = parts[:3]
        return ".".join(parts) + ".*"
