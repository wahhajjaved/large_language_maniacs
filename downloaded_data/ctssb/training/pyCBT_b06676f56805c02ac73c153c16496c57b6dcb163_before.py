import pytz
from dateutil.parser import parse
from datetime import datetime, timedelta


def timezone_shift(datetime_str=None, in_tz="America/Caracas", out_tz="UTC", fmt="RFC3339"):
    """Turns a datetime string from one timezone to another in a given format

    Given a datetime string in a timezone 'in_tz', this function performs the
    conversion to 'out_tz' (only if 'in_tz' not equal to 'out_tz') and returns
    the result in a given format 'fmt'.

    Parameters
    ----------
    datetime_str: str
        A string representation of a datetime.
    in_tz, out_tz: str
        The name of a timezone (ex. EST, America/Caracas).
    fmt: str
        A datetime format string (valid for datetime.strftime)
        or one of the options:
            - RFC3339
            - UNIX
            - JSON
        Any the listed options will be in UTC regardless of 'out_tz'.
    """
    if datetime_str is None:
        dt = datetime.now(tzinfo=pytz.timezone(in_tz))
    else:
        try:
            dt = parse(datetime_str)
        except ValueError:
            try:
                dt = timedelta(np.float64(dt_str)) + datetime(1970, 1, 1)
            except ValueError:
                raise ValueError("Unknown datetime format for {}.".format(datetime_str))

    if dt.tzinfo is None: dt = dt.replace(tzinfo=pytz.timezone(in_tz))

    if fmt in ["RFC3339", "UNIX", "JSON"]: out_tz = "UTC"
    if in_tz != out_tz: dt.astimezone(pytz.timezone(out_tz))

    if fmt == "UNIX":
        dt_str = round((dt - datetime(1970, 1, 1, tzinfo=pytz.UTC)).total_seconds(), 9)
    elif fmt == "JSON":
        dt_str = round((dt - datetime(1970, 1, 1, tzinfo=pytz.UTC)).total_seconds()*1000.0, 6)
    elif fmt == "RFC3339":
        dt_str = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        dt_str = dt.strftime(fmt)

    return dt_str
