# -*- coding: utf-8 -*-

import logging

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot
from Schedule.SchedulerCountdown import CountdownMessageBox

ALL_TASKS_COMPLETED = 0
SELECTED_TASKS_COMPLETED = 1

ACTION_NONE = 0
ACTION_POWEROFF = 1
ACTION_HYBRIDSLEEP = 2
ACTION_HIBERNATE = 3
ACTION_SUSPEND = 4

# Scheduler controls what happens when tasks finished.
class Scheduler(QObject):
    sigSchedulerSummaryUpdated = pyqtSignal()
    sigActionConfirmed = pyqtSignal(bool)

    POSSIBLE_ACTWHENS = (
        (ALL_TASKS_COMPLETED, "所有的"),
        (SELECTED_TASKS_COMPLETED, "选中的"),
    )

    _ALL_POSSIBLE_ACTIONS = (
        (ACTION_NONE, "无"),
        (ACTION_POWEROFF, "关机", "poweroff"),
        (ACTION_HYBRIDSLEEP, "混合休眠", "hybridsleep"),
        (ACTION_HIBERNATE, "休眠", "hibernate"),
        (ACTION_SUSPEND, "睡眠", "suspend"),
    )
    POSSIBLE_ACTIONS = None

    app = None
    _action = None
    _actWhen = None
    _waitingTaskIds = None         # user-selected tasks
    _stillWaitingTasksNumber = 0   # (computed) user-selected tasks - nolonger running tasks
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self._waitingTaskIds = set()
        self.reset()

        # compute POSSIBLE_ACTIONS
        self.POSSIBLE_ACTIONS = []
        for action in self._ALL_POSSIBLE_ACTIONS:
            if len(action) == 2:
                # ACTION_NONE
                self.POSSIBLE_ACTIONS.append(action)
            else:
                if self.app.settings.get("scheduler", action[2] + "cmd"):
                    self.POSSIBLE_ACTIONS.append(action)

        self.app.etmpy.runningTasksStat.sigTaskNolongerRunning.connect(self.slotMayAct)
        self.app.etmpy.runningTasksStat.sigTaskAdded.connect(self.slotMayAct)
        self.sigActionConfirmed[bool].connect(self.act)

    @property
    def actWhen(self):
        # tasks
        return self._actWhen

    @actWhen.setter
    def actWhen(self, value):
        raise NotImplementedError("use set method")

    @property
    def waitingTaskIds(self):
        return self._waitingTaskIds

    @waitingTaskIds.setter
    def waitingTaskIds(self, value):
        raise NotImplementedError("use set method")

    @property
    def action(self):
        return self._action

    @action.setter
    def action(self, value):
        raise NotImplementedError("use set method")

    @classmethod
    def getActionName(cls, actionId):
        return cls.POSSIBLE_ACTIONS[actionId][1]

    def getSummary(self):
        # return either True / False / str
        # True -> action undergoing, system shutting down
        # False -> scheduled to do nothing
        # str -> one sentence summary
        if self.action == ACTION_NONE:
            return False

        if self._stillWaitingTasksNumber:
            return "{}个任务结束后{}".format(self._stillWaitingTasksNumber,
                                            self.getActionName(self.action))
        else:
            return True

    @pyqtSlot(int)
    def slotMayAct(self):
        if self.action == ACTION_NONE:
            self.sigSchedulerSummaryUpdated.emit()
            logging.info("cancel schedule because action is none")
            return

        runningTaskIds = self.app.etmpy.runningTasksStat.getTIDs()
        if self.actWhen == SELECTED_TASKS_COMPLETED:
            stillWaitingTaskIds = set(runningTaskIds) & self.waitingTaskIds
            self._stillWaitingTasksNumber = len(stillWaitingTaskIds)
        elif self.actWhen == ALL_TASKS_COMPLETED:
            self._stillWaitingTasksNumber = len(runningTaskIds)
        else:
            raise Exception("Unknown actWhen.")

        if self._stillWaitingTasksNumber > 0:
            self.sigSchedulerSummaryUpdated.emit()
            logging.info("not take action because desired tasks are running.")
            return

        self.confirmDlg = CountdownMessageBox(self.getActionName(self.action))
        self.confirmDlg.show()
        self.confirmDlg.activateWindow()
        self.confirmDlg.raise_()

    def set(self, actWhen, taskIds, action):
        if actWhen == SELECTED_TASKS_COMPLETED:
            self._actWhen, self._waitingTaskIds, self._action = actWhen, taskIds, action
        else:
            self._actWhen, self._action = actWhen, action

        self.slotMayAct()

    def reset(self):
        # Should be called when
        # 1. app starts up
        # 2. immediately before power-control commands are run
        # 3. action is canceled by user
        self.set(ALL_TASKS_COMPLETED, set(), ACTION_NONE)

    @pyqtSlot(int)
    def act(self, confirmed):
        del self.confirmDlg
        if confirmed:
            if self.action == ACTION_POWEROFF:
                cmd = self.app.settings.get("scheduler", "poweroffcmd")
            elif self.action == ACTION_HYBRIDSLEEP:
                cmd = self.app.settings.get("scheduler", "hybridsleepcmd")
            elif self.action == ACTION_HIBERNATE:
                cmd = self.app.settings.get("scheduler", "hibernatecmd")
            elif self.action == ACTION_SUSPEND:
                cmd = self.app.settings.get("scheduler", "suspendcmd")
            else:
                raise Exception("Unknown action")
            self.reset()
            print(cmd) # TODO
        else:
            self.reset()
