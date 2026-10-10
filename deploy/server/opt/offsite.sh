#!/bin/bash
# 把当日备份上传到腾讯云轻量对象存储（异地副本）。
# 由 backup.sh 在本地备份成功后调用；上传失败不影响本地备份。
#
# 桶：lhcos-36974-1301304366  地域：ap-hongkong（与服务器同地域，走内网不计流量）
# 凭据在 /opt/rightwrite/.cos.yaml（600），不经命令行传递——命令行参数在 ps 里可见。
#
# 启用方法见文末注释。
set -euo pipefail

CFG=/opt/rightwrite/.cos.yaml
BUCKET_ALIAS=backup

if grep -q "REPLACE_WITH_SECRET" "$CFG" 2>/dev/null; then
    echo "异地上传未启用：$CFG 中的密钥仍是占位值，跳过"
    exit 0
fi

# coscli 会在当前目录写日志，必须切到可写目录，否则报 permission denied
cd /opt/rightwrite
export HOME=/opt/rightwrite

PREFIX="rightwrite/$(date +%Y/%m)"
for f in "$@"; do
    coscli cp "$f" "cos://${BUCKET_ALIAS}/${PREFIX}/$(basename "$f")" -c "$CFG"
done

echo "异地上传完成 → cos://${BUCKET_ALIAS}/${PREFIX}/  共 $# 个文件"

# ── 启用步骤（需在你自己的终端执行，密钥不要经过聊天记录）──────────────
# 1. 腾讯云控制台 → 访问管理 → API 密钥管理 → 新建密钥
#    建议用子账号，只授予该桶的读写权限
# 2. ssh 登录服务器后执行（会交互提示输入，不回显）：
#      read -rsp "SecretId: "  SID; echo
#      read -rsp "SecretKey: " SKEY; echo
#      sudo sed -i "s|REPLACE_WITH_SECRET_ID|$SID|; s|REPLACE_WITH_SECRET_KEY|$SKEY|" \
#           /opt/rightwrite/.cos.yaml
#      unset SID SKEY; history -c
# 3. 验证：sudo systemctl start rightwrite-backup
#          sudo journalctl -u rightwrite-backup -n 20
