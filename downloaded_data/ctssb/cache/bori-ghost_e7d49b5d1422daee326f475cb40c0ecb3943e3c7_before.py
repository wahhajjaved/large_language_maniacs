import discord
import random
from comandos.cartas_objetos import *

async def da_carta(client, message, nick_autor, avatar_autor, mensaje_separado, prefijo):
	servidor = discord.utils.get(client.servers, id = "310951366736609281")
	if len(message.mentions) == 0:
		jugadores = (client.user, message.author)
	else:
		jugadores = (message.mentions[0], message.author)
	manos = [[],[]]
	while len(manos[0]) < 3 or len(manos[1]) < 3:
		i = random.randint(0,39)
		i2 = random.randint(0,39)
		while i2 == i:
			i2 = random.randint(0,39)
		if baraja[i] not in manos[0] and baraja[i2] not in manos[1]:
			manos[0].append(baraja[i])
			manos[1].append(baraja[i2])
	i = 0
	mensajes = [[],[]]
	while i <= 1:
		mensajes[i] = ""
		for carta in manos[i]:
			emoji = discord.utils.get(servidor.emojis, name=carta.emoji)
			mensajes[i] += str(emoji)
		if jugadores[i] != client.user:
			await client.send_message(jugadores[i], mensajes[i])
		i += 1
	reverso_emoji = discord.utils.get(servidor.emojis, name="reversonaipe")
	embed = discord.Embed(title="Truco",
							description="Partido entre {} y {}.".format(jugadores[0].display_name, jugadores[1].display_name),
							colour = 0x00AAAA)
	embed.add_field(name="Mano de {}".format(jugadores[0].display_name),
					value=str(reverso_emoji)*3)
	embed.add_field(name="Mesa",value="---")
	embed.add_field(name="Mano de {}".format(jugadores[1].display_name),
					value=str(reverso_emoji)*3)
	embed.set_footer(icon_url="https://cdn.icon-icons.com/icons2/1310/PNG/512/hourglass_86336.png",
						text="Es el turno de {}".format(jugadores[0].display_name))
	mensaje_juego = await client.send_message(message.channel, embed=embed)
	respuesta = None
	while respuesta == None:
		respuesta = await client.wait_for_message(author=jugadores[0])
		if hasattr(respuesta.server, "id"):
			if respuesta.server.id != message.server.id:
				respuesta = None
	emoji_jugada = manos[0][int(respuesta)].emoji
	emoji_jugada = discord.utils.get(servidor.emojis, name=emoji_jugada)
	await client.send_message(message.channel, str(emoji_jugada))