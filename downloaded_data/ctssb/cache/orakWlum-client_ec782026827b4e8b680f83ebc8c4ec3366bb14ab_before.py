class Consumptions (object):
    """
    okW Consumptions
    """

    def __init__(self, API):
        self.API = API

    def by_cups (self, CUPS, date_start, date_end):
        """
        Return consumptions for a CUPS (or a list) between a range of dates

        - dates must be timestamps
        - CUPS can be a string or a list of strings with the CUPS
        """
        params = {
            "date_start": date_start,
            "date_end": date_end,
            "cups": CUPS,
        }
        return self.API.get(resource="/consumptions", params=params)

    def by_aggregates (self, date_start, date_end, aggregates=None):
        """
        Return consumptions grouped by REE aggregates between a range of dates

        - dates must be timestamps
        - aggregates can be the list of aggregates to reach or None
        """
        params = {
            "date_start": date_start,
            "date_end": date_end,
        }
        return self.API.get(resource="/consumptions_by_aggregates", params=params)
