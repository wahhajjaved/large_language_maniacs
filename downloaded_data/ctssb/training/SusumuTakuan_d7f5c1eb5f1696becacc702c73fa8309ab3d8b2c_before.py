#
# developer.py
#
# developer functions for managing SusumuTakuan remotely
#

import discord
import asyncio
import subprocess

import access
from database import Command, CommandClass, Role, User


#Create database registration function
def register_functions(session):

	class_id = session.query(CommandClass).filter(CommandClass.name == 'developer').first()
	if ( class_id == None ):
		dev_class = CommandClass(name="developer")
		session.add(dev_class)

	cmd_id = session.query(Command).filter(Command.name == 'update_git').first()		
	if (cmd_id == None ):
		cmd_update_git = Command(name="update_git")
		cmd_update_git.command_class = dev_class
		session.add(cmd_update_git)

	cmd_id = session.query(Command).filter(Command.name == 'restart_bot').first()		
	if (cmd_id == None ):
		cmd_restart_bot = Command(name="restart_bot")
		cmd_restart_bot.command_class = dev_class
		session.add(cmd_restart_bot)

	cmd_id = session.query(Command).filter(Command.name == 'debug_output').first()		
	if (cmd_id == None ):
		cmd_debug_output = Command(name="debug_output")
		cmd_debug_output.command_class = dev_class
		session.add(cmd_debug_output)

	cmd_id = session.query(Command).filter(Command.name == 'debug_error').first()		
	if (cmd_id == None ):
		cmd_debug_error = Command(name="debug_error")
		cmd_debug_error.command_class = dev_class
		session.add(cmd_debug_error)

	session.commit()

#Add developers to internal group
def register_developer_access(session, developers):

	developer_class = session.query(CommandClass).filter(CommandClass.name == 'developer').first()
	developer_role = session.query(Role).filter(Role.name == 'developer', Role.server_id == 1).first() 

	access.grant_role_access(session, developer_role, developer_class)


	for developer in developers:
		the_developer = session.query(User).filter(User.id == developer).first()
		if ( the_developer == None):
			the_developer.roles.append(developer_role)

	session.commit()


async def update_git(client, message, developers):
	tmp = await client.send_message(message.channel, 'Updating my code via git...')
	users = message.channel.recipients
	for user in users:
		if user.id != client.user.id:
			print('%s/%s requested to update my code.' % (user.name, user.id))

		if user.id in developers:
			process = subprocess.run(["sh", "control.sh", "refresh"], universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
			tmp = await client.send_message(message.channel, process.stdout)
		else:
			print('%s/%s not allowed to run update command.' % (user.name, user.id))
			tmp = await client.send_message(message.channel, 'Unauthorized')	


async def restart_bot(client, message, developers):
	tmp = await client.send_message(message.channel, 'Restarting myself...')
	users = message.channel.recipients
	for user in users:
		if user.id != client.user.id:
			print('%s/%s requested to restart me.' % (user.name, user.id))

		if user.id in developers:
			process = subprocess.run(["sh", "control.sh", "restart"], universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
			tmp = await client.send_message(message.channel, process.stdout)
		else:
			print('%s/%s not allowed to run restart command.' % (user.name, user.id))
			tmp = await client.send_message(message.channel, 'Unauthorized')

async def debug_output(client, message, developers):
	tmp = await client.send_message(message.channel, 'Providing debug log of stdout...')
	message_array=message.content.split(" ")
	try:
		num_lines=int(message_array[1])
	except ValueError:
		print("debug_error: User gave invalid value for number of lines")
		tmp = await client.send_message(message.channel, '%s is not a valid number of lines' % (message_array[1]))
	log_lines='-%d' % (num_lines)
	users = message.channel.recipients
	for user in users:
		if user.id != client.user.id:
			print('%s/%s requested output log.' % (user.name, user.id))

		if user.id in developers:
			process = subprocess.run(["tail", log_lines, "logs/output.log"], universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
			tmp = await client.send_message(message.channel, process.stdout)
		else:
			print('%s/%s not allowed to run debug command.' % (user.name, user.id))
			tmp = await client.send_message(message.channel, 'Unauthorized')

async def debug_error(client, message, developers):
	tmp = await client.send_message(message.channel, 'Providing debug log of stderr...')
	message_array=message.content.split(" ")
	try:
		num_lines=int(message_array[1])
	except ValueError:
		print("debug_error: User gave invalid value for number of lines")
		tmp = await client.send_message(message.channel, '%s is not a valid number of lines' % (message_array[1]))
	log_lines='-%d' % (num_lines)
	users = message.channel.recipients
	for user in users:
		if user.id != client.user.id:
			print('%s/%s requested error log.' % (user.name, user.id))

		if user.id in developers:
			process = subprocess.run(["tail", log_lines, "logs/error.log"], universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
			tmp = await client.send_message(message.channel, process.stdout)
		else:
			print('%s/%s not allowed to run debug command.' % (user.name, user.id))
			tmp = await client.send_message(message.channel, 'Unauthorized')