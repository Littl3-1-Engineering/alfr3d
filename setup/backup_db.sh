#!/bin/bash
# backup_db.sh

BACKUP_DIR="$(dirname "$0")/../backup"
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
    MYSQL_HOST="localhost"
    MYSQL_ROOT_PASSWORD="rootpassword"  # pragma: allowlist secret
    MYSQL_NAME="alfr3d_db"
    DUMP_CMD="docker compose exec -T mysql mysqldump"
fi

# Run backup
$DUMP_CMD -uroot -p$MYSQL_ROOT_PASSWORD $MYSQL_NAME > $BACKUP_FILE

# Verify and cleanup
if [ $? -eq 0 ]; then
    echo "Backup successful: $BACKUP_FILE"
    # Keep only 3 most recent backups
    ls -t $BACKUP_DIR/*.sql 2>/dev/null | tail -n +4 | xargs rm -f
else
    echo "Backup failed"
    exit 1
fi
