# Made by Mr. - Version 0.3 by DrLecter
import sys
from net.sf.l2j.gameserver.model.quest import State
from net.sf.l2j.gameserver.model.quest import QuestState
from net.sf.l2j.gameserver.model.quest.jython import QuestJython as JQuest

FLAME_SHARD = 1020
ICE_SHARD = 1021
ADENA = 57

DROPLIST={
20109:[30,FLAME_SHARD],
20110:[30,ICE_SHARD],
20112:[40,FLAME_SHARD],
20113:[40,ICE_SHARD],
20114:[50,FLAME_SHARD],
20115:[50,ICE_SHARD]
}

class Quest (JQuest) :

 def __init__(self,id,name,descr): JQuest.__init__(self,id,name,descr)

 def onEvent (self,event,st) :
    htmltext = event
    if event == "30004-04.htm" :
      st.set("cond","1")
      st.setState(STARTED)
      st.playSound("ItemSound.quest_accept")
    elif event == "30004-08.htm" :
      st.exitQuest(1)
      st.playSound("ItemSound.quest_finish")
    return htmltext

 def onTalk (Self,npc,st):
   htmltext = "<html><head><body>I have nothing to say you</body></html>"
   id = st.getState()
   if id == CREATED :
     st.set("cond","0")
   if int(st.get("cond"))==0 :
     if st.getPlayer().getLevel() >= 17 :
       htmltext = "30004-03.htm"
     else:
       htmltext = "30004-02.htm"
       st.exitQuest(1)
   else :
     flame=st.getQuestItemsCount(FLAME_SHARD)
     ice=st.getQuestItemsCount(ICE_SHARD)
     if flame==ice==0 :
       htmltext = "30004-05.htm"
     else :
       if flame+ice > 9 :
          st.giveItems(ADENA,5000+30*(flame+ice))
       else :
          st.giveItems(ADENA,30*(flame+ice))
       st.takeItems(FLAME_SHARD,-1)
       st.takeItems(ICE_SHARD,-1)
       htmltext = "30004-07.htm"
   return htmltext

 def onKill (self,npc,st):
   npcId = npc.getNpcId()
   chance,item=DROPLIST[npcId]
   if st.getRandom(100)<chance :
     st.giveItems(item,1)
     st.playSound("ItemSound.quest_itemget")
   return

QUEST       = Quest(306,"306_CrystalOfFireice","Crystal Of Fireice")
CREATED     = State('Start', QUEST)
STARTING    = State('Starting', QUEST)
STARTED     = State('Started', QUEST)
COMPLETED   = State('Completed', QUEST)

QUEST.setInitialState(CREATED)
QUEST.addStartNpc(30004)

CREATED.addTalkId(30004)
STARTING.addTalkId(30004)
STARTED.addTalkId(30004)
COMPLETED.addTalkId(30004)

STARTED.addKillId(20109)
STARTED.addKillId(20110)
STARTED.addKillId(20112)
STARTED.addKillId(20113)
STARTED.addKillId(20114)
STARTED.addKillId(20115)

STARTED.addQuestDrop(20109,FLAME_SHARD,1)
STARTED.addQuestDrop(20110,ICE_SHARD,1)

print "importing quests: 306: Crystal Of Fireice"
