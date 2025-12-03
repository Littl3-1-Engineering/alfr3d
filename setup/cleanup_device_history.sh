#!/bin/bash
docker exec alfr3d-mysql-1 mysql -u root -prootpassword -e "
USE alfr3d_db;
DELETE FROM device_history
WHERE timestamp < DATE_SUB(NOW(), INTERVAL 180 DAY);
OPTIMIZE TABLE device_history;
"
