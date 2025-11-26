#!/bin/bash
# backup_db.sh

BACKUP_DIR="../backup"
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
BACKUP_FILE="${BACKUP_DIR}/alfr3d_backup_${TIMESTAMP}.sql"

# Create backup dir
mkdir -p $BACKUP_DIR

# Detect environment and set connection
if command -v kubectl &> /dev/null && kubectl get pods mysql &> /dev/null; then
    # K8s environment
    MYSQL_HOST=$(kubectl get svc mysql -o jsonpath='{.spec.clusterIP}')
    MYSQL_CMD="kubectl exec -i deployment/mysql -- mysql"
    DUMP_CMD="kubectl exec -i deployment/mysql -- mysqldump"
else
    # Docker Compose environment
    MYSQL_HOST="mysql"
    MYSQL_CMD="docker-compose exec mysql mysql"
    DUMP_CMD="docker-compose exec mysql mysqldump"
fi

# Run backup
$DUMP_CMD -h$MYSQL_HOST -uroot -p$MYSQL_ROOT_PASSWORD $MYSQL_NAME > $BACKUP_FILE

# Verify and cleanup
if [ $? -eq 0 ]; then
    echo "Backup successful: $BACKUP_FILE"
    # Keep only 3 most recent backups
    ls -t $BACKUP_DIR/*.gz 2>/dev/null | tail -n +4 | xargs rm -f
else
    echo "Backup failed"
    exit 1
fi
