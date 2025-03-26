# this project is licensed under the WTFPLv2, see COPYING.txt for details

"""Multi-splitter widget

The multi-splitter widget allows to have complex splitting layouts, with arbitrary levels of horizontal/vertical
splits. For example, it's possible to have editors layed out this way in a window::

	+--+----+----+
	|  |    |    |
	+--+----+    |
	|       |    |
	|       +----+
	|       |    |
	+-------+----+

Each split may contain a :any:`eye.widgets.tabs.TabWidget`, containing a single or multiple tabs.
"""

from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt, QPoint, QRect, QTimer
from PyQt5.QtWidgets import QSplitter, QWidget, QStackedLayout
Signal = pyqtSignal

import logging

from .. import consts
from .helpers import WidgetMixin
from ..qt import Slot

__all__ = ('SplitManager', 'Splitter', 'QSplitter')


LOGGER = logging.getLogger(__name__)


class Splitter(QSplitter, WidgetMixin):
	"""Splitter widget for a single splitting level

	`Splitter` objects are handled by the :any:`SplitManager` widget.
	"""

	HandleBar = 42

	def __init__(self, **kwargs):
		super(Splitter, self).__init__(**kwargs)

		self.addCategory('splitter')

	def children(self):
		for i in range(self.count()):
			yield self.widget(i)

	def childAt(self, pos):
		"""Return child widget at position

		:type pos: QPoint
		:param pos: relative to the top-left corner of this `Splitter` (which is at `(0, 0)`).
		:return: return value will be `HandleBar` if `pos` is right on a handle bar of this splitter.
		         If the final widget under `pos` is contained in a sub-`Splitter` or sub-sub-`Splitter`,
		         it won't be returned, only the direct child, the direct sub-`Splitter` will be returned.
		"""
		if not self.rect().contains(pos):
			return None
		for i in range(self.count()):
			w = self.widget(i)
			if w.geometry().contains(pos):
				return w
		return self.HandleBar

	def parentManager(self):
		"""Returns the :any:`SplitManager` managing this splitter

		:rtype: SplitManager
		"""
		w = self.parent()
		while not isinstance(w, SplitManager):
			w = w.parent()
		return w

	def widgets(self):
		"""Return all direct children widgets

		Children returned by this method may be `Splitter` widgets if there are sub-splitters.
		:rtype: list
		"""
		return [self.widget(i) for i in range(self.count())]

	def removeChild(self, widget):
		assert self.isAncestorOf(widget)
		assert self is not widget

		widget.setParent(None)

	def replaceChild(self, child, new):
		assert child is not new
		assert self is not child
		assert self is not new
		assert self.isAncestorOf(child)

		idx = self.indexOf(child)
		child.setParent(None)
		self.insertWidget(idx, new)


class SplitManager(QWidget, WidgetMixin):
	"""Split manager widget

	This widget allows to do multiple levels of splitter without having to manage the levels by hand.

	Instances of this class have the `"splitmanager"` category by default.
	"""

	SplitterClass = Splitter

	def __init__(self, **kwargs):
		super(SplitManager, self).__init__(**kwargs)

		self.root = self.SplitterClass(orientation=Qt.Horizontal)

		layout = QStackedLayout()
		self.setLayout(layout)
		layout.addWidget(self.root)

		self.optimizeTimer = QTimer()
		self.optimizeTimer.setInterval(0)
		self.optimizeTimer.setSingleShot(True)
		self.optimizeTimer.timeout.connect(self._optimize)

		self.addCategory('splitmanager')

	# TODO check if it can be integrated synchronously in calls
	@Slot()
	def _optimize(self):
		splitters = [self.root]
		i = 0
		while i < len(splitters):
			spl = splitters[i]
			splitters.extend(c for c in spl.children() if isinstance(c, QSplitter))
			i += 1
		splitters.pop(0)
		splitters.reverse()

		for spl in splitters:
			parent = spl.parent()
			if parent is None:
				continue

			if spl.count() == 0:
				parent.removeChild(spl)
			elif spl.count() == 1:
				child = next(iter(spl.children()))
				parent.replaceChild(spl, child)

	## split/move/delete
	def splitAt(self, currentWidget, direction, newWidget):
		if currentWidget is None:
			parent = self.root
			idx = 0
		else:
			assert self.isAncestorOf(currentWidget)
			parent = currentWidget.parent()
			idx = parent.indexOf(currentWidget)

		orientation = consts.ORIENTATIONS[direction]
		if parent.orientation() == orientation:
			if direction in (consts.DOWN, consts.RIGHT):
				idx += 1
			parent.insertWidget(idx, newWidget)
		else:
			# currentWidget is moved, so it may lose focus
			refocus = currentWidget.hasFocus()

			newSplit = self.SplitterClass(orientation=orientation)
			parent.insertWidget(idx, newSplit)
			if currentWidget:
				newSplit.addWidget(currentWidget)
			newSplit.addWidget(newWidget)

			if refocus:
				currentWidget.setFocus()

	def moveWidget(self, currentWidget, direction, newWidget):
		if currentWidget is newWidget:
			LOGGER.info('will not move %r over itself', currentWidget)
			return

		self.removeWidget(newWidget)
		self.splitAt(currentWidget, direction, newWidget)
		self.optimizeTimer.start()

	def removeWidget(self, widget):
		if not self.isAncestorOf(widget):
			LOGGER.info("cannot remove widget %r since it doesn't belong to %r", widget, self)
			return

		spl, _ = self.childId(widget)
		spl.removeChild(widget)
		self.optimizeTimer.start()

	## balance
	@Slot()
	def balanceSplitsRecursive(self, startAt=None):
		for w in self._iterRecursive(startAt):
			if isinstance(w, self.SplitterClass):
				self.balanceSplits(w)

	def balanceSplits(self, spl):
		spl.setSizes([1] * spl.count())  # qt redistributes space

	## getters
	def allChildren(self):
		"""Get all non-splitter children widgets

		:return: the direct children of `Splitter`s that are not `Splitter`s themselves
		:rtype: list
		"""
		return [w for w in self._iterRecursive() if not isinstance(w, self.SplitterClass)]

	def childRect(self, widget):
		return QRect(widget.mapTo(self, QPoint()), widget.size())

	def childId(self, widget):
		spl = widget
		while not isinstance(spl, QSplitter):
			spl = spl.parent()
		return (spl, spl.indexOf(widget))

	def deepChildAt(self, pos):
		"""Get the non-splitter widget at `pos`

		:param pos: the point where to look a widget, in coordinates relative to top-left corner of
		              this `SplitManager`
		:type pos: QPoint
		:return: the first child at position `pos` that is not a splitter, unlike :any:`Splitter.childAt`.
		:rtype: QWidget
		"""
		widget = self.root
		while isinstance(widget, QSplitter):
			widget = widget.childAt(widget.mapFrom(self, pos))
		return widget

	def _iterRecursive(self, startAt=None):
		if startAt is None:
			startAt = self.root

		splitters = [startAt]
		yield startAt
		while splitters:
			spl = splitters.pop()
			for i in range(spl.count()):
				w = spl.widget(i)
				if isinstance(w, self.SplitterClass):
					splitters.append(w)
				yield w

	## close management
	def requestClose(self):
		for c in self.allChildren():
			if not c.requestClose():
				return False
		return True
