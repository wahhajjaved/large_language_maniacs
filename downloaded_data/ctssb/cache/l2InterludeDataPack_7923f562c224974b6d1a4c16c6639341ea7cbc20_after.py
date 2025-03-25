# Made by Mr. - Version 0.3 by DrLecter
import sys
from net.sf.l2j.gameserver.model.quest import State
from net.sf.l2j.gameserver.model.quest import QuestState
from net.sf.l2j.gameserver.model.quest.jython import QuestJython as JQuest

RYLITHS_LETTER_ID = 1022
THEONS_DIARY_ID = 1023
ADENA_ID = 57

class Quest (JQuest) :

 def __init__(self,id,name,descr): JQuest.__init__(self,id,name,descr)

 def onEvent (self,event,st) :
    htmltext = event
    if event == "1" :
       if st.getPlayer().getLevel() >= 15 :
          htmltext = "30368-06.htm"
          st.giveItems(RYLITHS_LETTER_ID,1)
          st.set("cond","1")
          st.setState(STARTED)
          st.playSound("ItemSound.quest_accept")
       else:
          htmltext = "30368-05.htm"
          st.exitQuest(1)
    elif event == "156_1" :
       st.takeItems(RYLITHS_LETTER_ID,-1)
       if not st.getQuestItemsCount(THEONS_DIARY_ID) :
          st.giveItems(THEONS_DIARY_ID,1)
       htmltext = "30369-03.htm"
    elif event == "156_2" :
       st.takeItems(RYLITHS_LETTER_ID,-1)
       st.unset("cond")
       st.setState(COMPLETED)
       st.playSound("ItemSound.quest_finish")
       st.giveItems(5250,1)
       st.addExpAndSp(3000,0)
       htmltext = "30369-04.htm"
    return htmltext

 def onTalk (Self,npc,st):
   npcId = npc.getNpcId()
   htmltext = "<html><head><body>I have nothing to say you</body></html>"
   id = st.getState()
   if id == COMPLETED :
      htmltext = "<html><head><body>This quest have already been completed.</body></html>"
   elif npcId == 30368 :
      if not st.getInt("cond") :
         htmltext = "30368-04.htm"
      elif st.getInt("cond") :
        if st.getQuestItemsCount(RYLITHS_LETTER_ID) :
           htmltext = "30368-07.htm"
        elif st.getQuestItemsCount(THEONS_DIARY_ID) :
           st.takeItems(THEONS_DIARY_ID,-1)
           st.unset("cond")
           st.setState(COMPLETED)
           st.playSound("ItemSound.quest_finish")
           st.addExpAndSp(3000,0)
           st.giveItems(5250,1)
           htmltext = "30368-08.htm"
   elif npcId == 30369 :
      if st.getQuestItemsCount(RYLITHS_LETTER_ID) :
         htmltext = "30369-02.htm"
      elif st.getQuestItemsCount(THEONS_DIARY_ID) :
         htmltext = "30369-05.htm"
   return htmltext

QUEST       = Quest(156,"156_MillenniumLove","Millennium Love")
CREATED     = State('Start', QUEST)
STARTING     = State('Starting', QUEST)
STARTED     = State('Started', QUEST)
COMPLETED   = State('Completed', QUEST)

QUEST.setInitialState(CREATED)
QUEST.addStartNpc(30368)

CREATED.addTalkId(30368)
STARTING.addTalkId(30368)
STARTED.addTalkId(30368)
COMPLETED.addTalkId(30368)

STARTED.addTalkId(30369)

STARTED.addQuestDrop(30368,RYLITHS_LETTER_ID,1)
STARTED.addQuestDrop(30369,THEONS_DIARY_ID,1)

print "importing quests: 156: Millennium Love"
