"""Abstract classes for Triggers and Values."""

from sqlalchemy import (
    Column,
    Integer,
    Text,
    DateTime,
    ForeignKey
)

from sqlalchemy.orm import (
    relationship
)

from sqlalchemy.ext.declarative import declared_attr

from arguxserver.util import TRIGGER_EXPR


# pylint: disable=too-few-public-methods
class AbstractValue(object):

    """
    AbstractValue class.

    All value types must be a subclass of the AbstractValue class.
    """

    id = Column(Integer, primary_key=True)  # pylint: disable=invalid-name
    timestamp = Column(DateTime, nullable=False)

    # pylint: disable=no-self-use
    @declared_attr
    def item_id(self):
        """Return Item-id integer related to this value."""
        return Column(Integer, ForeignKey('item.id'), nullable=False)


# pylint: disable=too-few-public-methods
class AbstractSimpleTrigger(object):

    """
    AbstractSimpleTrigger class.

    All simple-trigger types must be a subclass of
    the AbstractSimpleTrigger class.

    """

    id = Column(Integer, primary_key=True)  # pylint: disable=invalid-name
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=False, default="")
    rule = Column(Text, nullable=False)

    trigger_handlers = {}

    # pylint: disable=no-self-use
    @declared_attr
    def severity_id(self):
        """Return TriggerSeverity-id integer related to this trigger."""
        return Column(Integer, ForeignKey('trigger_severity.id'), nullable=False)

    # pylint: disable=no-self-use
    @declared_attr
    def severity(self):
        """Return TriggerSeverity object related to this trigger."""
        return relationship("TriggerSeverity")

    # pylint: disable=no-self-use
    @declared_attr
    def item_id(self):
        """Return Item-id integer related to this trigger."""
        return Column(Integer, ForeignKey('item.id'), nullable=False)

    # pylint: disable=no-self-use
    @declared_attr
    def item(self):
        """Return Item object related to this trigger."""
        return relationship("Item")

    @staticmethod
    def validate_rule(rule):
        """Validate Trigger-Rule."""
        i = TRIGGER_EXPR.match(rule)

        if i is None:
            return False

        ret = [i.group(2), i.group(2), i.group(3), i.group(4)]

        return ret


# pylint: disable=too-few-public-methods
class AbstractSimpleAlert(object):

    """
    AbstractSimpleAlert class.

    All simple-alert types must be a subclass of
    the AbstractSimpleAlert class.
    """

    id = Column(Integer, primary_key=True)  # pylint: disable=invalid-name
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
