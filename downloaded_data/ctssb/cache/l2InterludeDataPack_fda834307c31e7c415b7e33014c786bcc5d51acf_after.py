# Silver Haired Shaman - Version 0.1 by DrLecter
import sys
from net.sf.l2j.gameserver.model.quest import State
from net.sf.l2j.gameserver.model.quest import QuestState
from net.sf.l2j.gameserver.model.quest.jython import QuestJython as JQuest

#NPC
DIETER=30111
#Items
HAIR=5874
ADENA=57
#BASE CHANCE FOR DROP
CHANCE = 55

class Quest (JQuest) :

 def __init__(self,id,name,descr,party): JQuest.__init__(self,id,name,descr,party)

 def onEvent (self,event,st) :
   htmltext = event
   cond = st.getInt("cond")
   if event == "30111-2.htm" and cond == 0 :
     st.set("cond","1")
     st.setState(STARTED)
     st.playSound("ItemSound.quest_accept")
   elif event == "30111-6.htm" :
     st.exitQuest(1)
     st.playSound("ItemSound.quest_finish")
   return htmltext

 def onTalk (Self,npc,st):
   htmltext = "<html><head><body>I have nothing to say you</body></html>"
   id = st.getState()
   cond=st.getInt("cond")
   if cond == 0 :
     if st.getPlayer().getLevel() >= 48 :
       htmltext = "30111-1.htm"
     else:
       htmltext = "30111-0.htm"
       st.exitQuest(1)
   else :
     hair=st.getQuestItemsCount(HAIR)
     if not hair :
       htmltext = "30111-3.htm"
     else :
       st.giveItems(ADENA,12070+500*hair)
       st.takeItems(HAIR,-1)
       htmltext = "30111-4.htm"
   return htmltext

 def onKill (self,npc,st):
   if st.getRandom(100) < CHANCE + ((npc.getNpcId() - 20985) * 2) :
     st.giveItems(HAIR,1)
     st.playSound("ItemSound.quest_itemget")
   return

QUEST       = Quest(366,"366_SilverHairedShaman","Silver Haired Shaman",True)
CREATED     = State('Start', QUEST)
STARTED     = State('Started', QUEST)

QUEST.setInitialState(CREATED)
QUEST.addStartNpc(DIETER)

CREATED.addTalkId(DIETER)
STARTED.addTalkId(DIETER)

for mob in range(20986,20989) :
    STARTED.addKillId(mob)

STARTED.addQuestDrop(DIETER,HAIR,1)

print "importing quests: 366: Silver Haired Shaman"
