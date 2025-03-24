'''
Created on Jan 18, 2018

Made for Zambez-AI

@author: Kalerne aka dBasshunterb
'''

def Thanks(bot):
    @bot.command(pass_context=True)
    async def thanks(ctx):
        thanksFile = open("data/numThanks.txt", "r")
        numThanks = int(thanksFile.readline())
        thanksFile.close()
        
        numThanks += 1
        
        thanksFile = open("data/numThanks.txt", "w")
        thanksFile.write(str(numThanks))
        thanksFile.close()
        
        await bot.say("Thank you for using Zambez-AI!\n" +
                      "Created by: Kalerne aka dBasshunterb\n" + 
                      "I have been thanked " + str(numThanks) + " times!")