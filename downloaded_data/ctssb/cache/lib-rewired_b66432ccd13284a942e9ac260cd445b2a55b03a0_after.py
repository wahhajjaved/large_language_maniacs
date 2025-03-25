import types
import logging


class Handler():
    def __init__(self, parent):
        self.parent = parent
        self.logger = logging.getLogger('lib:re:wired')

    # switch to the right function
    def process(self, msg):
        type = int(msg.type)
        values = msg.msg
        self.logger.debug("got a %s", type)
        if type == 200:                         # Server Info
            self.serverInfo(values)
            return 1
        elif type == 202:                       # Pong
            self.pong(values)
            return 1
        elif type == 203:                       # Server Banner
            self.serverBanner(values)
            return 1
        elif type == 302:                       # Client Join
            self.clientJoin(values)
            return 1
        elif type == 303:                       # Client Leave
            self.clientLeave(values)
            return 1
        elif type == 304:                       # Status Change
            self.statusChange(values)
            return 1
        elif type == 305:                       # Private Message recieved
            self.privateMessage(values)
            return 1
        elif type == 306:                       # Client Kicked
            self.clientKicked(values)
        elif type == 307:                       # Client Banned
            self.clientBanned(values)
            return 1
        elif type == 331:                       # Private Chat Invitiation
            self.privateChatInvite(values)
            return 1
        elif type == 341:                       # Chat Topic
            self.gotChatTopic(values)
            return 1
        elif type == 602:                       # Chat Topic
            self.gotPrivileges(values)
            return 1
        else:
            self.logger.debug("%s is unkown!", type)
        return 1

    def serverInfo(self, values):
        try:
            self.parent.serverinfo['ServerVersion'] = values[0]
            self.parent.serverinfo['ServerName'] = values[1]
            self.parent.serverinfo['ServerDescription'] = values[2]
            self.parent.serverinfo['ServerStarted'] = values[0]
            self.parent.serverinfo['ServerFiles'] = values[0]
            self.parent.serverinfo['ServerSize'] = values[0]
        except KeyError:
            self.logger.debug("Invalid field count for 200 Server Info")
            return 0
        return 1

    def pong(self, values):
        self.logger.debug("Got Pong")
        return 1

    def serverBanner(self, values):
        self.logger.debug("Got Server Banner")
        try:
            self.parent.serverinfo['ServerBanner'] = values[0]
        except KeyError:
            return 0
        return 1

    def gotChatTopic(self, values):
        try:
            self.parent.topics[int(values[0])] = \
            {'nick': values[1], 'user': values[2], 'ip': values[3], 'date': values[4], 'text': values[5]}
        except KeyError:
            self.logger.debug("Invalid field count for 341 Chat Topic")
            return 0
        self.logger.debug("Topic for chat " + str(values[0]) + ": " + str(values[5]))
        return 1

    def clientJoin(self, values):
        auser = types.user()
        if not auser.initFromDict(values):
            return 0
        if int(values[0]) == 1:
            self.parent.userlist[auser.userid] = auser
            self.logger.debug("User " + str(auser.userid) + " joined Server")
        else:
            if not int(values[0]) in self.parent.activeChats:
                # the hell? we're not in that chat!
                return 0
            try:
                self.parent.userlist[int(auser.userid)].chats.append(int(values[0]))
            except KeyError, AttributeError:
                return 0
        if "__ClientJoin" in self.parent.notifications:
            try:
                for acallback in self.parent.notifications["__ClientJoin"]:
                    acallback([int(auser.userid), int(values[0])])
            except:
                self.logger.debug("Error in callback for __ClientJoin")
                return 0
        return 1

    def clientKicked(self, values):
        if not len(values) == 3:
            return 0
        self.logger.debug("User %s kicked by %s", self.parent.getUserNameByID(values[0]), self.parent.getUserNameByID(values[1]))
        if "__ClientKicked" in self.parent.notifications:
            try:
                for acallback in self.parent.notifications["__ClientKicked"]:
                    acallback([int(values[1]), int(values[0]), str(values[2])])
            except:
                self.logger.debug("Error in callback for __ClientKicked")
                pass
        self.clientLeave([1, values[0]])
        return 1

    def clientBanned(self, values):
        if not len(values) == 3:
            return 0
        self.logger.debug("User %s banned by %s", self.parent.getUserNameByID(values[0]), self.parent.getUserNameByID(values[1]))
        if "__ClientBanned" in self.parent.notifications:
            try:
                for acallback in self.parent.notifications["__ClientBanned"]:
                    acallback([int(values[1]), int(values[0]), str(values[2])])
            except:
                self.logger.debug("Error in callback for __ClientBanned")
                pass
        self.clientLeave([1, values[0]])
        return 1

    def clientLeave(self, values):
        if not len(values) == 2:
            return 0
        if not int(values[1]) in self.parent.userlist:
            self.logger.debug("No such user in userlist!")
        # handle the callback early so it can still get the userdata and cleanup after it
        if "__ClientLeave" in self.parent.notifications:
            try:
                user = self.parent.userlist[int(values[1])]
                for acallback in self.parent.notifications["__ClientLeave"]:
                    acallback([int(values[1]), int(values[0])], {'user': user.login, 'nick': user.nick})
            except:
                self.logger.debug("Error in callback for __ClientLeave")
                pass  # continue as we still got some cleanup to do

        if int(values[0]) == 1:  # public chat leave means server leave
            if int(values[1]) in self.parent.userlist:
                self.parent.userlist.pop(int(values[1]))
            self.logger.debug("User %s left", values[1])
            return 1
        # client left a private chat
        if not int(values[0]) in self.parent.userlist[int(values[1])].chats:
            return 0  # this user never was active in this chat
        self.parent.userlist[int(values[1])].chats.remove(int(values[0]))
        self.logger.debug("User %s left chat %s", values[1], values[0])
        # check if we are the only one left in the private cheat
        if not self.parent.getChatUsers(values[0]):
            self.logger.debug("Chat %s is empty... leaving")
            self.parent.leaveChat(values[0])
        return 1

    def privateMessage(self, values):
        self.logger.debug("Got 305 PM by user %s", values[0])
        if "__PrivateMessage" in self.parent.notifications:
            try:
                for acallback in self.parent.notifications["__PrivateMessage"]:
                    acallback(int(values[0]), str(values[1]))
            except:
                self.logger.debug("Error in callback for __PrivateChatInvite")
                return 0
        return 1

    def privateChatInvite(self, values):
        self.logger.debug("Got 331 for chat %s from user %s", values[0], values[1])
        if "__PrivateChatInvite" in self.parent.notifications:
            try:
                for acallback in self.parent.notifications["__PrivateChatInvite"]:
                    acallback(int(values[0]), int(values[1]))
            except:
                self.logger.debug("Error in callback for __PrivateChatInvite")
                return 0
        return 1

    def statusChange(self, values):
        if not len(values) == 6:
            self.logger.debug("Invalid 304")
            return 0
        if not int(values[0]) in self.parent.userlist:
            self.logger.debug("Got 304 for not existing user %s", values[0])
            return 0
        self.parent.userlist[int(values[0])].idle = values[1]
        self.parent.userlist[int(values[0])].admin = values[2]
        self.parent.userlist[int(values[0])].icon = values[3]
        self.parent.userlist[int(values[0])].nick = values[4]
        self.parent.userlist[int(values[0])].status = values[5]
        if "__ClientStatusChange" in self.parent.notifications:
            try:
                for acallback in self.parent.notifications["__ClientStatusChange"]:
                    acallback(int(values[0]))
            except:
                self.logger.debug("Error in callback for __ClientStatusChange")
                return 0
        return 1

    def gotPrivileges(self, values):
        if len(values) != 23:
            self.logger.debug("Invalid Field count in 602 (gotPrivileges): %2")
            return 0
        self.parent.privileges = {}
        self.parent.privileges['getUserInfo'] = int(values[0])
        self.parent.privileges['broadcast'] = int(values[1])
        self.parent.privileges['postNews'] = int(values[2])
        self.parent.privileges['clearNews'] = int(values[3])
        self.parent.privileges['download'] = int(values[4])
        self.parent.privileges['upload'] = int(values[5])
        self.parent.privileges['uploadAnywhere'] = int(values[6])
        self.parent.privileges['createFolders'] = int(values[7])
        self.parent.privileges['alterFiles'] = int(values[8])
        self.parent.privileges['deleteFiles'] = int(values[9])
        self.parent.privileges['viewDropboxes'] = int(values[10])
        self.parent.privileges['createAccounts'] = int(values[11])
        self.parent.privileges['editAccounts'] = int(values[12])
        self.parent.privileges['deleteAccounts'] = int(values[13])
        self.parent.privileges['elevatePrivileges'] = int(values[14])
        self.parent.privileges['kickUsers'] = int(values[15])
        self.parent.privileges['banUsers'] = int(values[16])
        self.parent.privileges['cannotBeKicked'] = int(values[17])
        self.parent.privileges['downloadSpeed'] = int(values[18])
        self.parent.privileges['uploadSpeed'] = int(values[19])
        self.parent.privileges['downloadLimit'] = int(values[20])
        self.parent.privileges['uploadLimit'] = int(values[21])
        self.parent.privileges['changeTopic'] = int(values[22])
        return 1
