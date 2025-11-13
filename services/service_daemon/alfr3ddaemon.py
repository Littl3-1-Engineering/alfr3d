#!/usr/bin/python

"""
	This is the main Alfr3d daemon running most standard services
"""
# Copyright (c) 2010-2018 LiTtl3.1 Industries (LiTtl3.1).
# All rights reserved.
# This source code and any compilation or derivative thereof is the
# proprietary information of LiTtl3.1 Industries and is
# confidential in nature.
# Use of this source code is subject to the terms of the applicable
# LiTtl3.1 Industries license agreement.
#
# Under no circumstances is this component (or portion thereof) to be in any
# way affected or brought under the terms of any Open Source License without
# the prior express written permission of LiTtl3.1 Industries.
#
# For the purpose of this clause, the term Open Source Software/Component
# includes:
#
# (i) any software/component that requires as a condition of use, modification
#	 and/or distribution of such software/component, that such software/
#	 component:
#	 a. be disclosed or distributed in source code form;
#	 b. be licensed for the purpose of making derivative works; and/or
# (ii) any software/component that contains, is derived in any manner (in whole
#	  or in part) from, or statically or dynamically links against any
#	  software/component specified under (i).
#

# Imports
import logging
import time
import os						# used to allow execution of system level commands
import sys
import schedule					# 3rd party lib used for alarm clock managment.
from random import randint		# used for random number generator
from kafka import KafkaProducer # user to write messages to Kafka

# current path from which python is executed
CURRENT_PATH = os.path.dirname(__file__)

# import my own utilities
sys.path.append(os.path.join(os.path.join(os.getcwd(),os.path.dirname(__file__)),"../"))
from utils import util_routines


# set up daemon things
# directories created in Dockerfile

# get main DB credentials
MYSQL_DATABASE 	= os.environ.get('MYSQL_DATABASE')
MYSQL_DB 	= os.environ.get('MYSQL_NAME')
MYSQL_USER 	= os.environ.get('MYSQL_USER')
MYSQL_PSWD 	= os.environ.get('MYSQL_PSWD')
KAFKA_URL       = os.environ['KAFKA_BOOTSTRAP_SERVERS']

producer = None

# time of sunset/sunrise - defaults
# SUNSET_TIME = datetime.datetime.now().replace(hour=19, minute=0)
# SUNRISE_TIME = datetime.datetime.now().replace(hour=6, minute=30)
# BED_TIME = datetime.datetime.now().replace(hour=23, minute=00)

# various counters to be used for pacing spreadout functions
QUIP_START_TIME = time.time()
QUIP_WAIT_TIME = randint(5,10)

# set up logging
logger = logging.getLogger("DaemonLog")
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)
logger.addHandler(handler)

def get_producer():
	global producer
	if producer is None:
		try:
			print("Connecting to Kafka at: "+KAFKA_URL)
			producer = KafkaProducer(bootstrap_servers=[KAFKA_URL])
			logger.info("Connected to Kafka")
		except Exception as e:
			logger.error("Failed to connect to Kafka")
			return None
	return producer

class MyDaemon:
	def run(self):
		while True:

			"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
				Check online members
			"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
			logger.info("Time for localnet scan")
			p = get_producer()
			if p:
				p.send("device", b"scan net")

			"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
				Check routines
			"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
			logger.info("Routine check")
			util_routines.checkRoutines()			

			"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
				Things to do only during waking hours and only when
				god or owner is in tha house
			"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
			logger.info("Checking if mute")
			if not self.checkMute():
				"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
					Things to do only during waking hours and only when
					god is in tha house
				"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
				# ramble quips every once in a while
				try:
					logger.info("Is it time for a smartass quip?")
					## Do a quip
					self.beSmart()
				except Exception as e:
					logger.error("Failed to complete the quip block")
					logger.error("Traceback: "+str(e))
					# this could be a good trigger to restart alfr3d_speak service

				# check emails
				try:
					logger.info("Time to check Gmail")
					self.checkGmail()
				except Exception as e:
					logger.error("Failed to check Gmail")
					logger.error("Traceback: "+str(e))

			# OK Take a break
			time.sleep(60)

	def checkGmail(self):
		"""
			Description:
				Checks the unread count in gMail
		"""
		logger.info("Checking email")

		p = get_producer()
		if p:
			p.send("google", b"check gmail")

	def beSmart(self):
		"""
			Description:
				speak a quip
		"""
		global QUIP_START_TIME
		global QUIP_WAIT_TIME

		if time.time() - QUIP_START_TIME > QUIP_WAIT_TIME*60:
			logger.info("It is time to be a smartass")

			p = get_producer()
			if p:
				p.send("speak", b"alfr3d-speak.random")

			QUIP_START_TIME = time.time()
			QUIP_WAIT_TIME = randint(10,50)
			print("Time until next quip: ", QUIP_WAIT_TIME) 	#DEBUG

			logger.info("QUIP_START_TIME and QUIP_WAIT_TIME have been reset")
			logger.info("Next quip will be shouted in "+str(QUIP_WAIT_TIME)+" minutes.")

	def playTune(self):
		"""
			Description:
				pick a random song from current weather category and play it
		"""
		logger.info("playing a tune")

	def nightlight(self):
		"""
			Description:
				is anyone at home?
				is it after dark?
				turn the lights on or off as needed.
		"""
		logger.info("nightlight auto-check")

	def checkMute(self):
		"""
			Description:
				checks what time it is and decides if Alfr3d should be quiet
				- between wake-up time and bedtime
				- only when Athos is at home
				- only when 'owner' is at home
		"""
		logger.info("Checking if Alfr3d should be muted")
		result = util_routines.checkMute()

		return result


def sunriseRoutine():
	"""
		Description:
			sunset routine - perform this routine 30 minutes before sunrise
			giving the users time to go see sunrise
	"""
	logger.info("Pre-sunrise routine")

def morningRoutine():
	"""
		Description:
			perform morning routine - ring alarm, speak weather, check email, etc..
	"""
	logger.info("Time for morning routine")

def sunsetRoutine():
	"""
		Description:
			routine to perform at sunset - turn on ambient lights
	"""
	logger.info("Time for sunset routine")

def bedtimeRoutine():
	"""
		Description:
			routine to perform at bedtime - turn on ambient lights
	"""
	logger.info("Bedtime")

def resetRoutines():
	"""
		Description:
			refresh some things at midnight
	"""
	logger.info("Time to reset routines")
	util_routines.resetRoutines()


def init_daemon():
	"""
		Description:
			initialize alfr3d services
	"""
	logger.info("Initializing systems check")
	p = get_producer()
	if p:
		p.send("speak", b"Initializing systems checks")

	faults = 0

	# initial geo check
	logger.info("Running a geoscan")
	p = get_producer()
	if p:
		p.send("environment", b"check location")

	# set up some routine schedules
	try:
		logger.info("Setting up scheduled routines")
		p = get_producer()
		if p:
			p.send("speak", b"Setting up scheduled routines")
		#utilities.createRoutines()
		resetRoutines()

		# "8.30" in the following function is just a placeholder
		# until i deploy a more configurable alarm clock
		schedule.every().day.at("00:05").do(resetRoutines)
		#schedule.every().day.at(str(bed_time.hour)+":"+str(bed_time.minute)).do(bedtimeRoutine)
	except Exception as e:
		logger.error("Failed to set schedules")
		logger.error("Traceback: "+str(e))
		faults+=1												# bump up fault counter

	p = get_producer()
	if p:
		p.send("speak", b"Systems check is complete")
	if faults != 0:
		logger.warning("Some startup faults were detected")
		p = get_producer()
		if p:
			p.send("speak", b"Some faults were detected but system started successfully")

		#producer.send("speak", b"Total number of faults is "+str(faults))

	else:
		logger.info("All systems are up and operational")
		p = get_producer()
		if p:
			p.send("speak", b"All systems are up and operational")

	return

if __name__ == "__main__":
	daemon = MyDaemon()
	if len(sys.argv) == 2:
		if 'start' == sys.argv[1]:
			logger.info("Alfr3d Daemon initializing")
			init_daemon()
			logger.info("Alfr3d Daemon starting...")
			daemon.run()
		else:
			print("Unknown command")
			sys.exit(2)
	else:
		print("usage: %s start" % sys.argv[0])
		sys.exit(2)