from time import strftime, localtime

from spike.model import db
from shlex import shlex


class NaxsiRules(db.Model):
    __bind_key__ = 'rules'
    __tablename__ = 'naxsi_rules'

    id = db.Column(db.Integer, primary_key=True)
    msg = db.Column(db.String(), nullable=False)
    detection = db.Column(db.String(1024), nullable=False)
    mz = db.Column(db.String(1024), nullable=False)
    score = db.Column(db.String(1024), nullable=False)
    sid = db.Column(db.Integer, nullable=False, unique=True)
    ruleset = db.Column(db.String(1024), nullable=False)
    rmks = db.Column(db.Text, nullable=True, server_default="")
    active = db.Column(db.Integer, nullable=False, server_default="1")
    negative = db.Column(db.Integer, nullable=False, server_default='0')
    timestamp = db.Column(db.Integer, nullable=False)

    mr_kw = ["MainRule", "BasicRule", "main_rule", "basic_rule"]
    static_mz = {"$ARGS_VAR", "$BODY_VAR", "$URL", "$HEADERS_VAR"}
    full_zones = {"ARGS", "BODY", "URL", "HEADERS", "FILE_EXT", "RAW_BODY"}
    rx_mz = {"$ARGS_VAR_X", "$BODY_VAR_X", "$URL_X", "$HEADERS_VAR_X"}
    sub_mz = list(static_mz) + list(full_zones) + list(rx_mz)

    def __init__(self, msg="", detection="", mz="", score="", sid='42000', ruleset="", rmks="", active=0, negative=0,
                 timestamp=0):
        self.msg = msg
        self.detection = detection
        self.mz = mz
        self.score = score
        self.sid = sid
        self.ruleset = ruleset
        self.rmks = rmks
        self.active = active
        self.negative = 1 if negative == 'checked' else 0
        self.timestamp = timestamp
        self.warnings = []
        self.error = []

    def fullstr(self):
        rdate = strftime("%F - %H:%M", localtime(float(str(self.timestamp))))
        rmks = "# ".join(self.rmks.strip().split("\n"))
        return "#\n# sid: {0} | date: {1}\n#\n# {2}\n#\n{3}".format(self.sid, rdate, rmks, self.__str__())

    def __str__(self):
        negate = 'negative' if self.negative == 1 else ''
        return 'MainRule {} "{}" "msg:{}" "mz:{}" "s:{}" id:{} ;'.format(
            negate, self.detection, self.msg, self.mz, self.score, self.sid)

    def explain(self):
        """ Return a string explaining the rule

         :return str: A textual explanation of the rule
         """
        translation = {'ARGS': 'argument', 'BODY': 'body', 'URL': 'url', 'HEADER': 'header'}
        explanation = 'The rule number <strong>{0}</strong> is '.format(self.sid)
        if self.negative:
            explanation += '<strong>not</strong> '
        explanation += 'setting the '

        scores = []
        for score in self.score.split(','):
            scores.append('<strong>{0}</strong> to <strong>{1}</strong> '.format(*score.split(':', 1)))
        explanation += ', '.join(scores) + 'when it '
        if self.detection.startswith('str:'):
            explanation += 'finds the string <strong>{}</strong> '.format(self.detection[4:])
        else:
            explanation += 'matches the regexp <strong>{}</strong> '.format(self.detection[3:])

        zones = []
        for mz in self.mz.split('|'):
            if mz.startswith('$'):
                current_zone, arg = mz.split(":", 1)
                zone_name = "?"

                for translated_name in translation:  # translate zone names
                    if translated_name in current_zone:
                        zone_name = translation[translated_name]

                if "$URL" in current_zone:
                    regexp = "matching regex" if current_zone == "$URL_X" else ""
                    explanation += "on the URL {} '{}' ".format(regexp, arg)
                else:
                    regexp = "matching regex" if current_zone.endswith("_X") else ""
                    explanation += "in the var with name {} '{}' of {} ".format(regexp, arg, zone_name)
            else:
                zones.append('the <strong>{0}</strong>'.format(translation[mz]))
        return explanation

    def validate(self):
        self.warnings = list()
        self.error = list()

        self.__validate_matchzone(self.mz)
        self.__validate_id(self.sid)
        self.__validate_score(self.score)

        if self.detection.startswith('rx:'):
            self.__validate_detection_rx(self.detection)
        elif self.detection.startswith('str:'):
            self.__validate_detection_str(self.detection)
        else:
            self.error.append("Your 'detection' string must start with str: or rx:")

        if not self.msg:
            self.warnings.append("Rule has no 'msg:'.")
        if not self.score:
            self.error.append("Rule has no score.")

    def __fail(self, msg):
        self.error.append(msg)
        return False

    # Bellow are parsers for specific parts of a rule

    def __validate_detection_str(self, p_str, assign=False):
        if assign is True:
            self.detection = p_str
        return True

    def __validate_detection_rx(self, p_str, assign=False):
        if not p_str.islower():
            self.warnings.append("detection {} is not lower-case. naxsi is case-insensitive".format(p_str))

        try:  # try to validate the regex with PCRE's python bindings
            import pcre
            try:  # if we can't compile the regex, it's likely invalid
                pcre.compile(p_str[3:])
            except pcre.PCREError:
                return self.__fail("{} is not a valid regex:".format(p_str))
        except ImportError:  # python-pcre is an optional dependency
            pass

        if assign is True:
            self.detection = p_str
        return True

    def __validate_score(self, p_str, assign=False):
        for score in p_str.split(','):
            if ':' not in score:
                self.__fail("You score '{}' has no value or name.".format(score))
            name, value = score.split(':')
            if not value.isdigit():
                self.__fail("Your value '{}' for your score '{}' is not numeric.".format(value, score))
            elif not name.startswith('$'):
                self.__fail("Your name '{}' for your score '{}' does not start with a '$'.".format(name, score))
        if assign:
            self.score = p_str
        return True

    def __validate_matchzone(self, p_str, assign=False):
        has_zone = False
        mz_state = set()
        for loc in p_str.split('|'):
            keyword, arg = loc, None
            if loc.startswith("$"):
                if loc.find(":") == -1:
                    return self.__fail("Missing 2nd part after ':' in {0}".format(loc))
                keyword, arg = loc.split(":")

            if keyword not in self.sub_mz:  # check if `keyword` is a valid keyword
                return self.__fail("'{0}' no a known sub-part of mz : {1}".format(keyword, self.sub_mz))

            mz_state.add(keyword)

            # verify that the rule doesn't attempt to target REGEX and STATIC _VAR/URL at the same time
            if len(self.rx_mz & mz_state) and len(self.static_mz & mz_state):
                return self.__fail("You can't mix static $* with regex $*_X ({})".format(', '.join(mz_state)))

            if arg and not arg.islower():  # just a gentle reminder
                self.warnings.append("{0} in {1} is not lowercase. naxsi is case-insensitive".format(arg, loc))

            # the rule targets an actual zone
            if keyword not in ["$URL", "$URL_X"] and keyword in (self.rx_mz | self.full_zones | self.static_mz):
                has_zone = True

        if has_zone is False:
            return self.__fail("The rule/whitelist doesn't target any zone.")

        if assign is True:
            self.mz = p_str

        return True

    def __validate_id(self, p_str, assign=False):
        try:
            num = int(p_str)
            if num < 10000:
                self.warnings.append("rule IDs below 10k are reserved ({0})".format(num))
        except ValueError:
            self.error.append("id:{0} is not numeric".format(p_str))
            return False
        if assign is True:
            self.sid = num
        return True

    @staticmethod
    def splitter(full_str):
        lexer = shlex(full_str)
        lexer.whitespace_split = True
        return list(iter(lexer.get_token, ''))

    def parse_rule(self, full_str):
        """
        Parse and validate a full naxsi rule
        :param full_str: raw rule
        :return: [True|False, dict]
        """
        self.warnings = list()
        self.error = list()

        func_map = {"id:": self.__validate_id, "str:": self.__validate_detection_str,
                    "rx:": self.__validate_detection_rx, "msg:": lambda p_str, assign=False: True,
                    "mz:": self.__validate_matchzone, "negative": lambda p_str, assign=False: True,
                    "s:": self.__validate_score}

        split = self.splitter(full_str)  # parse string
        intersection = set(split).intersection(set(self.mr_kw))

        if not intersection:
            return self.__fail("No mainrule/basicrule keyword.")
        elif len(intersection) > 1:
            return self.__fail("Multiple mainrule/basicrule keywords.")

        split.remove(intersection.pop())  # remove the mainrule/basicrule keyword

        if ";" in split:
            split.remove(";")

        while split:  # iterate while there is data, as handlers can defer
            for keyword in split:
                orig_kw = keyword
                keyword = keyword.strip()

                if keyword.endswith(";"):  # remove semi-colons
                    keyword = keyword[:-1]
                if keyword.startswith(('"', "'")) and (keyword[0] == keyword[-1]):  # remove (double-)quotes
                    keyword = keyword[1:-1]

                parsed = False
                for frag_kw in func_map:
                    if keyword.startswith(frag_kw):  # use the right parser
                        function = func_map[frag_kw]
                        if frag_kw in ('rx:', 'str:'):  # don't remove the leading "str:" or "rx:"
                            payload = keyword
                        else:
                            payload = keyword[len(frag_kw):]

                        if function(payload, assign=True) is True:
                            parsed = True
                            split.remove(orig_kw)
                            break
                        return self.__fail("parsing of element '{0}' failed.".format(keyword))

                if parsed is False:  # we have an item that wasn't successfully parsed
                    return self.__fail("'{}' is an invalid element and thus can not be parsed.".format(keyword))
        return True
