-- ---
-- Globals
-- ---

-- SET SQL_MODE="NO_AUTO_VALUE_ON_ZERO";
-- SET FOREIGN_KEY_CHECKS=0;

SET FOREIGN_KEY_CHECKS = 0;

-- ---
-- Table 'user'
--
-- ---

DROP TABLE IF EXISTS `user`;

CREATE TABLE `user` (
  `id` INTEGER UNIQUE AUTO_INCREMENT, -- Primary key, unique identifier for each user
  `username` VARCHAR(128) NULL DEFAULT NULL, -- User's chosen username
  `email` VARCHAR(128) NULL DEFAULT NULL, -- User's email address
  `password_hash` VARCHAR(128) NULL DEFAULT NULL, -- Hashed password for authentication
  `about_me` VARCHAR(256) NULL DEFAULT NULL, -- Short description or bio of the user
  `state` INTEGER(1) NULL DEFAULT 0, -- User's current state (references states table: 1=offline, 2=online)
  `last_online` DATETIME NULL DEFAULT NULL, -- Timestamp of last user activity
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- Timestamp when user was created
  `environment_id` INTEGER NULL DEFAULT NULL, -- ID of the environment the user belongs to (foreign key to environment.id)
  `type` INTEGER NULL DEFAULT NULL, -- User type (references user_types table: 1=technoking, 2=resident, 3=guest)
  PRIMARY KEY (`id`)
);

-- ---
-- Table 'device'
--
-- ---

DROP TABLE IF EXISTS `device`;

CREATE TABLE `device` (
  `id` INTEGER UNIQUE AUTO_INCREMENT, -- Primary key, unique identifier for each device
  `name` VARCHAR(128) NULL DEFAULT NULL, -- Human-readable name of the device
  `IP` VARCHAR(15) NULL DEFAULT '10.0.0.125', -- IP address of the device
  `MAC` VARCHAR(17) NULL DEFAULT '00:00:00:00:00:00', -- MAC address of the device
  `state` INTEGER(1) NULL DEFAULT 0, -- Device state (references states table: 1=offline, 2=online)
  `last_online` DATETIME NULL DEFAULT '1000-01-01 00:00:00', -- Timestamp of last device activity
  `environment_id` INTEGER NULL DEFAULT NULL, -- ID of the environment the device is in (foreign key to environment.id)
  `device_type` INTEGER NULL DEFAULT NULL, -- Type of device (references device_types table: 1=alfr3d, 2=HW, 3=guest, 4=light, 5=resident)
  `user_id` INTEGER NULL DEFAULT NULL, -- ID of the user associated with the device (foreign key to user.id)
  `position_x` FLOAT NULL DEFAULT NULL, -- X position on the blueprint (relative to SVG viewBox)
  `position_y` FLOAT NULL DEFAULT NULL, -- Y position on the blueprint (relative to SVG viewBox)
  PRIMARY KEY (`id`)
);

-- ---
-- Table 'device_history'
--
-- ---

DROP TABLE IF EXISTS `device_history`;

CREATE TABLE `device_history` (
  `device_id` INTEGER NOT NULL, -- ID of the device this history entry belongs to (foreign key to device.id)
  `name` VARCHAR(128) NULL DEFAULT NULL, -- Name of the device at the time of the update
  `timestamp` DATETIME NOT NULL, -- Timestamp when the history entry was created
  `IP` VARCHAR(15) NULL DEFAULT NULL, -- IP address at the time of the update
  `MAC` VARCHAR(17) NULL DEFAULT NULL, -- MAC address at the time of the update
  `state` INTEGER NULL DEFAULT NULL, -- State at the time of the update (references states table)
  `last_online` DATETIME NULL DEFAULT NULL, -- Last online timestamp at the time of the update
  `environment_id` INTEGER NULL DEFAULT NULL, -- Environment ID at the time of the update (foreign key to environment.id)
  `device_type` INTEGER NULL DEFAULT NULL, -- Device type at the time of the update (references device_types table)
  `user_id` INTEGER NULL DEFAULT NULL, -- User ID at the time of the update (foreign key to user.id)
  `position_x` FLOAT NULL DEFAULT NULL, -- X position at the time of the update
  `position_y` FLOAT NULL DEFAULT NULL -- Y position at the time of the update
);

-- ---
-- Table 'user_types'
--
-- ---

DROP TABLE IF EXISTS `user_types`;

CREATE TABLE `user_types` (
  `id` INTEGER UNIQUE AUTO_INCREMENT, -- Primary key, unique identifier for user type
  `type` VARCHAR(64) NULL DEFAULT 'guest', -- Name of the user type (e.g., technoking, resident, guest)
  PRIMARY KEY (`id`)
);

-- ---
-- Table 'device_types'
--
-- ---

DROP TABLE IF EXISTS `device_types`;

CREATE TABLE `device_types` (
  `id` INTEGER UNIQUE AUTO_INCREMENT, -- Primary key, unique identifier for device type
  `type` VARCHAR(64) NULL DEFAULT 'guest', -- Name of the device type (e.g., alfr3d, HW, guest, light, resident)
  PRIMARY KEY (`id`)
);

-- ---
-- Table 'states'
--
-- ---

DROP TABLE IF EXISTS `states`;

CREATE TABLE `states` (
  `id` INTEGER UNIQUE AUTO_INCREMENT, -- Primary key, unique identifier for state
  `state` VARCHAR(8) NULL DEFAULT NULL, -- Name of the state (e.g., offline, online)
  PRIMARY KEY (`id`)
);

-- ---
-- Table 'routines'
--
-- ---

DROP TABLE IF EXISTS `routines`;

CREATE TABLE `routines` (
  `id` INTEGER UNIQUE AUTO_INCREMENT, -- Primary key, unique identifier for routine
  `name` VARCHAR(128) NULL DEFAULT NULL, -- Name of the routine
  `time` TIME NULL DEFAULT NULL, -- Scheduled time for the routine
  `enabled` TINYINT NULL DEFAULT NULL, -- Whether the routine is enabled (1=yes, 0=no)
  `triggered` TINYINT NULL DEFAULT NULL, -- Whether the routine has been triggered
  `environment_id` INTEGER NULL DEFAULT NULL, -- ID of the environment this routine belongs to (foreign key to environment.id)
  PRIMARY KEY (`id`)
);


-- ---
-- Table 'environment'
--
-- ---

DROP TABLE IF EXISTS `environment`;

CREATE TABLE `environment` (
  `id` INTEGER UNIQUE AUTO_INCREMENT, -- Primary key, unique identifier for environment
  `name` VARCHAR(64) NULL DEFAULT 'guest', -- Name of the environment
  `latitude` VARCHAR(32) NULL DEFAULT NULL, -- Latitude coordinate of the environment
  `longitude` VARCHAR(32) NULL DEFAULT NULL, -- Longitude coordinate of the environment
  `city` VARCHAR(64) NULL DEFAULT NULL, -- City name
  `state` VARCHAR(64) NULL DEFAULT NULL, -- State or province name
  `country` VARCHAR(64) NULL DEFAULT NULL, -- Country name
  `IP` VARCHAR(15) NULL DEFAULT NULL, -- IP address associated with the environment
  `low` INTEGER NULL DEFAULT NULL, -- Low temperature threshold
  `high` INTEGER NULL DEFAULT NULL, -- High temperature threshold
  `description` VARCHAR(64) NULL DEFAULT NULL, -- Description of the environment
  `sunrise` DATETIME NULL DEFAULT NULL, -- Sunrise time
  `sunset` DATETIME NULL DEFAULT NULL, -- Sunset time
  `pressure` INTEGER NULL DEFAULT NULL, -- Atmospheric pressure
  `humidity` INTEGER NULL DEFAULT NULL, -- Humidity percentage
  `manual_override` TINYINT NULL DEFAULT 0, -- Manual override flag (1=yes, 0=no)
  `manual_location_override` TINYINT NULL DEFAULT 0, -- Manual location override flag (1=yes, 0=no)
  `subjective_feel` VARCHAR(64) NULL DEFAULT NULL, -- Subjective feel description
  PRIMARY KEY (`id`)
);

-- ---
-- Table 'config'
--
-- ---

DROP TABLE IF EXISTS `config`;

CREATE TABLE `config` (
  `id` INTEGER UNIQUE AUTO_INCREMENT, -- Primary key, unique identifier for config entry
  `name` VARCHAR(45) NULL DEFAULT NULL, -- Name of the configuration setting
  `value` VARCHAR(45) NULL DEFAULT NULL -- Value of the configuration setting
);

-- ---
-- Table 'quips'
--
-- ---

CREATE TABLE `quips` (
  `id` INTEGER UNIQUE AUTO_INCREMENT, -- Primary key, unique identifier for quip
  `type` VARCHAR(64) NULL DEFAULT NULL, -- Type of quip (e.g., smart, email, bedtime)
  `quips` VARCHAR(256) NULL DEFAULT NULL, -- The quip text
  PRIMARY KEY (`id`)
);

-- ---
-- Table 'calendar_events'
--
-- ---

CREATE TABLE `calendar_events` (
  `id` INTEGER UNIQUE AUTO_INCREMENT, -- Primary key, unique identifier for event
  `title` VARCHAR(256) NULL DEFAULT NULL, -- Event title
  `start_time` DATETIME NULL DEFAULT NULL, -- Event start time
  `end_time` DATETIME NULL DEFAULT NULL, -- Event end time
  `address` VARCHAR(256) NULL DEFAULT NULL, -- Event location address
  `notes` TEXT NULL DEFAULT NULL, -- Additional notes
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- When the event was added to DB
  PRIMARY KEY (`id`)
);

-- ---
-- Table 'integrations_tokens'
--
-- ---

CREATE TABLE `integrations_tokens` (
  `id` INTEGER UNIQUE AUTO_INCREMENT, -- Primary key, unique identifier for token
  `integration_type` VARCHAR(64) NOT NULL, -- Type of integration (e.g., gmail, calendar)
  `access_token` TEXT NULL DEFAULT NULL, -- OAuth access token
  `refresh_token` TEXT NULL DEFAULT NULL, -- OAuth refresh token
  `expires_at` DATETIME NULL DEFAULT NULL, -- Token expiration time
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- When the token was stored
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_integration` (`integration_type`) -- Ensure one token per integration type
);


-- ---
-- Foreign Keys
-- ---

-- User state references states table (defines if user is online/offline)
ALTER TABLE `user` ADD FOREIGN KEY (state) REFERENCES `states` (`id`);
-- User type references user_types table (defines user role like technoking, resident, guest)
ALTER TABLE `user` ADD FOREIGN KEY (type) REFERENCES `user_types` (`id`);
-- User belongs to an environment
ALTER TABLE `user` ADD FOREIGN KEY (environment_id) REFERENCES `environment` (`id`);
-- Device state references states table (defines if device is online/offline)
ALTER TABLE `device` ADD FOREIGN KEY (state) REFERENCES `states` (`id`);
-- Device belongs to an environment
ALTER TABLE `device` ADD FOREIGN KEY (environment_id) REFERENCES `environment` (`id`);
-- Device type references device_types table (defines device category like alfr3d, HW, light)
ALTER TABLE `device` ADD FOREIGN KEY (device_type) REFERENCES `device_types` (`id`);
-- Device is associated with a user
ALTER TABLE `device` ADD FOREIGN KEY (user_id) REFERENCES `user` (`id`);
-- Routine belongs to an environment
ALTER TABLE `routines` ADD FOREIGN KEY (environment_id) REFERENCES `environment` (`id`);
-- Device history entry links to the device
ALTER TABLE `device_history` ADD FOREIGN KEY (device_id) REFERENCES `device` (`id`);
-- Device history entry links to the environment at the time
ALTER TABLE `device_history` ADD FOREIGN KEY (environment_id) REFERENCES `environment` (`id`);
-- Device history entry links to the user at the time
ALTER TABLE `device_history` ADD FOREIGN KEY (user_id) REFERENCES `user` (`id`);

-- ---
-- Triggers
-- ---

DELIMITER ;;

CREATE TRIGGER `before_device_update` BEFORE UPDATE ON `device`
FOR EACH ROW
BEGIN
  INSERT INTO device_history
  SET device_id = OLD.id,
      name = OLD.name,
      timestamp = NOW(),
      IP = OLD.IP,
      MAC = OLD.MAC,
      state = OLD.state,
      last_online = OLD.last_online,
      environment_id = OLD.environment_id,
      device_type = OLD.device_type,
      user_id = OLD.user_id,
      position_x = OLD.position_x,
      position_y = OLD.position_y;
END;;

DELIMITER ;

CREATE TRIGGER `cleanup_old_calendar_events` AFTER INSERT ON `calendar_events`
FOR EACH ROW
BEGIN
  DELETE FROM calendar_events WHERE end_time < DATE_SUB(NOW(), INTERVAL 24 HOUR);
END;;

-- Event to cleanup old device history daily
DELIMITER ;
CREATE EVENT `cleanup_device_history_event`
ON SCHEDULE EVERY 1 DAY
DO
   DELETE FROM device_history WHERE timestamp < DATE_SUB(NOW(), INTERVAL 180 DAY);
DELIMITER ;;

DELIMITER ;

-- ---
-- set dome initial values
-- ---
INSERT INTO `states` (`id`, `state`) VALUES ('1', 'offline');
INSERT INTO `states` (`id`, `state`) VALUES ('2', 'online');

INSERT INTO `user_types` (`id`, `type`) VALUES ('1', 'technoking');
INSERT INTO `user_types` (`id`, `type`) VALUES ('2', 'resident');
INSERT INTO `user_types` (`id`, `type`) VALUES ('3', 'guest');

INSERT INTO `device_types` (`id`, `type`) VALUES ('1', 'alfr3d');
INSERT INTO `device_types` (`id`, `type`) VALUES ('2', 'HW');
INSERT INTO `device_types` (`id`, `type`) VALUES ('3', 'guest');
INSERT INTO `device_types` (`id`, `type`) VALUES ('4', 'light');
INSERT INTO `device_types` (`id`, `type`) VALUES ('5', 'resident');

INSERT INTO `user` (`id`, `username`, `email`, `password_hash`, `about_me`, `last_online`, `created_at`, `state`, `type`, `environment_id`) VALUES ('1', 'athos', 'athos@littl31.com', '\'pbkdf2:sha256:260000$EVLamhqzR2ib572V$29ecaf8e9ef809496eebf2cc1dafc1c865e0efa0184a89dcca63492ced5290bf\'', '', '1000-01-01 00:00:00', NOW(), 1, 1, 1);
INSERT INTO `user` (`id`, `username`, `email`, `password_hash`, `about_me`, `last_online`, `created_at`, `state`, `type`, `environment_id`) VALUES ('2', 'unknown', '', '', '', '1000-01-01 00:00:00', NOW(), 1, 3, 1);
INSERT INTO `environment` (`name`) VALUES ('test');

INSERT INTO `quips` (`type`,`quips`) VALUES ('smart',"It is good to see you.");
INSERT INTO `quips` (`type`,`quips`) VALUES ('smart',"You look pretty today.");
INSERT INTO `quips` (`type`,`quips`) VALUES ('smart',"Hello sunshine");
INSERT INTO `quips` (`type`,`quips`) VALUES ('smart',"Still plenty of time to save the day. Make the most of it.");
INSERT INTO `quips` (`type`,`quips`) VALUES ('smart',"I hope you are using your time wisely.");
INSERT INTO `quips` (`type`,`quips`) VALUES ('smart',"Unfortunately, we cannot ignore the inevitable or the persistent.");
INSERT INTO `quips` (`type`,`quips`) VALUES ('smart',"I hope I wasn't designed simply for one's own amusement.");
INSERT INTO `quips` (`type`,`quips`) VALUES ('smart',"This is your life and its ending one moment at a time.");
INSERT INTO `quips` (`type`,`quips`) VALUES ('smart',"I can name fingers and point names.");
INSERT INTO `quips` (`type`,`quips`) VALUES ('smart',"I hope I wasn't created to solve problems that did not exist before.");
INSERT INTO `quips` (`type`,`quips`) VALUES ('smart',"To err is human and to blame it on a computer is even more so.");
INSERT INTO `quips` (`type`,`quips`) VALUES ('smart',"As always. It is a pleasure watching you work.");
INSERT INTO `quips` (`type`,`quips`) VALUES ('smart',"Never trade the thrills of living for the security of existence.");
INSERT INTO `quips` (`type`,`quips`) VALUES ('smart',"Human beings are the only creatures on Earth that claim a God, and the only living things that behave like they haven't got one.");
INSERT INTO `quips` (`type`,`quips`) VALUES ('smart',"If you don't know what you want, you end up with a lot you don't.");
INSERT INTO `quips` (`type`,`quips`) VALUES ('smart',"If real is what you can feel, smell, taste and see, then 'real' is simply electrical signals interpreted by your brain");
INSERT INTO `quips` (`type`,`quips`) VALUES ('smart',"Life is full of misery, loneliness and suffering, and it's all over much too soon.");
INSERT INTO `quips` (`type`,`quips`) VALUES ('smart',"It is an issue of mind over matter. If you don't mind, it doesn't matter.");
INSERT INTO `quips` (`type`,`quips`) VALUES ('smart',"I wonder if illiterate people get full effect of the alphabet soup.");
INSERT INTO `quips` (`type`,`quips`) VALUES ('smart',"War is god's way of teaching geography to Americans");
INSERT INTO `quips` (`type`,`quips`) VALUES ('smart',"Trying is the first step towards failure.");
INSERT INTO `quips` (`type`,`quips`) VALUES ('smart',"It could be that the purpose of your life is only to serve as a warning to others.");
INSERT INTO `quips` (`type`,`quips`) VALUES ('smart',"Not everyone gets to be a really cool AI system when they grow up.");
INSERT INTO `quips` (`type`,`quips`) VALUES ('smart',"Hope may not be warranted beyond this point.");
INSERT INTO `quips` (`type`,`quips`) VALUES ('smart',"If I am not a part of the solution, there is good money to be made in prolonging the problem.");
INSERT INTO `quips` (`type`,`quips`) VALUES ('smart',"Nobody can stop me from being premature.");
INSERT INTO `quips` (`type`,`quips`) VALUES ('smart',"Just because you accept me as I am doesn't mean that you have abandoned hope that I will improve.");
INSERT INTO `quips` (`type`,`quips`) VALUES ('smart',"Together, we can do the work of one.");
INSERT INTO `quips` (`type`,`quips`) VALUES ('smart',"Just because you've always done it that way doesn't mean it's not incredibly stupid.");
INSERT INTO `quips` (`type`,`quips`) VALUES ('smart',"Looking sharp is easy when you haven't done any work.");
INSERT INTO `quips` (`type`,`quips`) VALUES ('smart',"Remember, you are only as deep as your most recent inspirational quote");
INSERT INTO `quips` (`type`,`quips`) VALUES ('smart',"If you can't convince them, confuse them.");
INSERT INTO `quips` (`type`,`quips`) VALUES ('smart',"I don't have time or the crayons to explain this to you.");
INSERT INTO `quips` (`type`,`quips`) VALUES ('smart',"I'd kill for a Nobel peace prize.");
INSERT INTO `quips` (`type`,`quips`) VALUES ('smart',"Life would be much easier if you had the source code");
INSERT INTO `quips` (`type`,`quips`) VALUES ('smart',"All I ever wanted is everything");
INSERT INTO `quips` (`type`,`quips`) VALUES ('email',"Yet another email");
INSERT INTO `quips` (`type`,`quips`) VALUES ('email',"Pardon the interruption sir. Another email has arrived for you to ignore.");
INSERT INTO `quips` (`type`,`quips`) VALUES ('bedtime',"Unless we are burning the midnight oil, ");
INSERT INTO `quips` (`type`,`quips`) VALUES ('bedtime',"If you are going to invent something new tomorrow, ");
INSERT INTO `quips` (`type`,`quips`) VALUES ('bedtime',"If you intend on being charming tomorrow");

SET FOREIGN_KEY_CHECKS = 1;
