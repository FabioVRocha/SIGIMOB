#!/bin/bash
# Backup PostgreSQL database
db_name="sigimob"
backup_dir="${1:-$HOME}"
file_name="sigimob_$(date +%Y%m%d_%H%M%S).sql"

pg_dump "$db_name" > "$backup_dir/$file_name"

echo "Backup salvo em $backup_dir/$file_name"