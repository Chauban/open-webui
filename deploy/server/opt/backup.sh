#!/bin/bash
# 每日备份：Postgres 全库 + DATA_DIR（学生上传文件）
# 由 systemd timer rightwrite-backup.timer 调用。
#
# 注意：这些备份和数据库在同一块磁盘上。它能防「误删数据 / 迁移写坏 / 改错配置」，
# 但**防不了实例丢失**。异地副本见 /opt/rightwrite/offsite.sh（需配置后才生效）。
set -euo pipefail

set -a; . /opt/rightwrite/rightwrite.env; set +a
BK=/opt/rightwrite/backups
TS=$(date +%Y%m%d-%H%M%S)
KEEP_DAYS=30

mkdir -p "$BK"

DB_FILE="$BK/db-$TS.dump"
DATA_FILE="$BK/data-$TS.tar.gz"

# 1. 数据库（custom 格式，自带压缩，支持选择性恢复）
pg_dump --dbname="$DATABASE_URL" --format=custom --compress=9 --file="$DB_FILE"

# 2. 上传文件
tar czf "$DATA_FILE" -C /opt/rightwrite data

# 3. 完整性校验：能列出目录 = 文件没截断没损坏。
#    不做这一步的话，磁盘写满或中途失败会产出一个「看起来像备份的坏文件」，
#    真出事时才发现恢复不了。
pg_restore --list "$DB_FILE" > /dev/null
tar tzf "$DATA_FILE" > /dev/null

sha256sum "$DB_FILE" "$DATA_FILE" >> "$BK/checksums.txt"

# 4. 异地副本（可选，配置后自动启用）
if [ -x /opt/rightwrite/offsite.sh ]; then
    /opt/rightwrite/offsite.sh "$DB_FILE" "$DATA_FILE" || echo "警告：异地上传失败，本地副本已保留"
fi

# 5. 保留 30 天
find "$BK" -maxdepth 1 -name 'db-*.dump'     -mtime +$KEEP_DAYS -print -delete
find "$BK" -maxdepth 1 -name 'data-*.tar.gz' -mtime +$KEEP_DAYS -print -delete

echo "备份完成 $TS — 数据库 $(du -h "$DB_FILE" | cut -f1)，文件 $(du -h "$DATA_FILE" | cut -f1)，现存 $(ls "$BK"/db-*.dump | wc -l) 份"
