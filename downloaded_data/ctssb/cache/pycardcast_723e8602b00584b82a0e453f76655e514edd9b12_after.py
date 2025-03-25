# Copyright © 2015 Elizabeth Myers.
# All rights reserved.
# This file is part of the pycardcast project. See LICENSE in the root
# directory for licensing information.

from pycardcast.util import isoformat
from pycardcast import NotFoundError, RetrievalError


class CardNotFoundError(NotFoundError):
    """Card or cards were not found."""


class CardRetrievalError(RetrievalError):
    """Error retrieving card or cards."""


class Card:

    def __init__(self, created, cid, text):
        self.created = created
        self.cid = cid
        self.text = text


class BlackCard(Card):

    def __init__(self, created, cid, text, pick=None):
        # Remove blanks
        if pick is None:
            self.pick = len(text) - 1
            if self.pick == 0:
                # This shouldn't happen...
                self.pick = 1
        else:
            self.pick = pick

        # Avoid "foo?_____" problem
        if text[-1] == '' and text[-2][-1] != ' ':
            text.pop()

        text = "_____".join(filter(None, text))

        super().__init__(created, cid, text)

    @classmethod
    def from_json(cls, data):
        if "calls" in data:
            return [cls.from_json(c) for c in data["calls"]]

        if data["id"] == "not_found":
            raise CardNotFoundError(data["message"])

        return cls(isoformat(data["created_at"]), data["id"], data["text"])

    def __hash__(self):
        return hash((self.pick, self.created, self.cid, self.text)) + 1

    def __repr__(self):
        return "BlackCard(created={}, cid={}, text={}, pick={})".format(
            self.created, self.cid, self.text, self.pick)


class WhiteCard(Card):
    
    @classmethod
    def from_json(cls, data):
        if "responses" in data:
            return [cls.from_json(c) for c in data["responses"]]

        if data["id"] == "not_found":
            raise CardNotFoundError(data["message"])

        return cls(isoformat(data["created_at"]), data["id"], data["text"])

    def __hash__(self):
        return hash((self.created, self.cid, self.text)) - 1

    def __repr__(self):
        return "WhiteCard(created={}, cid={}, text={})".format(
            self.created, self.cid, self.text)
