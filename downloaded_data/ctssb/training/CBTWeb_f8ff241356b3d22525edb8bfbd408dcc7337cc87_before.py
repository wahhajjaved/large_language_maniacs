import numpy as np
from pyCBT.providers.oanda import historical

from . import instruments

class Datasets(object):

    def __init__(self, client, settings):
        self.client = client
        self.settings = settings

    def download(self):
        data = historical.Candles(
            client=self.client,
            instrument=self.settings.get("candles_symbol"),
            resolution=self.settings.get("resolution"),
            from_date=self.settings.get("datetimes")[0],
            to_date=self.settings.get("datetimes")[1],
            datetime_fmt="JSON",
            timezone=self.settings.get("timezone")
        ).as_dictionary()
        self.for_candles = {"name": instruments[self.settings.get("candles_symbol")]["name"], "data": data}

        price_i = self.for_candles["data"][self.settings.get("price", "Close")][-self.settings.get("timeframe"):]
        prices_j = []
        for symbol in self.settings.get("charts_symbols"):
            prices_j += [
                historical.Candles(
                    client=self.client,
                    instrument=symbol,
                    resolution=self.settings.get("resolution"),
                    from_date=self.settings.get("datetimes")[0],
                    to_date=self.settings.get("datetimes")[1],
                    datetime_fmt="JSON",
                    timezone=self.settings.get("timezone")
                ).as_dictionary()[self.settings.get("price", "Close")][-self.settings.get("timeframe"):]
            ]
        self.for_charts = {
            "name_i": instruments[self.settings.get("candles_symbol")]["name"],
            "names_j": [instruments[symbol]["name"] for symbol in self.settings.get("charts_symbols")],
            "price_i": price_i,
            "prices_j": prices_j
        }

    def get_highcharts_candles(self):
        """Returns the candles data dictionary
        """
        ohlc = []
        volume = []
        for i in xrange(len(self.for_candles["data"]["Datetime"])):
            ohlc += [[
                self.for_candles["data"]["Datetime"][i],
                self.for_candles["data"]["Open"][i],
                self.for_candles["data"]["High"][i],
                self.for_candles["data"]["Low"][i],
                self.for_candles["data"]["Close"][i]
            ]]
            volume += [[
                self.for_candles["data"]["Datetime"][i],
                self.for_candles["data"]["Volume"][i]
            ]]

        data = {
            "name": self.for_candles["name"],
            "ohlc": ohlc,
            "volume": volume
        }
        return data

    def get_highcharts_correlations(self):
        data = {
            "name": self.for_charts["name_i"],
            "categories": self.for_charts["names_j"],
            "series": {
                "negative": [],
                "positive": []
            }
        }
        price_i = self.for_charts["price_i"]
        for price_j in self.for_charts["prices_j"]:
            corr_ij = np.corrcoef(price_i, price_j)[1, 0]
            if corr_ij < 0:
                data["series"]["negative"] += [-corr_ij]
                data["series"]["positive"] += [0.0]
            else:
                data["series"]["negative"] += [0.0]
                data["series"]["positive"] += [corr_ij]

        return data

    def get_highcharts_heatmap(self):
        data = {
            "name": self.for_charts["name_i"],
            "categories": self.for_charts["names_j"],
            "series": {
                "negative": [],
                "positive": []
            }
        }
        price_i = self.for_charts["price_i"]
        for price_j in self.for_charts["prices_j"]:
            # TODO: parse symbol name:
            #       * is there a common & currency? NO: cycle
            #       * is common currency above or below
            #       * compute exrate_ij = price_j / price_i
            #       * compute heat_ij = (exrate_ij[-1] - exrate_ij[0]) / exrate_ij[0] * 100.0
            exrate_ij = np.array(price_j) / np.array(price_i)
            heat_ij = (exrate_ij[-1] - exrate_ij[0]) / exrate_ij[0] * 100.0
            if heat_ij < 0:
                data["series"]["negative"] += [-heat_ij]
                data["series"]["positive"] += [0.0]
            else:
                data["series"]["negative"] += [0.0]
                data["series"]["positive"] += [heat_ij]

        return data

    def get_highcharts_volatility(self):
        data = {
            "name": self.for_charts["name_i"],
            "categories": self.for_charts["names_j"],
            "volatility": []
        }
        for price_j in self.for_charts["prices_j"]:
            mu = np.median(price_j)
            sg = np.percentile(price_j, [16, 84])
            data["volatility"] += [[round((sg[0]/mu-1)*100, 2), round((sg[1]/mu-1)*100, 2)]]

        return data
