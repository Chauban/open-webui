#!/bin/bash
# 服务器端部署脚本，安装在 /opt/rightwrite/deploy.sh（root 所有）。
# 由本地 deploy/deploy.sh 按哈希自动覆盖安装，不要直接改服务器上的副本。
#
# 用法（root，nohup 后台跑，SSH 断线不影响）：
#   deploy.sh <目标提交 sha> <是否构建 1|0> [要清空的表,逗号分隔]
#
# 顺序有讲究：
#   - 备份、拉代码放在停机之前：GitHub 连不上时应用照常在线
#   - 构建必须先停应用：应用常驻 3.5GB，叠上 vite 会把 8GB 打满、机器失联
#   - 清表必须在停机之后：旧代码还在跑会继续写入证据
#   - 迁移由 systemd 的 ExecStartPre（migrate.sh）单进程执行
# 最后一行固定为 "DEPLOY OK <sha>" 或 "DEPLOY FAIL <原因>"，本地靠它判断结果。
set -uo pipefail

TARGET=${1:?缺目标提交}
BUILD=${2:?缺构建标记}
TRUNCATE=${3:-}
APP=/opt/rightwrite/app

exec 9>/tmp/rw-deploy.lock
flock -n 9 || { echo "DEPLOY FAIL 已有另一次部署在进行"; exit 1; }

step() { echo; echo ">> $(date +%T) $*"; }
fail() { echo "DEPLOY FAIL $*"; exit 1; }
as_app() { sudo -u rightwrite "$@"; }

step "备份数据库与上传文件"
systemctl start rightwrite-backup || fail "备份失败，未做任何改动（journalctl -u rightwrite-backup）"

step "拉取代码"
fetched=0
for i in 1 2 3 4 5; do
    as_app git -C "$APP" fetch -q origin main && { fetched=1; break; }
    echo "  fetch 第 $i 次失败，10 秒后重试"
    sleep 10
done
[ "$fetched" = 1 ] || fail "连不上 GitHub，未做任何改动，应用仍在线"
as_app git -C "$APP" merge -q --ff-only "$TARGET" || fail "无法快进到 $TARGET，未停应用"
echo "  代码已在 $(as_app git -C "$APP" log --oneline -1)"

step "停止应用"
systemctl stop rightwrite || fail "停止应用失败"

if [ -n "$TRUNCATE" ]; then
    step "清空迁移守卫要求的表"
    DB_URL=$(grep '^DATABASE_URL=' /opt/rightwrite/rightwrite.env | cut -d= -f2-)
    # 守卫点名的表之间常有外键，PG 不许单独清被引用的表（即便引用方已空），
    # 所以存在的表收齐后用一条 TRUNCATE 一起清；不加 CASCADE，免得连带清掉名单外的表
    existing=()
    for t in ${TRUNCATE//,/ }; do
        [[ $t =~ ^[a-z_][a-z0-9_]*$ ]] || fail "非法表名 $t（应用已停止）"
        exists=$(psql "$DB_URL" -tAc "select 1 from pg_tables where schemaname='public' and tablename='$t'")
        if [ "$exists" = 1 ]; then
            existing+=("\"$t\"")
        else
            echo "  $t 不存在，跳过"
        fi
    done
    if [ ${#existing[@]} -gt 0 ]; then
        list=$(IFS=,; echo "${existing[*]}")
        psql "$DB_URL" -qc "truncate table $list" || fail "清空 $list 失败（应用已停止）"
        echo "  已清空 $list"
    fi
fi

if [ "$BUILD" = 1 ]; then
    step "构建前端（约 3 分钟）"
    # /tmp 有 sticky 保护：别的用户留下的同名日志 root 也写不进，先删
    rm -f /tmp/rw-build.log
    if ! as_app /opt/rightwrite/build.sh > /tmp/rw-build.log 2>&1; then
        tail -n 30 /tmp/rw-build.log
        fail "构建失败，应用已停止（完整日志 /tmp/rw-build.log）"
    fi
    # 本地据此判断前端是否需要重建；不能看 git HEAD，构建失败时 HEAD 已前移
    echo "$TARGET" > /opt/rightwrite/built-commit
else
    step "只改了后端，跳过构建"
fi

step "启动应用（ExecStartPre 执行迁移）"
if ! systemctl start rightwrite; then
    journalctl -u rightwrite -n 40 -o cat --no-pager
    fail "启动失败，应用未运行"
fi

step "等待健康检查"
for i in $(seq 1 36); do
    curl -sf -m 5 http://127.0.0.1:8080/health > /dev/null && break
    sleep 5
done
if ! curl -sf -m 5 http://127.0.0.1:8080/health > /dev/null; then
    journalctl -u rightwrite -n 40 -o cat --no-pager
    fail "3 分钟内健康检查未通过"
fi

echo "DEPLOY OK $TARGET (NRestarts=$(systemctl show -p NRestarts --value rightwrite))"
