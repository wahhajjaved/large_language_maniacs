# Made by Mr. Have fun! - Version 0.3 by DrLecter

import sys
from net.sf.l2j.gameserver.model.quest import State
from net.sf.l2j.gameserver.model.quest import QuestState
from net.sf.l2j.gameserver.model.quest.jython import QuestJython as JQuest

KAROYDS_LETTER_ID = 968
CECKTINONS_VOUCHER1_ID = 969
CECKTINONS_VOUCHER2_ID = 970
BONE_FRAGMENT1_ID = 1107
SOUL_CATCHER_ID = 971
PRESERVE_OIL_ID = 972
ZOMBIE_HEAD_ID = 973
STEELBENDERS_HEAD_ID = 974
BLOODSABER_ID = 975

class Quest (JQuest) :

 def __init__(self,id,name,descr): JQuest.__init__(self,id,name,descr)

 def onEvent (self,event,st) :
    htmltext = event
    if event == "30307-05.htm" :
        st.giveItems(KAROYDS_LETTER_ID,1)
        st.set("cond","1")
        st.setState(STARTED)
        st.playSound("ItemSound.quest_accept")
    return htmltext


 def onTalk (Self,npc,st) :
   npcId = npc.getNpcId()
   htmltext = "<html><head><body>I have nothing to say you</body></html>"
   id = st.getState()
   if id == CREATED :
     st.set("cond","0")
     st.set("onlyone","0")
   if npcId == 30307 and int(st.get("cond"))==0 and int(st.get("onlyone"))==0 :
     if st.getPlayer().getRace().ordinal() != 2 :
        htmltext = "30307-00.htm"
     elif st.getPlayer().getLevel() >= 11 :
        htmltext = "30307-03.htm"
        return htmltext
     else:
        htmltext = "30307-02.htm"
        st.exitQuest(1)
   elif npcId == 30307 and int(st.get("cond"))==0 and int(st.get("onlyone"))==1 :
        htmltext = "<html><head><body>This quest have already been completed.</body></html>"
   elif npcId == 30307 and int(st.get("cond"))>=1 and (st.getQuestItemsCount(KAROYDS_LETTER_ID)>=1 or st.getQuestItemsCount(CECKTINONS_VOUCHER1_ID)>=1 or st.getQuestItemsCount(CECKTINONS_VOUCHER2_ID)>=1) :
        htmltext = "30307-06.htm"
   elif npcId == 30132 and int(st.get("cond"))==1 and st.getQuestItemsCount(KAROYDS_LETTER_ID)==1 :
        htmltext = "30132-01.htm"
        st.set("cond","2")
        st.takeItems(KAROYDS_LETTER_ID,1)
        st.giveItems(CECKTINONS_VOUCHER1_ID,1)
   elif npcId == 30132 and int(st.get("cond"))>=2 and (st.getQuestItemsCount(CECKTINONS_VOUCHER1_ID)>=1 or st.getQuestItemsCount(CECKTINONS_VOUCHER2_ID)>=1) :
        htmltext = "30132-02.htm"
   elif npcId == 30144 and int(st.get("cond"))==2 and st.getQuestItemsCount(CECKTINONS_VOUCHER1_ID)>=1 :
        htmltext = "30144-01.htm"
        st.set("cond","3")
        st.takeItems(CECKTINONS_VOUCHER1_ID,1)
        st.giveItems(CECKTINONS_VOUCHER2_ID,1)
   elif npcId == 30144 and int(st.get("cond"))==3 and st.getQuestItemsCount(CECKTINONS_VOUCHER2_ID)>=1 and st.getQuestItemsCount(BONE_FRAGMENT1_ID)<10 :
        htmltext = "30144-02.htm"
   elif npcId == 30144 and int(st.get("cond"))==4 and st.getQuestItemsCount(CECKTINONS_VOUCHER2_ID)==1 and st.getQuestItemsCount(BONE_FRAGMENT1_ID)>=10 :
        htmltext = "30144-03.htm"
        st.set("cond","5")
        st.takeItems(CECKTINONS_VOUCHER2_ID,1)
        st.takeItems(BONE_FRAGMENT1_ID,10)
        st.giveItems(SOUL_CATCHER_ID,1)
   elif npcId == 30144 and int(st.get("cond"))==5 and st.getQuestItemsCount(SOUL_CATCHER_ID)==1 :
        htmltext = "30144-04.htm"
   elif npcId == 30132 and int(st.get("cond"))==5 and st.getQuestItemsCount(SOUL_CATCHER_ID)==1 :
        htmltext = "30132-03.htm"
        st.set("cond","6")
        st.takeItems(SOUL_CATCHER_ID,1)
        st.giveItems(PRESERVE_OIL_ID,1)
   elif npcId == 30132 and int(st.get("cond"))==6 and st.getQuestItemsCount(PRESERVE_OIL_ID)==1 and st.getQuestItemsCount(ZOMBIE_HEAD_ID)==0 and st.getQuestItemsCount(STEELBENDERS_HEAD_ID)==0 :
        htmltext = "30132-04.htm"
   elif npcId == 30132 and int(st.get("cond"))==7 and st.getQuestItemsCount(ZOMBIE_HEAD_ID)==1 :
        htmltext = "30132-05.htm"
        st.set("cond","8")
        st.takeItems(ZOMBIE_HEAD_ID,1)
        st.giveItems(STEELBENDERS_HEAD_ID,1)
   elif npcId == 30132 and int(st.get("cond"))==8 and st.getQuestItemsCount(STEELBENDERS_HEAD_ID)==1 :
        htmltext = "30132-06.htm"
   elif npcId == 30307 and int(st.get("cond"))==8 and st.getQuestItemsCount(STEELBENDERS_HEAD_ID)==1 :
        htmltext = "30307-07.htm"
        st.takeItems(STEELBENDERS_HEAD_ID,1)
        st.giveItems(BLOODSABER_ID,1)
        st.set("cond","0")
        st.setState(COMPLETED)
        st.playSound("ItemSound.quest_finish")
        st.set("onlyone","1")
   return htmltext

 def onKill (self,npc,st):
   npcId = npc.getNpcId()
   if npcId in [20517,20518,20455] :
      if st.getQuestItemsCount(CECKTINONS_VOUCHER2_ID) == 1 and st.getQuestItemsCount(BONE_FRAGMENT1_ID)<10 :
         if st.getRandom(10)<3 :
            st.giveItems(BONE_FRAGMENT1_ID,1)
            if st.getQuestItemsCount(BONE_FRAGMENT1_ID) == 10 :
              st.playSound("ItemSound.quest_middle")
              st.set("cond","4")
            else:
              st.playSound("ItemSound.quest_itemget")
   elif npcId in [20015,20020] :
      if st.getQuestItemsCount(PRESERVE_OIL_ID) == 1 :
         if st.getRandom(10)<3 :
            st.set("cond","7")
            st.giveItems(ZOMBIE_HEAD_ID,1)
            st.playSound("ItemSound.quest_middle")
            st.takeItems(PRESERVE_OIL_ID,1)
   return

QUEST       = Quest(103,"103_SpiritOfCraftsman","Spirit Of Craftsman")
CREATED     = State('Start', QUEST)
STARTED     = State('Started', QUEST)
COMPLETED   = State('Completed', QUEST)


QUEST.setInitialState(CREATED)
QUEST.addStartNpc(30307)

CREATED.addTalkId(30307)

STARTED.addTalkId(30132)
STARTED.addTalkId(30144)
STARTED.addTalkId(30307)

STARTED.addKillId(20015)
STARTED.addKillId(20020)
STARTED.addKillId(20455)
STARTED.addKillId(20517)
STARTED.addKillId(20518)

STARTED.addQuestDrop(30307,KAROYDS_LETTER_ID,1)
STARTED.addQuestDrop(30132,CECKTINONS_VOUCHER1_ID,1)
STARTED.addQuestDrop(30144,CECKTINONS_VOUCHER2_ID,1)
STARTED.addQuestDrop(20517,BONE_FRAGMENT1_ID,1)
STARTED.addQuestDrop(20518,BONE_FRAGMENT1_ID,1)
STARTED.addQuestDrop(20455,BONE_FRAGMENT1_ID,1)
STARTED.addQuestDrop(30144,SOUL_CATCHER_ID,1)
STARTED.addQuestDrop(30132,PRESERVE_OIL_ID,1)
STARTED.addQuestDrop(20015,ZOMBIE_HEAD_ID,1)
STARTED.addQuestDrop(20020,ZOMBIE_HEAD_ID,1)
STARTED.addQuestDrop(30132,STEELBENDERS_HEAD_ID,1)

print "importing quests: 103: Spirit Of Craftsman"
