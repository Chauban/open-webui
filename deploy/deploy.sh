#!/usr/bin/env bash
# 一键：合并分支 → 推送 GitHub → 部署到 rightwrite.cc（Git Bash 下运行）
#
# 用法：
#   deploy/deploy.sh                                只部署（本地 main 有未推送提交会先推送）
#   deploy/deploy.sh <分支> [-m "merge: 合入xxx"]    合并分支到 main、推送、部署
# 选项：
#   --target hitsz     部署到哈工深实例（hitsz.rightwrite.cc）；默认是现网 rightwrite.cc
#   --truncate t1,t2   部署时（停机后、迁移前）清空这些表，用于迁移守卫
#   --guards-ok        已确认守卫迁移点名的表为空，不需清表
#   --deps-done        依赖文件有变动但已在服务器装好
#   --force            生产已是最新也重新部署
#   --no-deploy        只合并推送，不部署
#
# 本地 main 与 GitHub 分叉时先自动合并一次，无冲突就继续。
# 以下情况会在停机前停下（已回退、未推送），交给人判断：任何合并冲突、
# 新迁移带守卫（raise RuntimeError）、依赖文件变动。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$ROOT"
REMOTE_SRC="$ROOT/deploy/remote.sh"
TARGET_NAME=prod

BRANCH="" MSG="" TRUNCATE="" GUARDS_OK=0 DEPS_DONE=0 FORCE=0 DEPLOY=1
while [ $# -gt 0 ]; do
    case "$1" in
        -m) MSG=$2; shift ;;
        --target) TARGET_NAME=$2; shift ;;
        --truncate) TRUNCATE=$2; shift ;;
        --guards-ok) GUARDS_OK=1 ;;
        --deps-done) DEPS_DONE=1 ;;
        --force) FORCE=1 ;;
        --no-deploy) DEPLOY=0 ;;
        -*) echo "未知选项 $1" >&2; exit 2 ;;
        *) BRANCH=$1 ;;
    esac
    shift
done

say() { printf '\n== %s\n' "$*"; }
die() { printf '\n✗ %s\n' "$*" >&2; exit 1; }
# 两台机器目录结构相同，remote.sh 原样复用；只差 SSH 别名和对外域名。
case "$TARGET_NAME" in
    prod) HOST=rightwrite DOMAIN=rightwrite.cc ;;
    hitsz) HOST=rightwrite-hitsz DOMAIN=hitsz.rightwrite.cc ;;
    *) die "未知目标 $TARGET_NAME（可选 prod / hitsz）" ;;
esac

retry() {
    local n=$1 i; shift
    for ((i = 1; i <= n; i++)); do
        "$@" && return 0
        echo "  …第 $i 次失败，重试" >&2
        sleep 5
    done
    return 1
}

cd "$REPO"

# ---------- 1. 合并与推送 ----------
[ "$(git branch --show-current)" = main ] || die "主仓库当前不在 main，先切回 main"

dirty=$(git status --porcelain --untracked-files=no)
[ -n "$dirty" ] && printf '注意：以下未提交改动不会上线：\n%s\n' "$dirty"

say "同步 GitHub"
retry 3 git fetch -q origin || die "fetch 失败"
if ! git merge-base --is-ancestor origin/main main; then
    if git merge-base --is-ancestor main origin/main; then
        git merge -q --ff-only origin/main
        echo "  本地 main 已快进到 GitHub 最新"
    else
        echo "  本地 main 与 GitHub 各有新提交，尝试自动合并："
        git log --oneline main..origin/main | sed 's/^/    GitHub: /'
        git merge --no-ff -q -m "merge: 合入 GitHub 上的新提交" origin/main \
            || { git merge --abort 2> /dev/null || true; die "与 GitHub 上的提交冲突（或会覆盖未提交改动），已回退，需人工合并"; }
        echo "  已自动合并，无冲突"
    fi
fi

if [ -n "$BRANCH" ]; then
    git rev-parse --verify -q "$BRANCH^{commit}" > /dev/null || die "分支 $BRANCH 不存在"
    if git merge-base --is-ancestor "$BRANCH" main; then
        echo "  $BRANCH 已在 main 里，无需合并"
    else
        say "合并 $BRANCH → main"
        git merge --no-ff -m "${MSG:-merge: 合入 $BRANCH}" "$BRANCH" \
            || { git merge --abort 2> /dev/null || true; die "合并失败（冲突或会覆盖未提交改动），已回退"; }
    fi
fi

if [ "$(git rev-list --count origin/main..main)" -gt 0 ]; then
    say "推送到 GitHub"
    git log --oneline origin/main..main
    retry 3 git push -q origin main || die "推送失败"
fi
TARGET=$(git rev-parse main)
echo "  GitHub 上已是最新：$(git log --oneline -1)"

[ "$DEPLOY" = 1 ] || exit 0

# ---------- 2. 部署前检查（停机前） ----------
say "对比 $DOMAIN 上的版本"
PROD=$(retry 3 ssh $HOST 'sudo -u rightwrite git -C /opt/rightwrite/app rev-parse HEAD') || die "连不上服务器"
if [ "$PROD" = "$TARGET" ] && [ "$FORCE" = 0 ]; then
    echo "  生产已是 ${TARGET:0:9}，无需部署（重新部署加 --force）"
    exit 0
fi
git cat-file -e "$PROD^{commit}" 2> /dev/null || die "本地找不到生产所在提交 $PROD"
git merge-base --is-ancestor "$PROD" "$TARGET" || die "生产提交不在 main 历史上，无法快进"

echo "  生产 ${PROD:0:9} → ${TARGET:0:9}，待上线提交："
git log --oneline "$PROD..$TARGET" | sed 's/^/    /'
CHANGED=$(git diff --name-only "$PROD" "$TARGET")

deps=$(grep -E '^(package\.json|package-lock\.json|backend/requirements\.txt)$' <<< "$CHANGED" || true)
if [ -n "$deps" ] && [ "$DEPS_DONE" = 0 ]; then
    die "依赖文件有变动，先在服务器装依赖（见 docs/deployment/部署流程.md 第六节第 4 条），再加 --deps-done：
$deps"
fi

guarded=""
for f in $(git diff --name-only --diff-filter=A "$PROD" "$TARGET" -- 'backend/open_webui/migrations/versions/*.py'); do
    echo "  新迁移：$f"
    git show "$TARGET:$f" | grep -q 'raise RuntimeError' && guarded+="$f"$'\n'
done
if [ -n "$guarded" ] && [ -z "$TRUNCATE" ] && [ "$GUARDS_OK" = 0 ]; then
    die "以下迁移带守卫（表非空即拒绝升级），读守卫点名的表后加 --truncate t1,t2 或 --guards-ok：
$guarded"
fi

# 前端以「最近一次构建成功的提交」为基准，而不是 git HEAD：构建失败后 HEAD 已前移，
# 按 HEAD 比会把没构建过的前端改动当成已上线。没有记录就构建。
BUILT=$(ssh $HOST 'sudo cat /opt/rightwrite/built-commit 2>/dev/null' || true)
if [ -z "$BUILT" ] || ! git cat-file -e "$BUILT^{commit}" 2> /dev/null; then
    echo "  服务器没有可用的构建记录，本次构建前端"
    BUILD=1
elif git diff --name-only "$BUILT" "$TARGET" | grep -qv '^backend/'; then
    BUILD=1
else
    BUILD=0
fi

# ---------- 3. 服务器端执行 ----------
local_hash=$(sed 's/\r$//' "$REMOTE_SRC" | sha256sum | cut -d' ' -f1)
remote_hash=$(ssh $HOST 'sha256sum /opt/rightwrite/deploy.sh 2>/dev/null | cut -d" " -f1' || true)
if [ "$local_hash" != "$remote_hash" ]; then
    echo "  更新服务器上的部署脚本"
    sed 's/\r$//' "$REMOTE_SRC" | ssh $HOST 'cat > /tmp/rw-deploy.sh && sudo install -m 755 -o root -g root /tmp/rw-deploy.sh /opt/rightwrite/deploy.sh && rm /tmp/rw-deploy.sh'
fi

say "服务器部署中（$([ $BUILD = 1 ] && echo '含构建，约 5 分钟' || echo '仅后端，约 2 分钟')）"
ssh $HOST "sudo nohup /opt/rightwrite/deploy.sh $TARGET $BUILD '$TRUNCATE' > /tmp/rw-deploy.log 2>&1 < /dev/null &"

deadline=$((SECONDS + 1200)) last="" result=""
while ((SECONDS < deadline)); do
    sleep 15
    out=$(ssh $HOST 'tail -n 60 /tmp/rw-deploy.log' 2> /dev/null) || { echo "  …SSH 暂时连不上（构建时常见），继续等"; continue; }
    while IFS= read -r line; do
        [ -n "$line" ] && ! grep -qxF -- "$line" <<< "$last" && echo "  $line"
    done <<< "$(grep '^>>' <<< "$out" || true)"
    last=$(grep '^>>' <<< "$out" || true)
    if grep -q "^DEPLOY OK $TARGET" <<< "$out"; then result=ok; break; fi
    if grep -q '^DEPLOY FAIL' <<< "$out"; then result=fail; break; fi
done

case "$result" in
    ok)
        grep '^DEPLOY OK' <<< "$out"
        health=$(curl -s -m 20 "https://$DOMAIN/health" || true)
        echo "  外网健康检查：${health:-无响应（本机若开了代理，结果可能不可信）}"
        say "部署完成：$(git log --oneline -1 "$TARGET")"
        ;;
    fail)
        echo "$out"
        die "服务器端失败，完整日志：ssh $HOST 'cat /tmp/rw-deploy.log'"
        ;;
    *) die "20 分钟未等到结果，查看：ssh $HOST 'tail -n 60 /tmp/rw-deploy.log'" ;;
esac
